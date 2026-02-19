import { FontAwesome, FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React, { useState } from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function HomeScreen() {
  const [menuOpen, setMenuOpen] = useState(false);
  const router = useRouter();
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
          <Text style={styles.headerTitle}>Inicio</Text>
        </View>

        <View style={styles.content}>
          <TouchableOpacity style={styles.mainButton} onPress={() => router.push('/upload')}>
            <LinearGradient
              colors={['#007AFF', '#8E54E9']}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 1 }}
              style={styles.gradientButton}
            />
            <View style={styles.buttonContent}>
              <FontAwesome5 name="chess" size={45} color="white" />
              <Text style={styles.buttonText}>Analizar una nueva partida</Text>
            </View>
          </TouchableOpacity>

         <TouchableOpacity 
            style={[styles.mainButton, styles.solidButton]} 
            onPress={() => router.push('/tips')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome name="exclamation-circle" size={45} color="white" />
              <Text style={styles.buttonText}>Consejos para la grabación de partidas</Text>
            </View>
          </TouchableOpacity>


        </View>
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
    justifyContent: 'flex-start',
    alignItems: 'center', 
    gap: 20,
    backgroundColor: '#F8F9FA',
    paddingTop: 40,
  },
  mainTitle: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#2c3e50',
    marginBottom: 10,
    textAlign: 'center',
    width: '80%',
  },
  mainButton: {
    width: '80%',
    height: 160,
    borderRadius: 12,
    justifyContent: 'center',
    alignItems: 'center',
    elevation: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
  },
  buttonContent: {
    justifyContent: 'center',
    alignItems: 'center',
    gap: 10,
  },
  buttonText: { 
    color: '#fff', 
    fontSize: 22,
    fontWeight: '600',
    textAlign: 'center',
  },
  gradientButton: {
    position: 'absolute',
    width: '100%',
    height: '100%',
    borderRadius: 12,
  },
   solidButton: {
    backgroundColor: '#10b981', // Verde sólido - puedes cambiar el color
  },
});