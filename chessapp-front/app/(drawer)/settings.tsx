import { useThemeColors } from '@/hooks/use-theme-color';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Modal, Platform, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
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
  const [supportModalVisible, setSupportModalVisible] = useState(false);
  const [supportEmail, setSupportEmail] = useState('');
  const [supportMessage, setSupportMessage] = useState('');

  const languages = [
    { id: 'Español', name: 'Español', flag: '🇪🇸' },
    { id: 'English', name: 'English', flag: '🇬🇧' },
  ];

  const handleLanguageSelect = (langId: string) => {
    Alert.alert('Idioma seleccionado', `Has elegido ${langId}`);
  };

  const handleDeleteVideos = () => {
    Alert.alert(
      'Eliminar videos',
      '¿Estás seguro de que quieres eliminar todos los videos?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Eliminar', onPress: () => console.log('Videos eliminados'), style: 'destructive' },
      ]
    );
  };

  const handleOpenSupportModal = () => {
    setSupportModalVisible(true);
  };

  const handleCloseSupportModal = () => {
    setSupportModalVisible(false);
    setSupportEmail('');
    setSupportMessage('');
  };

  const handleSendSupport = () => {
    if (!supportEmail.trim() || !supportMessage.trim()) {
      Alert.alert('Error', 'Por favor, completa todos los campos');
      return;
    }

    // Aquí enviarías los datos al backend
    console.log('Email:', supportEmail);
    console.log('Mensaje:', supportMessage);

    // Cerrar modal y mostrar mensaje de éxito
    setSupportModalVisible(false);
    setSupportEmail('');
    setSupportMessage('');

    Alert.alert(
      'Mensaje enviado',
      'Gracias por contactar con nosotros. Se le atenderá tan pronto como sea posible.',
      [{ text: 'OK' }]
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
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Recibe alertas de que el análisis esté listo</Text>
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
          </View>

          {/* Sección: Almacenamiento */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Almacenamiento y datos</Text>
            
            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={handleDeleteVideos}>
              <View style={styles.settingLeft}>
                <Ionicons name="trash-outline" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>Eliminar todas las partidas</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>Borrar todas las partidas guardadas</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Sección: Ayuda y Soporte */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>Ayuda y soporte</Text>
            
            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={() => router.push('/about')}>
              <View style={styles.settingLeft}>
                <Ionicons name="information-circle-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Acerca de</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={() => router.push('/tips')}>
              <View style={styles.settingLeft}>
                <Ionicons name="help-circle-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Tutorial</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity 
              style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}
              onPress={handleOpenSupportModal}
            >
              <View style={styles.settingLeft}>
                <Ionicons name="mail-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Contactar soporte</Text>
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

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="star-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>Valorar la app</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Versión */}
          <View style={styles.versionContainer}>
            <Text style={[styles.versionText, { color: colors.textSecondary }]}>Chess Analyzer v1.0.0</Text>
            <Text style={[styles.versionSubtext, { color: colors.textSecondary }]}>© 2026 Todos los derechos reservados</Text>
          </View>
        </ScrollView>

        <Modal
          visible={supportModalVisible}
          animationType="slide"
          transparent={true}
          onRequestClose={handleCloseSupportModal}
        >
          <KeyboardAvoidingView 
            behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
            style={styles.modalOverlay}
          >
            <TouchableOpacity 
              style={styles.modalBackdrop}
              activeOpacity={1}
              onPress={handleCloseSupportModal}
            />
            <View style={[styles.modalContent, { backgroundColor: colors.card }]}>
              {/* Header del modal */}
              <View style={styles.modalHeader}>
                <Text style={[styles.modalTitle, { color: colors.text }]}>Contactar soporte</Text>
                <TouchableOpacity onPress={handleCloseSupportModal} style={styles.closeButton}>
                  <Ionicons name="close" size={28} color={colors.text} />
                </TouchableOpacity>
              </View>

              {/* Formulario */}
              <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
                {/* Campo de email */}
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: colors.text }]}>Tu correo electrónico</Text>
                  <TextInput
                    style={[styles.input, { 
                      backgroundColor: colors.background, 
                      color: colors.text,
                      borderColor: colors.border
                    }]}
                    placeholder="ejemplo@correo.com"
                    placeholderTextColor={colors.textSecondary}
                    value={supportEmail}
                    onChangeText={setSupportEmail}
                    keyboardType="email-address"
                    autoCapitalize="none"
                  />
                </View>

                {/* Campo de mensaje */}
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: colors.text }]}>Mensaje</Text>
                  <TextInput
                    style={[styles.textArea, { 
                      backgroundColor: colors.background, 
                      color: colors.text,
                      borderColor: colors.border
                    }]}
                    placeholder="Describe tu problema o pregunta..."
                    placeholderTextColor={colors.textSecondary}
                    value={supportMessage}
                    onChangeText={setSupportMessage}
                    multiline
                    numberOfLines={6}
                    textAlignVertical="top"
                  />
                </View>
              </ScrollView>

              {/* Botones */}
              <View style={styles.modalFooter}>
                <TouchableOpacity 
                  style={[styles.modalButton, styles.cancelButton, { borderColor: colors.border }]}
                  onPress={handleCloseSupportModal}
                >
                  <Text style={[styles.cancelButtonText, { color: colors.text }]}>Cancelar</Text>
                </TouchableOpacity>

                <TouchableOpacity 
                  style={[styles.modalButton, styles.sendButton, { backgroundColor: colors.primary }]}
                  onPress={handleSendSupport}
                >
                  <Text style={styles.sendButtonText}>Enviar</Text>
                </TouchableOpacity>
              </View>
            </View>
          </KeyboardAvoidingView>
        </Modal>
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
  modalOverlay: {
    flex: 1,
    justifyContent: 'flex-end',
  },
  modalBackdrop: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'rgba(0, 0, 0, 0.5)',
  },
  modalContent: {
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '85%',
    elevation: 5,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -2 },
    shadowOpacity: 0.25,
    shadowRadius: 3.84,
  },
  modalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: '#e5e7eb',
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: 'bold',
  },
  closeButton: {
    padding: 5,
  },
  modalBody: {
    padding: 20,
    maxHeight: 400,
  },
  inputGroup: {
    marginBottom: 20,
  },
  inputLabel: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
  },
  input: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 15,
    fontSize: 16,
  },
  textArea: {
    borderWidth: 1,
    borderRadius: 10,
    padding: 15,
    fontSize: 16,
    minHeight: 150,
  },
  modalFooter: {
    flexDirection: 'row',
    gap: 12,
    padding: 20,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  modalButton: {
    flex: 1,
    paddingVertical: 15,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  cancelButton: {
    borderWidth: 2,
  },
  cancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
  },
  sendButton: {
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
  },
  sendButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
});

function setSupportModalVisible(arg0: boolean) {
  throw new Error('Function not implemented.');
}
