import AsyncStorage from '@react-native-async-storage/async-storage';
import { analysisChain, analyzeVideoWithProgress, getEngineAnalysis, PositionAnalysis, saveEngineAnalysis } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Clipboard, Dimensions, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

const LAST_GAME_KEY = 'lastGame';

export type LastGameData = {
  file: string;
  analysisId: string;
  moves: number;
  date: string;
};

// Mapeo de letras FEN a símbolos Unicode de ajedrez
const PIECE_SYMBOLS: Record<string, string> = {
  K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟',
};

// ── Helpers para el análisis de motores ─────────────────────────────────────

type AgreementType = 'total' | 'mayoria' | 'desempate';

function getAgreementType(step: import('@/constants/api').ChainStep): AgreementType {
  if (step.full_agreement) return 'total';
  const { stockfish: sf, obsidian: obs, plentychess: pc } = step.engines;
  if (sf.san === obs.san || sf.san === pc.san || obs.san === pc.san) return 'mayoria';
  return 'desempate';
}

/** Colores de los motores que están de acuerdo. */
const ENGINE_COLORS = { stockfish: '#3b82f6', obsidian: '#8b5cf6', plentychess: '#10b981' };

function getAgreementDots(step: import('@/constants/api').ChainStep): string[] {
  if (step.full_agreement) return Object.values(ENGINE_COLORS);
  const { stockfish: sf, obsidian: obs, plentychess: pc } = step.engines;
  if (sf.san === obs.san) return [ENGINE_COLORS.stockfish, ENGINE_COLORS.obsidian];
  if (sf.san === pc.san) return [ENGINE_COLORS.stockfish, ENGINE_COLORS.plentychess];
  if (obs.san === pc.san) return [ENGINE_COLORS.obsidian, ENGINE_COLORS.plentychess];
  return [ENGINE_COLORS.stockfish]; // desempate → Stockfish
}

/** Una sola puntuación en centipawns según las reglas de acuerdo. */
function computeScore(step: import('@/constants/api').ChainStep): number {
  const { stockfish: sf, obsidian: obs, plentychess: pc } = step.engines;
  if (step.full_agreement) {
    const sorted = [sf.score, obs.score, pc.score].sort((a, b) => a - b);
    return sorted[1]; // mediana
  }
  if (sf.san === obs.san) return (sf.score + obs.score) / 2;
  if (sf.san === pc.san)  return (sf.score + pc.score)  / 2;
  if (obs.san === pc.san) return (obs.score + pc.score) / 2;
  return sf.score; // desempate → Stockfish
}

// ── Tablero ──────────────────────────────────────────────────────────────────

// Convierte la parte de posición de un FEN en una matriz 8×8 de letras de piezas
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

type Phase = 'analyzing' | 'done' | 'error';

