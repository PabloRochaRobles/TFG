import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { API_BASE_URL, deleteVideo, listVideos } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTheme } from '../../contexts/ThemeContext';

// ── Tarjeta individual de vídeo ──────────────────────────────────────────────
type VideoCardProps = {
  fileName: string;
  onDelete: () => void;
  onAnalyze: () => void;
};

function VideoCard({ fileName, onDelete, onAnalyze }: VideoCardProps) {
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

  const player = useVideoPlayer(
    {
      uri: `${API_BASE_URL}/api/partidas/stream/${fileName}/`,
      headers: { 'ngrok-skip-browser-warning': 'true' },
    },
    (p) => { p.loop = false; },
  );

  return (
    <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <VideoView
        player={player}
        style={styles.cardVideo}
        allowsFullscreen
        allowsPictureInPicture={false}
      />
      <Text
        style={[styles.cardName, { color: colors.textSecondary }]}
        numberOfLines={1}
      >
        {fileName}
      </Text>
      <View style={styles.cardActions}>
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}
          onPress={onAnalyze}
        >
          <Ionicons name="search" size={22} color={colors.primary} />
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.actionBtn, { backgroundColor: isDarkMode ? '#3f1f1f' : '#fee2e2', borderColor: '#ef4444' }]}
          onPress={onDelete}
        >
          <Ionicons name="trash-outline" size={22} color="#ef4444" />
        </TouchableOpacity>
      </View>
    </View>
  );
}

// ── Pantalla de librería ─────────────────────────────────────────────────────
export default function LibraryScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

  const [videos, setVideos] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const list = await listVideos();
      setVideos(list);
    } catch {
      setError('No se pudo cargar la librería');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVideos();
  }, [fetchVideos]);

  const handleDelete = (fileName: string) => {
    Alert.alert(
      'Eliminar vídeo',
      `¿Seguro que quieres eliminar este vídeo?`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'Eliminar',
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteVideo(fileName);
              setVideos((prev) => prev.filter((v) => v !== fileName));
            } catch {
              Alert.alert('Error', 'No se pudo eliminar el vídeo');
            }
          },
        },
      ],
    );
  };

  const handleAnalyze = (fileName: string) => {
    router.push({ pathname: '/(drawer)/analysis', params: { file: fileName } });
  };

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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Librería</Text>
          <TouchableOpacity style={styles.refreshButton} onPress={fetchVideos}>
            <Ionicons name="refresh" size={24} color={colors.headerText} />
          </TouchableOpacity>
        </View>

        <View style={[styles.content, { backgroundColor: colors.background }]}>

          {loading ? (
            <View style={styles.centered}>
              <ActivityIndicator size="large" color={colors.primary} />
            </View>
          ) : error ? (
            <View style={styles.centered}>
              <Text style={[styles.errorText, { color: colors.text }]}>{error}</Text>
              <TouchableOpacity
                style={[styles.retryBtn, { backgroundColor: colors.buttonBg }]}
                onPress={fetchVideos}
              >
                <Text style={[styles.retryText, { color: colors.buttonText }]}>Reintentar</Text>
              </TouchableOpacity>
            </View>
          ) : videos.length === 0 ? (
            <View style={styles.centered}>
              <Ionicons name="videocam-off-outline" size={64} color={colors.textSecondary} />
              <Text style={[styles.emptyText, { color: colors.text }]}>
                No se ha subido ningún{'\n'}vídeo aún
              </Text>
              <TouchableOpacity
                style={[styles.retryBtn, { backgroundColor: colors.buttonBg }]}
                onPress={() => router.push('/(drawer)/(tabs)/upload')}
              >
                <Text style={[styles.retryText, { color: colors.buttonText }]}>Subir vídeo</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <Text style={[styles.counterText, { color: colors.text }]}>
                {videos.length} {videos.length === 1 ? 'vídeo' : 'vídeos'}
              </Text>
              <FlatList
                data={videos}
                keyExtractor={(item) => item}
                renderItem={({ item }) => (
                  <VideoCard
                    fileName={item}
                    onDelete={() => handleDelete(item)}
                    onAnalyze={() => handleAnalyze(item)}
                  />
                )}
                contentContainerStyle={styles.list}
                showsVerticalScrollIndicator={false}
              />
            </>
          )}

        </View>
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
  headerTitle: { flex: 1, fontSize: 22, fontWeight: 'bold' },
  refreshButton: { padding: 4 },
  content: { flex: 1 },
  centered: {
    flex: 1,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 20,
    padding: 30,
  },
  emptyText: {
    fontSize: 20,
    fontWeight: 'bold',
    textAlign: 'center',
    lineHeight: 30,
  },
  errorText: {
    fontSize: 16,
    textAlign: 'center',
  },
  retryBtn: {
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 12,
  },
  retryText: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  counterText: {
    fontSize: 16,
    fontWeight: '600',
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 8,
  },
  list: {
    paddingHorizontal: 16,
    paddingBottom: 20,
    gap: 16,
  },
  // VideoCard
  card: {
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
  },
  cardVideo: {
    width: '100%',
    aspectRatio: 16 / 9,
  },
  cardName: {
    fontSize: 12,
    paddingHorizontal: 12,
    paddingTop: 8,
    paddingBottom: 4,
  },
  cardActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    padding: 12,
  },
  actionBtn: {
    width: 44,
    height: 44,
    borderRadius: 22,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
