import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useFocusEffect, useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  Alert,
  Dimensions,
  Image,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { Gesture, GestureDetector } from 'react-native-gesture-handler';
import Animated, { runOnJS, useAnimatedStyle, useSharedValue, withSpring } from 'react-native-reanimated';
import { SafeAreaView } from 'react-native-safe-area-context';

import { getFirstFrameUrl, uploadVideo } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { useTheme } from '../../contexts/ThemeContext';

// ── Calibración ──────────────────────────────────────────────────────────────
const CORNER_ORDER = [
  { key: 'TL', square: 'a1', label: 'Superior-Izq  (a1)', color: '#22c55e' },
  { key: 'TR', square: 'a8', label: 'Superior-Der  (a8)', color: '#f97316' },
  { key: 'BR', square: 'h8', label: 'Inferior-Der  (h8)', color: '#ef4444' },
  { key: 'BL', square: 'h1', label: 'Inferior-Izq  (h1)', color: '#3b82f6' },
];
type Corner = [number, number]; // coordenadas relativas [0-1]

type Phase = 'idle' | 'uploading' | 'uploaded' | 'calibrating' | 'error';

export default function UploadScreen() {
  const [videoUri, setVideoUri] = useState<string | null>(null);
  const [videoFileName, setVideoFileName] = useState<string | null>(null);
  const [savedFileName, setSavedFileName] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);

  // Estado de calibración
  const [corners, setCorners] = useState<Corner[]>([]);
  const [imgDisplay, setImgDisplay] = useState({ offsetX: 0, offsetY: 0, displayW: 1, displayH: 1 });
  const screenWidth = Dimensions.get('window').width - 40;
  const cw = screenWidth;
  const ch = screenWidth * 0.65;

  // Zoom / pan — shared values for gesture worklets
  const scale    = useSharedValue(1);
  const tx       = useSharedValue(0);
  const ty       = useSharedValue(0);
  const savedScale = useSharedValue(1);
  const savedTx    = useSharedValue(0);
  const savedTy    = useSharedValue(0);
  // imgDisplay mirrored as shared values so they're accessible inside worklets
  const imgOffX = useSharedValue(0);
  const imgOffY = useSharedValue(0);
  const imgDW   = useSharedValue(1);
  const imgDH   = useSharedValue(1);
  const [zoomLevel, setZoomLevel] = useState(1);

  // Resetea la pantalla la próxima vez que se enfoque tras haber lanzado un análisis
  const analysisStarted = useRef(false);
  useFocusEffect(useCallback(() => {
    if (analysisStarted.current) {
      analysisStarted.current = false;
      setVideoUri(null);
      setVideoFileName(null);
      setSavedFileName(null);
      setPhase('idle');
      setCorners([]);
      scale.value = 1; tx.value = 0; ty.value = 0;
      savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
      setZoomLevel(1);
    }
  }, []));

  const navigation = useNavigation();
  const router = useRouter();
  const { cameraUri } = useLocalSearchParams<{ cameraUri?: string }>();

  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  const player = useVideoPlayer('', (p) => { p.loop = true; });

  useEffect(() => {
    if (cameraUri) {
      setVideoUri(cameraUri);
      setVideoFileName('grabacion.mp4');
      setSavedFileName(null);
      setPhase('idle');
    }
  }, [cameraUri]);

  useEffect(() => {
    if (videoUri) {
      player.replace({ uri: videoUri });
      player.pause();
    }
  }, [videoUri]);

  const pickVideo = async () => {
    if (phase === 'uploading') return;

    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert(t.upload.permissionDenied, t.upload.galleryPermission);
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      allowsEditing: false,
      quality: 1,
    });

    if (!result.canceled) {
      const asset = result.assets[0];
      setVideoUri(asset.uri);
      setVideoFileName(asset.fileName ?? asset.uri.split('/').pop() ?? 'video.mp4');
      setSavedFileName(null);
      setPhase('idle');
      setCorners([]);
    }
  };

  const handleUpload = async () => {
    if (!videoUri || !videoFileName) return;
    try {
      setPhase('uploading');
      setUploadProgress(0);
      const uploadResult = await uploadVideo(videoUri, videoFileName, setUploadProgress);
      setSavedFileName(uploadResult.file);
      setPhase('uploaded');
    } catch (err: any) {
      setPhase('error');
      Alert.alert('Error', err.message ?? 'Ha ocurrido un error inesperado');
    }
  };

  const handleReset = () => {
    setVideoUri(null);
    setVideoFileName(null);
    setSavedFileName(null);
    setPhase('idle');
    setCorners([]);
    scale.value = 1; tx.value = 0; ty.value = 0;
    savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
    setZoomLevel(1);
  };

  // ── Calibración ────────────────────────────────────────────────────────────

  // Calcula el área real de la imagen corrigiendo el letterbox de resizeMode="contain"
  const handleImageLoad = (e: any) => {
    const { width: natW, height: natH } = e.nativeEvent.source;
    const imgRatio = natW / natH;
    const contRatio = cw / ch;
    let dW: number, dH: number;
    if (imgRatio > contRatio) { dW = cw; dH = cw / imgRatio; }
    else                       { dH = ch; dW = ch * imgRatio; }
    const oX = (cw - dW) / 2;
    const oY = (ch - dH) / 2;
    setImgDisplay({ offsetX: oX, offsetY: oY, displayW: dW, displayH: dH });
    // Also update shared values for worklet access
    imgOffX.value = oX; imgOffY.value = oY;
    imgDW.value = dW;   imgDH.value = dH;
  };

  const addCorner = (rx: number, ry: number) => {
    setCorners(prev => (prev.length >= 4 ? prev : [...prev, [rx, ry]]));
  };

  const resetZoom = () => {
    scale.value = withSpring(1);
    tx.value    = withSpring(0);
    ty.value    = withSpring(0);
    savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
    setZoomLevel(1);
  };

  // ── Gestures ──
  const pinchGesture = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = Math.max(1, Math.min(6, savedScale.value * e.scale));
    })
    .onEnd(() => {
      if (scale.value < 1.05) {
        scale.value = withSpring(1); tx.value = withSpring(0); ty.value = withSpring(0);
        savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
        runOnJS(setZoomLevel)(1);
      } else {
        savedScale.value = scale.value;
        runOnJS(setZoomLevel)(scale.value);
      }
    });

  const panGesture = Gesture.Pan()
    .minDistance(8)
    .onUpdate((e) => {
      tx.value = savedTx.value + e.translationX;
      ty.value = savedTy.value + e.translationY;
    })
    .onEnd(() => {
      savedTx.value = tx.value;
      savedTy.value = ty.value;
    });

  const tapGesture = Gesture.Tap().onEnd((e) => {
    'worklet';
    // Reverse the zoom/pan transform to get original image-space coordinates
    const vx = (e.x - cw / 2 - tx.value) / scale.value + cw / 2;
    const vy = (e.y - ch / 2 - ty.value) / scale.value + ch / 2;
    const ix = vx - imgOffX.value;
    const iy = vy - imgOffY.value;
    if (ix < 0 || iy < 0 || ix > imgDW.value || iy > imgDH.value) return;
    runOnJS(addCorner)(ix / imgDW.value, iy / imgDH.value);
  });

  const composedGesture = Gesture.Exclusive(
    Gesture.Simultaneous(pinchGesture, panGesture),
    tapGesture,
  );

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: scale.value },
      { translateX: tx.value },
      { translateY: ty.value },
    ],
  }));

  const handleConfirmAnalysis = () => {
    if (corners.length !== 4 || !savedFileName) return;
    analysisStarted.current = true;
    router.push({
      pathname: '/(drawer)/analysis',
      params: {
        file: savedFileName,
        corners: JSON.stringify(corners),
      },
    });
  };

  const isLoading = phase === 'uploading';
  const frameUri = savedFileName ? getFirstFrameUrl(savedFileName) : null;
  const nextCorner = corners.length < 4 ? CORNER_ORDER[corners.length] : null;

  return (
    <>
      <StatusBar style={isDarkMode ? 'light' : 'dark'} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>

        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>
            {phase === 'calibrating' ? t.upload.calibrateTitle : t.upload.title}
          </Text>
        </View>

        <ScrollView
          scrollEnabled={phase !== 'calibrating'}
          contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}
        >

          {/* ── Fase de calibración ── */}
          {phase === 'calibrating' && frameUri && (
            <View style={styles.calibrateSection}>

              {/* Instrucciones */}
              <View style={[styles.infoBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                <Text style={[styles.infoText, { color: colors.textSecondary }]}>
                  {t.upload.calibrateInstructions}
                </Text>
              </View>

              {/* Indicadores de paso */}
              <View style={styles.stepsRow}>
                {CORNER_ORDER.map((c, idx) => (
                  <View key={c.key} style={styles.stepItem}>
                    <View style={[
                      styles.stepDot,
                      {
                        backgroundColor: idx < corners.length ? c.color : colors.border,
                        borderColor: idx === corners.length ? c.color : 'transparent',
                      },
                    ]}>
                      {idx < corners.length && (
                        <Ionicons name="checkmark" size={12} color="#fff" />
                      )}
                    </View>
                    <Text style={[styles.stepLabel, { color: idx === corners.length ? c.color : colors.textSecondary }]}>
                      {c.square}
                    </Text>
                  </View>
                ))}
              </View>

              {/* Texto de ayuda */}
              {nextCorner ? (
                <Text style={[styles.nextHint, { color: nextCorner.color }]}>
                  {t.upload.tapCorner} {nextCorner.label}
                </Text>
              ) : (
                <Text style={[styles.nextHint, { color: colors.primary }]}>
                  {t.upload.allCornersSelected}
                </Text>
              )}

              {/* Imagen con zoom — GestureDetector envuelve el Animated.View */}
              <View style={styles.imageWrapper}>
                <GestureDetector gesture={composedGesture}>
                  <Animated.View style={[styles.imageContainer, animatedStyle]}>
                    <Image
                      source={{
                        uri: frameUri,
                        headers: { 'ngrok-skip-browser-warning': 'true' },
                      }}
                      style={{ width: cw, height: ch }}
                      resizeMode="contain"
                      onLoad={handleImageLoad}
                    />
                    {/* Marcadores tipo cruceta — el centro coincide con el toque exacto */}
                    {corners.map(([rx, ry], idx) => {
                      const c = CORNER_ORDER[idx];
                      const cx = imgDisplay.offsetX + rx * imgDisplay.displayW;
                      const cy = imgDisplay.offsetY + ry * imgDisplay.displayH;
                      return (
                        <View key={idx} style={[styles.crosshair, { left: cx - 16, top: cy - 16 }]}>
                          {/* Líneas de cruceta */}
                          <View style={[styles.chHLine, { backgroundColor: c.color }]} />
                          <View style={[styles.chVLine, { backgroundColor: c.color }]} />
                          {/* Punto central */}
                          <View style={[styles.chDot, { backgroundColor: c.color }]} />
                          {/* Badge con número */}
                          <View style={[styles.chBadge, { backgroundColor: c.color }]}>
                            <Text style={styles.chBadgeText}>{idx + 1}</Text>
                          </View>
                        </View>
                      );
                    })}
                  </Animated.View>
                </GestureDetector>
              </View>
              <Text style={[styles.zoomHint, { color: colors.textSecondary }]}>
                Pellizca para hacer zoom · Toca para marcar esquinas
              </Text>

              {/* Botones secundarios */}
              <View style={styles.calibrateActions}>
                {zoomLevel > 1.05 && (
                  <TouchableOpacity
                    style={[styles.btnSecondary, { borderColor: colors.border }]}
                    onPress={resetZoom}
                  >
                    <Ionicons name="scan-outline" size={16} color={colors.text} />
                    <Text style={[styles.btnSecondaryText, { color: colors.text }]}>Zoom</Text>
                  </TouchableOpacity>
                )}
                {corners.length > 0 && (
                  <TouchableOpacity
                    style={[styles.btnSecondary, { borderColor: colors.border }]}
                    onPress={() => setCorners(c => c.slice(0, -1))}
                  >
                    <Ionicons name="arrow-undo" size={16} color={colors.text} />
                    <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                      {t.upload.undoCorner}
                    </Text>
                  </TouchableOpacity>
                )}
                {corners.length > 0 && (
                  <TouchableOpacity
                    style={[styles.btnSecondary, { borderColor: colors.border }]}
                    onPress={() => { setCorners([]); resetZoom(); }}
                  >
                    <Ionicons name="refresh" size={16} color={colors.text} />
                    <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                      {t.upload.resetCorners}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>

              {/* Botón analizar */}
              {corners.length === 4 && (
                <TouchableOpacity
                  style={[styles.analyzeButton, { backgroundColor: colors.primary }]}
                  onPress={handleConfirmAnalysis}
                >
                  <Ionicons name="analytics" size={20} color="#fff" />
                  <Text style={[styles.analyzeButtonText, { color: '#fff' }]}>
                    {t.upload.confirmAndAnalyze}
                  </Text>
                </TouchableOpacity>
              )}

              {/* Descartar vídeo — siempre visible en calibración */}
              <TouchableOpacity
                style={[styles.discardButton, { borderColor: '#ef4444' }]}
                onPress={handleReset}
              >
                <Ionicons name="trash-outline" size={16} color="#ef4444" />
                <Text style={[styles.discardButtonText, { color: '#ef4444' }]}>
                  {t.upload.discard}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* ── Resto de fases (idle / uploading / uploaded / error) ── */}
          {phase !== 'calibrating' && (
            <>
              {/* Zona de selección / previsualización de vídeo */}
              {videoUri ? (
                <View style={styles.playerContainer}>
                  <VideoView
                    player={player}
                    style={styles.player}
                    allowsFullscreen
                    allowsPictureInPicture={false}
                  />
                </View>
              ) : (
                <TouchableOpacity
                  style={[
                    styles.uploadBox,
                    { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border },
                  ]}
                  onPress={pickVideo}
                  disabled={isLoading}
                >
                  <Ionicons name="cloud-upload-outline" size={60} color={colors.text} />
                  <Text style={[styles.uploadText, { color: colors.text }]}>
                    {t.upload.tapToSelect}
                  </Text>
                </TouchableOpacity>
              )}

              {/* Barra de progreso de subida */}
              {isLoading && (
                <View style={styles.loadingContainer}>
                  <Text style={[styles.loadingText, { color: colors.text }]}>
                    {t.upload.uploading} {uploadProgress}%
                  </Text>
                  <View style={[styles.progressTrack, { backgroundColor: colors.border }]}>
                    <View style={[styles.progressFill, { backgroundColor: colors.primary, flex: uploadProgress }]} />
                    <View style={{ flex: 100 - uploadProgress }} />
                  </View>
                </View>
              )}

              {/* Botones de acción */}
              {videoUri && !isLoading && (
                <View style={styles.buttonRow}>
                  <TouchableOpacity
                    style={[styles.cancelButton, { borderColor: colors.border }]}
                    onPress={handleReset}
                  >
                    <Text style={[styles.cancelButtonText, { color: colors.text }]}>{t.upload.cancel}</Text>
                  </TouchableOpacity>

                  {phase === 'uploaded' ? (
                    <TouchableOpacity
                      style={[styles.analyzeButton, { backgroundColor: colors.primary }]}
                      onPress={() => { setCorners([]); resetZoom(); setPhase('calibrating'); }}
                    >
                      <Ionicons name="scan" size={20} color="#fff" />
                      <Text style={[styles.analyzeButtonText, { color: '#fff' }]}>
                        {t.upload.calibrateImage}
                      </Text>
                    </TouchableOpacity>
                  ) : (
                    <TouchableOpacity
                      style={[styles.analyzeButton, { backgroundColor: colors.buttonBg }]}
                      onPress={handleUpload}
                    >
                      <Text style={[styles.analyzeButtonText, { color: colors.buttonText }]}>
                        {t.upload.uploadVideo}
                      </Text>
                    </TouchableOpacity>
                  )}
                </View>
              )}

              {/* Pasos / Instrucciones */}
              <View style={styles.stepsContainer}>
                <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                  <Text style={[styles.stepTitle, { color: colors.text }]}>{t.upload.step1}</Text>
                  <Text style={[styles.stepDescription, { color: colors.text }]}>{t.upload.step1Text}</Text>
                </View>
                <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                  <Text style={[styles.stepTitle, { color: colors.text }]}>{t.upload.step2}</Text>
                  <Text style={[styles.stepDescription, { color: colors.text }]}>{t.upload.step2Text}</Text>
                </View>
                <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                  <Text style={[styles.stepTitle, { color: colors.text }]}>{t.upload.step3}</Text>
                  <Text style={[styles.stepDescription, { color: colors.text }]}>{t.upload.step3Text}</Text>
                </View>
                <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                  <Text style={[styles.stepTitle, { color: colors.text }]}>{t.upload.step4}</Text>
                  <Text style={[styles.stepDescription, { color: colors.text }]}>{t.upload.step4Text}</Text>
                </View>
              </View>
            </>
          )}

        </ScrollView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  menuButton: { marginRight: 15 },
  headerTitle: { fontSize: 22, fontWeight: 'bold' },
  content: {
    flexGrow: 1,
    padding: 20,
    alignItems: 'stretch',
  },

  // ── Subida ──
  uploadBox: {
    width: '100%',
    aspectRatio: 1.2,
    borderRadius: 20,
    borderWidth: 1,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },
  uploadText: {
    fontSize: 16,
    fontWeight: 'bold',
    textAlign: 'center',
    marginTop: 15,
    paddingHorizontal: 10,
  },
  loadingContainer: { gap: 10, marginBottom: 20 },
  loadingText: { fontSize: 16, textAlign: 'center' },
  progressTrack: { height: 10, borderRadius: 5, overflow: 'hidden', width: '100%', flexDirection: 'row' },
  progressFill: { height: 10, borderRadius: 5 },
  buttonRow: { flexDirection: 'row', gap: 12, marginBottom: 20 },
  cancelButton: {
    flex: 1,
    paddingVertical: 15,
    borderRadius: 15,
    alignItems: 'center',
    borderWidth: 1,
  },
  cancelButtonText: { fontSize: 16, fontWeight: 'bold' },
  analyzeButton: {
    flex: 1,
    flexDirection: 'row',
    paddingVertical: 15,
    borderRadius: 15,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  analyzeButtonText: { fontSize: 16, fontWeight: 'bold' },
  playerContainer: { width: '100%', marginBottom: 20, gap: 10 },
  player: { width: '100%', aspectRatio: 16 / 9, borderRadius: 15, overflow: 'hidden' },
  stepsContainer: { width: '100%', gap: 15, paddingBottom: 20 },
  stepBox: { width: '100%', borderRadius: 15, borderWidth: 1, padding: 15 },
  stepTitle: { fontSize: 16, fontWeight: 'bold' },
  stepDescription: { fontSize: 16 },

  // ── Calibración ──
  calibrateSection: { gap: 14 },
  infoBox: { borderRadius: 10, borderWidth: 1, padding: 14 },
  infoText: { fontSize: 13, lineHeight: 20 },
  stepsRow: { flexDirection: 'row', justifyContent: 'space-around' },
  stepItem: { alignItems: 'center', gap: 4 },
  stepDot: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepLabel: { fontSize: 12, fontWeight: '600' },
  nextHint: { fontSize: 14, fontWeight: '600', textAlign: 'center' },
  imageWrapper: { overflow: 'hidden', borderRadius: 8 },
  zoomHint: { fontSize: 11, textAlign: 'center', marginTop: 4 },
  imageContainer: { position: 'relative', alignSelf: 'center' },
  // Marcador tipo cruceta
  crosshair: { position: 'absolute', width: 32, height: 32, alignItems: 'center', justifyContent: 'center' },
  chHLine:   { position: 'absolute', width: 32, height: 1.5 },
  chVLine:   { position: 'absolute', width: 1.5, height: 32 },
  chDot:     { width: 5, height: 5, borderRadius: 2.5, zIndex: 2 },
  chBadge:   {
    position: 'absolute', top: -9, right: -9,
    width: 15, height: 15, borderRadius: 7.5,
    alignItems: 'center', justifyContent: 'center', zIndex: 3,
  },
  chBadgeText: { fontSize: 9, fontWeight: '800', color: '#fff' },
  calibrateActions: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  discardButton: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, borderWidth: 1, borderRadius: 10, paddingVertical: 12,
  },
  discardButtonText: { fontSize: 14, fontWeight: '600' },
  btnSecondary: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  btnSecondaryText: { fontSize: 14 },
});
