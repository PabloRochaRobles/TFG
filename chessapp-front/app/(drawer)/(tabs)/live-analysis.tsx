/**
 * live-analysis.tsx — Pantalla de análisis en directo desde la cámara.
 *
 * Flujo:
 *   1. Vista previa de la cámara con permiso pedido si hace falta.
 *   2. Pulsar "Capturar para calibrar" → se toma una foto fija.
 *   3. El usuario marca las 4 esquinas (a1 → a8 → h8 → h1) sobre esa foto.
 *   4. Pulsar "Comenzar" → se abre la sesión en directo en el backend,
 *      se conecta el WebSocket, se envía el `init` con las esquinas en
 *      coordenadas absolutas de la foto, y empieza el bucle de captura
 *      que envía un fotograma cada CAPTURE_INTERVAL_MS.
 *   5. Cada `fen_ready` del backend actualiza la lista de posiciones y
 *      el tablero mostrado en pantalla. Al pulsar "Detener" se cierra
 *      la sesión.
 *
 * NO toca `camera.tsx` ni el flujo de subida + análisis offline: esta
 * pantalla es una vía paralela.
 */
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
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

import ChessPiece from '@/components/ChessPiece';
import {
  createLiveSession, openLiveAnalysisWS, type EngineResult, type LiveEvent,
} from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { useTheme } from '@/contexts/ThemeContext';

// ── Configuración ────────────────────────────────────────────────────────────
const CAPTURE_INTERVAL_MS = 2000;   // periodicidad del envío de frames
const CAPTURE_QUALITY     = 0.5;    // 0-1; menos = JPEG más ligero, más rápido

// Forma real (en runtime) de lo que devuelve `takePictureAsync` en expo-camera.
// Los tipos exportados en SDK 54 están desfasados respecto al comportamiento
// real, por eso se castea.
type CapturedPhoto = { uri: string; width?: number; height?: number } | undefined;
const CORNER_ORDER = [
  { key: 'TL', square: 'a1', label: 'a1', color: '#22c55e' },
  { key: 'TR', square: 'a8', label: 'a8', color: '#f97316' },
  { key: 'BR', square: 'h8', label: 'h8', color: '#ef4444' },
  { key: 'BL', square: 'h1', label: 'h1', color: '#3b82f6' },
] as const;

type RelCorner = [number, number];   // coords relativas 0-1 sobre la imagen
type Stage = 'preview' | 'calibrating' | 'live' | 'stopped';
type LiveEngineAnalysis = {
  index: number;
  fen: string;
  score: number;
  best_move_san: string;
  best_move_uci: string;
  full_agreement: boolean;
  engines: { stockfish: EngineResult; obsidian: EngineResult; plentychess: EngineResult };
};

// ── Tablero ──────────────────────────────────────────────────────────────────
function fenToBoard(fen: string): string[][] {
  const rows = fen.split(' ')[0].split('/');
  return rows.map(row => {
    const cells: string[] = [];
    for (const ch of row) {
      if (/\d/.test(ch)) cells.push(...Array(Number(ch)).fill(''));
      else cells.push(ch);
    }
    return cells;
  });
}

const SCREEN_W   = Dimensions.get('window').width;
const EVAL_BAR_W = 46;
const BOARD_SIZE = Math.floor((SCREEN_W - 40 - 24 - EVAL_BAR_W) / 8) * 8;
const CELL_SIZE  = BOARD_SIZE / 8;
const PIECE_RATIO = 0.85;

// Tamaño del contenedor de la captura de calibración (espacio lógico).
const CALIB_W = SCREEN_W - 40;
const CALIB_H = (SCREEN_W - 40) * 0.65;

