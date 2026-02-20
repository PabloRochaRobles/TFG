import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Alert, Clipboard, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function AnalysisScreen() {
  const router = useRouter();
  const navigation = useNavigation();

  // Estado del análisis (mock data - reemplazar con backend)
  const totalMoves = 42; // Total de movimientos en la partida
  const [currentMove, setCurrentMove] = useState(0); // Movimiento actual (0 = posición inicial)
  
  // Posición FEN actual (esto vendría del backend)
  const fenPosition = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  
  // Top 5 mejores movimientos según análisis
  const topMoves = [
    { move: 'e4', evaluation: '+0.3', engines: ['Stockfish', 'Obsidian', 'Plentychess'] },
    { move: 'd4', evaluation: '+0.2', engines: ['Stockfish', 'Obsidian'] },
    { move: 'Nf3', evaluation: '+0.1', engines: ['Stockfish', 'Plentychess'] },
    { move: 'c4', evaluation: '0.0', engines: ['Obsidian'] },
    { move: 'g3', evaluation: '-0.1', engines: ['Plentychess'] },
  ];

  // Movimiento jugado en la partida
  const playedMove = 'e4';

  // Navegación de movimientos
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

  // Copiar FEN al portapapeles
  const copyFEN = () => {
    Clipboard.setString(fenPosition);
    Alert.alert('Copiado', 'Posición FEN copiada al portapapeles');
  };

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Análisis de Partida</Text>
          <TouchableOpacity 
            style={styles.closeButton}
            onPress={() => router.back()}
          >
            <Ionicons name="close" size={30} color="white" />
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
          {/* Información de movimiento actual */}
          <View style={styles.moveInfo}>
            <Text style={styles.moveNumber}>
              Movimiento {currentMove} de {totalMoves}
            </Text>
            {currentMove > 0 && (
              <View style={styles.playedMoveContainer}>
                <Text style={styles.playedMoveLabel}>Jugado:</Text>
                <Text style={styles.playedMove}>{playedMove}</Text>
              </View>
            )}
          </View>

          {/* Tablero de ajedrez (placeholder) */}
          <View style={styles.boardContainer}>
            <View style={styles.chessBoard}>
              {/* Aquí iría el componente del tablero real */}
              {/* Por ahora, un placeholder visual */}
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
                        {/* Aquí irían las piezas */}
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
          <View style={styles.controls}>
            <TouchableOpacity
              style={[styles.controlButton, currentMove === 0 && styles.controlButtonDisabled]}
              onPress={goToStart}
              disabled={currentMove === 0}
            >
              <Ionicons 
                name="play-skip-back" 
                size={24} 
                color={currentMove === 0 ? '#d1d5db' : '#3b82f6'} 
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.controlButton, currentMove === 0 && styles.controlButtonDisabled]}
              onPress={goToPrevious}
              disabled={currentMove === 0}
            >
              <Ionicons 
                name="chevron-back" 
                size={28} 
                color={currentMove === 0 ? '#d1d5db' : '#3b82f6'} 
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.controlButton, currentMove === totalMoves && styles.controlButtonDisabled]}
              onPress={goToNext}
              disabled={currentMove === totalMoves}
            >
              <Ionicons 
                name="chevron-forward" 
                size={28} 
                color={currentMove === totalMoves ? '#d1d5db' : '#3b82f6'} 
              />
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.controlButton, currentMove === totalMoves && styles.controlButtonDisabled]}
              onPress={goToEnd}
              disabled={currentMove === totalMoves}
            >
              <Ionicons 
                name="play-skip-forward" 
                size={24} 
                color={currentMove === totalMoves ? '#d1d5db' : '#3b82f6'} 
              />
            </TouchableOpacity>
          </View>

          {/* Posición FEN */}
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Text style={styles.sectionTitle}>Posición FEN</Text>
              <TouchableOpacity style={styles.copyButton} onPress={copyFEN}>
                <Ionicons name="copy-outline" size={20} color="#3b82f6" />
                <Text style={styles.copyButtonText}>Copiar</Text>
              </TouchableOpacity>
            </View>
            <View style={styles.fenContainer}>
              <Text style={styles.fenText} numberOfLines={2}>
                {fenPosition}
              </Text>
            </View>
          </View>

          {/* Top 5 mejores movimientos */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Mejores movimientos (consenso de motores)</Text>
            <View style={styles.movesContainer}>
              {topMoves.map((moveData, index) => (
                <View key={index} style={styles.moveCard}>
                  <View style={styles.moveRank}>
                    <Text style={styles.moveRankText}>#{index + 1}</Text>
                  </View>
                  
                  <View style={styles.moveDetails}>
                    <View style={styles.moveHeader}>
                      <Text style={styles.moveNotation}>{moveData.move}</Text>
                      <View style={[
                        styles.evaluationBadge,
                        moveData.evaluation.startsWith('+') 
                          ? styles.positiveEval 
                          : moveData.evaluation.startsWith('-')
                          ? styles.negativeEval
                          : styles.neutralEval
                      ]}>
                        <Text style={styles.evaluationText}>{moveData.evaluation}</Text>
                      </View>
                    </View>
                    
                    <View style={styles.enginesContainer}>
                      {moveData.engines.map((engine, idx) => (
                        <View key={idx} style={styles.engineBadge}>
                          <FontAwesome5 name="chess-knight" size={10} color="#6b7280" />
                          <Text style={styles.engineText}>{engine}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                </View>
              ))}
            </View>
          </View>

          {/* Leyenda de motores */}
          <View style={styles.legend}>
            <Text style={styles.legendTitle}>Motores de análisis:</Text>
            <View style={styles.legendItems}>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#3b82f6' }]} />
                <Text style={styles.legendText}>Stockfish 16</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#8b5cf6' }]} />
                <Text style={styles.legendText}>Obsidian</Text>
              </View>
              <View style={styles.legendItem}>
                <View style={[styles.legendDot, { backgroundColor: '#10b981' }]} />
                <Text style={styles.legendText}>Plentychess</Text>
              </View>
            </View>
          </View>

          {/* Acciones adicionales */}
          <View style={styles.actions}>
            <TouchableOpacity style={styles.actionButton}>
              <Ionicons name="download-outline" size={22} color="#3b82f6" />
              <Text style={styles.actionButtonText}>Exportar PGN</Text>
            </TouchableOpacity>

            <TouchableOpacity style={styles.actionButton}>
              <Ionicons name="share-social-outline" size={22} color="#3b82f6" />
              <Text style={styles.actionButtonText}>Compartir</Text>
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
    backgroundColor: '#3b82f6' 
  },
  header: {
    height: 60,
    backgroundColor: '#3b82f6',
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
    color: 'white', 
    fontSize: 20, 
    fontWeight: 'bold',
    flex: 1,
    textAlign: 'center',
  },
  scrollView: {
    flex: 1,
    backgroundColor: '#F8F9FA',
  },
  content: {
    paddingTop: 20,
    paddingHorizontal: 20,
  },

  // Info de movimiento
  moveInfo: {
    backgroundColor: '#fff',
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
    color: '#1f2937',
  },
  playedMoveContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  playedMoveLabel: {
    fontSize: 14,
    color: '#6b7280',
  },
  playedMove: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#3b82f6',
  },

  // Tablero
  boardContainer: {
    backgroundColor: '#fff',
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
    backgroundColor: '#fff',
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
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#3b82f6',
  },
  controlButtonDisabled: {
    backgroundColor: '#f3f4f6',
    borderColor: '#d1d5db',
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
    color: '#1f2937',
  },

  // FEN
  copyButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: '#eff6ff',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
  },
  copyButtonText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#3b82f6',
  },
  fenContainer: {
    backgroundColor: '#fff',
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
    color: '#4b5563',
    lineHeight: 20,
  },

  // Mejores movimientos
  movesContainer: {
    gap: 12,
  },
  moveCard: {
    backgroundColor: '#fff',
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
    backgroundColor: '#3b82f6',
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
    color: '#1f2937',
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
    color: '#1f2937',
  },
  enginesContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
  },
  engineBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f9fafb',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
    gap: 4,
  },
  engineText: {
    fontSize: 11,
    color: '#6b7280',
    fontWeight: '500',
  },

  // Leyenda
  legend: {
    backgroundColor: '#fff',
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
    color: '#6b7280',
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
    color: '#4b5563',
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
    backgroundColor: '#fff',
    paddingVertical: 14,
    borderRadius: 12,
    gap: 8,
    borderWidth: 2,
    borderColor: '#3b82f6',
  },
  actionButtonText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3b82f6',
  },
});