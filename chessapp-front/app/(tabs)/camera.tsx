import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRef, useState } from 'react';
import { Button, Text, TouchableOpacity, View } from 'react-native';

export default function CameraScreen() {
  const [permission, requestPermission] = useCameraPermissions();
  const cameraRef = useRef<CameraView>(null);
  const [isRecording, setIsRecording] = useState(false);

  if (!permission) return <View />; // Cargando permisos

  if (!permission.granted) {
    return (
      <View style={{ flex: 1, justifyContent: 'center' }}>
        <Text>Necesitamos permiso para usar la cámara</Text>
        <Button onPress={requestPermission} title="Conceder permiso" />
      </View>
    );
  }

  const handleRecord = async () => {
    if (cameraRef.current) {
      if (isRecording) {
        cameraRef.current.stopRecording();
        setIsRecording(false);
      } else {
        setIsRecording(true);
        const video = await cameraRef.current.recordAsync();
        console.log("Video guardado en:", video?.uri);
      }
    }
  };

  return (
    <View style={{ flex: 1 }}>
      <CameraView style={{ flex: 1 }} ref={cameraRef} mode="video">
        <View style={{ flex: 1, justifyContent: 'flex-end', alignItems: 'center', marginBottom: 50 }}>
          <TouchableOpacity 
            onPress={handleRecord}
            style={{ width: 70, height: 70, borderRadius: 35, backgroundColor: isRecording ? 'red' : 'white' }} 
          />
        </View>
      </CameraView>
    </View>
  );
}