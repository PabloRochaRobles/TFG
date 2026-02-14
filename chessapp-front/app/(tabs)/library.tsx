import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { LinearGradient } from 'expo-linear-gradient';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function LibraryScreen() {
  const router = useRouter();
  const videoCount = 0; // Simulamos que no hay vídeos para mostrar la vista de la imagen

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header Azul Principal */}
        <View style={styles.header}>
          <TouchableOpacity style={styles.menuButton}>
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Librería</Text>
        </View>

        <View style={styles.content}>
          {/* Botón Atrás */}
          <TouchableOpacity style={styles.backContainer} onPress={() => router.back()}>
            <Ionicons name="arrow-back-circle" size={40} color="black" />
            <Text style={styles.backText}>Atrás</Text>
          </TouchableOpacity>

          {/* Contador de Vídeos */}
          <Text style={styles.counterText}>{videoCount} videos</Text>

          {/* Estado Vacío (Empty State) */}
          <View style={styles.emptyContainer}>
            <Text style={styles.emptyText}>No se ha subido ningún{"\n"}video aún</Text>

            {/* Botón con Degradado */}
            <TouchableOpacity 
              style={styles.gradientButtonContainer}
              onPress={() => router.push('/upload')}
            >
              <LinearGradient
                colors={['#007AFF', '#8E54E9']} // Azul a Púrpura
                start={{ x: 0, y: 0.5 }}
                end={{ x: 1, y: 0.5 }}
                style={styles.gradientButton}
              >
                <FontAwesome name="upload" size={45} color="white" />
                <Text style={styles.buttonText}>Subir video</Text>
              </LinearGradient>
            </TouchableOpacity>
          </View>
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
    padding: 20,
    backgroundColor: '#F8F9FA' // Fondo blanco del contenido
  },
  
  backContainer: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    marginBottom: 30 
  },
  backText: { 
    fontSize: 20, 
    fontWeight: 'bold', 
    marginLeft: 10 
  },

  counterText: { 
    fontSize: 24, 
    fontWeight: 'bold', 
    marginBottom: 50 
  },

  emptyContainer: { 
    flex: 1, 
    alignItems: 'center', 
    paddingTop: 20 
  },
  emptyText: { 
    fontSize: 22, 
    fontWeight: 'bold', 
    textAlign: 'center', 
    marginBottom: 40,
    lineHeight: 30 
  },

  gradientButtonContainer: {
    width: '85%',
    borderRadius: 20,
    overflow: 'hidden',
    elevation: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
  },
  gradientButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 15,
    paddingHorizontal: 20,
    gap: 15
  },
  buttonText: { 
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold' 
  },
});