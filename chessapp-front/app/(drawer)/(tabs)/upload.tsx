import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { uploadVideo } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTheme } from '../../contexts/ThemeContext';

type Phase = 'idle' | 'uploading' | 'uploaded' | 'error';

export default function UploadScreen() {
  const [videoUri, setVideoUri] = useState<string | null>(null);
  const [videoFileName, setVideoFileName] = useState<string | null>(null);
  const [savedFileName, setSavedFileName] = useState<string | null>(null);
  const [phase, setPhase] = useState<Phase>('idle');
  const navigation = useNavigation();
  const router = useRouter();

  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

  const player = useVideoPlayer('', (p) => { p.loop = true; });

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
      Alert.alert('Permiso denegado', 'Se necesitan permisos para acceder a la galería');
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
    }
  };

  const handleUpload = async () => {
    if (!videoUri || !videoFileName) return;

    try {
      setPhase('uploading');
      const uploadResult = await uploadVideo(videoUri, videoFileName);
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
  };

  const isLoading = phase === 'uploading';

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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Subir Video</Text>
        </View>

        <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}>

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
                Toca para seleccionar un vídeo
              </Text>
            </TouchableOpacity>
          )}

          {/* Estado de carga */}
          {isLoading && (
            <View style={styles.loadingContainer}>
              <ActivityIndicator size="large" color={colors.primary} />
              <Text style={[styles.loadingText, { color: colors.text }]}>Subiendo video...</Text>
            </View>
          )}

          {/* Botones de acción */}
          {videoUri && !isLoading && (
            <View style={styles.buttonRow}>
              <TouchableOpacity
                style={[styles.cancelButton, { borderColor: colors.border }]}
                onPress={handleReset}
              >
                <Text style={[styles.cancelButtonText, { color: colors.text }]}>Cancelar</Text>
              </TouchableOpacity>
              {phase === 'uploaded' ? (
                <TouchableOpacity
                  style={[styles.analyzeButton, { backgroundColor: '#27ae60' }]}
                  onPress={() => router.push({ pathname: '/(drawer)/analysis', params: { file: savedFileName } })}
                >
                  <Text style={[styles.analyzeButtonText, { color: '#fff' }]}>Analizar partida</Text>
                </TouchableOpacity>
              ) : (
                <TouchableOpacity
                  style={[styles.analyzeButton, { backgroundColor: colors.buttonBg }]}
                  onPress={handleUpload}
                >
                  <Text style={[styles.analyzeButtonText, { color: colors.buttonText }]}>Subir video</Text>
                </TouchableOpacity>
              )}
            </View>
          )}

          {/* Pasos / Instrucciones */}
          {(
            <View style={styles.stepsContainer}>
              <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                <Text style={[styles.stepTitle, { color: colors.text }]}>Paso 1:</Text>
                <Text style={[styles.stepDescription, { color: colors.text }]}>Selecciona tu partida de ajedrez.</Text>
              </View>
              <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                <Text style={[styles.stepTitle, { color: colors.text }]}>Paso 2:</Text>
                <Text style={[styles.stepDescription, { color: colors.text }]}>Pulsa el botón de subir vídeo.</Text>
              </View>
              <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
                <Text style={[styles.stepTitle, { color: colors.text }]}>Paso 3:</Text>
                <Text style={[styles.stepDescription, { color: colors.text }]}>Pulsa el botón de analizar.</Text>
              </View>
            </View>
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
  loadingContainer: {
    alignItems: 'center',
    gap: 10,
    marginBottom: 20,
  },
  loadingText: {
    fontSize: 16,
  },
  resultBox: {
    borderRadius: 15,
    borderWidth: 1,
    padding: 20,
    alignItems: 'center',
    gap: 8,
    marginBottom: 20,
  },
  resultTitle: {
    fontSize: 18,
    fontWeight: 'bold',
  },
  resultDetail: {
    fontSize: 14,
  },
  resetButton: {
    marginTop: 10,
    borderWidth: 1,
    borderRadius: 10,
    paddingHorizontal: 20,
    paddingVertical: 8,
  },
  buttonRow: {
    flexDirection: 'row',
    gap: 12,
    marginBottom: 20,
  },
  cancelButton: {
    flex: 1,
    paddingVertical: 15,
    borderRadius: 15,
    alignItems: 'center',
    borderWidth: 1,
  },
  cancelButtonText: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  analyzeButton: {
    flex: 1,
    paddingVertical: 15,
    borderRadius: 15,
    alignItems: 'center',
  },
  analyzeButtonText: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  stepsContainer: {
    width: '100%',
    gap: 15,
    paddingBottom: 20,
  },
  stepBox: {
    width: '100%',
    borderRadius: 15,
    borderWidth: 1,
    padding: 15,
  },
  stepTitle: { fontSize: 16, fontWeight: 'bold' },
  stepDescription: { fontSize: 16 },
  playerContainer: {
    width: '100%',
    marginBottom: 20,
    gap: 10,
  },
  player: {
    width: '100%',
    aspectRatio: 16 / 9,
    borderRadius: 15,
    overflow: 'hidden',
  },
});
