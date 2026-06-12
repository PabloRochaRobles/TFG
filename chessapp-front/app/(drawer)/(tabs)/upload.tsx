import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useFocusEffect, useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
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

import { fetchWarpedPreview, getFirstFrameUrl, uploadVideo } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { useTheme } from '@/contexts/ThemeContext';

// ── Compresión de vídeo ───────────────────────────────────────────────────────
// Usa react-native-compressor si está disponible (Development Build / producción).
// En Expo Go el require falla silenciosamente y se sube el vídeo original.
//
// IMPORTANTE: SIEMPRE se pasa el vídeo por `Video.compress`, aunque ya sea
// pequeño. La razón no es solo de tamaño: el URI original que entrega el
// picker / la cámara en Android suele ser un `content://` que el
// `XMLHttpRequest` de `uploadVideo` no puede transmitir de forma fiable
// (se subía un fichero truncado de ~28 bytes, sin `moov` atom, y el
// backend lo rechazaba). `Video.compress` devuelve siempre un `file://`
// real en la caché de la app, que sí se sube correctamente. Por tanto la
// compresión cumple aquí una doble función: reducir tamaño y normalizar
// el contenedor a un fichero subible.
//
// Se usa modo `auto`. Se probó `manual` (720p / 800 kbps) para acelerar
// el encode, pero en algunos dispositivos Android react-native-compressor
// en modo `manual` produce un MP4 vacío de 28 bytes (solo la cabecera
// `ftyp`, sin pista de vídeo), que el backend rechaza con "moov atom not
// found". El modo `auto` es más lento pero genera ficheros válidos de
// forma fiable, que es el requisito prioritario.
async function compressVideoSafe(
  uri: string,
  onProgress: (pct: number) => void,
): Promise<string> {
  console.log('[compress] URI de entrada:', uri);

  // 1. Cargar el módulo nativo. Si esto falla, el build no lo incluye
  //    (típico de Expo Go). Lo distinguimos del fallo de compresión.
  let Video: any;
  try {
    Video = require('react-native-compressor').Video;
  } catch (e) {
    console.warn('[compress] react-native-compressor NO disponible en este build:', e);
    // No tenemos forma de normalizar el contenedor; subir el URI tal cual
    // (puede funcionar si ya es un file:// legible).
    return uri;
  }

  // 2. Comprimir. Si esto lanza, NO subimos un fichero potencialmente
  //    corrupto en silencio: propagamos el error para que el usuario lo
  //    vea y quede registrado en la consola de Metro.
  try {
    const out = await Video.compress(
      uri,
      {
        compressionMethod: 'auto',
        maxSize: 1280,
        bitrate: 1_500_000,
      },
      (progress: number) => onProgress(Math.round(progress * 100)),
    );
    console.log('[compress] OK, fichero comprimido:', out);
    return out;
  } catch (e) {
    console.error('[compress] Video.compress falló:', e);
    throw new Error(
      'No se pudo procesar el vídeo para la subida. ' +
      'Detalle: ' + (e instanceof Error ? e.message : String(e)),
    );
  }
}

// ── Calibración ──────────────────────────────────────────────────────────────
const CORNER_ORDER = [
  { key: 'TL', square: 'a1', color: '#22c55e' },
  { key: 'TR', square: 'a8', color: '#f97316' },
  { key: 'BR', square: 'h8', color: '#ef4444' },
  { key: 'BL', square: 'h1', color: '#3b82f6' },
];
type Corner = [number, number]; // coordenadas relativas [0-1]

type Phase = 'idle' | 'uploading' | 'uploaded' | 'calibrating' | 'adjusting' | 'error';

// ── Perspectiva: matemática para corregir esquinas tras ajuste de encuadre ──

type Mat3 = [[number, number, number], [number, number, number], [number, number, number]];

function gaussElim(A: number[][], b: number[]): number[] {
  const n = b.length;
  const M = A.map((row, i) => [...row, b[i]]);
  for (let col = 0; col < n; col++) {
    let maxRow = col;
    for (let row = col + 1; row < n; row++) {
      if (Math.abs(M[row][col]) > Math.abs(M[maxRow][col])) maxRow = row;
    }
    [M[col], M[maxRow]] = [M[maxRow], M[col]];
    for (let row = 0; row < n; row++) {
      if (row !== col && Math.abs(M[col][col]) > 1e-12) {
        const f = M[row][col] / M[col][col];
        for (let j = col; j <= n; j++) M[row][j] -= f * M[col][j];
      }
    }
  }
  return M.map((row, i) => (Math.abs(row[i]) > 1e-12 ? row[n] / row[i] : 0));
}

