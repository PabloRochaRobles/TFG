import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { router } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function UploadScreen() {
  const [videoUri, setVideoUri] = useState<string | null>(null);

  const pickVideo = async () => {
    // Solicitar permisos (necesario en algunas versiones de Android/iOS)
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    
    if (status !== 'granted') {
      alert('Se necesitan permisos para acceder a la galería');
      return;
    }

    // Abrir el gestor de archivos/galería
    let result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'], // Restringimos solo a vídeos
      allowsEditing: true,    // Permite recortar el vídeo si es necesario
      quality: 1,
    });

    if (!result.canceled) {
      setVideoUri(result.assets[0].uri);
      console.log("Vídeo seleccionado:", result.assets[0].uri);
    }
  };

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header Azul */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.menuButton}>
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Subir Video</Text>
        </View>

        <ScrollView contentContainerStyle={styles.content}>
          {/* Botón Atrás */}
          <TouchableOpacity style={styles.backContainer} onPress={() => router.back()}>
            <Ionicons name="arrow-back-circle" size={45} color="black" />
            <Text style={styles.backText}>Atrás</Text>
          </TouchableOpacity>

          {/* Zona de Selección de Vídeo */}
          <TouchableOpacity style={styles.uploadBox} onPress={pickVideo}>
            {videoUri ? (
              <Ionicons name="checkmark-circle" size={60} color="#27ae60" />
            ) : (
              <Ionicons name="camera" size={60} color="black" />
            )}
            <Text style={styles.uploadText}>
              {videoUri ? "Vídeo cargado con éxito" : "Toca para seleccionar un vídeo"}
            </Text>
          </TouchableOpacity>

          {/* Pasos / Instrucciones */}
          <View style={styles.stepsContainer}>
            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Paso 1:</Text>
              <Text style={styles.stepDescription}>Selecciona tu partida de ajedrez</Text>
            </View>

            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Paso 2:</Text>
              <Text style={styles.stepDescription}>Pulsa el botón de generar análisis</Text>
            </View>

            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Paso 3:</Text>
              <Text style={styles.stepDescription}>Revisa el resultado obtenido</Text>
            </View>
          </View>
        </ScrollView>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: '#3b82f6' // Mismo color que el header
  },
  header: {
    height: 60,
    backgroundColor: '#3b82f6',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  menuButton: { 
    borderRightWidth: 1, 
    borderRightColor: 'rgba(255,255,255,0.3)', 
    paddingRight: 15, 
    marginRight: 15 
  },
  headerTitle: { 
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold' 
  },
  
  content: { 
    flexGrow: 1,
    padding: 20, 
    alignItems: 'center',
    backgroundColor: '#F8F9FA' // Fondo blanco del contenido
  },
  
  backContainer: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    alignSelf: 'flex-start', 
    marginBottom: 20 
  },
  backText: { 
    fontSize: 20, 
    fontWeight: 'bold', 
    marginLeft: 10 
  },

  uploadBox: {
    width: '100%',
    aspectRatio: 1.2,
    backgroundColor: '#D1D5DB',
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#4B5563',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 30,
  },
  uploadText: { 
    fontSize: 18, 
    fontWeight: 'bold', 
    textAlign: 'center', 
    marginTop: 15 
  },

  stepsContainer: { 
    width: '100%', 
    gap: 15, 
    paddingHorizontal: 20
  },
  stepBox: {
    width: '100%',
    backgroundColor: '#D1D5DB',
    borderRadius: 15,
    borderWidth: 1,
    borderColor: '#4B5563',
    padding: 15,
  },
  stepTitle: { 
    fontSize: 16, 
    fontWeight: 'bold' 
  },
  stepDescription: { 
    fontSize: 16 
  },
});