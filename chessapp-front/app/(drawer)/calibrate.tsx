import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { Ionicons } from '@expo/vector-icons';
import { router, useLocalSearchParams } from 'expo-router';
import { useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Dimensions,
  Image,
  LayoutChangeEvent,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
// ActivityIndicator and Alert kept for the video-list loading path
import { SafeAreaView } from 'react-native-safe-area-context';
import { getFirstFrameUrl, listVideos } from '../../constants/api';

const CORNER_ORDER = [
  { key: 'TL', square: 'a1', label: 'Superior-Izq  (a1)', color: '#22c55e' },
  { key: 'TR', square: 'a8', label: 'Superior-Der  (a8)', color: '#f97316' },
  { key: 'BR', square: 'h8', label: 'Inferior-Der  (h8)', color: '#ef4444' },
  { key: 'BL', square: 'h1', label: 'Inferior-Izq  (h1)', color: '#3b82f6' },
];

type Corner = [number, number]; // relative [0-1]

export default function CalibrateScreen() {
  const colors = useThemeColors();
  const t = useTranslation();
  const { file: fileParam } = useLocalSearchParams<{ file?: string }>();

  const [videos, setVideos] = useState<string[]>([]);
  const [loadingVideos, setLoadingVideos] = useState(false);
  const [selectedVideo, setSelectedVideo] = useState<string | null>(fileParam ?? null);
  const [corners, setCorners] = useState<Corner[]>([]);
  const [rotation, setRotation] = useState(0);

  const imageRef = useRef<View>(null);
  const [imageLayout, setImageLayout] = useState({ x: 0, y: 0, width: 1, height: 1 });

  const screenWidth = Dimensions.get('window').width - 32;

  const loadVideos = async () => {
    setLoadingVideos(true);
    try {
      const list = await listVideos();
      setVideos(list);
    } catch {
      Alert.alert('Error', 'No se pudieron cargar los vídeos');
    } finally {
      setLoadingVideos(false);
    }
  };

  // Load video list when user first opens the screen
  useState(() => { loadVideos(); });

  const selectVideo = (fileName: string) => {
    setSelectedVideo(fileName);
    setCorners([]);
  };

  const handleImageLayout = (e: LayoutChangeEvent) => {
    const { x, y, width, height } = e.nativeEvent.layout;
    setImageLayout({ x, y, width, height });
  };

  const handleImageTouch = (e: any) => {
    if (corners.length >= 4) return;
    const { locationX, locationY } = e.nativeEvent;
    const W = imageLayout.width;
    const H = imageLayout.height;

    let rx: number, ry: number;
    if (rotation === 0) {
      rx = Math.max(0, Math.min(1, locationX / W));
      ry = Math.max(0, Math.min(1, locationY / H));
    } else {
      // El imageContainer está rotado θ° (sentido horario).
      // locationX/locationY están en el espacio sin rotar del TouchableOpacity.
      // Aplicamos la rotación inversa para obtener las coordenadas originales de la imagen.
      const θ = (rotation * Math.PI) / 180;
      const dx = locationX - W / 2;
      const dy = locationY - H / 2;
      const origX = W / 2 + dx * Math.cos(θ) + dy * Math.sin(θ);
      const origY = H / 2 - dx * Math.sin(θ) + dy * Math.cos(θ);
      rx = Math.max(0, Math.min(1, origX / W));
      ry = Math.max(0, Math.min(1, origY / H));
    }
    setCorners(prev => [...prev, [rx, ry]]);
  };

  const rotateBy = (delta: number) => {
    setRotation(prev => ((prev + delta) % 360 + 360) % 360);
  };

  const handleConfirm = () => {
    if (corners.length !== 4 || !selectedVideo) return;
    router.replace({
      pathname: '/(drawer)/analysis',
      params: {
        file: fileParam ?? selectedVideo,
        corners: JSON.stringify(corners),
      },
    });
  };

  const frameUri = selectedVideo
    ? getFirstFrameUrl(selectedVideo)
    : null;

  const nextCorner = corners.length < 4 ? CORNER_ORDER[corners.length] : null;

  return (
    <SafeAreaView style={[styles.safe, { backgroundColor: colors.background }]}>
      {/* Header */}
      <View style={[styles.header, { borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => router.back()} style={styles.backBtn}>
          <Ionicons name="arrow-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>
          {t.calibrate.title}
        </Text>
        <View style={{ width: 40 }} />
      </View>

      <ScrollView contentContainerStyle={styles.content}>
        {/* Instructions */}
        <View style={[styles.infoBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
          <Text style={[styles.infoText, { color: colors.textSecondary }]}>
            {t.calibrate.instructions}
          </Text>
        </View>

        {/* Video list — hidden when a specific file was passed as param */}
        {!fileParam && (
          <>
            <Text style={[styles.sectionLabel, { color: colors.text }]}>
              {t.calibrate.selectVideo}
            </Text>

            {loadingVideos ? (
              <ActivityIndicator color={colors.primary} style={{ marginVertical: 12 }} />
            ) : videos.length === 0 ? (
              <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
                {t.calibrate.noVideos}
              </Text>
            ) : (
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.videoRow}>
                {videos.map(v => (
                  <TouchableOpacity
                    key={v}
                    style={[
                      styles.videoChip,
                      { borderColor: selectedVideo === v ? colors.primary : colors.border,
                        backgroundColor: selectedVideo === v ? colors.primaryLight : colors.card },
                    ]}
                    onPress={() => selectVideo(v)}
                  >
                    <Text
                      style={[styles.videoChipText,
                        { color: selectedVideo === v ? colors.primary : colors.text }]}
                      numberOfLines={1}
                    >
                      {v}
                    </Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            )}
          </>
        )}

        {/* Frame image + corner selection */}
        {frameUri && (
          <View style={styles.imageSection}>
            {/* Corner step indicator */}
            <View style={styles.stepsRow}>
              {CORNER_ORDER.map((c, idx) => (
                <View key={c.key} style={styles.stepItem}>
                  <View style={[
                    styles.stepDot,
                    { backgroundColor: idx < corners.length ? c.color : colors.border,
                      borderColor: idx === corners.length ? c.color : 'transparent' },
                  ]}>
                    {idx < corners.length && (
                      <Ionicons name="checkmark" size={12} color="#fff" />
                    )}
                  </View>
                  <Text style={[styles.stepLabel, { color: idx === corners.length ? c.color : colors.textSecondary }]}>
                    {c.square}
                  </Text>
                </View>
              ))}
            </View>

            {nextCorner && (
              <Text style={[styles.nextHint, { color: nextCorner.color }]}>
                {t.calibrate.tapCorner} {nextCorner.label}
              </Text>
            )}
            {corners.length === 4 && (
              <Text style={[styles.nextHint, { color: colors.primary }]}>
                {t.calibrate.allSelected}
              </Text>
            )}

            {/* Rotation control */}
            <View style={styles.rotationRow}>
              <Text style={[styles.rotationLabel, { color: colors.textSecondary }]}>
                {t.calibrate.rotationLabel}
              </Text>
              <View style={styles.rotationControls}>
                <TouchableOpacity
                  style={[styles.rotBtn, { borderColor: colors.border }]}
                  onPress={() => rotateBy(-5)}
                >
                  <Ionicons name="remove" size={12} color={colors.text} />
                  <Text style={[styles.rotBtnText, { color: colors.text }]}>5°</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.rotBtn, { borderColor: colors.border }]}
                  onPress={() => rotateBy(-1)}
                >
                  <Ionicons name="remove" size={12} color={colors.text} />
                  <Text style={[styles.rotBtnText, { color: colors.text }]}>1°</Text>
                </TouchableOpacity>
                <View style={[styles.rotDisplay, { borderColor: colors.border, backgroundColor: colors.card }]}>
                  <Text style={[styles.rotDisplayText, { color: colors.text }]}>
                    {rotation}°
                  </Text>
                </View>
                <TouchableOpacity
                  style={[styles.rotBtn, { borderColor: colors.border }]}
                  onPress={() => rotateBy(1)}
                >
                  <Ionicons name="add" size={12} color={colors.text} />
                  <Text style={[styles.rotBtnText, { color: colors.text }]}>1°</Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[styles.rotBtn, { borderColor: colors.border }]}
                  onPress={() => rotateBy(5)}
                >
                  <Ionicons name="add" size={12} color={colors.text} />
                  <Text style={[styles.rotBtnText, { color: colors.text }]}>5°</Text>
                </TouchableOpacity>
                {rotation !== 0 && (
                  <TouchableOpacity
                    style={[styles.rotBtn, { borderColor: colors.primary }]}
                    onPress={() => setRotation(0)}
                  >
                    <Ionicons name="refresh" size={14} color={colors.primary} />
                  </TouchableOpacity>
                )}
              </View>
            </View>

            {/* Touchable image */}
            <TouchableOpacity
              activeOpacity={1}
              onPress={handleImageTouch}
              style={styles.imageWrapper}
            >
              <View
                ref={imageRef}
                onLayout={handleImageLayout}
                style={[styles.imageContainer, rotation !== 0 && { transform: [{ rotate: `${rotation}deg` }] }]}
              >
                <Image
                  source={{
                    uri: frameUri,
                    headers: { 'ngrok-skip-browser-warning': 'true' },
                  }}
                  style={{ width: screenWidth, height: screenWidth * 0.65 }}
                  resizeMode="contain"
                />
                {/* Corner markers */}
                {corners.map(([rx, ry], idx) => {
                  const c = CORNER_ORDER[idx];
                  const left = rx * imageLayout.width - 14;
                  const top  = ry * imageLayout.height - 14;
                  return (
                    <View
                      key={idx}
                      style={[styles.marker, { left, top, borderColor: c.color, backgroundColor: c.color + '33' }]}
                    >
                      <Text style={[styles.markerText, { color: c.color }]}>{idx + 1}</Text>
                    </View>
                  );
                })}
              </View>
            </TouchableOpacity>

            {/* Action buttons */}
            <View style={styles.actions}>
              {corners.length > 0 && (
                <TouchableOpacity
                  style={[styles.btnSecondary, { borderColor: colors.border }]}
                  onPress={() => setCorners(c => c.slice(0, -1))}
                >
                  <Ionicons name="arrow-undo" size={18} color={colors.text} />
                  <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                    {t.calibrate.undo}
                  </Text>
                </TouchableOpacity>
              )}
              {corners.length > 0 && (
                <TouchableOpacity
                  style={[styles.btnSecondary, { borderColor: colors.border }]}
                  onPress={() => setCorners([])}
                >
                  <Ionicons name="refresh" size={18} color={colors.text} />
                  <Text style={[styles.btnSecondaryText, { color: colors.text }]}>
                    {t.calibrate.reset}
                  </Text>
                </TouchableOpacity>
              )}
            </View>

            {corners.length === 4 && (
              <TouchableOpacity
                style={[styles.btnPrimary, { backgroundColor: colors.primary }]}
                onPress={handleConfirm}
              >
                <Ionicons name="arrow-forward-circle" size={20} color="#fff" />
                <Text style={styles.btnPrimaryText}>{t.calibrate.save}</Text>
              </TouchableOpacity>
            )}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe:         { flex: 1 },
  header:       { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
                  paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1 },
  backBtn:      { width: 40, alignItems: 'flex-start' },
  headerTitle:  { fontSize: 18, fontWeight: '600' },
  content:      { padding: 16, gap: 16 },
  infoBox:      { borderRadius: 10, borderWidth: 1, padding: 14 },
  infoText:     { fontSize: 13, lineHeight: 20 },
  sectionLabel: { fontSize: 15, fontWeight: '600' },
  emptyText:    { fontSize: 14, fontStyle: 'italic' },
  videoRow:     { flexDirection: 'row' },
  videoChip:    { borderWidth: 1.5, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 8,
                  marginRight: 8, maxWidth: 200 },
  videoChipText:{ fontSize: 13, fontWeight: '500' },
  imageSection: { gap: 12 },
  stepsRow:     { flexDirection: 'row', justifyContent: 'space-around' },
  stepItem:     { alignItems: 'center', gap: 4 },
  stepDot:      { width: 26, height: 26, borderRadius: 13, borderWidth: 2,
                  alignItems: 'center', justifyContent: 'center' },
  stepLabel:    { fontSize: 12, fontWeight: '600' },
  nextHint:     { fontSize: 14, fontWeight: '600', textAlign: 'center' },
  rotationRow:      { gap: 6 },
  rotationLabel:    { fontSize: 13, fontWeight: '500' },
  rotationControls: { flexDirection: 'row', alignItems: 'center', gap: 6, flexWrap: 'wrap' },
  rotBtn:           { flexDirection: 'row', alignItems: 'center', gap: 2, borderWidth: 1,
                      borderRadius: 6, paddingHorizontal: 10, paddingVertical: 6 },
  rotBtnText:       { fontSize: 12, fontWeight: '500' },
  rotDisplay:       { borderWidth: 1, borderRadius: 6, paddingHorizontal: 12, paddingVertical: 6,
                      minWidth: 52, alignItems: 'center' },
  rotDisplayText:   { fontSize: 13, fontWeight: '700', fontVariant: ['tabular-nums'] },
  imageWrapper: { overflow: 'visible' },
  imageContainer: { position: 'relative' },
  marker:       { position: 'absolute', width: 28, height: 28, borderRadius: 14, borderWidth: 2,
                  alignItems: 'center', justifyContent: 'center' },
  markerText:   { fontSize: 12, fontWeight: '800' },
  actions:      { flexDirection: 'row', gap: 10 },
  btnSecondary: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1,
                  borderRadius: 8, paddingHorizontal: 14, paddingVertical: 10 },
  btnSecondaryText: { fontSize: 14 },
  btnPrimary:   { flexDirection: 'row', alignItems: 'center', justifyContent: 'center',
                  gap: 8, borderRadius: 10, paddingVertical: 14 },
  btnPrimaryText: { color: '#fff', fontSize: 16, fontWeight: '600' },
});
