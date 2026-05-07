import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { CameraView, useCameraPermissions } from 'expo-camera';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useRef, useState } from 'react';
import { ActivityIndicator, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

export default function CameraScreen() {
  const t = useTranslation();
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();

  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const [isRecording, setIsRecording] = useState(false);

  if (!permission) {
    return (
      <View style={[styles.permissionContainer, { backgroundColor: colors.background }]}>
        <ActivityIndicator color={colors.primary} />
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={[styles.permissionContainer, { backgroundColor: colors.background }]}>
        <Ionicons name="videocam-off-outline" size={64} color={colors.textSecondary} />
        <Text style={[styles.permissionText, { color: colors.text }]}>
          {t.camera.permissionText}
        </Text>
        <TouchableOpacity
          style={[styles.permissionButton, { backgroundColor: colors.buttonBg }]}
          onPress={requestPermission}
        >
          <Text style={[styles.permissionButtonText, { color: colors.buttonText }]}>
            {t.camera.grantPermissions}
          </Text>
        </TouchableOpacity>
      </View>
    );
  }

  const handleToggleRecord = async () => {
    if (!cameraRef.current) return;

    if (isRecording) {
      cameraRef.current.stopRecording();
      return;
    }

    setIsRecording(true);
    try {
      const video = await cameraRef.current.recordAsync();
      if (video?.uri) {
        router.push({
          pathname: '/(drawer)/(tabs)/upload',
          params: { cameraUri: video.uri },
        });
      }
    } finally {
      setIsRecording(false);
    }
  };

  return (
    <>
      <StatusBar style="light" />
      <View style={styles.container}>
        <CameraView style={StyleSheet.absoluteFill} ref={cameraRef} mode="video" />

        <View style={styles.header}>
          <TouchableOpacity
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color="#fff" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t.camera.title}</Text>
        </View>

        <View style={styles.controls}>
          {isRecording && <Text style={styles.recordingLabel}>{t.camera.recording}</Text>}
          <TouchableOpacity
            style={[styles.recordButton, isRecording && styles.recordButtonActive]}
            onPress={handleToggleRecord}
            activeOpacity={0.8}
          >
            <View style={[styles.recordInner, isRecording && styles.recordInnerActive]} />
          </TouchableOpacity>
          <Text style={styles.hint}>
            {isRecording ? t.camera.tapToStop : t.camera.tapToRecord}
          </Text>
        </View>
      </View>
    </>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#000',
  },
  permissionContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
    gap: 16,
  },
  permissionText: {
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 22,
  },
  permissionButton: {
    paddingHorizontal: 28,
    paddingVertical: 12,
    borderRadius: 12,
    marginTop: 8,
  },
  permissionButtonText: {
    fontSize: 16,
    fontWeight: 'bold',
  },
  header: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    paddingTop: 50,
    paddingBottom: 12,
    paddingHorizontal: 15,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  menuButton: {
    marginRight: 15,
  },
  headerTitle: {
    color: '#fff',
    fontSize: 22,
    fontWeight: 'bold',
  },
  controls: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: 50,
    alignItems: 'center',
    gap: 12,
  },
  recordButton: {
    width: 78,
    height: 78,
    borderRadius: 39,
    borderWidth: 4,
    borderColor: '#fff',
    backgroundColor: 'transparent',
    alignItems: 'center',
    justifyContent: 'center',
  },
  recordButtonActive: {
    borderColor: '#fff',
  },
  recordInner: {
    width: 60,
    height: 60,
    borderRadius: 30,
    backgroundColor: '#ef4444',
  },
  recordInnerActive: {
    width: 28,
    height: 28,
    borderRadius: 4,
  },
  recordingLabel: {
    color: '#fff',
    backgroundColor: 'rgba(239, 68, 68, 0.85)',
    fontWeight: 'bold',
    fontSize: 14,
    paddingHorizontal: 14,
    paddingVertical: 4,
    borderRadius: 14,
    overflow: 'hidden',
  },
  hint: {
    color: 'rgba(255,255,255,0.85)',
    fontSize: 13,
  },
});
