import { useThemeColors } from '@/hooks/use-theme-color';
import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { LinearGradient } from 'expo-linear-gradient';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../../contexts/ThemeContext';

export default function LibraryScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const videoCount = 0;

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Librería</Text>
        </View>

        <View style={[styles.content, { backgroundColor: colors.background }]}>
          {/* Contador de Vídeos */}
          <Text style={[styles.counterText, { color: colors.text }]}>
            {videoCount} videos
          </Text>

          {/* Estado Vacío (Empty State) */}
          <View style={styles.emptyContainer}>
            <Text style={[styles.emptyText, { color: colors.text }]}>
              No se ha subido ningún{"\n"}video aún
            </Text>

            {/* Botón con Degradado */}
            <TouchableOpacity 
              style={styles.gradientButtonContainer}
              onPress={() => router.push('/upload')}
            >
              <LinearGradient
                colors={['#007AFF', '#8E54E9']}
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
  },
  header: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 15,
  },
  menuButton: { 
    marginRight: 15 
  },
  headerTitle: { 
    fontSize: 22, 
    fontWeight: 'bold' 
  },
  
  content: { 
    flex: 1, 
    padding: 20,
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