function getPerspTransform(src: Corner[], dst: Corner[]): Mat3 {
  const A: number[][] = [];
  const b: number[] = [];
  for (let i = 0; i < 4; i++) {
    const [x, y] = src[i];
    const [xp, yp] = dst[i];
    A.push([x, y, 1, 0, 0, 0, -xp * x, -xp * y]);
    b.push(xp);
    A.push([0, 0, 0, x, y, 1, -yp * x, -yp * y]);
    b.push(yp);
  }
  const h = gaussElim(A, b);
  return [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1]];
}

function invertMat3(m: Mat3): Mat3 {
  const [[a, b, c], [d, e, f], [g, h, k]] = m;
  const det = a * (e * k - f * h) - b * (d * k - f * g) + c * (d * h - e * g);
  return [
    [(e * k - f * h) / det, (c * h - b * k) / det, (b * f - c * e) / det],
    [(f * g - d * k) / det, (a * k - c * g) / det, (c * d - a * f) / det],
    [(d * h - e * g) / det, (b * g - a * h) / det, (a * e - b * d) / det],
  ];
}

function applyH(M: Mat3, pt: Corner): Corner {
  const [x, y] = pt;
  const w = M[2][0] * x + M[2][1] * y + M[2][2];
  return [(M[0][0] * x + M[0][1] * y + M[0][2]) / w, (M[1][0] * x + M[1][1] * y + M[1][2]) / w];
}

/**
 * Calcula las esquinas corregidas en el espacio de la imagen original a partir
 * del ajuste de encuadre que el usuario realizó (pan + zoom sobre la imagen warpeada).
 *
 * La imagen warpeada se muestra centrada en un contenedor cuadrado de lado G.
 * Tras el ajuste (panX, panY, userScale), los bordes del contenedor corresponden
 * a nuevas posiciones en la imagen warpeada [0-1]. Se les aplica la homografía
 * inversa para obtener las esquinas corregidas en el espacio original [0-1].
 */
function computeCorrectedCorners(
  originalCorners: Corner[],
  containerSize: number,
  panX: number,
  panY: number,
  userScale: number,
): Corner[] {
  // El backend mapea las esquinas de origen a los 4 vértices del cuadrado unitario
  // en el orden: TL→(0,0), TR→(1,0), BR→(1,1), BL→(0,1)
  const dst: Corner[] = [[0, 0], [1, 0], [1, 1], [0, 1]];
  const M = getPerspTransform(originalCorners, dst);
  const Minv = invertMat3(M);

  const G = containerSize;
  // Las esquinas del contenedor en coordenadas de pantalla se mapean al espacio
  // warpeado [0-1] invirtiendo la transformada de visualización:
  //   warped_x = (screen_x - G/2 - panX) / (G * userScale) + 0.5
  const screenCorners: Corner[] = [[0, 0], [G, 0], [G, G], [0, G]];
  return screenCorners.map(([sx, sy]): Corner => {
    const wx = (sx - G / 2 - panX) / (G * userScale) + 0.5;
    const wy = (sy - G / 2 - panY) / (G * userScale) + 0.5;
    return applyH(Minv, [wx, wy]);
  });
}

// ─────────────────────────────────────────────────────────────────────────────

