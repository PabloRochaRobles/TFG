import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import * as ImagePicker from 'expo-image-picker';
import { useNavigation } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

// Imports de tema
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTheme } from '../../contexts/ThemeContext';

export default function UploadScreen() {
  const [videoUri, setVideoUri] = useState<string | null>(null);
  const navigation = useNavigation();
  
  // Hooks de tema
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

  const pickVideo = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    
    if (status !== 'granted') {
      alert('Se necesitan permisos para acceder a la galería');
      return;
    }

    let result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      allowsEditing: true,
      quality: 1,
    });

    if (!result.canceled) {
      setVideoUri(result.assets[0].uri);
    }
  };

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
        
        {/* Header Dinámico */}
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

          {/* Zona de Selección de Vídeo */}
          <TouchableOpacity 
            style={[
              styles.uploadBox, 
              { 
                backgroundColor: isDarkMode ? colors.card : '#D1D5DB', 
                borderColor: colors.border 
              }
            ]} 
            onPress={pickVideo}
          >
            {videoUri ? (
              <Ionicons name="checkmark-circle" size={60} color="#27ae60" />
            ) : (
              <Ionicons name="camera" size={60} color={colors.text} />
            )}
            <Text style={[styles.uploadText, { color: colors.text }]}>
              {videoUri ? "Vídeo cargado con éxito" : "Toca para seleccionar un vídeo"}
            </Text>
          </TouchableOpacity>

          {/* Pasos / Instrucciones */}
          <View style={styles.stepsContainer}>
            <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Paso 1:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>Selecciona tu partida de ajedrez</Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Paso 2:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>Pulsa el botón de generar análisis</Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: isDarkMode ? colors.card : '#D1D5DB', borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Paso 3:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>Revisa el resultado obtenido</Text>
            </View>
          </View>
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
    paddingBottom: 20 
  },
  stepBox: {
    width: '100%',
    borderRadius: 15,
    borderWidth: 1,
    padding: 15,
  },
  stepTitle: { fontSize: 16, fontWeight: 'bold' },
  stepDescription: { fontSize: 16 },
});