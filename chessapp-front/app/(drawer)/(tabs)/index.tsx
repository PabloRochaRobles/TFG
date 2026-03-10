import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { FontAwesome, FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../../contexts/ThemeContext';

export default function HomeScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  // Datos de ejemplo (mock data) - Reemplazar con datos del backend
  const lastGame = {
    videoUri: 'https://via.placeholder.com/300x200',
    date: '15 Feb 2026',
    moves: 42,
    videoId: '12345',
  };

  const handlePlayVideo = () => {
    console.log('Reproducir video:', lastGame.videoId);
    router.push('/analysis');
  };

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity 
            style={[styles.menuButton, { borderRightColor: 'rgba(255,255,255,0.3)' }]}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.home.title}</Text>
        </View>

        <ScrollView style={[styles.scrollView, { backgroundColor: colors.background }]} contentContainerStyle={styles.content}>
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
              <Text style={styles.buttonText}>{t.home.analyzeNewGame}</Text>
            </View>
          </TouchableOpacity>

          {/* Botón: Consejos */}
          <TouchableOpacity 
            style={[styles.mainButton, styles.solidButton]} 
            onPress={() => router.push('/tips')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome name="exclamation-circle" size={45} color="white" />
              <Text style={styles.buttonText}>{t.home.recordingTips}</Text>
            </View>
          </TouchableOpacity>

          {/* Sección: Última partida */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>
              {t.home.lastGame}
            </Text>
            
            {lastGame ? (
              <TouchableOpacity 
                style={[styles.lastGameCard, { backgroundColor: colors.card }]}
                onPress={handlePlayVideo}
                activeOpacity={0.7}
              >
                {/* Miniatura del video */}
                <View style={styles.thumbnailContainer}>
                  <Image 
                    source={{ uri: lastGame.videoUri }}
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
                    <Ionicons name="calendar-outline" size={20} color={colors.textSecondary} />
                    <Text style={[styles.infoText, { color: colors.textSecondary }]}>{lastGame.date}</Text>
                  </View>
                  <View style={styles.infoRow}>
                    <FontAwesome5 name="chess-knight" size={18} color={colors.textSecondary} />
                    <Text style={[styles.infoText, { color: colors.textSecondary }]}>{lastGame.moves} {t.home.moves}</Text>
                  </View>
                </View>

                {/* Indicador de tap para ver */}
                <View style={[styles.tapIndicator, { backgroundColor: colors.primaryLight }]}>
                  <Text style={[styles.tapText, { color: colors.primary }]}>{t.home.tapToView}</Text>
                  <Ionicons name="arrow-forward" size={16} color={colors.primary} />
                </View>
              </TouchableOpacity>
            ) : (
              <View style={[styles.emptyCard, { backgroundColor: colors.card }]}>
                <Ionicons name="cloud-upload-outline" size={60} color={colors.textSecondary} />
                <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
                  {t.home.noGamesYet}
                </Text>
                <TouchableOpacity
                  style={[styles.emptyButton, { backgroundColor: colors.primary }]}
                  onPress={() => router.push('/upload')}
                >
                  <Text style={styles.emptyButtonText}>{t.home.uploadFirst}</Text>
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
  },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  menuButton: { 
    borderRightWidth: 1,
    paddingRight: 15, 
    marginRight: 15 
  },
  headerTitle: { 
    fontSize: 22, 
    fontWeight: 'bold' 
  },
  scrollView: {
    flex: 1,
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
    marginBottom: 15,
  },
  lastGameCard: {
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
    fontWeight: '500',
  },

  // Indicador de tap
  tapIndicator: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    gap: 8,
  },
  tapText: {
    fontSize: 15,
    fontWeight: '600',
  },

  // Estado vacío
  emptyCard: {
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
    textAlign: 'center',
    marginTop: 15,
    marginBottom: 20,
  },
  emptyButton: {
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