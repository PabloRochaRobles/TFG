import { Ionicons } from '@expo/vector-icons';
import { useVideoPlayer, VideoView } from 'expo-video';
import React, { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  StyleProp,
  StyleSheet,
  TouchableOpacity,
  View,
  ViewStyle,
} from 'react-native';

import { API_BASE_URL, getFirstFrameUrl } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { tokenStore } from '@/lib/tokenStorage';

type VideoPreviewProps = {
  fileName: string;
  style?: StyleProp<ViewStyle>;
};

function StreamPlayer({ fileName, style }: VideoPreviewProps) {
  const access = tokenStore.getAccess();
  const player = useVideoPlayer(
    {
      uri: `${API_BASE_URL}/api/partidas/stream/${fileName}/`,
      headers: {
        'ngrok-skip-browser-warning': 'true',
        ...(access ? { Authorization: `Bearer ${access}` } : {}),
      },
    },
    (p) => { p.loop = false; },
  );

  return (
    <VideoView
      player={player}
      style={style}
      fullscreenOptions={{ enable: true }}
      allowsPictureInPicture={false}
    />
  );
}

export default function VideoPreview({ fileName, style }: VideoPreviewProps) {
  const colors = useThemeColors();
  const [thumbnail, setThumbnail] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [showPlayer, setShowPlayer] = useState(false);

  useEffect(() => {
    let active = true;
    setThumbnail(null);
    setLoading(true);
    setShowPlayer(false);

    getFirstFrameUrl(fileName)
      .then((uri) => {
        if (active) setThumbnail(uri);
      })
      .catch(() => {
        if (active) setThumbnail(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => { active = false; };
  }, [fileName]);

  if (showPlayer) {
    return <StreamPlayer fileName={fileName} style={style} />;
  }

  return (
    <TouchableOpacity
      style={[styles.preview, style, { backgroundColor: colors.card }]}
      activeOpacity={0.85}
      onPress={() => setShowPlayer(true)}
    >
      {thumbnail ? (
        <Image source={{ uri: thumbnail }} style={StyleSheet.absoluteFill} resizeMode="cover" />
      ) : (
        <View style={styles.fallback}>
          {loading ? (
            <ActivityIndicator color={colors.primary} />
          ) : (
            <Ionicons name="videocam-outline" size={30} color={colors.textSecondary} />
          )}
        </View>
      )}
      {!loading && (
        <View style={styles.playBadge}>
          <Ionicons name="play" size={20} color="#fff" />
        </View>
      )}
    </TouchableOpacity>
  );
}

const styles = StyleSheet.create({
  preview: {
    position: 'relative',
    overflow: 'hidden',
    alignItems: 'center',
    justifyContent: 'center',
  },
  fallback: {
    ...StyleSheet.absoluteFillObject,
    alignItems: 'center',
    justifyContent: 'center',
  },
  playBadge: {
    width: 46,
    height: 46,
    borderRadius: 23,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: 'rgba(0,0,0,0.58)',
  },
});
