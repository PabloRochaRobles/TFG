import { useThemeColors } from '@/hooks/use-theme-color';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

export default function SettingsScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode, toggleTheme } = useTheme();

  // Estados para las configuraciones
  const [notifications, setNotifications] = useState(true);
  const [autoAnalysis, setAutoAnalysis] = useState(false);
  const [saveToCloud, setSaveToCloud] = useState(true);
  const [highQuality, setHighQuality] = useState(true);

  const languages = [
    { id: 'Español', name: 'Español', flag: '🇪🇸' },
    { id: 'English', name: 'English', flag: '🇬🇧' },
  ];

  const handleLanguageSelect = (langId: string) => {
    Alert.alert('Idioma seleccionado', `Has elegido ${langId}`);
  };

  const handleClearCache = () => {
    Alert.alert(
      'Limpiar caché',
      '¿Estás seguro de que quieres eliminar todos los datos temporales?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Limpiar', onPress: () => console.log('Caché limpiada'), style: 'destructive' },
      ]
    );
  };

  const handleExportData = () => {
    Alert.alert('Exportar datos', 'Tus partidas se exportarán en formato PGN');
  };

  const handleDeleteAccount = () => {
    Alert.alert(
      'Eliminar cuenta',
      'Esta acción es irreversible. ¿Estás seguro?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Eliminar', onPress: () => console.log('Cuenta eliminada'), style: 'destructive' },
      ]
    );
  };

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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Ajustes</Text>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={28} color={colors.headerText} />
          </TouchableOpacity>
        </View>
        
        <ScrollView style={[styles.content, { backgroundColor: colors.background }]}>
          
          {/* Sección: Apariencia */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Apariencia</Text>

            {/* Modo oscuro */}
            <View style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="moon" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Modo oscuro</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Tema oscuro para la app</Text>
                </View>
              </View>
              <Switch
                value={isDarkMode}
                onValueChange={toggleTheme}
                trackColor={{ false: '#d1d5db', true: colors.primary }}
                thumbColor={isDarkMode ? '#fff' : '#f3f4f6'}
              />
            </View>
          </View>

          {/* Sección: Idioma */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Idioma y región</Text>
            
            {languages.map((lang) => (
              <TouchableOpacity
                key={lang.id}
                style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}
                onPress={() => handleLanguageSelect(lang.id)}
              >
                <View style={styles.settingLeft}>
                  <Text style={styles.flag}>{lang.flag}</Text>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>{lang.name}</Text>
                </View>
                {lang.id === 'es' && (
                  <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>

          {/* Sección: Notificaciones */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Notificaciones</Text>
            
            <View style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="notifications" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Notificaciones push</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Recibe alertas de nuevas partidas</Text>
                </View>
              </View>
              <Switch
                value={notifications}
                onValueChange={setNotifications}
                trackColor={{ false: '#d1d5db', true: colors.primary }}
                thumbColor={notifications ? '#fff' : '#f3f4f6'}
              />
            </View>
          </View>

          {/* Sección: Análisis */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Análisis de partidas</Text>
            
            <View style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="flash" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Análisis automático</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Analizar al subir el video</Text>
                </View>
              </View>
              <Switch
                value={autoAnalysis}
                onValueChange={setAutoAnalysis}
                trackColor={{ false: '#d1d5db', true: colors.primary }}
                thumbColor={autoAnalysis ? '#fff' : '#f3f4f6'}
              />
            </View>

            <View style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="videocam" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Calidad de grabación</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Alta calidad (1080p)</Text>
                </View>
              </View>
              <Switch
                value={highQuality}
                onValueChange={setHighQuality}
                trackColor={{ false: '#d1d5db', true: colors.primary }}
                thumbColor={highQuality ? '#fff' : '#f3f4f6'}
              />
            </View>
          </View>

          {/* Sección: Almacenamiento */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Almacenamiento y datos</Text>
            
            <View style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="cloud" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Guardar en la nube</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Respaldo automático</Text>
                </View>
              </View>
              <Switch
                value={saveToCloud}
                onValueChange={setSaveToCloud}
                trackColor={{ false: '#d1d5db', true: colors.primary }}
                thumbColor={saveToCloud ? '#fff' : '#f3f4f6'}
              />
            </View>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={handleClearCache}>
              <View style={styles.settingLeft}>
                <Ionicons name="trash-outline" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Limpiar caché</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Liberar espacio (124 MB)</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={handleExportData}>
              <View style={styles.settingLeft}>
                <Ionicons name="download-outline" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Exportar partidas</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Descargar en formato PGN</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Sección: Cuenta */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Cuenta</Text>
            
            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="person-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Editar perfil</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="key-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Cambiar contraseña</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="shield-checkmark-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Privacidad y seguridad</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Sección: Ayuda */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Ayuda y soporte</Text>
            
            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={() => router.push('/about')}>
              <View style={styles.settingLeft}>
                <Ionicons name="information-circle-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Acerca de</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="help-circle-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Tutorial</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="mail-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Contactar soporte</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="star-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Valorar la app</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Sección: Peligro */}
          <View style={styles.section}>
            <TouchableOpacity 
              style={[styles.settingItem, styles.dangerItem, { borderBottomColor: colors.border }]} 
              onPress={handleDeleteAccount}
            >
              <View style={styles.settingLeft}>
                <Ionicons name="warning-outline" size={24} color="#ef4444" />
                <Text style={[styles.settingTitle, styles.dangerText]}>Eliminar cuenta</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#ef4444" />
            </TouchableOpacity>
          </View>

          {/* Versión */}
          <View style={styles.versionContainer}>
            <Text style={[styles.versionText, { color: colors.textSecondary }]}>ChessVision v1.0.0</Text>
            <Text style={[styles.versionSubtext, { color: colors.textSecondary }]}>© 2026 Todos los derechos reservados</Text>
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
    justifyContent: 'space-between',
    paddingHorizontal: 15,
  },
  backButton: {
    padding: 5,
  },
  menuButton: {
    padding: 5,
  },
  headerTitle: { 
    fontSize: 22, 
    fontWeight: 'bold',
  },
  content: { 
    flex: 1,
  },

  // Secciones
  section: {
    marginTop: 20,
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
    paddingHorizontal: 20,
    marginBottom: 10,
  },

  // Items de configuración
  settingItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 15,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
  },
  settingLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
    gap: 15,
  },
  settingTextContainer: {
    flex: 1,
  },
  settingTitle: {
    fontSize: 16,
    fontWeight: '500',
  },
  settingDescription: {
    fontSize: 13,
    marginTop: 2,
  },

  // Grupo de configuración
  settingGroup: {
    paddingVertical: 15,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
  },
  settingLabel: {
    fontSize: 16,
    fontWeight: '500',
    marginBottom: 15,
  },

  // Temas
  themeScroll: {
    marginTop: 5,
  },
  themeOption: {
    alignItems: 'center',
    marginRight: 20,
  },
  colorCircle: {
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 3,
  },
  themeName: {
    fontSize: 12,
    textAlign: 'center',
    maxWidth: 80,
  },

  // Idiomas
  flag: {
    fontSize: 28,
  },

  // Zona de peligro
  dangerItem: {
    backgroundColor: '#fef2f2',
  },
  dangerText: {
    color: '#ef4444',
    fontWeight: '600',
  },

  // Versión
  versionContainer: {
    alignItems: 'center',
    paddingVertical: 30,
    paddingBottom: 40,
  },
  versionText: {
    fontSize: 14,
    fontWeight: '500',
  },
  versionSubtext: {
    fontSize: 12,
    marginTop: 5,
  },
});