// ── Pantalla ─────────────────────────────────────────────────────────────────
export default function LiveAnalysisScreen() {
  const t          = useTranslation();
  const colors     = useThemeColors();
  const { isDarkMode } = useTheme();
  const navigation = useNavigation();
  const router     = useRouter();

  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);

  const [stage, setStage] = useState<Stage>('preview');
  const [snapshot, setSnapshot] = useState<{ uri: string; w: number; h: number } | null>(null);
  const [snapshotLayout, setSnapshotLayout] = useState({ offsetX: 0, offsetY: 0, displayW: 1, displayH: 1 });
  const [corners, setCorners] = useState<RelCorner[]>([]);

  // ── Pinch-to-zoom + pan para la calibración (idéntico patrón al de upload.tsx)
  // Los shared values se transforman dentro de los gestos (worklets); el
  // estado `zoomLevel` se sincroniza desde JS para alternar el botón
  // "Deshacer zoom".
  const scale       = useSharedValue(1);
  const tx          = useSharedValue(0);
  const ty          = useSharedValue(0);
  const savedScale  = useSharedValue(1);
  const savedTx     = useSharedValue(0);
  const savedTy     = useSharedValue(0);
  // `imgDisplay` reflejado en shared values para acceso en worklets.
  const imgOffX = useSharedValue(0);
  const imgOffY = useSharedValue(0);
  const imgDW   = useSharedValue(1);
  const imgDH   = useSharedValue(1);
  const [zoomLevel, setZoomLevel] = useState(1);

  // Estado de la sesión en directo
  const [fens, setFens]               = useState<string[]>([]);
  const [, setStats]             = useState<Record<string, number>>({});
  const [, setLastDecision] = useState<string>('');
  const [engineByIndex, setEngineByIndex] = useState<Record<number, LiveEngineAnalysis>>({});
  const [lastEngineError, setLastEngineError] = useState<string>('');
  const [isStarting, setIsStarting]   = useState(false);
  const wsRef = useRef<ReturnType<typeof openLiveAnalysisWS> | null>(null);
  const captureBusyRef = useRef(false);
  const captureIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ── Limpieza al salir ──────────────────────────────────────────────────────
  useEffect(() => () => {
    if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
    wsRef.current?.close();
  }, []);

  // IMPORTANTE: este hook DEBE declararse antes de cualquier `return`
  // condicional (permisos), de lo contrario rompe las Rules of Hooks.
  const onWsEvent = useCallback((ev: LiveEvent) => {
    if (ev.type === 'ready') {
      setFens([ev.fen]);
      setStats({});
      setLastDecision('');
      setEngineByIndex({});
      setLastEngineError('');
    } else if (ev.type === 'frame_result') {
      setLastDecision(ev.decision);
      setStats(prev => ({ ...prev, [ev.decision]: (prev[ev.decision] ?? 0) + 1 }));
    } else if (ev.type === 'fen_ready') {
      const nextFens = ev.fens?.length ? ev.fens : [ev.fen];
      setFens(prev => [...prev, ...nextFens]);
    } else if (ev.type === 'engine_ready') {
      setEngineByIndex(prev => ({
        ...prev,
        [ev.index]: {
          index: ev.index,
          fen: ev.fen,
          score: ev.score,
          best_move_san: ev.best_move_san,
          best_move_uci: ev.best_move_uci,
          full_agreement: ev.full_agreement,
          engines: ev.engines,
        },
      }));
      setLastEngineError('');
    } else if (ev.type === 'engine_error') {
      setLastEngineError(ev.error);
    } else if (ev.type === 'error') {
      Alert.alert('Sesión en directo', ev.error);
    }
  }, []);

  // IMPORTANTE: `useAnimatedStyle` también es un hook (usa useRef por dentro)
  // y debe declararse antes de los `return` condicionales de permisos.
  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: scale.value },
      { translateX: tx.value },
      { translateY: ty.value },
    ],
  }));

  // ── Permisos ───────────────────────────────────────────────────────────────
  if (!permission) {
    return (
      <View style={[styles.center, { backgroundColor: colors.background }]}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }
  if (!permission.granted) {
    return (
      <View style={[styles.center, { backgroundColor: colors.background }]}>
        <Ionicons name="videocam-off-outline" size={64} color={colors.textSecondary} />
        <Text style={[styles.permissionText, { color: colors.text }]}>{t.camera.permissionText}</Text>
        <TouchableOpacity
          style={[styles.permissionBtn, { backgroundColor: colors.buttonBg }]}
          onPress={requestPermission}
        >
          <Text style={[styles.permissionBtnText, { color: colors.buttonText }]}>
            {t.camera.grantPermissions}
          </Text>
        </TouchableOpacity>
      </View>
    );
  }

  // ── 1. Vista previa: tomar foto para calibrar ──────────────────────────────
  const handleCapture = async () => {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: CAPTURE_QUALITY,
        base64: false,
        skipProcessing: true,
        shutterSound: false,
      } as any) as unknown as CapturedPhoto;
      if (!photo?.uri) return;
      setSnapshot({ uri: photo.uri, w: photo.width ?? 0, h: photo.height ?? 0 });
      setCorners([]);
      resetZoom();
      setStage('calibrating');
    } catch {
      Alert.alert('Error', 'No se pudo capturar el fotograma.');
    }
  };

  // ── 2. Calibración: layout de la imagen y gestos ───────────────────────────
  const onSnapshotLayout = (e: any) => {
    const { width: natW, height: natH } = e.nativeEvent.source;
    const imgRatio  = natW / natH;
    const contRatio = CALIB_W / CALIB_H;
    let dW: number, dH: number;
    if (imgRatio > contRatio) { dW = CALIB_W; dH = CALIB_W / imgRatio; }
    else                       { dH = CALIB_H; dW = CALIB_H * imgRatio; }
    const oX = (CALIB_W - dW) / 2;
    const oY = (CALIB_H - dH) / 2;
    setSnapshotLayout({ offsetX: oX, offsetY: oY, displayW: dW, displayH: dH });
    imgOffX.value = oX; imgOffY.value = oY;
    imgDW.value   = dW; imgDH.value   = dH;
    // Si el evento nos da dimensiones reales mejores, las preferimos al
    // snapshot que devolvió takePictureAsync (que a veces es 0).
    if (snapshot && (snapshot.w === 0 || snapshot.h === 0)) {
      setSnapshot({ ...snapshot, w: natW, h: natH });
    }
  };

  // Llamado desde el worklet de tap para añadir una esquina sin salir del JS.
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

  // ── Gestos: pinch (zoom), pan (desplazar) y tap (marcar esquina). ─────────
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

  // ── 3. Comenzar: WS + bucle de envío de frames ─────────────────────────────
  const handleStart = async () => {
    if (!snapshot || corners.length !== 4) return;
    setIsStarting(true);
    try {
      const taskId = await createLiveSession();
      const handle = openLiveAnalysisWS(taskId, onWsEvent);
      wsRef.current = handle;
      // Esquinas en píxeles absolutos del snapshot original
      const absCorners: [number, number][] = corners.map(([rx, ry]) => [
        rx * snapshot.w, ry * snapshot.h,
      ]);
      handle.init(absCorners);
      setStage('live');
      startCaptureLoop();
    } catch (e: any) {
      Alert.alert('Error', e?.message ?? 'No se pudo iniciar el directo.');
    } finally {
      setIsStarting(false);
    }
  };

  const startCaptureLoop = () => {
    if (captureIntervalRef.current) clearInterval(captureIntervalRef.current);
    captureIntervalRef.current = setInterval(() => { void captureAndSend(); }, CAPTURE_INTERVAL_MS);
  };

  const captureAndSend = async () => {
    if (captureBusyRef.current) return;
    if (!cameraRef.current || !wsRef.current?.isOpen()) return;
    captureBusyRef.current = true;
    try {
      const photo = await cameraRef.current.takePictureAsync({
        quality: CAPTURE_QUALITY,
        base64: false,
        skipProcessing: true,
        shutterSound: false,
      } as any) as unknown as CapturedPhoto;
      if (!photo?.uri) return;
      // Convertir el fichero JPEG en disco a ArrayBuffer y enviarlo binario.
      const resp = await fetch(photo.uri);
      const buf  = await resp.arrayBuffer();
      wsRef.current.sendFrame(buf);
    } catch {
      // Captura puntual: ignorar y reintentar en el siguiente tick.
    } finally {
      captureBusyRef.current = false;
    }
  };

  // ── 4. Eventos WS: `onWsEvent` está declarado arriba (antes de los
  //    early returns de permisos) para no romper las Rules of Hooks.

  // ── 5. Detener ─────────────────────────────────────────────────────────────
  const stopSession = () => {
    if (captureIntervalRef.current) {
      clearInterval(captureIntervalRef.current);
      captureIntervalRef.current = null;
    }
    wsRef.current?.close();
    wsRef.current = null;
  };

  // Navega a la pantalla de análisis reutilizando la secuencia de FENs
  // reconstruida durante el directo (posición inicial + una por jugada).
  // Allí se muestran las mejores jugadas según el consenso de motores con
  // navegación adelante/atrás, igual que en el análisis de vídeo.
  const openAnalysis = (sequence: string[]) => {
    router.push({
      pathname: '/(drawer)/analysis',
      params: { fens: JSON.stringify(sequence) },
    });
  };

  const handleStop = () => {
    stopSession();
    setStage('stopped');
    // Si se reconstruyó al menos una jugada, abrir directamente el análisis.
    if (fens.length >= 2) openAnalysis(fens);
  };

  const handleRestart = () => {
    setSnapshot(null);
    setCorners([]);
    setFens([]);
    setStats({});
    setLastDecision('');
    setEngineByIndex({});
    setLastEngineError('');
    setStage('preview');
  };

  // ── Render ────────────────────────────────────────────────────────────────
  const currentFen = fens.length > 0 ? fens[fens.length - 1] : 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const board = fenToBoard(currentFen);
  const currentIndex = Math.max(0, fens.length - 1);
  const currentEngine = engineByIndex[currentIndex];
  const evalScore = currentEngine?.score ?? 0;
  const whitePercent = Math.max(4, Math.min(96, 50 + evalScore * 10));
  const evalLabel = currentEngine
    ? `${evalScore > 0 ? '+' : ''}${evalScore.toFixed(2)}`
    : '...';
  const evalLabelOnTop = evalScore < 0;
  const engineRows = [
    { key: 'stockfish', name: 'Stockfish', move: currentEngine?.engines.stockfish.san },
    { key: 'obsidian', name: 'Obsidian', move: currentEngine?.engines.obsidian.san },
    { key: 'plentychess', name: 'PlentyChess', move: currentEngine?.engines.plentychess.san },
  ];

  return (
    <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
      <StatusBar style={isDarkMode ? 'light' : 'dark'} />

      {/* Cabecera */}
      <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
        <TouchableOpacity onPress={() => navigation.dispatch(DrawerActions.openDrawer())}>
          <Ionicons name="menu" size={30} color={colors.headerText} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.live.title}</Text>
      </View>

      <ScrollView
        style={[styles.contentScroll, { backgroundColor: colors.background }]}
        contentContainerStyle={styles.content}
        scrollEnabled={stage !== 'calibrating'}
      >

        {/* ── Etapa: vista previa de la cámara ── */}
        {stage === 'preview' && (
          <>
            <View style={styles.cameraWrapper}>
              <CameraView
                ref={cameraRef}
                style={StyleSheet.absoluteFill}
                mode="picture"
                animateShutter={false}
              />
            </View>
            <Text style={[styles.hint, { color: colors.textSecondary }]}>{t.live.previewHint}</Text>
            <TouchableOpacity
              style={[styles.primaryBtn, { backgroundColor: colors.primary }]}
              onPress={handleCapture}
            >
              <Ionicons name="camera" size={20} color={colors.buttonText} />
              <Text style={[styles.primaryBtnText, { color: colors.buttonText }]}>{t.live.captureToCalibrate}</Text>
            </TouchableOpacity>
          </>
        )}

        {/* ── Etapa: calibración sobre snapshot ── */}
        {stage === 'calibrating' && snapshot && (
          <>
            <Text style={[styles.hint, { color: colors.textSecondary }]}>{t.live.calibrateHint}</Text>
            <View style={styles.stepsRow}>
              {CORNER_ORDER.map((c, idx) => (
                <View key={c.key} style={styles.stepItem}>
                  <View style={[
                    styles.stepDot,
                    {
                      backgroundColor: idx < corners.length ? c.color : colors.border,
                      borderColor:     idx === corners.length ? c.color : 'transparent',
                    },
                  ]}>
                    {idx < corners.length && <Ionicons name="checkmark" size={12} color="#fff" />}
                  </View>
                  <Text style={[styles.stepLabel, { color: idx === corners.length ? c.color : colors.textSecondary }]}>
                    {c.label}
                  </Text>
                </View>
              ))}
            </View>
            {/* Captura con pinch-to-zoom + pan (mismo patrón que upload.tsx).
                El tap añade esquinas; el pinch amplía la imagen; el pan la
                desplaza cuando hay zoom activo. */}
            <View style={[styles.snapshotOuter, { width: CALIB_W, height: CALIB_H }]}>
              <GestureDetector gesture={composedGesture}>
                <Animated.View style={[styles.snapshotWrapper, { width: CALIB_W, height: CALIB_H }, animatedStyle]}>
                  <Image
                    source={{ uri: snapshot.uri }}
                    style={{ width: CALIB_W, height: CALIB_H }}
                    resizeMode="contain"
                    onLoad={onSnapshotLayout}
                  />
                  {corners.map(([rx, ry], idx) => {
                    const c = CORNER_ORDER[idx];
                    const cx = snapshotLayout.offsetX + rx * snapshotLayout.displayW;
                    const cy = snapshotLayout.offsetY + ry * snapshotLayout.displayH;
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
              {t.live.zoomHint}
            </Text>
            {zoomLevel > 1.05 && (
              <TouchableOpacity
                style={[styles.secondaryBtn, { borderColor: colors.border }]}
                onPress={resetZoom}
              >
                <Ionicons name="scan-outline" size={16} color={colors.text} />
                <Text style={[styles.secondaryBtnText, { color: colors.text }]}>
                  {t.live.resetZoom}
                </Text>
              </TouchableOpacity>
            )}
            <View style={styles.row}>
              {corners.length > 0 && (
                <TouchableOpacity
                  style={[styles.secondaryBtn, { borderColor: colors.border }]}
                  onPress={() => setCorners(prev => prev.slice(0, -1))}
                >
                  <Ionicons name="arrow-undo" size={16} color={colors.text} />
                  <Text style={[styles.secondaryBtnText, { color: colors.text }]}>{t.live.undo}</Text>
                </TouchableOpacity>
              )}
              <TouchableOpacity
                style={[styles.secondaryBtn, { borderColor: colors.border }]}
                onPress={() => { setSnapshot(null); setCorners([]); resetZoom(); setStage('preview'); }}
              >
                <Ionicons name="camera-reverse" size={16} color={colors.text} />
                <Text style={[styles.secondaryBtnText, { color: colors.text }]}>{t.live.retake}</Text>
              </TouchableOpacity>
            </View>
            {corners.length === 4 && (
              <TouchableOpacity
                style={[styles.primaryBtn, { backgroundColor: colors.primary, opacity: isStarting ? 0.5 : 1 }]}
                onPress={handleStart}
                disabled={isStarting}
              >
                {isStarting ? (
                  <ActivityIndicator color={colors.buttonText} />
                ) : (
                  <>
                    <Ionicons name="play-circle" size={20} color={colors.buttonText} />
                    <Text style={[styles.primaryBtnText, { color: colors.buttonText }]}>{t.live.start}</Text>
                  </>
                )}
              </TouchableOpacity>
            )}
          </>
        )}

        {/* ── Etapa: directo ── */}
        {(stage === 'live' || stage === 'stopped') && (
          <>
            {stage === 'live' && (
              <View style={[styles.liveBadge, { backgroundColor: '#ef4444' }]}>
                <View style={styles.liveDot} />
                <Text style={styles.liveBadgeText}>{t.live.recording}</Text>
              </View>
            )}
            {/* Vista en vivo de la cámara; se usa también para capturar los frames enviados al backend. */}
            {stage === 'live' && (
              <View style={styles.liveCameraWrapper}>
                <CameraView
                  ref={cameraRef}
                  style={StyleSheet.absoluteFill}
                  mode="picture"
                  animateShutter={false}
                />
              </View>
            )}
            <View style={[styles.boardContainer, { backgroundColor: colors.card }]}>
              <View style={styles.boardWithEval}>
                <View style={styles.evalBar}>
                  <View style={[styles.blackEval, { height: `${100 - whitePercent}%` }]} />
                  <View style={[styles.whiteEval, { height: `${whitePercent}%` }]} />
                  <View style={[
                    styles.evalLabelWrap,
                    evalLabelOnTop ? styles.evalLabelTop : styles.evalLabelBottom,
                  ]}>
                    <Text
                      style={[
                        styles.evalLabel,
                        { color: evalLabelOnTop ? '#fff' : '#111827' },
                      ]}
                      numberOfLines={1}
                      adjustsFontSizeToFit
                      minimumFontScale={0.75}
                    >
                      {evalLabel}
                    </Text>
                  </View>
                </View>
                <View style={styles.chessBoard}>
                  {board.map((row, rowIdx) => (
                    <View key={rowIdx} style={styles.boardRow}>
                      {row.map((piece, colIdx) => {
                        const isLight = (rowIdx + colIdx) % 2 === 0;
                        return (
                          <View key={colIdx} style={[styles.square, isLight ? styles.lightSquare : styles.darkSquare]}>
                            {piece !== '' && (
                              <ChessPiece piece={piece} size={Math.floor(CELL_SIZE * PIECE_RATIO)} />
                            )}
                          </View>
                        );
                      })}
                    </View>
                  ))}
                </View>
              </View>
            </View>
            <View style={[styles.enginePanel, { backgroundColor: colors.card }]}>
              <Text style={[styles.engineTitle, { color: colors.text }]}>Mejor Jugada</Text>
              {engineRows.map((engine) => (
                <View key={engine.key} style={[styles.engineRow, { borderColor: colors.border }]}>
                  <Text style={[styles.engineName, { color: colors.text }]}>{engine.name}</Text>
                  <Text style={[styles.engineMove, { color: colors.textSecondary }]} numberOfLines={1}>
                    {engine.move ?? 'calculando...'}
                  </Text>
                </View>
              ))}
              {lastEngineError ? (
                <Text style={[styles.engineError, { color: '#ef4444' }]}>
                  Motor: {lastEngineError}
                </Text>
              ) : null}
            </View>
            {stage === 'live' ? (
              <TouchableOpacity
                style={[styles.primaryBtn, { backgroundColor: '#ef4444' }]}
                onPress={handleStop}
              >
                <Ionicons name="stop-circle" size={20} color="#fff" />
                <Text style={[styles.primaryBtnText, { color: '#fff' }]}>{t.live.stop}</Text>
              </TouchableOpacity>
            ) : (
              <>
                {fens.length >= 2 && (
                  <TouchableOpacity
                    style={[styles.primaryBtn, { backgroundColor: colors.primary }]}
                    onPress={() => openAnalysis(fens)}
                  >
                    <Ionicons name="stats-chart" size={20} color={colors.buttonText} />
                    <Text style={[styles.primaryBtnText, { color: colors.buttonText }]}>{t.live.viewAnalysis}</Text>
                  </TouchableOpacity>
                )}
                <TouchableOpacity
                  style={[styles.secondaryBtn, { borderColor: colors.border }]}
                  onPress={handleRestart}
                >
                  <Ionicons name="refresh" size={16} color={colors.text} />
                  <Text style={[styles.secondaryBtnText, { color: colors.text }]}>{t.live.restart}</Text>
                </TouchableOpacity>
              </>
            )}
          </>
        )}

      </ScrollView>
    </SafeAreaView>
  );
}

// ── Estilos ─────────────────────────────────────────────────────────────────
const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    height: 60, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 15, gap: 12,
  },
  headerTitle: { fontSize: 22, fontWeight: 'bold' },
  contentScroll: { flex: 1 },
  content: { flexGrow: 1, padding: 20, gap: 14 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 16 },
  permissionText: { fontSize: 16, textAlign: 'center', lineHeight: 22 },
  permissionBtn: { paddingHorizontal: 28, paddingVertical: 12, borderRadius: 12, marginTop: 8 },
  permissionBtnText: { fontSize: 16, fontWeight: 'bold' },

  cameraWrapper: {
    width: '100%', aspectRatio: 16 / 9, borderRadius: 16, overflow: 'hidden', backgroundColor: '#000',
  },
  liveCameraWrapper: {
    width: '100%', aspectRatio: 16 / 9, borderRadius: 12, overflow: 'hidden', backgroundColor: '#000',
  },
  hint: { fontSize: 13, textAlign: 'center' },

  primaryBtn: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 8, paddingVertical: 14, borderRadius: 14,
  },
  primaryBtnText: { fontSize: 16, fontWeight: 'bold' },
  secondaryBtn: {
    flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
    gap: 6, paddingVertical: 10, borderWidth: 1, borderRadius: 10,
  },
  secondaryBtnText: { fontSize: 14 },
  row: { flexDirection: 'row', gap: 10 },

  stepsRow: { flexDirection: 'row', justifyContent: 'space-around' },
  stepItem: { alignItems: 'center', gap: 4 },
  stepDot: {
    width: 28, height: 28, borderRadius: 14, borderWidth: 2,
    alignItems: 'center', justifyContent: 'center',
  },
  stepLabel: { fontSize: 12, fontWeight: '600' },

  snapshotOuter: {
    alignSelf: 'center', position: 'relative', overflow: 'hidden',
    borderRadius: 8, backgroundColor: '#000',
  },
  snapshotWrapper: {
    position: 'relative', overflow: 'visible',
  },
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
  zoomHint: { fontSize: 11, textAlign: 'center', marginTop: 4 },

  liveBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    alignSelf: 'flex-start', paddingHorizontal: 10, paddingVertical: 4, borderRadius: 12,
  },
  liveDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#fff' },
  liveBadgeText: { color: '#fff', fontWeight: 'bold', fontSize: 12 },

  boardContainer: {
    borderRadius: 12, padding: 12, alignItems: 'center', elevation: 3,
    shadowColor: '#000', shadowOffset: { width: 0, height: 2 }, shadowOpacity: 0.1, shadowRadius: 3.84,
  },
  boardWithEval: {
    flexDirection: 'row', alignItems: 'center', gap: 8,
  },
  evalBar: {
    width: 38, height: BOARD_SIZE, borderRadius: 6, overflow: 'hidden',
    borderWidth: 1, borderColor: '#4b5563', backgroundColor: '#111827',
  },
  blackEval: { width: '100%', backgroundColor: '#111827' },
  whiteEval: { width: '100%', backgroundColor: '#f9fafb' },
  evalLabelWrap: {
    position: 'absolute', left: 2, right: 2,
    paddingVertical: 3,
    alignItems: 'center',
  },
  evalLabelTop: { top: 6 },
  evalLabelBottom: { bottom: 6 },
  evalLabel: { fontSize: 11, fontWeight: '800', textAlign: 'center' },
  chessBoard: {
    width: BOARD_SIZE, height: BOARD_SIZE, borderWidth: 2, borderColor: '#4b5563',
    borderRadius: 8, overflow: 'hidden',
  },
  boardRow:    { width: BOARD_SIZE, height: CELL_SIZE, flexDirection: 'row' },
  square:      { width: CELL_SIZE, height: CELL_SIZE, alignItems: 'center', justifyContent: 'center' },
  lightSquare: { backgroundColor: '#f0d9b5' },
  darkSquare:  { backgroundColor: '#b58863' },

  enginePanel: { borderRadius: 10, padding: 12, gap: 8 },
  engineTitle: { fontSize: 14, fontWeight: 'bold' },
  engineRow: {
    minHeight: 38, borderWidth: 1, borderRadius: 8, paddingHorizontal: 10,
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10,
  },
  engineName: { fontSize: 13, fontWeight: '700', flexShrink: 0 },
  engineMove: { fontSize: 13, fontWeight: '600', flex: 1, textAlign: 'right' },
  engineError: { fontSize: 12 },
});
