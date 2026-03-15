import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useEffect, useRef, useState } from 'react';
import {
  Alert,
  Dimensions,
  Image,
  LayoutChangeEvent, // kept for imageContainer onLayout (future use)
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
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
  const imageRef = useRef<View>(null);
  const [imageLayout, setImageLayout] = useState({ width: 1, height: 1 });
  // Dimensiones reales de la imagen mostrada dentro del contenedor (sin letterbox)
  const [imgDisplay, setImgDisplay] = useState({ offsetX: 0, offsetY: 0, displayW: 1, displayH: 1 });
  const screenWidth = Dimensions.get('window').width - 40;

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
  };

  // ── Calibración ────────────────────────────────────────────────────────────
  const handleImageLayout = (e: LayoutChangeEvent) => {
    const { width, height } = e.nativeEvent.layout;
    setImageLayout({ width, height });
  };

  // Calcula el área real de la imagen corrigiendo el letterbox de resizeMode="contain"
  const handleImageLoad = (e: any) => {
    const { width: natW, height: natH } = e.nativeEvent.source;
    const contW = screenWidth;
    const contH = screenWidth * 0.65;
    const imgRatio = natW / natH;
    const contRatio = contW / contH;
    let displayW: number, displayH: number;
    if (imgRatio > contRatio) {
      displayW = contW;
      displayH = contW / imgRatio;
    } else {
      displayH = contH;
      displayW = contH * imgRatio;
    }
    const offsetX = (contW - displayW) / 2;
    const offsetY = (contH - displayH) / 2;
    setImgDisplay({ offsetX, offsetY, displayW, displayH });
  };

  const handleImageTouch = (e: any) => {
    if (corners.length >= 4) return;
    const { locationX, locationY } = e.nativeEvent;
    // Corregir offset del letterbox
    const ix = locationX - imgDisplay.offsetX;
    const iy = locationY - imgDisplay.offsetY;
    // Ignorar toques fuera de la imagen real
    if (ix < 0 || iy < 0 || ix > imgDisplay.displayW || iy > imgDisplay.displayH) return;
    const rx = ix / imgDisplay.displayW;
    const ry = iy / imgDisplay.displayH;
    setCorners(prev => [...prev, [rx, ry]]);
  };

  const handleConfirmAnalysis = () => {
    if (corners.length !== 4 || !savedFileName) return;
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

        <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}>

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

              {/* Imagen tocable */}
              <TouchableOpacity
                activeOpacity={1}
                onPress={handleImageTouch}
                style={styles.imageWrapper}
              >
                <View ref={imageRef} onLayout={handleImageLayout} style={styles.imageContainer}>
                  <Image
                    source={{
                      uri: frameUri,
                      headers: { 'ngrok-skip-browser-warning': 'true' },
                    }}
                    style={{ width: screenWidth, height: screenWidth * 0.65 }}
                    resizeMode="contain"
                    onLoad={handleImageLoad}
                  />
                  {/* Marcadores de esquinas — posicionados sobre el área real de la imagen */}
                  {corners.map(([rx, ry], idx) => {
                    const c = CORNER_ORDER[idx];
                    return (
                      <View
                        key={idx}
                        style={[
                          styles.marker,
                          {
                            left: imgDisplay.offsetX + rx * imgDisplay.displayW - 14,
                            top:  imgDisplay.offsetY + ry * imgDisplay.displayH - 14,
                            borderColor: c.color,
                            backgroundColor: c.color + '44',
                          },
                        ]}
                      >
                        <Text style={[styles.markerText, { color: c.color }]}>{idx + 1}</Text>
                      </View>
                    );
                  })}
                </View>
              </TouchableOpacity>

              {/* Botones secundarios */}
              {corners.length > 0 && (
                <View style={styles.calibrateActions}>
                  <TouchableOpacity
                    style={[styles.btnSecondary, { borderColor: colors.border }]}
                    onPress={() => setCorners(c => c.slice(0, -1))}
                  >
                    <Ionicons name="arrow-undo" size={16} color={colors.text} />
                    <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                      {t.upload.undoCorner}
                    </Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={[styles.btnSecondary, { borderColor: colors.border }]}
                    onPress={() => setCorners([])}
                  >
                    <Ionicons name="refresh" size={16} color={colors.text} />
                    <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                      {t.upload.resetCorners}
                    </Text>
                  </TouchableOpacity>
                </View>
              )}

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
                    <View style={[styles.progressFill, { backgroundColor: colors.primary, width: `${uploadProgress}%` }]} />
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
                      onPress={() => { setCorners([]); setPhase('calibrating'); }}
                    >
                      <Ionicons name="scan" size={20} color="#fff" />
                      <Text style={[styles.analyzeButtonText, { color: '#fff' }]}>
                        {t.upload.analyzeGame}
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
  progressTrack: { height: 10, borderRadius: 5, overflow: 'hidden', width: '100%' },
  progressFill: { height: '100%', borderRadius: 5 },
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
  imageWrapper: {},
  imageContainer: { position: 'relative', alignSelf: 'center' },
  marker: {
    position: 'absolute',
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  markerText: { fontSize: 12, fontWeight: '800' },
  calibrateActions: { flexDirection: 'row', gap: 10 },
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
