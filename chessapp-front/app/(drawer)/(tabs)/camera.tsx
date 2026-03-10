import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useRef, useState } from 'react';
import { Button, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';

export default function CameraScreen() {
  const [cameraPermission, requestCameraPermission] = useCameraPermissions();
  const [micPermission, requestMicPermission] = useMicrophonePermissions();
  const cameraRef = useRef<CameraView>(null);
  const [isRecording, setIsRecording] = useState(false);
  const t = useTranslation();
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();

  if (!cameraPermission || !micPermission) return <View />;

  if (!cameraPermission.granted || !micPermission.granted) {
    return (
      <View style={[styles.permissionContainer, { backgroundColor: colors.background }]}>
        <Text style={[styles.permissionText, { color: colors.text }]}>
          {t.camera.permissionText}
        </Text>
        <Button
          onPress={async () => {
            if (!cameraPermission.granted) await requestCameraPermission();
            if (!micPermission.granted) await requestMicPermission();
          }}
          title={t.camera.grantPermissions}
        />
      </View>
    );
  }

  const handleRecord = async () => {
    if (!cameraRef.current) return;

    if (isRecording) {
      cameraRef.current.stopRecording();
      setIsRecording(false);
    } else {
      setIsRecording(true);
      const video = await cameraRef.current.recordAsync();
      setIsRecording(false);

      if (video?.uri) {
        router.push({
          pathname: '/(drawer)/(tabs)/upload',
          params: { cameraUri: video.uri },
        });
      }
    }
  };

  return (
    <>
      <StatusBar style="light" />
      <View style={styles.container}>
        {/* Header sobre la cámara */}
        <View style={styles.header}>
          <TouchableOpacity
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color="#fff" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>{t.camera.title}</Text>
        </View>

        <CameraView style={styles.camera} ref={cameraRef} mode="video" />

        {/* Controles */}
        <View style={styles.controlsOverlay}>
          {isRecording && (
            <Text style={styles.recordingText}>{t.camera.recording}</Text>
          )}
          <TouchableOpacity
            onPress={handleRecord}
            style={[styles.recordButton, { backgroundColor: isRecording ? 'red' : 'white' }]}
          />
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
  header: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 10,
    flexDirection: 'row',
    alignItems: 'center',
    paddingTop: 50,
    paddingBottom: 12,
    paddingHorizontal: 15,
    backgroundColor: 'rgba(0,0,0,0.4)',
  },
  menuButton: { marginRight: 15 },
  headerTitle: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#fff',
  },
  camera: {
    flex: 1,
  },
  permissionContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  permissionText: {
    textAlign: 'center',
    marginBottom: 20,
    fontSize: 16,
  },
  controlsOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    paddingBottom: 50,
    alignItems: 'center',
    gap: 12,
  },
  recordButton: {
    width: 70,
    height: 70,
    borderRadius: 35,
    borderWidth: 4,
    borderColor: 'white',
  },
  recordingText: {
    color: 'red',
    fontSize: 16,
    fontWeight: 'bold',
    backgroundColor: 'rgba(0,0,0,0.5)',
    paddingHorizontal: 15,
    paddingVertical: 5,
    borderRadius: 15,
  },
  hint: {
    color: 'rgba(255,255,255,0.8)',
    fontSize: 13,
  },
});
