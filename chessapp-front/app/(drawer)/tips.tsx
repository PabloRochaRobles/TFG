import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import React from 'react';
import { ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/contexts/ThemeContext';

export default function TipsScreen() {
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const router = useRouter();
  const t = useTranslation();

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          
          {/* Botón de vuelta a atrás */}
          <TouchableOpacity style={styles.backButton} onPress={() => router.back()}>
            <Ionicons name="arrow-back" size={28} color={colors.headerText} />
          </TouchableOpacity>

          <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.tips.title}</Text>
          
          {/* Botón desplegable lateral */}
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={28} color={colors.headerText} />
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={[styles.content, { backgroundColor: colors.background }]}>
          {/* Enumeración de consejos */}
          <View style={styles.stepsContainer}>
            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>{t.tips.tip1Label}</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>{t.tips.tip1}</Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>{t.tips.tip2Label}</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>{t.tips.tip2}</Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>{t.tips.tip3Label}</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>{t.tips.tip3}</Text>
            </View>

            <View style={[styles.stepBox, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.stepTitle, { color: colors.text }]}>{t.tips.tip4Label}</Text>
              <Text style={[styles.stepDescription, { color: colors.text }]}>{t.tips.tip4}</Text>
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
