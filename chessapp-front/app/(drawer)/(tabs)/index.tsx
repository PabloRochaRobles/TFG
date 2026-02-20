import { FontAwesome, FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function HomeScreen() {
  const [menuOpen, setMenuOpen] = useState(false);
  const router = useRouter();
  const navigation = useNavigation();

  // Datos de ejemplo (mock data) - Reemplazar con datos del backend
  const lastGame = {
    videoUri: 'https://via.placeholder.com/300x200', // URL de la miniatura del video
    // O si es local: require('../../../assets/images/video-thumbnail.jpg')
    date: '15 Feb 2026',
    moves: 42,
    videoId: '12345', // ID para reproducir el video
  };

  // Si no hay partidas, cambia a: const lastGame = null;

  const handlePlayVideo = () => {
    // Aquí navegarás a la pantalla de reproducción con el ID del video
    console.log('Reproducir video:', lastGame.videoId);
    // router.push(`/video/${lastGame.videoId}`);
    // Por ahora va a library
    router.push('/analysis');
  };

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header Azul */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.menuButton} 
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Inicio</Text>
        </View>

        <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
          {/* Botón: Analizar nueva partida */}
          <TouchableOpacity style={styles.mainButton} onPress={() => router.push('/upload')}>
            <LinearGradient
              colors={['#007AFF', '#8E54E9']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.gradientButton}
            />
            <View style={styles.buttonContent}>
              <FontAwesome5 name="chess" size={45} color="white" />
              <Text style={styles.buttonText}>Analizar una nueva partida</Text>
            </View>
          </TouchableOpacity>

          {/* Botón: Consejos */}
          <TouchableOpacity 
            style={[styles.mainButton, styles.solidButton]} 
            onPress={() => router.push('/tips')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome name="exclamation-circle" size={45} color="white" />
              <Text style={styles.buttonText}>Consejos para la grabación de partidas</Text>
            </View>
          </TouchableOpacity>

          {/* Sección: Última partida */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Última partida analizada
            </Text>
            
            {lastGame ? (
              <TouchableOpacity 
                style={styles.lastGameCard}
                onPress={handlePlayVideo}
                activeOpacity={0.7}
              >
                {/* Miniatura del video */}
                <View style={styles.thumbnailContainer}>
                  <Image 
                    source={{ uri: lastGame.videoUri }}
                    // O si es local: source={require('../../../assets/images/video-thumbnail.jpg')}
                    style={styles.thumbnail}
                    resizeMode="cover"
                  />
                  {/* Overlay con botón de play */}
                  <View style={styles.playOverlay}>
                    <View style={styles.playButton}>
                      <Ionicons name="play" size={40} color="white" />
                    </View>
                  </View>
                </View>

                {/* Información del video */}
                <View style={styles.gameInfo}>
                  <View style={styles.infoRow}>
                    <Ionicons name="calendar-outline" size={20} color="#6b7280" />
                    <Text style={styles.infoText}>{lastGame.date}</Text>
                  </View>
                  <View style={styles.infoRow}>
                    <FontAwesome5 name="chess-knight" size={18} color="#6b7280" />
                    <Text style={styles.infoText}>{lastGame.moves} movimientos</Text>
                  </View>
                </View>

                {/* Indicador de tap para ver */}
                <View style={styles.tapIndicator}>
                  <Text style={styles.tapText}>Toca para ver el análisis</Text>
                  <Ionicons name="arrow-forward" size={16} color="#3b82f6" />
                </View>
              </TouchableOpacity>
            ) : (
              <View style={styles.emptyCard}>
                <Ionicons name="cloud-upload-outline" size={60} color="#9ca3af" />
                <Text style={styles.emptyText}>Aún no has subido ninguna partida</Text>
                <TouchableOpacity 
                  style={styles.emptyButton}
                  onPress={() => router.push('/upload')}
                >
                  <Text style={styles.emptyButtonText}>Subir primera partida</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>
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
    paddingHorizontal: 15,
  },
  menuButton: { 
    borderRightWidth: 1, 
    borderRightColor: 'rgba(255,255,255,0.3)', 
    paddingRight: 15, 
    marginRight: 15 
  },
  headerTitle: { 
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold' 
  },
  scrollView: {
    flex: 1,
    backgroundColor: '#F8F9FA',
  },
  content: { 
    alignItems: 'center', 
    gap: 20,
    paddingTop: 40,
    paddingBottom: 40,
  },
  mainButton: {
    width: '80%',
    height: 160,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
  },
  buttonContent: {
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  buttonText: { 
    color: '#fff', 
    fontSize: 22,
    fontWeight: '600',
    textAlign: 'center',
    paddingHorizontal: 10,
  },
  gradientButton: {
    position: 'absolute',
    width: '100%',
    height: '100%',
    borderRadius: 12,
  },
  solidButton: {
    backgroundColor: '#10b981',
  },

  // Sección última partida
  section: {
    width: '80%',
    marginTop: 10,
  },
  sectionTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 15,
  },
  lastGameCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    overflow: 'hidden',
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
  },

  // Miniatura del video
  thumbnailContainer: {
    position: 'relative',
    width: '100%',
    height: 200,
    backgroundColor: '#000',
  },
  thumbnail: {
    width: '100%',
    height: '100%',
  },
  playOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0,0,0,0.3)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  playButton: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: 'rgba(59, 130, 246, 0.9)',
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 5,
  },

  // Información del video
  gameInfo: {
    padding: 15,
    gap: 10,
  },
  infoRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  infoText: {
    fontSize: 16,
    color: '#4b5563',
    fontWeight: '500',
  },

  // Indicador de tap
  tapIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: '#eff6ff',
    gap: 8,
  },
  tapText: {
    fontSize: 15,
    fontWeight: '600',
    color: '#3b82f6',
  },

  // Estado vacío
  emptyCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 30,
    alignItems: 'center',
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
  },
  emptyText: {
    fontSize: 16,
    color: '#6b7280',
    textAlign: 'center',
    marginTop: 15,
    marginBottom: 20,
  },
  emptyButton: {
    backgroundColor: '#3b82f6',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  emptyButtonText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
});