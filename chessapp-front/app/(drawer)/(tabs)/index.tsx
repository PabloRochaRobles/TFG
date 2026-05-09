import AsyncStorage from '@react-native-async-storage/async-storage';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { API_BASE_URL, listVideos } from '@/constants/api';
import { FontAwesome, FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useFocusEffect, useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { tokenStore } from '../../lib/tokenStorage';
import { useTheme } from '../../contexts/ThemeContext';

const LAST_GAME_KEY = 'lastGame';

type LastGameData = {
  file: string;
  analysisId: string;
  moves: number;
  date: string;
};

// ── Tarjeta de la última partida ─────────────────────────────────────────────
// Componente separado para poder usar el hook useVideoPlayer sin condiciones.
type LastGameCardProps = {
  game: LastGameData;
  isAnalyzed: boolean;
  onPress: () => void;
};

function LastGameCard({ game, isAnalyzed, onPress }: LastGameCardProps) {
  const colors = useThemeColors();
  const t = useTranslation();

  // El stream del vídeo requiere JWT en el backend; expo-video acepta
  // headers en la fuente, así que añadimos Authorization manualmente.
  const access = tokenStore.getAccess();
  const player = useVideoPlayer(
    {
      uri: `${API_BASE_URL}/api/partidas/stream/${game.file}/`,
      headers: {
        'ngrok-skip-browser-warning': 'true',
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
    },
    (p) => { p.loop = false; },
  );

  return (
    <View style={[styles.gameCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
      {/* Miniatura de vídeo */}
      <VideoView
        player={player}
        style={styles.gameVideo}
        allowsFullscreen
        allowsPictureInPicture={false}
      />

      {/* Badge de estado + metadatos */}
      <View style={styles.cardMeta}>
        <View style={[styles.badge, { backgroundColor: isAnalyzed ? '#dcfce7' : '#fef9c3' }]}>
          <Text style={[styles.badgeText, { color: isAnalyzed ? '#16a34a' : '#a16207' }]}>
            {isAnalyzed ? t.home.analyzed : t.home.notAnalyzed}
          </Text>
        </View>
        {isAnalyzed && (
          <>
            {game.date ? (
              <View style={styles.metaItem}>
                <Ionicons name="calendar-outline" size={13} color={colors.textSecondary} />
                <Text style={[styles.metaText, { color: colors.textSecondary }]}>{game.date}</Text>
              </View>
            ) : null}
            <View style={styles.metaItem}>
              <Ionicons name="git-branch-outline" size={13} color={colors.textSecondary} />
              <Text style={[styles.metaText, { color: colors.textSecondary }]}>
                {game.moves} {t.home.moves}
              </Text>
            </View>
          </>
        )}
      </View>

      {/* Botón de acción */}
      <TouchableOpacity
        style={[styles.actionBtn, { backgroundColor: isAnalyzed ? colors.primary : '#f97316' }]}
        onPress={onPress}
      >
        <Ionicons
          name={isAnalyzed ? 'bar-chart-outline' : 'play-outline'}
          size={18}
          color="white"
          style={{ marginRight: 6 }}
        />
        <Text style={styles.actionBtnText}>
          {isAnalyzed ? t.home.viewAnalysis : t.home.analyze}
        </Text>
      </TouchableOpacity>
    </View>
  );
}

// ── Pantalla de inicio ────────────────────────────────────────────────────────
export default function HomeScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  const [latestVideo, setLatestVideo] = useState<string | null>(null);
  const [lastGame, setLastGame]       = useState<LastGameData | null>(null);
  const [loadingCard, setLoadingCard] = useState(true);

  useFocusEffect(
    useCallback(() => {
      let active = true;
      setLoadingCard(true);
      Promise.all([
        listVideos().catch(() => [] as string[]),
        AsyncStorage.getItem(LAST_GAME_KEY)
          .then((v) => (v ? (JSON.parse(v) as LastGameData) : null))
          .catch(() => null),
      ]).then(([videos, game]) => {
        if (!active) return;
        setLatestVideo(videos.length > 0 ? videos[0] : null);
        setLastGame(game);
        setLoadingCard(false);
      });
      return () => { active = false; };
    }, []),
  );

  const isAnalyzed = !!(latestVideo && lastGame && lastGame.file === latestVideo);
  const displayGame: LastGameData | null = isAnalyzed
    ? lastGame
    : latestVideo
      ? { file: latestVideo, analysisId: '', moves: 0, date: '' }
      : null;

  const handleGameAction = () => {
    if (!displayGame) return;
    router.push({ pathname: '/(drawer)/analysis', params: { file: displayGame.file } });
  };

  return (
    <>
      <StatusBar style={isDarkMode ? 'light' : 'dark'} />
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

        <ScrollView
          style={[styles.scrollView, { backgroundColor: colors.background }]}
          contentContainerStyle={styles.content}
        >
          {/* Botón: Analizar nueva partida */}
          <TouchableOpacity
            style={[styles.mainButton, { backgroundColor: '#007AFF' }]}
            onPress={() => router.push('/upload')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome5 name="chess" size={45} color="white" />
              <Text style={styles.buttonText}>{t.home.analyzeNewGame}</Text>
            </View>
          </TouchableOpacity>

          {/* Botón: Consejos para la grabación */}
          <TouchableOpacity
            style={[styles.mainButton, styles.solidButton]}
            onPress={() => router.push('/tips')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome name="exclamation-circle" size={45} color="white" />
              <Text style={styles.buttonText}>{t.home.recordingTips}</Text>
            </View>
          </TouchableOpacity>

          {/* ── Última partida ── */}
          <View style={styles.sectionHeader}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>{t.home.lastGame}</Text>
          </View>

          {loadingCard ? (
            <View style={[styles.loadingCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : displayGame ? (
            <LastGameCard
              game={displayGame}
              isAnalyzed={isAnalyzed}
              onPress={handleGameAction}
            />
          ) : (
            <View style={[styles.emptyCard, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <FontAwesome5 name="chess-board" size={32} color={colors.textSecondary} />
              <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
                {t.home.noGamesYet}
              </Text>
            </View>
          )}
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  container:  { flex: 1 },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  menuButton: {
    borderRightWidth: 1,
    paddingRight: 15,
    marginRight: 15,
  },
  headerTitle: { fontSize: 22, fontWeight: 'bold' },
  scrollView:  { flex: 1 },
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
  solidButton: { backgroundColor: '#3cb18a' },

  // ── Sección última partida ──
  sectionHeader: {
    width: '80%',
    alignItems: 'flex-start',
    marginBottom: -8,
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
  },
  gameCard: {
    width: '80%',
    borderRadius: 16,
    borderWidth: 1,
    overflow: 'hidden',
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.12,
    shadowRadius: 3,
  },
  gameVideo: {
    width: '100%',
    aspectRatio: 16 / 9,
  },
  cardMeta: {
    flexDirection: 'row',
    alignItems: 'center',
    flexWrap: 'wrap',
    gap: 10,
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 4,
  },
  badge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 99,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: '700',
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  metaText: {
    fontSize: 12,
  },
  actionBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    margin: 12,
    marginTop: 8,
    borderRadius: 10,
    paddingVertical: 11,
  },
  actionBtnText: {
    color: 'white',
    fontWeight: '700',
    fontSize: 15,
  },
  loadingCard: {
    width: '80%',
    height: 80,
    borderRadius: 16,
    borderWidth: 1,
    alignItems: 'center',
    justifyContent: 'center',
  },
  emptyCard: {
    width: '80%',
    borderRadius: 16,
    borderWidth: 1,
    alignItems: 'center',
    paddingVertical: 28,
    gap: 10,
  },
  emptyText: {
    fontSize: 14,
    textAlign: 'center',
    paddingHorizontal: 16,
  },
});
