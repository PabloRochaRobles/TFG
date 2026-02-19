import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function UploadScreen() {
  const navigation = useNavigation();

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header Azul */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Consejos para la grabación</Text>
        </View>

        <ScrollView contentContainerStyle={styles.content}>

          {/* Pasos / Instrucciones */}
          <View style={styles.stepsContainer}>
            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Consejo 1:</Text>
              <Text style={styles.stepDescription}>Asegúrate que la grabación se realiza en un entorno bien iluminado y evita luces directas que creen reflejos sobre el tablero</Text>
            </View>

            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Consejo 2:</Text>
              <Text style={styles.stepDescription}>Mantén la estabilidad de la grabación. Usar un tripode o un soporte previene los movimientos de la cámara</Text>
            </View>

            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Consejo 3:</Text>
              <Text style={styles.stepDescription}>Coloca la cámara desde una posición frontal y elevada que permita diferenciar claramente las piezas del tablero.</Text>
            </View>

            <View style={styles.stepBox}>
              <Text style={styles.stepTitle}>Consejo 4:</Text>
              <Text style={styles.stepDescription}>Mantenga las manos fuera del encuadre y realice movimientos claros.</Text>
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
    backgroundColor: '#3b82f6'
  },
  header: {
    height: 60,
    backgroundColor: '#3b82f6',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  menuButton: { 
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
    alignItems: 'stretch',
    backgroundColor: '#F8F9FA'
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
    borderColor: '#86b8ff',
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
  stepImage: {
    width: '100%',
    height: 250,
    marginTop: 10,
  },
});