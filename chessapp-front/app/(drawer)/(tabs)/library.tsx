import AsyncStorage from '@react-native-async-storage/async-storage';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useFocusEffect, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useCallback, useState } from 'react';
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

import VideoPreview from '@/components/VideoPreview';
import { deleteVideo, listVideos } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { useTheme } from '@/contexts/ThemeContext';

// ── Tarjeta individual de vídeo ──────────────────────────────────────────────
type VideoCardProps = {
  fileName: string;
  isAnalyzed: boolean;
  onDelete: () => void;
  onAnalyze: () => void;
};

function VideoCard({ fileName, isAnalyzed, onDelete, onAnalyze }: VideoCardProps) {
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  return (
    <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
      <VideoPreview fileName={fileName} style={styles.cardVideo} />
      <View style={styles.cardActions}>
        <TouchableOpacity
          style={[
            styles.analyzeBtn,
            isAnalyzed
              ? { backgroundColor: colors.primaryLight, borderColor: colors.primary }
              : { backgroundColor: isDarkMode ? '#2d1f0e' : '#fff7ed', borderColor: '#f97316' },
          ]}
          onPress={onAnalyze}
        >
          <Ionicons
            name={isAnalyzed ? 'bar-chart-outline' : 'play-circle-outline'}
            size={18}
            color={isAnalyzed ? colors.primary : '#f97316'}
          />
          <Text style={[styles.analyzeBtnText, { color: isAnalyzed ? colors.primary : '#f97316' }]}>
            {isAnalyzed ? t.library.viewAnalysis : t.library.performAnalysis}
          </Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.deleteBtn, { backgroundColor: isDarkMode ? '#3f1f1f' : '#fee2e2', borderColor: '#ef4444' }]}
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
  const t = useTranslation();

  const [videos, setVideos]                   = useState<string[]>([]);
  const [analyzedVideos, setAnalyzedVideos]   = useState<Record<string, string>>({});
  const [loading, setLoading]                 = useState(true);
  const [error, setError]                     = useState<string | null>(null);

  const fetchVideos = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [list, raw] = await Promise.all([
        listVideos(),
        AsyncStorage.getItem('analyzedVideos'),
      ]);
      setVideos(list);
      setAnalyzedVideos(raw ? JSON.parse(raw) as Record<string, string> : {});
    } catch {
      setError('loadError');
    } finally {
      setLoading(false);
    }
  }, []);

  // Refrescar cada vez que la pantalla se enfoca (ej: al volver del análisis)
  useFocusEffect(
    useCallback(() => {
      fetchVideos();
    }, [fetchVideos]),
  );

  const handleDelete = (fileName: string) => {
    Alert.alert(
      t.library.deleteVideo,
      t.library.deleteConfirm,
      [
        { text: t.library.cancel, style: 'cancel' },
        {
          text: t.library.delete,
          style: 'destructive',
          onPress: async () => {
            try {
              await deleteVideo(fileName);
              setVideos((prev) => prev.filter((v) => v !== fileName));
              // También eliminar del mapa de analizados
              setAnalyzedVideos((prev) => {
                const next = { ...prev };
                delete next[fileName];
                AsyncStorage.setItem('analyzedVideos', JSON.stringify(next)).catch(() => {});
                return next;
              });
            } catch {
              Alert.alert(t.library.error, t.library.deleteError);
            }
          },
        },
      ],
    );
  };

  const handleAnalyze = (fileName: string, isAnalyzed: boolean) => {
    if (isAnalyzed) {
      // Ir directo al análisis (cargará desde caché)
      router.push({ pathname: '/(drawer)/analysis', params: { file: fileName } });
    } else {
      // Ir a calibración obligatoria antes de analizar
      router.push({ pathname: '/(drawer)/(tabs)/upload', params: { preloaded: fileName } });
    }
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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.library.title}</Text>
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
              <Text style={[styles.errorText, { color: colors.text }]}>{t.library.loadError}</Text>
              <TouchableOpacity
                style={[styles.retryBtn, { backgroundColor: colors.buttonBg }]}
                onPress={fetchVideos}
              >
                <Text style={[styles.retryText, { color: colors.buttonText }]}>{t.library.retry}</Text>
              </TouchableOpacity>
            </View>
          ) : videos.length === 0 ? (
            <View style={styles.centered}>
              <Ionicons name="videocam-off-outline" size={64} color={colors.textSecondary} />
              <Text style={[styles.emptyText, { color: colors.text }]}>
                {t.library.noVideos}
              </Text>
              <TouchableOpacity
                style={[styles.retryBtn, { backgroundColor: colors.buttonBg }]}
                onPress={() => router.push('/(drawer)/(tabs)/upload')}
              >
                <Text style={[styles.retryText, { color: colors.buttonText }]}>{t.library.uploadVideo}</Text>
              </TouchableOpacity>
            </View>
          ) : (
            <>
              <Text style={[styles.counterText, { color: colors.text }]}>
                {videos.length} {videos.length === 1 ? t.library.video : t.library.videos}
              </Text>
              <FlatList
                data={videos}
                keyExtractor={(item) => item}
                renderItem={({ item }) => (
                  <VideoCard
                    fileName={item}
                    isAnalyzed={item in analyzedVideos}
                    onDelete={() => handleDelete(item)}
                    onAnalyze={() => handleAnalyze(item, item in analyzedVideos)}
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
  cardActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    padding: 12,
  },
  analyzeBtn: {
    flex: 1,
    height: 44,
    borderRadius: 10,
    borderWidth: 1.5,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  analyzeBtnText: {
    fontSize: 15,
    fontWeight: '700',
  },
  deleteBtn: {
    width: 44,
    height: 44,
    borderRadius: 10,
    borderWidth: 1.5,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
