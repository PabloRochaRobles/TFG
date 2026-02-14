import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function HomeScreen() {
  const [menuOpen, setMenuOpen] = useState(false);
  const router = useRouter();

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>

        {/* Header Azul */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.menuButton}>
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Inicio</Text>
        </View>

        <View style={styles.content}>
          <TouchableOpacity style={styles.mainButton} onPress={() => router.push('/upload')}>
            <FontAwesome name="upload" size={28} color="white" style={{ marginRight: 10 }} />
            <Text style={styles.buttonText}>Subir vídeo</Text>
          </TouchableOpacity>

          <TouchableOpacity 
            style={[styles.mainButton, styles.secondaryButton]} 
            onPress={() => router.push('/camera')}
          >
            <FontAwesome name="camera" size={28} color="white" style={{ marginRight: 10 }} />
            <Text style={styles.buttonText}>Grabar vídeo</Text>
          </TouchableOpacity>

          <TouchableOpacity 
            style={[styles.mainButton, styles.accentButton]} 
            onPress={() => router.push('/library')}
          >
            <FontAwesome name="bookmark" size={28} color="white" style={{ marginRight: 10 }} />
            <Text style={styles.buttonText}>Ver librería</Text>
          </TouchableOpacity>
        </View>
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
    flex: 1, 
    justifyContent: 'center', 
    alignItems: 'center', 
    gap: 20,
    backgroundColor: '#F8F9FA' // Fondo blanco del contenido
  },
  mainButton: {
    width: '80%',
    height: 60,
    backgroundColor: '#2c3e50',
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    flexDirection: 'row', // Para poner ícono + texto
  },
  secondaryButton: { backgroundColor: '#34495e' },
  accentButton: { backgroundColor: '#27ae60' },
  buttonText: { 
    color: '#fff', 
    fontSize: 18, 
    fontWeight: '600' 
  },
});