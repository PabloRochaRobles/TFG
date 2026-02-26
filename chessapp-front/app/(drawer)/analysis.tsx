import { useThemeColors } from '@/hooks/use-theme-color';
import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useLocalSearchParams, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Alert, Clipboard, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

export default function AnalysisScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const { file } = useLocalSearchParams<{ file: string }>();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

  // Estado del análisis (mock data - reemplazar con backend)
  const totalMoves = 42;
  const [currentMove, setCurrentMove] = useState(0);
  
  const fenPosition = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  
  const topMoves = [
    { move: 'e4', evaluation: '+0.3', engines: ['Stockfish', 'Obsidian', 'Plentychess'] },
    { move: 'd4', evaluation: '+0.2', engines: ['Stockfish', 'Obsidian'] },
    { move: 'Nf3', evaluation: '+0.1', engines: ['Stockfish', 'Plentychess'] },
    { move: 'c4', evaluation: '0.0', engines: ['Obsidian'] },
    { move: 'g3', evaluation: '-0.1', engines: ['Plentychess'] },
  ];

  const playedMove = 'e4';

  const goToStart = () => {
    setCurrentMove(0);
  };

  const goToPrevious = () => {
    if (currentMove > 0) {
      setCurrentMove(currentMove - 1);
    }
  };

  const goToNext = () => {
    if (currentMove < totalMoves) {
      setCurrentMove(currentMove + 1);
    }
  };

  const goToEnd = () => {
    setCurrentMove(totalMoves);
  };

  const copyFEN = () => {
    Clipboard.setString(fenPosition);
    Alert.alert('Copiado', 'Posición FEN copiada al portapapeles');
  };

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
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
          <TouchableOpacity 
            style={styles.closeButton}
            onPress={() => router.back()}
          >
            <Ionicons name="close" size={30} color={colors.headerText} />
          </TouchableOpacity>
        </View>

        <ScrollView style={[styles.scrollView, { backgroundColor: colors.background }]} contentContainerStyle={styles.content}>
          {/* Información de movimiento actual */}
          <View style={[styles.moveInfo, { backgroundColor: colors.card }]}>
            <Text style={[styles.moveNumber, { color: colors.text }]}>
              Movimiento {currentMove} de {totalMoves}
            </Text>
            {currentMove > 0 && (
              <View style={styles.playedMoveContainer}>
                <Text style={[styles.playedMoveLabel, { color: colors.textSecondary }]}>Jugado:</Text>
                <Text style={[styles.playedMove, { color: colors.primary }]}>{playedMove}</Text>
              </View>
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
                        style={[
                          styles.square,
                          isLight ? styles.lightSquare : styles.darkSquare,
                        ]}
                      >
                        {row === 0 && col === 0 && (
                          <Text style={styles.piece}>♜</Text>
                        )}
                        {row === 0 && col === 4 && (
                          <Text style={styles.piece}>♚</Text>
                        )}
                        {row === 7 && col === 0 && (
                          <Text style={styles.piece}>♖</Text>
                        )}
                        {row === 7 && col === 4 && (
                          <Text style={styles.piece}>♔</Text>
                        )}
                      </View>
                    );
                  })}
                </View>
              ))}
            </View>
          </View>

          {/* Controles de navegación */}
          <View style={[styles.controls, { backgroundColor: colors.card }]}>
            <TouchableOpacity
              style={[
                styles.controlButton,
                { backgroundColor: colors.primaryLight, borderColor: colors.primary },
                currentMove === 0 && styles.controlButtonDisabled
              ]}
              onPress={goToStart}
              disabled={currentMove === 0}
            >
              <Ionicons 
                name="play-skip-back" 
                size={24} 
                color={currentMove === 0 ? colors.textSecondary : colors.primary} 
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.controlButton,
                { backgroundColor: colors.primaryLight, borderColor: colors.primary },
                currentMove === 0 && styles.controlButtonDisabled
              ]}
              onPress={goToPrevious}
              disabled={currentMove === 0}
            >
              <Ionicons 
                name="chevron-back" 
                size={28} 
                color={currentMove === 0 ? colors.textSecondary : colors.primary} 
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.controlButton,
                { backgroundColor: colors.primaryLight, borderColor: colors.primary },
                currentMove === totalMoves && styles.controlButtonDisabled
              ]}
              onPress={goToNext}
              disabled={currentMove === totalMoves}
            >
              <Ionicons 
                name="chevron-forward" 
                size={28} 
                color={currentMove === totalMoves ? colors.textSecondary : colors.primary} 
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={[
                styles.controlButton,
                { backgroundColor: colors.primaryLight, borderColor: colors.primary },
                currentMove === totalMoves && styles.controlButtonDisabled
              ]}
              onPress={goToEnd}
              disabled={currentMove === totalMoves}
            >
              <Ionicons 
                name="play-skip-forward" 
                size={24} 
                color={currentMove === totalMoves ? colors.textSecondary : colors.primary} 
              />
            </TouchableOpacity>
          </View>

          {/* Posición FEN */}
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>Posición FEN</Text>
              <TouchableOpacity style={[styles.copyButton, { backgroundColor: colors.primaryLight }]} onPress={copyFEN}>
                <Ionicons name="copy-outline" size={20} color={colors.primary} />
                <Text style={[styles.copyButtonText, { color: colors.primary }]}>Copiar</Text>
              </TouchableOpacity>
            </View>
            <View style={[styles.fenContainer, { backgroundColor: colors.card }]}>
              <Text style={[styles.fenText, { color: colors.textSecondary }]} numberOfLines={2}>
                {fenPosition}
              </Text>
            </View>
          </View>

          {/* Top 5 mejores movimientos */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Mejores movimientos (consenso de motores)</Text>
            <View style={styles.movesContainer}>
              {topMoves.map((moveData, index) => (
                <View key={index} style={[styles.moveCard, { backgroundColor: colors.card }]}>
                  <View style={[styles.moveRank, { backgroundColor: colors.primary }]}>
                    <Text style={styles.moveRankText}>#{index + 1}</Text>
                  </View>
                  
                  <View style={styles.moveDetails}>
                    <View style={styles.moveHeader}>
                      <Text style={[styles.moveNotation, { color: colors.text }]}>{moveData.move}</Text>
                      <View style={[
                        styles.evaluationBadge,
                        moveData.evaluation.startsWith('+') 
                          ? styles.positiveEval 
                          : moveData.evaluation.startsWith('-')
                          ? styles.negativeEval
                          : styles.neutralEval
                      ]}>
                        <Text style={[styles.evaluationText, { color: colors.text }]}>{moveData.evaluation}</Text>
                      </View>
                    </View>
                    
                    <View style={styles.enginesContainer}>
                      {moveData.engines.map((engine, idx) => (
                        <View key={idx} style={[styles.engineBadge, { backgroundColor: isDarkMode ? '#374151' : '#f9fafb' }]}>
                          <FontAwesome5 name="chess-knight" size={10} color={colors.textSecondary} />
                          <Text style={[styles.engineText, { color: colors.textSecondary }]}>{engine}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                </View>
              ))}
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
                <Text style={[styles.legendText, { color: colors.textSecondary }]}>Plentychess</Text>
              </View>
            </View>
          </View>

          {/* Acciones adicionales */}
          <View style={styles.actions}>
            <TouchableOpacity style={[styles.actionButton, { backgroundColor: colors.card, borderColor: colors.primary }]}>
              <Ionicons name="download-outline" size={22} color={colors.primary} />
              <Text style={[styles.actionButtonText, { color: colors.primary }]}>Exportar PGN</Text>
            </TouchableOpacity>

            <TouchableOpacity style={[styles.actionButton, { backgroundColor: colors.card, borderColor: colors.primary }]}>
              <Ionicons name="share-social-outline" size={22} color={colors.primary} />
              <Text style={[styles.actionButtonText, { color: colors.primary }]}>Compartir</Text>
            </TouchableOpacity>
          </View>

          {/* Espacio inferior */}
          <View style={{ height: 40 }} />
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1,
  },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 15,
  },
  menuButton: { 
    padding: 5,
  },
  closeButton: {
    padding: 5,
  },
  headerTitle: { 
    fontSize: 20, 
    fontWeight: 'bold',
    flex: 1,
    textAlign: 'center',
  },
  scrollView: {
    flex: 1,
  },
  content: {
    paddingTop: 20,
    paddingHorizontal: 20,
  },

  // Info de movimiento
  moveInfo: {
    borderRadius: 12,
    padding: 16,
    marginBottom: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  moveNumber: {
    fontSize: 16,
    fontWeight: '600',
  },
  playedMoveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  playedMoveLabel: {
    fontSize: 14,
  },
  playedMove: {
    fontSize: 18,
    fontWeight: 'bold',
  },

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
  },
  chessBoard: {
    aspectRatio: 1,
    borderWidth: 2,
    borderColor: '#4b5563',
    borderRadius: 8,
    overflow: 'hidden',
  },
  boardRow: {
    flex: 1,
    flexDirection: 'row',
  },
  square: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  lightSquare: {
    backgroundColor: '#f0d9b5',
  },
  darkSquare: {
    backgroundColor: '#b58863',
  },
  piece: {
    fontSize: 32,
  },

  // Controles
  controls: {
    flexDirection: 'row',
    justifyContent: 'center',
    gap: 20,
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
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
  },
  controlButtonDisabled: {
    opacity: 0.4,
  },

  // Secciones
  section: {
    marginBottom: 20,
  },
  sectionHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 12,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
  },

  // FEN
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  copyButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
  fenContainer: {
    borderRadius: 12,
    padding: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  fenText: {
    fontSize: 13,
    fontFamily: 'monospace',
    lineHeight: 20,
  },

  // Mejores movimientos
  movesContainer: {
    gap: 12,
  },
  moveCard: {
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  moveRank: {
    width: 36,
    height: 36,
    borderRadius: 18,
    justifyContent: 'center',
    alignItems: 'center',
  },
  moveRankText: {
    fontSize: 14,
    fontWeight: 'bold',
    color: '#fff',
  },
  moveDetails: {
    flex: 1,
  },
  moveHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  moveNotation: {
    fontSize: 20,
    fontWeight: 'bold',
  },
  evaluationBadge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 8,
  },
  positiveEval: {
    backgroundColor: '#d1fae5',
  },
  negativeEval: {
    backgroundColor: '#fee2e2',
  },
  neutralEval: {
    backgroundColor: '#f3f4f6',
  },
  evaluationText: {
    fontSize: 14,
    fontWeight: '700',
  },
  enginesContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  engineBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    gap: 4,
  },
  engineText: {
    fontSize: 11,
    fontWeight: '500',
  },

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
  legendTitle: {
    fontSize: 14,
    fontWeight: '600',
    marginBottom: 10,
  },
  legendItems: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 16,
  },
  legendItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  legendDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  legendText: {
    fontSize: 13,
  },

  // Acciones
  actions: {
    flexDirection: 'row',
    gap: 12,
  },
  actionButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
    borderWidth: 2,
  },
  actionButtonText: {
    fontSize: 15,
    fontWeight: '600',
  },
});