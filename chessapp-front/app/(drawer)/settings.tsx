import { deleteVideo, listVideos } from '@/constants/api';
import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import { Alert, KeyboardAvoidingView, Modal, Platform, ScrollView, StyleSheet, Switch, Text, TextInput, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { LANGUAGES, useLanguage } from '@/contexts/LanguageContext';
import { useTheme } from '@/contexts/ThemeContext';

export default function SettingsScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode, toggleTheme } = useTheme();
  const { language, setLanguage } = useLanguage();
  const t = useTranslation();

  // Estados para las configuraciones
  const [notifications, setNotifications] = useState(true);
  const [autoAnalysis, setAutoAnalysis] = useState(false);
  const [supportModalVisible, setSupportModalVisible] = useState(false);
  const [supportEmail, setSupportEmail] = useState('');
  const [supportMessage, setSupportMessage] = useState('');

  const handleDeleteVideos = () => {
    Alert.alert(
      t.settings.deleteVideos,
      t.settings.deleteVideosConfirm,
      [
        { text: t.settings.cancel, style: 'cancel' },
        {
          text: t.settings.delete,
          style: 'destructive',
          onPress: async () => {
            try {
              const videos = await listVideos();
              await Promise.all(videos.map((v) => deleteVideo(v)));
              Alert.alert(t.settings.deleteVideos, t.settings.deleteVideosSuccess);
            } catch {
              Alert.alert('Error', t.settings.deleteVideosError);
            }
          },
        },
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
      Alert.alert('Error', t.settings.fillAllFields);
      return;
    }

    console.log('Email:', supportEmail);
    console.log('Mensaje:', supportMessage);

    setSupportModalVisible(false);
    setSupportEmail('');
    setSupportMessage('');

    Alert.alert(
      t.settings.messageSent,
      t.settings.messageSentDesc,
      [{ text: t.settings.ok }]
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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>{t.settings.title}</Text>
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
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{t.settings.appearance}</Text>

            {/* Modo oscuro */}
            <View style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="moon" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>{t.settings.darkMode}</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>{t.settings.darkModeDesc}</Text>
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
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{t.settings.language}</Text>

            {LANGUAGES.map((lang) => (
              <TouchableOpacity
                key={lang.id}
                style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}
                onPress={() => setLanguage(lang.id)}
              >
                <View style={styles.settingLeft}>
                  <Text style={styles.flag}>{lang.flag}</Text>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>{lang.name}</Text>
                </View>
                {language === lang.id && (
                  <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>

          {/* Sección: Almacenamiento */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{t.settings.storage}</Text>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={handleDeleteVideos}>
              <View style={styles.settingLeft}>
                <Ionicons name="trash-outline" size={24} color={colors.textSecondary} />
                <View style={styles.settingTextContainer}>
                  <Text style={[styles.settingTitle, { color: colors.text }]}>{t.settings.deleteGames}</Text>
                  <Text style={[styles.settingDescription, { color: colors.textSecondary }]}>{t.settings.deleteGamesDesc}</Text>
                </View>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
          </View>

          {/* Sección: Ayuda y Soporte */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{t.settings.help}</Text>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]} onPress={() => router.push('/tips')}>
              <View style={styles.settingLeft}>
                <Ionicons name="help-circle-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>{t.settings.tutorial}</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity
              style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}
              onPress={handleOpenSupportModal}
            >
              <View style={styles.settingLeft}>
                <Ionicons name="mail-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>{t.settings.contactSupport}</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

            <TouchableOpacity style={[styles.settingItem, { backgroundColor: colors.card, borderBottomColor: colors.border }]}>
              <View style={styles.settingLeft}>
                <Ionicons name="shield-checkmark-outline" size={24} color={colors.textSecondary} />
                <Text style={[styles.settingTitle, { color: colors.text }]}>{t.settings.privacy}</Text>
              </View>
              <Ionicons name="chevron-forward" size={24} color={colors.textSecondary} />
            </TouchableOpacity>

          </View>

          {/* Versión */}
          <View style={styles.versionContainer}>
            <Text style={[styles.versionText, { color: colors.textSecondary }]}>{t.settings.version}</Text>
            <Text style={[styles.versionSubtext, { color: colors.textSecondary }]}>{t.settings.copyright}</Text>
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
                <Text style={[styles.modalTitle, { color: colors.text }]}>{t.settings.contactSupportTitle}</Text>
                <TouchableOpacity onPress={handleCloseSupportModal} style={styles.closeButton}>
                  <Ionicons name="close" size={28} color={colors.text} />
                </TouchableOpacity>
              </View>

              {/* Formulario */}
              <ScrollView style={styles.modalBody} showsVerticalScrollIndicator={false}>
                {/* Campo de email */}
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: colors.text }]}>{t.settings.emailLabel}</Text>
                  <TextInput
                    style={[styles.input, {
                      backgroundColor: colors.background,
                      color: colors.text,
                      borderColor: colors.border
                    }]}
                    placeholder={t.settings.emailPlaceholder}
                    placeholderTextColor={colors.textSecondary}
                    value={supportEmail}
                    onChangeText={setSupportEmail}
                    keyboardType="email-address"
                    autoCapitalize="none"
                  />
                </View>

                {/* Campo de mensaje */}
                <View style={styles.inputGroup}>
                  <Text style={[styles.inputLabel, { color: colors.text }]}>{t.settings.messageLabel}</Text>
                  <TextInput
                    style={[styles.textArea, {
                      backgroundColor: colors.background,
                      color: colors.text,
                      borderColor: colors.border
                    }]}
                    placeholder={t.settings.messagePlaceholder}
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
                  <Text style={[styles.cancelButtonText, { color: colors.text }]}>{t.settings.cancel}</Text>
                </TouchableOpacity>

                <TouchableOpacity
                  style={[styles.modalButton, styles.sendButton, { backgroundColor: colors.primary }]}
                  onPress={handleSendSupport}
                >
                  <Text style={styles.sendButtonText}>{t.settings.send}</Text>
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