export default function AnalysisScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const { file, corners: cornersParam } = useLocalSearchParams<{ file: string; corners?: string }>();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  const [phase, setPhase] = useState<Phase>('analyzing');
  const [totalFrames, setTotalFrames] = useState<number>(0);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [fens, setFens] = useState<string[]>([]);
  const [engineAnalysis, setEngineAnalysis] = useState<(PositionAnalysis | null)[]>([]);
  const [currentMove, setCurrentMove] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const disconnectWsRef = useRef<(() => void) | null>(null);

  // Pipeline: bounded concurrency for engine analysis
  const MAX_CONCURRENT = 2;
  const fensRef          = useRef<string[]>([]);
  const engineRef        = useRef<(PositionAnalysis | null)[]>([]);
  const pendingQueueRef  = useRef<{ fen: string; index: number }[]>([]);
  const activeCountRef   = useRef(0);
  const processNextRef   = useRef<() => void>(() => {});

  processNextRef.current = () => {
    while (activeCountRef.current < MAX_CONCURRENT && pendingQueueRef.current.length > 0) {
      const item = pendingQueueRef.current.shift()!;
      activeCountRef.current++;
      analysisChain([item.fen], 5)
        .then((result) => {
          activeCountRef.current--;
          engineRef.current[item.index] = result[0] ?? null;
          setEngineAnalysis([...engineRef.current]);
          processNextRef.current();
        })
        .catch(() => {
          activeCountRef.current--;
          processNextRef.current();
        });
    }
  };

  const enqueueFen = (fen: string, index: number) => {
    engineRef.current[index] = null;
    setEngineAnalysis([...engineRef.current]);
    pendingQueueRef.current.push({ fen, index });
    processNextRef.current();
  };

  const maxMove = fens.length > 0 ? fens.length - 1 : 0;

  useEffect(() => {
    if (file) runAnalysis();
  }, [file]);

  const runAnalysis = () => {
    setPhase('analyzing');
    setCurrentMove(0);
    setAnalysisProgress(0);
    setFens([]);
    setEngineAnalysis([]);
    fensRef.current        = [];
    engineRef.current      = [];
    pendingQueueRef.current = [];
    activeCountRef.current  = 0;

    const corners = cornersParam ? (JSON.parse(cornersParam) as [number, number][]) : undefined;

    disconnectWsRef.current = analyzeVideoWithProgress(
      file as string,
      corners,
      (pct) => setAnalysisProgress(pct),
      async (analisisId, detectedFens) => {
        setAnalysisProgress(100);
        setTotalFrames(detectedFens.length > 0 ? detectedFens.length - 1 : 0);
        setAnalysisId(analisisId);

        const cached = await getEngineAnalysis(analisisId);
        if (cached) {
          fensRef.current   = [...detectedFens];
          engineRef.current = [...cached];
          setFens(detectedFens);
          setEngineAnalysis([...cached]);
        } else {
          fensRef.current = [...detectedFens];
          setFens(detectedFens);
          // Queue any FENs not yet received via streaming (e.g. YOLO fallback skipped on_fen)
          detectedFens.forEach((fen, i) => {
            if (engineRef.current[i] === undefined) {
              enqueueFen(fen, i);
            }
          });
          // Save engine results once all analyses finish (fire-and-forget watcher)
          const checkDone = setInterval(() => {
            const all = engineRef.current;
            if (all.length > 0 && all.every((r) => r !== null)) {
              clearInterval(checkDone);
              saveEngineAnalysis(analisisId, all as PositionAnalysis[]);
            }
          }, 1000);
        }

        const lastGameData: LastGameData = {
          file:       file as string,
          analysisId: analisisId,
          moves:      detectedFens.length > 0 ? detectedFens.length - 1 : 0,
          date:       new Date().toLocaleDateString('es-ES', { day: '2-digit', month: 'short', year: 'numeric' }),
        };
        AsyncStorage.setItem(LAST_GAME_KEY, JSON.stringify(lastGameData));
        // Registrar el vídeo como analizado en el mapa global
        AsyncStorage.getItem('analyzedVideos')
          .then((raw) => {
            const map: Record<string, string> = raw ? JSON.parse(raw) : {};
            map[file as string] = analisisId;
            return AsyncStorage.setItem('analyzedVideos', JSON.stringify(map));
          })
          .catch(() => {});

        setPhase('done');
      },
      (_err) => setPhase('error'),
      (fen, index) => {
        // fen_ready: stream FEN and queue engine analysis immediately
        fensRef.current[index] = fen;
        setFens([...fensRef.current]);
        enqueueFen(fen, index);
      },
    );
  };

  // Cierra el WebSocket si el componente se desmonta durante el análisis
  useEffect(() => () => { disconnectWsRef.current?.(); }, []);

  const copyAnalysisId = () => {
    if (!analysisId) return;
    Clipboard.setString(analysisId);
    Alert.alert(t.analysis.copied, t.analysis.copiedMessage);
  };

  return (
    <>
      <StatusBar style={isDarkMode ? 'light' : 'dark'} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>

        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.analysis.title}</Text>
          <TouchableOpacity style={styles.closeButton} onPress={() => router.back()}>
            <Ionicons name="close" size={30} color={colors.headerText} />
          </TouchableOpacity>
        </View>

        <ScrollView
          style={[styles.scrollView, { backgroundColor: colors.background }]}
          contentContainerStyle={styles.content}
        >
          {/* Nombre del fichero */}
          <View style={[styles.fileInfo, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Ionicons name="film-outline" size={18} color={colors.textSecondary} />
            <Text style={[styles.fileName, { color: colors.textSecondary }]} numberOfLines={1}>
              {file ?? t.analysis.noFile}
            </Text>
          </View>

          {/* ── Estado: analizando ── */}
          {phase === 'analyzing' && (
            <View style={[styles.statusBox, { backgroundColor: colors.card }]}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.statusTitle, { color: colors.text }]}>{t.analysis.analyzing}</Text>
              <Text style={[styles.statusSub, { color: colors.textSecondary }]}>
                {analysisProgress < 50 ? t.analysis.extracting : t.analysis.generatingFens}
              </Text>
              <View style={[styles.progressTrack, { backgroundColor: colors.border }]}>
                <View style={[styles.progressFill, { backgroundColor: colors.primary, flex: analysisProgress }]} />
                <View style={{ flex: 100 - analysisProgress }} />
              </View>
              <Text style={[styles.progressPct, { color: colors.primary }]}>{analysisProgress}%</Text>
            </View>
          )}

          {/* ── Estado: error ── */}
          {phase === 'error' && (
            <View style={[styles.statusBox, { backgroundColor: colors.card }]}>
              <Ionicons name="alert-circle-outline" size={52} color="#ef4444" />
              <Text style={[styles.statusTitle, { color: colors.text }]}>{t.analysis.error}</Text>
              <Text style={[styles.statusSub, { color: colors.textSecondary }]}>
                {t.analysis.processingError}
              </Text>
              <TouchableOpacity
                style={[styles.retryButton, { backgroundColor: colors.buttonBg }]}
                onPress={runAnalysis}
              >
                <Text style={[styles.retryButtonText, { color: colors.buttonText }]}>{t.analysis.retry}</Text>
              </TouchableOpacity>
            </View>
          )}

          {/* ── Estado: completado ── */}
          {phase === 'done' && (
            <>
              {/* Resultado */}
              <View style={[styles.resultBox, { backgroundColor: colors.card }]}>
                <View style={styles.resultRow}>
                  <Ionicons name="checkmark-circle" size={26} color="#22c55e" />
                  <Text style={[styles.resultTitle, { color: colors.text }]}>{t.analysis.complete}</Text>
                </View>
                <View style={styles.statRow}>
                  <Text style={[styles.statLabel, { color: colors.textSecondary }]}>{t.analysis.positionsDetected}</Text>
                  <Text style={[styles.statValue, { color: colors.primary }]}>{totalFrames}</Text>
                </View>
                {analysisId && (
                  <TouchableOpacity style={styles.statRow} onPress={copyAnalysisId}>
                    <Text style={[styles.statLabel, { color: colors.textSecondary }]}>{t.analysis.analysisId}</Text>
                    <Text
                      style={[styles.statValue, { color: colors.textSecondary, fontSize: 12, flex: 1, textAlign: 'right' }]}
                      numberOfLines={1}
                    >
                      {analysisId}
                    </Text>
                    <Ionicons name="copy-outline" size={14} color={colors.textSecondary} style={{ marginLeft: 6 }} />
                  </TouchableOpacity>
                )}
              </View>

              {/* Tablero de ajedrez con piezas reales */}
              <View style={[styles.boardContainer, { backgroundColor: colors.card }]}>
                <View style={styles.chessBoard}>
                  {(fens.length > 0 ? fenToBoard(fens[currentMove]) : Array(8).fill(Array(8).fill(''))).map((row, rowIdx) => (
                    <View key={rowIdx} style={styles.boardRow}>
                      {(row as string[]).map((piece, colIdx) => {
                        const isLight = (rowIdx + colIdx) % 2 === 0;
                        const isWhitePiece = piece !== '' && piece === piece.toUpperCase();
                        return (
                          <View key={colIdx} style={[styles.square, isLight ? styles.lightSquare : styles.darkSquare]}>
                            {piece !== '' && (
                              <Text style={[styles.piece, { color: isWhitePiece ? '#F6F6F6' : '#1a1a1a', textShadowColor: isWhitePiece ? '#555' : '#ddd' }]}>
                                {PIECE_SYMBOLS[piece] ?? ''}
                              </Text>
                            )}
                          </View>
                        );
                      })}
                    </View>
                  ))}
                </View>
              </View>

              {/* Navegación de movimientos */}
              <View style={[styles.controls, { backgroundColor: colors.card }]}>
                <TouchableOpacity
                  style={[styles.controlButton, { backgroundColor: colors.primaryLight, borderColor: colors.primary }, currentMove === 0 && styles.controlButtonDisabled]}
                  onPress={() => setCurrentMove(0)}
                  disabled={currentMove === 0}
                >
                  <Ionicons name="play-skip-back" size={22} color={currentMove === 0 ? colors.textSecondary : colors.primary} />
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.controlButton, { backgroundColor: colors.primaryLight, borderColor: colors.primary }, currentMove === 0 && styles.controlButtonDisabled]}
                  onPress={() => setCurrentMove(c => Math.max(0, c - 1))}
                  disabled={currentMove === 0}
                >
                  <Ionicons name="chevron-back" size={26} color={currentMove === 0 ? colors.textSecondary : colors.primary} />
                </TouchableOpacity>
                <View style={[styles.moveCountBadge, { backgroundColor: colors.primaryLight }]}>
                  <Text style={[styles.moveCountText, { color: colors.primary }]}>
                    {currentMove} / {maxMove}
                  </Text>
                </View>
                <TouchableOpacity
                  style={[styles.controlButton, { backgroundColor: colors.primaryLight, borderColor: colors.primary }, currentMove === maxMove && styles.controlButtonDisabled]}
                  onPress={() => setCurrentMove(c => Math.min(maxMove, c + 1))}
                  disabled={currentMove === maxMove}
                >
                  <Ionicons name="chevron-forward" size={26} color={currentMove === maxMove ? colors.textSecondary : colors.primary} />
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.controlButton, { backgroundColor: colors.primaryLight, borderColor: colors.primary }, currentMove === maxMove && styles.controlButtonDisabled]}
                  onPress={() => setCurrentMove(maxMove)}
                  disabled={currentMove === maxMove}
                >
                  <Ionicons name="play-skip-forward" size={22} color={currentMove === maxMove ? colors.textSecondary : colors.primary} />
                </TouchableOpacity>
              </View>

              {/* Análisis de motores */}
              <View style={styles.section}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>
                  {t.analysis.moveAnalysis}
                </Text>

                {/* Leyenda de colores de motores */}
                <View style={[styles.legend, { backgroundColor: colors.card }]}>
                  <Text style={[styles.legendTitle, { color: colors.textSecondary }]}>
                    {t.analysis.analysisEngines}
                  </Text>
                  <View style={styles.legendItems}>
                    <View style={styles.legendItem}>
                      <View style={[styles.legendDot, { backgroundColor: ENGINE_COLORS.stockfish }]} />
                      <Text style={[styles.legendText, { color: colors.text }]}>Stockfish</Text>
                    </View>
                    <View style={styles.legendItem}>
                      <View style={[styles.legendDot, { backgroundColor: ENGINE_COLORS.obsidian }]} />
                      <Text style={[styles.legendText, { color: colors.text }]}>Obsidian</Text>
                    </View>
                    <View style={styles.legendItem}>
                      <View style={[styles.legendDot, { backgroundColor: ENGINE_COLORS.plentychess }]} />
                      <Text style={[styles.legendText, { color: colors.text }]}>PlentyChess</Text>
                    </View>
                  </View>
                </View>
                {engineAnalysis.length === 0 ? (
                  <View style={[styles.pendingBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                    <FontAwesome5 name="chess-knight" size={32} color={colors.textSecondary} />
                    <Text style={[styles.pendingDesc, { color: colors.textSecondary }]}>
                      {t.analysis.noAnalysis}
                    </Text>
                  </View>
                ) : (() => {
                  const posAnalysis = engineAnalysis[currentMove];
                  if (posAnalysis === null) return (
                    <View style={[styles.pendingBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                      <ActivityIndicator size="small" color={colors.primary} />
                      <Text style={[styles.pendingDesc, { color: colors.textSecondary }]}>
                        {t.analysis.calculatingMoves}
                      </Text>
                    </View>
                  );
                  if (posAnalysis === undefined) return (
                    <View style={[styles.pendingBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                      <Text style={[styles.pendingDesc, { color: colors.textSecondary }]}>
                        {t.analysis.noAnalysis}
                      </Text>
                    </View>
                  );
                  const validSteps = (posAnalysis.chain ?? []).filter((step) => step.engines != null);
                  if (validSteps.length === 0) {
                    const rootError  = (posAnalysis as any).error as string | undefined;
                    const chainErr   = (posAnalysis.chain ?? []).find((s) => 'error' in (s as any));
                    const chainErrMsg = chainErr ? (chainErr as any).error as string : undefined;
                    const hasError   = rootError !== undefined || chainErrMsg !== undefined;
                    const errorMsg   = rootError ?? chainErrMsg ?? '';
                    return (
                      <View style={[styles.pendingBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                        <Ionicons name="warning-outline" size={32} color="#f59e0b" />
                        <Text style={[styles.pendingDesc, { color: colors.textSecondary }]}>
                          {hasError
                            ? `${t.analysis.engineError}: ${errorMsg || 'error desconocido'}`
                            : t.analysis.noAnalysis}
                        </Text>
                      </View>
                    );
                  }
                  return (
                    <View style={[styles.engineBox, { backgroundColor: colors.card }]}>
                      {validSteps.map((step) => {
                        const agType  = getAgreementType(step);
                        const dots    = getAgreementDots(step);
                        const score   = computeScore(step);
                        const scoreStr = (score > 0 ? '+' : '') + score.toFixed(2);
                        const agLabel = agType === 'total'
                          ? t.analysis.fullAgreement
                          : agType === 'mayoria'
                          ? t.analysis.majorityAgreement
                          : t.analysis.tiebreaker;
                        const agBg    = agType === 'total' ? '#dcfce7'
                                      : agType === 'mayoria' ? '#fef9c3' : '#fee2e2';
                        const agColor = agType === 'total' ? '#16a34a'
                                      : agType === 'mayoria' ? '#a16207' : '#dc2626';
                        return (
                          <View key={step.step} style={[styles.chainStep, { borderColor: colors.border }]}>
                            <View style={styles.chainRow}>
                              {/* Número */}
                              <View style={[styles.stepBadge, { backgroundColor: colors.primaryLight }]}>
                                <Text style={[styles.stepBadgeText, { color: colors.primary }]}>{step.step}</Text>
                              </View>
                              {/* Jugada */}
                              <Text style={[styles.consensusMove, { color: colors.text }]}>{step.consensus_san}</Text>
                              {/* Etiqueta consenso + puntos de color */}
                              <View style={styles.agreementCol}>
                                <View style={[styles.agreementBadge, { backgroundColor: agBg }]}>
                                  <Text style={[styles.agreementText, { color: agColor }]}>{agLabel}</Text>
                                </View>
                                <View style={styles.dotsRow}>
                                  {dots.map((c, i) => (
                                    <View key={i} style={[styles.engineDot, { backgroundColor: c }]} />
                                  ))}
                                </View>
                              </View>
                              {/* Puntuación única */}
                              <Text style={[styles.scoreText, { color: score >= 0 ? '#16a34a' : '#dc2626' }]}>
                                {scoreStr}
                              </Text>
                            </View>
                          </View>
                        );
                      })}
                    </View>
                  );
                })()}
              </View>
            </>
          )}

          <View style={{ height: 40 }} />
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

// Tamaño del tablero ajustado al múltiplo de 8 más cercano para evitar artefactos sub-píxel
const BOARD_SIZE = Math.floor((Dimensions.get('window').width - 40 - 24) / 8) * 8;
const CELL_SIZE  = BOARD_SIZE / 8;

const styles = StyleSheet.create({
  container: { flex: 1 },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 15,
  },
  menuButton: { padding: 5 },
  closeButton: { padding: 5 },
  headerTitle: {
    fontSize: 20,
    fontWeight: 'bold',
    flex: 1,
    textAlign: 'center',
  },
  scrollView: { flex: 1 },
  content: {
    paddingTop: 20,
    paddingHorizontal: 20,
  },

  // Fichero
  fileInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    borderRadius: 10,
    borderWidth: 1,
    paddingHorizontal: 14,
    paddingVertical: 10,
    marginBottom: 16,
  },
  fileName: { fontSize: 13, flex: 1 },

  // Estado
  statusBox: {
    borderRadius: 16,
    padding: 32,
    alignItems: 'center',
    gap: 14,
    marginBottom: 20,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  statusTitle: { fontSize: 18, fontWeight: 'bold' },
  statusSub: { fontSize: 14, textAlign: 'center' },
  progressTrack: {
    flexDirection: 'row',
    height: 10,
    borderRadius: 5,
    overflow: 'hidden',
    width: '100%',
    marginTop: 4,
  },
  progressFill: {
    height: 10,
    borderRadius: 5,
  },
  progressPct: { fontSize: 13, fontWeight: '700' },
  retryButton: {
    marginTop: 8,
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 12,
  },
  retryButtonText: { fontSize: 16, fontWeight: 'bold' },

  // Resultado
  resultBox: {
    borderRadius: 14,
    padding: 16,
    marginBottom: 16,
    gap: 10,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  resultRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  resultTitle: { fontSize: 17, fontWeight: 'bold' },
  statRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  statLabel: { fontSize: 14 },
  statValue: { fontSize: 16, fontWeight: 'bold' },

  // Tablero
  boardContainer: {
    borderRadius: 12,
    padding: 12,
    marginBottom: 16,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
    alignItems: 'center',
    gap: 10,
  },
  chessBoard: {
    width: BOARD_SIZE,
    height: BOARD_SIZE,
    borderWidth: 2,
    borderColor: '#4b5563',
    borderRadius: 8,
    overflow: 'hidden',
  },
  boardRow: { width: BOARD_SIZE, height: CELL_SIZE, flexDirection: 'row' },
  square: { width: CELL_SIZE, height: CELL_SIZE, alignItems: 'center', justifyContent: 'center' },
  lightSquare: { backgroundColor: '#f0d9b5' },
  darkSquare: { backgroundColor: '#b58863' },
  piece: {
    fontSize: 22,
    textAlign: 'center',
    textShadowOffset: { width: 0.5, height: 0.5 },
    textShadowRadius: 1,
  },
  boardCaption: { fontSize: 12 },

  // Controles
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 12,
    marginBottom: 20,
    borderRadius: 12,
    padding: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  controlButton: {
    width: 52,
    height: 52,
    borderRadius: 26,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
  },
  controlButtonDisabled: { opacity: 0.4 },
  moveCountBadge: {
    paddingHorizontal: 14,
    paddingVertical: 6,
    borderRadius: 20,
  },
  moveCountText: { fontSize: 14, fontWeight: '700' },

  // Secciones
  section: { marginBottom: 20 },
  sectionTitle: { fontSize: 18, fontWeight: 'bold', marginBottom: 12 },

  // Pendiente
  pendingBox: {
    borderRadius: 14,
    borderWidth: 1,
    padding: 24,
    alignItems: 'center',
    gap: 12,
  },
  pendingTitle: { fontSize: 16, fontWeight: 'bold' },
  pendingDesc: { fontSize: 14, textAlign: 'center', lineHeight: 20 },

  // Leyenda
  legend: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 20,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  legendTitle: { fontSize: 14, fontWeight: '600', marginBottom: 10 },
  legendItems: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  legendDot: { width: 10, height: 10, borderRadius: 5 },
  legendText: { fontSize: 12 },

  // Motor de análisis
  engineBox: {
    borderRadius: 14,
    padding: 12,
    gap: 2,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  chainStep: {
    paddingVertical: 8,
    borderBottomWidth: 1,
  },
  chainRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  stepBadge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stepBadgeText: { fontSize: 12, fontWeight: '700' },
  consensusMove: { fontSize: 16, fontWeight: 'bold', flex: 1 },
  agreementCol: { alignItems: 'center', gap: 4 },
  agreementBadge: { paddingHorizontal: 7, paddingVertical: 2, borderRadius: 10 },
  agreementText: { fontSize: 10, fontWeight: '600' },
  dotsRow: { flexDirection: 'row', gap: 4 },
  engineDot: { width: 8, height: 8, borderRadius: 4 },
  scoreText: { fontSize: 13, fontWeight: '700', minWidth: 42, textAlign: 'right' },
});