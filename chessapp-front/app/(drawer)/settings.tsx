import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Alert, ScrollView, StyleSheet, Switch, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function SettingsScreen() {
  const router = useRouter();
  const navigation = useNavigation();

  // Estados para las configuraciones
  const [notifications, setNotifications] = useState(true);
  const [autoAnalysis, setAutoAnalysis] = useState(false);
  const [saveToCloud, setSaveToCloud] = useState(true);
  const [highQuality, setHighQuality] = useState(true);
  const [darkMode, setDarkMode] = useState(false);

  const themes = [
    { id: 'blue', name: 'Azul (Predeterminado)', color: '#3b82f6' },
    { id: 'green', name: 'Verde', color: '#10b981' },
    { id: 'purple', name: 'Púrpura', color: '#8b5cf6' },
    { id: 'orange', name: 'Naranja', color: '#f97316' },
    { id: 'red', name: 'Rojo', color: '#ef4444' },
  ];

  const languages = [
    { id: 'es', name: 'Español', flag: '🇪🇸' },
    { id: 'en', name: 'English', flag: '🇬🇧' },
    { id: 'fr', name: 'Français', flag: '🇫🇷' },
    { id: 'de', name: 'Deutsch', flag: '🇩🇪' },
  ];

  const handleThemeSelect = (themeId: string) => {
    Alert.alert('Tema seleccionado', `Has elegido el tema ${themeId}`);
    // Aquí implementarás el cambio de tema real
  };

  const handleLanguageSelect = (langId: string) => {
    Alert.alert('Idioma seleccionado', `Has elegido ${langId}`);
    // Aquí implementarás el cambio de idioma real
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
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Ajustes</Text>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={28} color="white" />
          </TouchableOpacity>
        </View>
        
        <ScrollView style={styles.content}>
          {/* Sección: Apariencia */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Apariencia</Text>
            
            {/* Tema de color */}
            <View style={styles.settingGroup}>
              <Text style={styles.settingLabel}>Tema de color</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.themeScroll}>
                {themes.map((theme) => (
                  <TouchableOpacity
                    key={theme.id}
                    style={styles.themeOption}
                    onPress={() => handleThemeSelect(theme.id)}
                  >
                    <View style={[styles.colorCircle, { backgroundColor: theme.color }]}>
                      {theme.id === 'blue' && (
                        <Ionicons name="checkmark" size={24} color="white" />
                      )}
                    </View>
                    <Text style={styles.themeName}>{theme.name}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>
            </View>

            {/* Modo oscuro */}
            <View style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="moon" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Modo oscuro</Text>
                  <Text style={styles.settingDescription}>Tema oscuro para la app</Text>
                </View>
              </View>
              <Switch
                value={darkMode}
                onValueChange={setDarkMode}
                trackColor={{ false: '#d1d5db', true: '#3b82f6' }}
                thumbColor={darkMode ? '#fff' : '#f3f4f6'}
              />
            </View>
          </View>

          {/* Sección: Idioma */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Idioma y región</Text>
            
            {languages.map((lang) => (
              <TouchableOpacity
                key={lang.id}
                style={styles.settingItem}
                onPress={() => handleLanguageSelect(lang.id)}
              >
                <View style={styles.settingLeft}>
                  <Text style={styles.flag}>{lang.flag}</Text>
                  <Text style={styles.settingTitle}>{lang.name}</Text>
                </View>
                {lang.id === 'es' && (
                  <Ionicons name="checkmark-circle" size={24} color="#3b82f6" />
                )}
              </TouchableOpacity>
            ))}
          </View>

          {/* Sección: Notificaciones */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Notificaciones</Text>
            
            <View style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="notifications" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Notificaciones push</Text>
                  <Text style={styles.settingDescription}>Recibe alertas de nuevas partidas</Text>
                </View>
              </View>
              <Switch
                value={notifications}
                onValueChange={setNotifications}
                trackColor={{ false: '#d1d5db', true: '#3b82f6' }}
                thumbColor={notifications ? '#fff' : '#f3f4f6'}
              />
            </View>
          </View>

          {/* Sección: Análisis */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Análisis de partidas</Text>
            
            <View style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="flash" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Análisis automático</Text>
                  <Text style={styles.settingDescription}>Analizar al subir el video</Text>
                </View>
              </View>
              <Switch
                value={autoAnalysis}
                onValueChange={setAutoAnalysis}
                trackColor={{ false: '#d1d5db', true: '#3b82f6' }}
                thumbColor={autoAnalysis ? '#fff' : '#f3f4f6'}
              />
            </View>

            <View style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="videocam" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Calidad de grabación</Text>
                  <Text style={styles.settingDescription}>Alta calidad (1080p)</Text>
                </View>
              </View>
              <Switch
                value={highQuality}
                onValueChange={setHighQuality}
                trackColor={{ false: '#d1d5db', true: '#3b82f6' }}
                thumbColor={highQuality ? '#fff' : '#f3f4f6'}
              />
            </View>
          </View>

          {/* Sección: Almacenamiento */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Almacenamiento y datos</Text>
            
            <View style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="cloud" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Guardar en la nube</Text>
                  <Text style={styles.settingDescription}>Respaldo automático</Text>
                </View>
              </View>
              <Switch
                value={saveToCloud}
                onValueChange={setSaveToCloud}
                trackColor={{ false: '#d1d5db', true: '#3b82f6' }}
                thumbColor={saveToCloud ? '#fff' : '#f3f4f6'}
              />
            </View>

            <TouchableOpacity style={styles.settingItem} onPress={handleClearCache}>
              <View style={styles.settingLeft}>
                <Ionicons name="trash-outline" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Limpiar caché</Text>
                  <Text style={styles.settingDescription}>Liberar espacio (124 MB)</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>

            <TouchableOpacity style={styles.settingItem} onPress={handleExportData}>
              <View style={styles.settingLeft}>
                <Ionicons name="download-outline" size={24} color="#6b7280" />
                <View style={styles.settingTextContainer}>
                  <Text style={styles.settingTitle}>Exportar partidas</Text>
                  <Text style={styles.settingDescription}>Descargar en formato PGN</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>
          </View>

          {/* Sección: Cuenta */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Cuenta</Text>
            
            <TouchableOpacity style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="person-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Editar perfil</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>

            <TouchableOpacity style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="key-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Cambiar contraseña</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>

            <TouchableOpacity style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="shield-checkmark-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Privacidad y seguridad</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>
          </View>

          {/* Sección: Ayuda */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Ayuda y soporte</Text>
            
            <TouchableOpacity style={styles.settingItem} onPress={() => router.push('/about')}>
              <View style={styles.settingLeft}>
                <Ionicons name="information-circle-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Acerca de</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>

            <TouchableOpacity style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="help-circle-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Tutorial</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>

            <TouchableOpacity style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="mail-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Contactar soporte</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>

            <TouchableOpacity style={styles.settingItem}>
              <View style={styles.settingLeft}>
                <Ionicons name="star-outline" size={24} color="#6b7280" />
                <Text style={styles.settingTitle}>Valorar la app</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
            </TouchableOpacity>
          </View>

          {/* Sección: Peligro */}
          <View style={styles.section}>
            <TouchableOpacity 
              style={[styles.settingItem, styles.dangerItem]} 
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
            <Text style={styles.versionText}>ChessVision v1.0.0</Text>
            <Text style={styles.versionSubtext}>© 2026 Todos los derechos reservados</Text>
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
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold',
  },
  content: { 
    flex: 1, 
    backgroundColor: '#F8F9FA',
  },

  // Secciones
  section: {
    marginTop: 20,
    marginBottom: 10,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: '#6b7280',
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
    backgroundColor: '#fff',
    paddingVertical: 15,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
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
    color: '#1f2937',
  },
  settingDescription: {
    fontSize: 13,
    color: '#9ca3af',
    marginTop: 2,
  },

  // Grupo de configuración
  settingGroup: {
    backgroundColor: '#fff',
    paddingVertical: 15,
    paddingHorizontal: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  settingLabel: {
    fontSize: 16,
    fontWeight: '500',
    color: '#1f2937',
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
    color: '#6b7280',
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
    color: '#6b7280',
    fontWeight: '500',
  },
  versionSubtext: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 5,
  },
});