import { useThemeColors } from '@/hooks/use-theme-color';
import { analyzeVideo } from '@/constants/api';
import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Clipboard, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

type Phase = 'analyzing' | 'done' | 'error';

export default function AnalysisScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const { file } = useLocalSearchParams<{ file: string }>();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

  const [phase, setPhase] = useState<Phase>('analyzing');
  const [totalFrames, setTotalFrames] = useState<number>(0);
  const [analysisId, setAnalysisId] = useState<string | null>(null);
  const [currentMove, setCurrentMove] = useState(0);

  useEffect(() => {
    if (file) runAnalysis();
  }, [file]);

  const runAnalysis = async () => {
    try {
      setPhase('analyzing');
      const result = await analyzeVideo(file as string);
      setTotalFrames(result.total_frames);
      setAnalysisId(result.analisis_id);
      setPhase('done');
    } catch (err: any) {
      setPhase('error');
    }
  };

  const copyAnalysisId = () => {
    if (!analysisId) return;
    Clipboard.setString(analysisId);
    Alert.alert('Copiado', 'ID de análisis copiado al portapapeles');
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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Análisis de Partida</Text>
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
              {file ?? 'Sin fichero'}
            </Text>
          </View>

          {/* ── Estado: analizando ── */}
          {phase === 'analyzing' && (
            <View style={[styles.statusBox, { backgroundColor: colors.card }]}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.statusTitle, { color: colors.text }]}>Analizando partida...</Text>
              <Text style={[styles.statusSub, { color: colors.textSecondary }]}>
                Extrayendo posiciones clave del vídeo
              </Text>
            </View>
          )}

          {/* ── Estado: error ── */}
          {phase === 'error' && (
            <View style={[styles.statusBox, { backgroundColor: colors.card }]}>
              <Ionicons name="alert-circle-outline" size={52} color="#ef4444" />
              <Text style={[styles.statusTitle, { color: colors.text }]}>Error en el análisis</Text>
              <Text style={[styles.statusSub, { color: colors.textSecondary }]}>
                No se ha podido procesar el vídeo
              </Text>
              <TouchableOpacity
                style={[styles.retryButton, { backgroundColor: colors.buttonBg }]}
                onPress={runAnalysis}
              >
                <Text style={[styles.retryButtonText, { color: colors.buttonText }]}>Reintentar</Text>
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
                  <Text style={[styles.resultTitle, { color: colors.text }]}>Análisis completado</Text>
                </View>
                <View style={styles.statRow}>
                  <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Posiciones detectadas:</Text>
                  <Text style={[styles.statValue, { color: colors.primary }]}>{totalFrames}</Text>
                </View>
                {analysisId && (
                  <TouchableOpacity style={styles.statRow} onPress={copyAnalysisId}>
                    <Text style={[styles.statLabel, { color: colors.textSecondary }]}>ID de análisis:</Text>
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

              {/* Tablero de ajedrez (placeholder) */}
              <View style={[styles.boardContainer, { backgroundColor: colors.card }]}>
                <View style={styles.chessBoard}>
                  {[...Array(8)].map((_, row) => (
                    <View key={row} style={styles.boardRow}>
                      {[...Array(8)].map((_, col) => {
                        const isLight = (row + col) % 2 === 0;
                        return (
                          <View
                            key={col}
                            style={[styles.square, isLight ? styles.lightSquare : styles.darkSquare]}
                          />
                        );
                      })}
                    </View>
                  ))}
                </View>
                <Text style={[styles.boardCaption, { color: colors.textSecondary }]}>
                  Tablero interactivo — próximamente
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
                    {currentMove} / {totalFrames}
                  </Text>
                </View>
                <TouchableOpacity
                  style={[styles.controlButton, { backgroundColor: colors.primaryLight, borderColor: colors.primary }, currentMove === totalFrames && styles.controlButtonDisabled]}
                  onPress={() => setCurrentMove(c => Math.min(totalFrames, c + 1))}
                  disabled={currentMove === totalFrames}
                >
                  <Ionicons name="chevron-forward" size={26} color={currentMove === totalFrames ? colors.textSecondary : colors.primary} />
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.controlButton, { backgroundColor: colors.primaryLight, borderColor: colors.primary }, currentMove === totalFrames && styles.controlButtonDisabled]}
                  onPress={() => setCurrentMove(totalFrames)}
                  disabled={currentMove === totalFrames}
                >
                  <Ionicons name="play-skip-forward" size={22} color={currentMove === totalFrames ? colors.textSecondary : colors.primary} />
                </TouchableOpacity>
              </View>

              {/* Análisis de motores — pendiente */}
              <View style={styles.section}>
                <Text style={[styles.sectionTitle, { color: colors.text }]}>
                  Análisis de jugadas (motores)
                </Text>
                <View style={[styles.pendingBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
                  <FontAwesome5 name="chess-knight" size={32} color={colors.textSecondary} />
                  <Text style={[styles.pendingTitle, { color: colors.text }]}>Próximamente</Text>
                  <Text style={[styles.pendingDesc, { color: colors.textSecondary }]}>
                    El análisis de jugadas con Stockfish, Obsidian y PlentyChess estará disponible
                    en cuanto se integre el reconocimiento de posiciones FEN desde las imágenes.
                  </Text>
                </View>
              </View>

              {/* Leyenda de motores */}
              <View style={[styles.legend, { backgroundColor: colors.card }]}>
                <Text style={[styles.legendTitle, { color: colors.textSecondary }]}>Motores de análisis:</Text>
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
    width: '100%',
    aspectRatio: 1,
    borderWidth: 2,
    borderColor: '#4b5563',
    borderRadius: 8,
    overflow: 'hidden',
  },
  boardRow: { flex: 1, flexDirection: 'row' },
  square: { flex: 1 },
  lightSquare: { backgroundColor: '#f0d9b5' },
  darkSquare: { backgroundColor: '#b58863' },
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