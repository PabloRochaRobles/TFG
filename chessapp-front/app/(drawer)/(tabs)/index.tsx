import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { FontAwesome, FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../../contexts/ThemeContext';

export default function HomeScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  return (
    <>
      <StatusBar style={isDarkMode ? 'light' : 'dark'} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>

        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity
            style={[styles.menuButton, { borderRightColor: 'rgba(255,255,255,0.3)' }]}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.home.title}</Text>
        </View>

        <ScrollView
          style={[styles.scrollView, { backgroundColor: colors.background }]}
          contentContainerStyle={styles.content}
        >
          {/* Botón: Analizar nueva partida */}
          <TouchableOpacity
            style={[styles.mainButton, { backgroundColor: '#007AFF' }]}
            onPress={() => router.push('/upload')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome5 name="chess" size={45} color="white" />
              <Text style={styles.buttonText}>{t.home.analyzeNewGame}</Text>
            </View>
          </TouchableOpacity>

          {/* Botón: Consejos para la grabación */}
          <TouchableOpacity
            style={[styles.mainButton, styles.solidButton]}
            onPress={() => router.push('/tips')}
          >
            <View style={styles.buttonContent}>
              <FontAwesome name="exclamation-circle" size={45} color="white" />
              <Text style={styles.buttonText}>{t.home.recordingTips}</Text>
            </View>
          </TouchableOpacity>

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
  menuButton: {
    borderRightWidth: 1,
    paddingRight: 15,
    marginRight: 15,
  },
  headerTitle: { fontSize: 22, fontWeight: 'bold' },
  scrollView: { flex: 1 },
  content: {
    alignItems: 'center',
    gap: 20,
    paddingTop: 40,
    paddingBottom: 40,
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
    paddingHorizontal: 10,
  },
  solidButton: {
    backgroundColor: '#3cb18a',
  },
});
