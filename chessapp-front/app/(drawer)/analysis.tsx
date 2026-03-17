import { analyzeVideo, getAnalysisProgress } from '@/constants/api';
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

// Mapeo de letras FEN a símbolos Unicode de ajedrez
const PIECE_SYMBOLS: Record<string, string> = {
  K: '♚', Q: '♛', R: '♜', B: '♝', N: '♞', P: '♟',
  k: '♚', q: '♛', r: '♜', b: '♝', n: '♞', p: '♟',
};

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
  const [currentMove, setCurrentMove] = useState(0);
  const [analysisProgress, setAnalysisProgress] = useState(0);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const maxMove = fens.length > 0 ? fens.length - 1 : 0;

  useEffect(() => {
    if (file) runAnalysis();
  }, [file]);

  const runAnalysis = async () => {
    try {
      setPhase('analyzing');
      setCurrentMove(0);
      setAnalysisProgress(0);

      // Inicia el polling del progreso cada 800ms
      if (pollRef.current) clearInterval(pollRef.current);
      pollRef.current = setInterval(async () => {
        const pct = await getAnalysisProgress(file as string);
        setAnalysisProgress(pct);
      }, 800);

      const corners = cornersParam ? (JSON.parse(cornersParam) as [number, number][]) : undefined;
      const result = await analyzeVideo(file as string, corners);

      clearInterval(pollRef.current!);
      pollRef.current = null;
      setAnalysisProgress(100);

      setTotalFrames(result.total_frames);
      setAnalysisId(result.analisis_id);
      setFens(result.fens ?? []);
      setPhase('done');
    } catch (err: any) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      setPhase('error');
    }
  };

  // Limpia el intervalo si el componente se desmonta durante el análisis
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

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
                <View style={[styles.progressFill, { backgroundColor: colors.primary, width: `${analysisProgress}%` }]} />
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
                <Text style={[styles.boardCaption, { color: colors.textSecondary }]}>
                  {t.analysis.interactiveBoard}
                </Text>
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

              {/* Análisis de motores — pendiente */}
              <View style={styles.section}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>
                  {t.analysis.moveAnalysis}
                </Text>
                <View style={[styles.pendingBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                  <FontAwesome5 name="chess-knight" size={32} color={colors.textSecondary} />
                  <Text style={[styles.pendingTitle, { color: colors.text }]}>{t.analysis.comingSoon}</Text>
                  <Text style={[styles.pendingDesc, { color: colors.textSecondary }]}>
                    {t.analysis.comingSoonText}
                  </Text>
                </View>
              </View>

              {/* Leyenda de motores */}
              <View style={[styles.legend, { backgroundColor: colors.card }]}>
                <Text style={[styles.legendTitle, { color: colors.textSecondary }]}>{t.analysis.analysisEngines}</Text>
                <View style={styles.legendItems}>
                  <View style={styles.legendItem}>
                    <View style={[styles.legendDot, { backgroundColor: '#3b82f6' }]} />
                    <Text style={[styles.legendText, { color: colors.textSecondary }]}>Stockfish 16</Text>
                  </View>
                  <View style={styles.legendItem}>
                    <View style={[styles.legendDot, { backgroundColor: '#8b5cf6' }]} />
                    <Text style={[styles.legendText, { color: colors.textSecondary }]}>Obsidian</Text>
                  </View>
                  <View style={styles.legendItem}>
                    <View style={[styles.legendDot, { backgroundColor: '#10b981' }]} />
                    <Text style={[styles.legendText, { color: colors.textSecondary }]}>PlentyChess</Text>
                  </View>
                </View>
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
    height: 10,
    borderRadius: 5,
    overflow: 'hidden',
    width: '100%',
    marginTop: 4,
  },
  progressFill: {
    height: '100%',
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
  legendDot: { width: 12, height: 12, borderRadius: 6 },
  legendText: { fontSize: 13 },
});