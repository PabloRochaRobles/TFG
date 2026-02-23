import { useThemeColors } from '@/hooks/use-theme-color';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

export default function TipsScreen() {
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const router = useRouter();

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Consejos para la grabación</Text>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={28} color={colors.headerText} />
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}>
          {/* Pasos / Instrucciones */}
          <View style={styles.stepsContainer}>
            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Consejo 1:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>
                Asegúrate que la grabación se realiza en un entorno bien iluminado y evita luces directas que creen reflejos sobre el tablero
              </Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Consejo 2:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>
                Mantén la estabilidad de la grabación. Usar un tripode o un soporte previene los movimientos de la cámara
              </Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Consejo 3:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>
                Coloca la cámara desde una posición frontal y elevada que permita diferenciar claramente las piezas del tablero.
              </Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>Consejo 4:</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>
                Mantenga las manos fuera del encuadre y realice movimientos claros.
              </Text>
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
  },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
    justifyContent: 'space-between',
  },
  menuButton: { 
    padding: 5,
    width: 38,
  },
  backButton: {
    marginRight: 15,
  },
  headerTitle: { 
    fontSize: 22, 
    fontWeight: 'bold',
    flex: 1,
    textAlign: 'center',
  },
  content: { 
    flexGrow: 1,
    padding: 20, 
    alignItems: 'stretch',
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
  stepTitle: { 
    fontSize: 16, 
    fontWeight: 'bold' 
  },
  stepDescription: { 
    fontSize: 16 
  },
});