export default function UploadScreen() {
  const [videoUri, setVideoUri] = useState<string | null>(null);
  const [videoFileName, setVideoFileName] = useState<string | null>(null);
  const [savedFileName, setSavedFileName] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const [uploadProgress, setUploadProgress] = useState(0);
  const [isCompressing, setIsCompressing] = useState(false);
  const [compressionProgress, setCompressionProgress] = useState(0);

  // Estado de calibración
  const [corners, setCorners] = useState<Corner[]>([]);
  const [imgDisplay, setImgDisplay] = useState({ offsetX: 0, offsetY: 0, displayW: 1, displayH: 1 });
  const screenWidth = Dimensions.get('window').width - 40;
  const cw = screenWidth;
  const ch = screenWidth * 0.65;

  // Zoom / pan calibración — shared values para gesture worklets
  const scale    = useSharedValue(1);
  const tx       = useSharedValue(0);
  const ty       = useSharedValue(0);
  const savedScale = useSharedValue(1);
  const savedTx    = useSharedValue(0);
  const savedTy    = useSharedValue(0);
  // imgDisplay reflejado como shared values para acceso en worklets
  const imgOffX = useSharedValue(0);
  const imgOffY = useSharedValue(0);
  const imgDW   = useSharedValue(1);
  const imgDH   = useSharedValue(1);
  const [zoomLevel, setZoomLevel] = useState(1);


  // Estado de ajuste de encuadre
  const adjSize = cw;                              // contenedor cuadrado
  const [warpedPreviewUri, setWarpedPreviewUri] = useState<string | null>(null);
  const [warpedLoading, setWarpedLoading] = useState(false);

  // Pan / zoom de ajuste (shared values independientes)
  const adjScale     = useSharedValue(1);
  const adjTx        = useSharedValue(0);
  const adjTy        = useSharedValue(0);
  const adjSavedScale = useSharedValue(1);
  const adjSavedTx    = useSharedValue(0);
  const adjSavedTy    = useSharedValue(0);

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
      setWarpedPreviewUri(null);
      scale.value = 1; tx.value = 0; ty.value = 0;
      savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
      setZoomLevel(1);
      adjScale.value = 1; adjTx.value = 0; adjTy.value = 0;
      adjSavedScale.value = 1; adjSavedTx.value = 0; adjSavedTy.value = 0;
    }
  }, []));

  const navigation = useNavigation();
  const router = useRouter();
  const { preloaded } = useLocalSearchParams<{ preloaded?: string }>();

  // Ref para saber si la pantalla se abrió desde la librería con un vídeo ya subido
  const preloadedRef = useRef<string | null>(null);

  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  const player = useVideoPlayer('', (p) => { p.loop = true; });

  // Cuando se llega desde la librería con un vídeo ya subido, saltar directo a calibración
  useEffect(() => {
    if (preloaded) {
      preloadedRef.current = preloaded;
      setSavedFileName(preloaded);
      setVideoUri(null);
      setVideoFileName(null);
      setCorners([]);
      scale.value = 1; tx.value = 0; ty.value = 0;
      savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
      setZoomLevel(1);
      adjScale.value = 1; adjTx.value = 0; adjTy.value = 0;
      adjSavedScale.value = 1; adjSavedTx.value = 0; adjSavedTy.value = 0;
      setPhase('calibrating');
    } else {
      preloadedRef.current = null;
    }
  }, [preloaded]);

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
      setIsCompressing(true);
      setCompressionProgress(0);
      const uriToUpload = await compressVideoSafe(videoUri, setCompressionProgress);
      setIsCompressing(false);
      const uploadResult = await uploadVideo(uriToUpload, videoFileName, setUploadProgress);
      setSavedFileName(uploadResult.file);
      setPhase('uploaded');
    } catch (err: any) {
      setIsCompressing(false);
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
    setWarpedPreviewUri(null);
    scale.value = 1; tx.value = 0; ty.value = 0;
    savedScale.value = 1; savedTx.value = 0; savedTy.value = 0;
    setZoomLevel(1);
    adjScale.value = 1; adjTx.value = 0; adjTy.value = 0;
    adjSavedScale.value = 1; adjSavedTx.value = 0; adjSavedTy.value = 0;
  };

  // En flujo preloaded (desde librería): resetear y volver atrás
  const handleDiscardPreloaded = () => {
    preloadedRef.current = null;
    handleReset();
    router.back();
  };

  // ── Calibración ────────────────────────────────────────────────────────────

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

  // ── Gestos calibración ──
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
    const vx = e.x;
    const vy = e.y;
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

  // ── Gestos ajuste de encuadre ──
  const adjPinch = Gesture.Pinch()
    .onUpdate((e) => {
      adjScale.value = Math.max(0.3, Math.min(5, adjSavedScale.value * e.scale));
    })
    .onEnd(() => {
      adjSavedScale.value = adjScale.value;
    });

  const adjPan = Gesture.Pan()
    .minDistance(5)
    .onUpdate((e) => {
      adjTx.value = adjSavedTx.value + e.translationX;
      adjTy.value = adjSavedTy.value + e.translationY;
    })
    .onEnd(() => {
      adjSavedTx.value = adjTx.value;
      adjSavedTy.value = adjTy.value;
    });

  const adjComposed = Gesture.Simultaneous(adjPinch, adjPan);

  const adjAnimatedStyle = useAnimatedStyle(() => ({
    transform: [
      { translateX: adjTx.value },
      { translateY: adjTy.value },
      { scale: adjScale.value },
    ],
  }));

  // ── Transición calibrating → adjusting ──
  const handleEnterAdjusting = async () => {
    if (corners.length !== 4 || !savedFileName) return;
    setWarpedPreviewUri(null);
    setWarpedLoading(true);
    // Resetear ajuste previo
    adjScale.value = 1; adjTx.value = 0; adjTy.value = 0;
    adjSavedScale.value = 1; adjSavedTx.value = 0; adjSavedTy.value = 0;
    setPhase('adjusting');
    try {
      const uri = await fetchWarpedPreview(savedFileName, corners as Corner[]);
      setWarpedPreviewUri(uri);
    } catch {
      Alert.alert('Error', 'No se pudo cargar la previsualización del tablero');
      setPhase('calibrating');
    } finally {
      setWarpedLoading(false);
    }
  };

  const resetAdjust = () => {
    adjScale.value = withSpring(1);
    adjTx.value    = withSpring(0);
    adjTy.value    = withSpring(0);
    adjSavedScale.value = 1; adjSavedTx.value = 0; adjSavedTy.value = 0;
  };

  // ── Confirmar ajuste y navegar al análisis ──
  const handleConfirmAdjustment = () => {
    if (!savedFileName) return;
    const corrected = computeCorrectedCorners(
      corners as Corner[],
      adjSize,
      adjTx.value,
      adjTy.value,
      adjScale.value,
    );
    analysisStarted.current = true;
    router.push({
      pathname: '/(drawer)/analysis',
      params: {
        file: savedFileName,
        corners: JSON.stringify(corrected),
      },
    });
  };

  const isLoading = phase === 'uploading';

  // El primer frame ya no es una URL plana: lo descargamos como data URL
  // (base64) porque el endpoint requiere JWT y `<Image>` no acepta cabeceras.
  const [frameUri, setFrameUri] = useState<string | null>(null);
  useEffect(() => {
    if (!savedFileName) { setFrameUri(null); return; }
    let cancelled = false;
    getFirstFrameUrl(savedFileName)
      .then((uri) => { if (!cancelled) setFrameUri(uri); })
      .catch(() => { if (!cancelled) setFrameUri(null); });
    return () => { cancelled = true; };
  }, [savedFileName]);

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
            {phase === 'calibrating'
              ? t.upload.calibrateTitle
              : phase === 'adjusting'
                ? t.upload.adjustTitle
                : t.upload.title}
          </Text>
        </View>

        <ScrollView
          scrollEnabled={phase !== 'calibrating' && phase !== 'adjusting'}
          contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}
        >

          {/* ── Fase de calibración ── */}
          {phase === 'calibrating' && frameUri && (
            <View style={styles.calibrateSection}>

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

              {nextCorner ? (
                <Text style={[styles.nextHint, { color: nextCorner.color }]}>
                  {t.upload.tapCorner} {nextCorner.square}
                </Text>
              ) : (
                <Text style={[styles.nextHint, { color: colors.primary }]}>
                  {t.upload.allCornersSelected}
                </Text>
              )}

              {/* Imagen con zoom */}
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
                    {corners.map(([rx, ry], idx) => {
                      const c = CORNER_ORDER[idx];
                      const cx = imgDisplay.offsetX + rx * imgDisplay.displayW;
                      const cy = imgDisplay.offsetY + ry * imgDisplay.displayH;
                      return (
                        <View key={idx} style={[styles.crosshair, { left: cx - 16, top: cy - 16 }]}>
                          <View style={[styles.chHLine, { backgroundColor: c.color }]} />
                          <View style={[styles.chVLine, { backgroundColor: c.color }]} />
                          <View style={[styles.chDot, { backgroundColor: c.color }]} />
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
                {t.upload.zoomHintCalibrate}
              </Text>

              {/* Botón "Deshacer zoom" — ancho completo, solo cuando hay zoom */}
              {zoomLevel > 1.05 && (
                <TouchableOpacity
                  style={[styles.btnSecondaryFull, { borderColor: colors.border }]}
                  onPress={resetZoom}
                >
                  <Ionicons name="scan-outline" size={16} color={colors.text} />
                  <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                    {t.upload.resetZoom}
                  </Text>
                </TouchableOpacity>
              )}

              {/* Botones secundarios */}
              <View style={styles.calibrateActions}>
                {corners.length > 0 && (
                  <TouchableOpacity
                    style={[styles.btnSecondary, styles.btnSecondaryFlex, { borderColor: colors.border }]}
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
                    style={[styles.btnSecondary, styles.btnSecondaryFlex, { borderColor: colors.border }]}
                    onPress={() => { setCorners([]); resetZoom(); }}
                  >
                    <Ionicons name="refresh" size={16} color={colors.text} />
                    <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                      {t.upload.resetCorners}
                    </Text>
                  </TouchableOpacity>
                )}
              </View>

              {/* Botón siguiente → fase de ajuste */}
              {corners.length === 4 && (
                <TouchableOpacity
                  style={[styles.analyzeButton, { backgroundColor: colors.primary }]}
                  onPress={handleEnterAdjusting}
                >
                  <Ionicons name="arrow-forward-circle" size={20} color="#fff" />
                  <Text style={[styles.analyzeButtonText, { color: '#fff' }]}>
                    {t.upload.confirmAndAnalyze}
                  </Text>
                </TouchableOpacity>
              )}

              <TouchableOpacity
                style={[styles.discardButton, { borderColor: preloadedRef.current ? colors.border : '#ef4444' }]}
                onPress={preloadedRef.current ? handleDiscardPreloaded : handleReset}
              >
                <Ionicons
                  name={preloadedRef.current ? 'arrow-back' : 'trash-outline'}
                  size={16}
                  color={preloadedRef.current ? colors.text : '#ef4444'}
                />
                <Text style={[styles.discardButtonText, { color: preloadedRef.current ? colors.text : '#ef4444' }]}>
                  {preloadedRef.current ? 'Volver' : t.upload.discard}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* ── Fase de ajuste de encuadre ── */}
          {phase === 'adjusting' && (
            <View style={styles.calibrateSection}>

              <View style={[styles.infoBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                <Text style={[styles.infoText, { color: colors.textSecondary }]}>
                  {t.upload.adjustInstructions}
                </Text>
              </View>

              {/* Contenedor cuadrado: imagen warpeada + cuadrícula fija */}
              <View style={[styles.adjWrapper, { width: adjSize, height: adjSize }]}>
                {warpedLoading || !warpedPreviewUri ? (
                  <View style={styles.adjLoading}>
                    <ActivityIndicator size="large" color={colors.primary} />
                    <Text style={[styles.adjLoadingText, { color: colors.textSecondary }]}>
                      {t.upload.loadingPreview}
                    </Text>
                  </View>
                ) : (
                  <>
                    {/* Imagen warpeada desplazable */}
                    <GestureDetector gesture={adjComposed}>
                      <View style={{ width: adjSize, height: adjSize }}>
                        <Animated.View
                          style={[
                            { position: 'absolute', width: adjSize, height: adjSize },
                            adjAnimatedStyle,
                          ]}
                        >
                          <Image
                            source={{ uri: warpedPreviewUri }}
                            style={{ width: adjSize, height: adjSize }}
                            resizeMode="cover"
                          />
                        </Animated.View>
                      </View>
                    </GestureDetector>

                    {/* Cuadrícula fija 8×8 — no recibe toques */}
                    <View style={StyleSheet.absoluteFillObject} pointerEvents="none">
                      {Array.from({ length: 9 }).map((_, i) => (
                        <View
                          key={`h${i}`}
                          style={[styles.gridLineH, {
                            top: (i / 8) * adjSize,
                            width: adjSize,
                          }]}
                        />
                      ))}
                      {Array.from({ length: 9 }).map((_, i) => (
                        <View
                          key={`v${i}`}
                          style={[styles.gridLineV, {
                            left: (i / 8) * adjSize,
                            height: adjSize,
                          }]}
                        />
                      ))}
                    </View>
                  </>
                )}
              </View>

              <Text style={[styles.zoomHint, { color: colors.textSecondary }]}>
                {t.upload.zoomHintAdjust}
              </Text>

              {/* Botones secundarios de ajuste */}
              <View style={styles.calibrateActions}>
                <TouchableOpacity
                  style={[styles.btnSecondary, styles.btnSecondaryFlex, { borderColor: colors.border }]}
                  onPress={resetAdjust}
                >
                  <Ionicons name="scan-outline" size={16} color={colors.text} />
                  <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                    {t.upload.adjustReset}
                  </Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.btnSecondary, styles.btnSecondaryFlex, { borderColor: colors.border }]}
                  onPress={() => setPhase('calibrating')}
                >
                  <Ionicons name="arrow-back" size={16} color={colors.text} />
                  <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                    {t.upload.adjustBack}
                  </Text>
                </TouchableOpacity>
              </View>

              {/* Botón analizar */}
              <TouchableOpacity
                style={[styles.analyzeButton, { backgroundColor: colors.primary, opacity: warpedLoading ? 0.5 : 1 }]}
                onPress={handleConfirmAdjustment}
                disabled={warpedLoading}
              >
                <Ionicons name="analytics" size={20} color="#fff" />
                <Text style={[styles.analyzeButtonText, { color: '#fff' }]}>
                  {t.upload.adjustConfirm}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.discardButton, { borderColor: preloadedRef.current ? colors.border : '#ef4444' }]}
                onPress={preloadedRef.current ? handleDiscardPreloaded : handleReset}
              >
                <Ionicons
                  name={preloadedRef.current ? 'arrow-back' : 'trash-outline'}
                  size={16}
                  color={preloadedRef.current ? colors.text : '#ef4444'}
                />
                <Text style={[styles.discardButtonText, { color: preloadedRef.current ? colors.text : '#ef4444' }]}>
                  {preloadedRef.current ? 'Volver' : t.upload.discard}
                </Text>
              </TouchableOpacity>
            </View>
          )}

          {/* ── Resto de fases (idle / uploading / uploaded / error) ── */}
          {phase !== 'calibrating' && phase !== 'adjusting' && (
            <>
              {videoUri ? (
                <View style={styles.playerContainer}>
                  <VideoView
                    player={player}
                    style={styles.player}
                    fullscreenOptions={{ enable: true }}
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

              {isLoading && (
                <View style={styles.loadingContainer}>
                  <Text style={[styles.loadingText, { color: colors.text }]}>
                    {isCompressing
                      ? `${t.upload.compressing} ${compressionProgress}%`
                      : `${t.upload.uploading} ${uploadProgress}%`}
                  </Text>
                  <View style={[styles.progressTrack, { backgroundColor: colors.border }]}>
                    {isCompressing ? (
                      <>
                        <View style={[styles.progressFill, { backgroundColor: colors.primary, flex: compressionProgress }]} />
                        <View style={{ flex: 100 - compressionProgress }} />
                      </>
                    ) : (
                      <>
                        <View style={[styles.progressFill, { backgroundColor: colors.primary, flex: uploadProgress }]} />
                        <View style={{ flex: 100 - uploadProgress }} />
                      </>
                    )}
                  </View>
                </View>
              )}

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
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: 8,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  btnSecondaryFlex: { flex: 1 },
  btnSecondaryFull: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    borderWidth: 1,
    borderRadius: 10,
    paddingVertical: 12,
  },
  btnSecondaryText: { fontSize: 14 },

  // ── Ajuste de encuadre ──
  adjWrapper: {
    alignSelf: 'center',
    overflow: 'hidden',
    borderRadius: 8,
    backgroundColor: '#000',
  },
  adjLoading: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 12,
  },
  adjLoadingText: { fontSize: 13 },
  gridLineH: {
    position: 'absolute',
    height: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.65)',
  },
  gridLineV: {
    position: 'absolute',
    width: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.65)',
  },
});
