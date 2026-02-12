import { Ionicons } from '@expo/vector-icons'; // Iconos incluidos en Expo
import { useRouter } from 'expo-router';
import React, { useState } from 'react';
import { SafeAreaView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';

export default function HomeScreen() {
  const [menuOpen, setMenuOpen] = useState(false);
  const router = useRouter()

  return (
    <SafeAreaView style={styles.container}>
      {/* Barra Superior */}
      <View style={styles.header}>
        <Text style={styles.logo}>ChessVision</Text>
        <TouchableOpacity onPress={() => setMenuOpen(!menuOpen)}>
          <Ionicons name="menu" size={32} color="black" />
        </TouchableOpacity>
      </View>

      {/* Header Azul */}
      <View style={styles.header}>
        <TouchableOpacity style={styles.menuButton}>
          <Ionicons name="menu" size={30} color="white" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Inicio</Text>
      </View>

      <View style={styles.content}>
        <TouchableOpacity style={styles.mainButton} onPress={() => router.push('/upload')}>
          <Text style={styles.buttonText}>Subir vídeo</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.mainButton, styles.secondaryButton]} onPress={() => router.push('/camera')}>
          <Text style={styles.buttonText}>Grabar vídeo</Text>
        </TouchableOpacity>

        <TouchableOpacity style={[styles.mainButton, styles.accentButton]} onPress={() => router.push('/explore')}>
          <Text style={styles.buttonText}>Ver librería</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#F8F9FA' },
  header: {
    height: 60,
    backgroundColor: '#3b82f6', // Azul del diseño
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },

  logo: { fontSize: 20, fontWeight: 'bold' },
  
  dropdown: { backgroundColor: '#fff', padding: 20, borderBottomWidth: 1, borderColor: '#eee' },
  
  menuItem: { paddingVertical: 10, fontSize: 16 },
  
  content: { flex: 1, justifyContent: 'center', alignItems: 'center', gap: 20 },
  
  menuButton: { borderRightWidth: 1, borderRightColor: 'rgba(255,255,255,0.3)', paddingRight: 15, marginRight: 15 },
  headerTitle: { color: 'white', fontSize: 22, fontWeight: 'bold' },

  mainButton: {
    width: '80%',
    height: 60,
    backgroundColor: '#2c3e50',
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
  
  },
  secondaryButton: { backgroundColor: '#34495e' },
  accentButton: { backgroundColor: '#27ae60' },
  buttonText: { color: '#fff', fontSize: 18, fontWeight: '600' },
});

