import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { DrawerContentScrollView, DrawerItem } from '@react-navigation/drawer';
import { useRouter } from 'expo-router';
import { Drawer } from 'expo-router/drawer';
import { useState } from 'react';
import { Modal, Pressable, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { LANGUAGES, useLanguage } from '../contexts/LanguageContext';
import { useTheme } from '../contexts/ThemeContext';

function CustomDrawerContent(props: any) {
  const router = useRouter();
  const { isDarkMode, toggleTheme } = useTheme();
  const { language, setLanguage } = useLanguage();
  const { logout } = useAuth();
  const colors = useThemeColors();
  const t = useTranslation();
  const [langExpanded,    setLangExpanded]    = useState(false);
  const [logoutConfirmOpen, setLogoutConfirmOpen] = useState(false);

  const currentLang = LANGUAGES.find((l) => l.id === language) ?? LANGUAGES[0];

  const DrawerSeparator = () => (
    <View style={[styles.separator, { backgroundColor: colors.border }]} />
  );

  return (
    <View style={[styles.drawerContainer, { backgroundColor: colors.card }]}>
      <DrawerContentScrollView {...props} contentContainerStyle={styles.scrollContent}>
        <DrawerItem
          label=""
          icon={({ color, size }) => (
            <Ionicons name="menu" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerSeparator />

        <DrawerItem
          label={t.drawer.home}
          icon={({ color, size }) => (
            <FontAwesome name="home" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerItem
          label={t.drawer.uploadVideo}
          icon={({ color, size }) => (
            <FontAwesome name="upload" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/upload');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerItem
          label={t.drawer.liveAnalysis}
          icon={({ color, size }) => (
            <FontAwesome name="camera" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/live-analysis');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerItem
          label={t.drawer.analyzePosition}
          icon={({ color, size }) => (
            <FontAwesome name="search" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/analyze-position');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerItem
          label={t.drawer.myLibrary}
          icon={({ color, size }) => (
            <FontAwesome name="bookmark" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/library');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerSeparator />

        <DrawerItem
          label={t.drawer.settings}
          icon={({ color, size }) => (
            <Ionicons name="settings" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/settings');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerSeparator />

        <DrawerItem
          label={t.auth.logout}
          icon={({ size }) => (
            <Ionicons name="log-out-outline" size={size} color="#ef4444" />
          )}
          onPress={() => setLogoutConfirmOpen(true)}
          inactiveTintColor="#ef4444"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />
      </DrawerContentScrollView>

      {/* Controles inferiores: idioma y tema */}
      <SafeAreaView edges={['bottom']} style={[styles.bottomContainer, { backgroundColor: colors.card, borderTopColor: colors.border }]}>
        <View style={[styles.bottomSeparator, { backgroundColor: colors.border }]} />

        {/* Selector de idioma */}
        <TouchableOpacity
          style={styles.langButton}
          onPress={() => setLangExpanded(!langExpanded)}
          activeOpacity={0.7}
        >
          <View style={styles.langContent}>
            <Text style={styles.langFlag}>{currentLang.flag}</Text>
            <Text style={[styles.langText, { color: colors.text }]}>{t.drawer.language}</Text>
          </View>
          <Ionicons
            name={langExpanded ? 'chevron-up' : 'chevron-down'}
            size={20}
            color={colors.textSecondary}
          />
        </TouchableOpacity>

        {/* Opciones de idioma desplegables */}
        {langExpanded && (
          <View style={[styles.langOptions, { backgroundColor: colors.background, borderColor: colors.border }]}>
            {LANGUAGES.map((lang, index) => (
              <TouchableOpacity
                key={lang.id}
                style={[
                  styles.langOption,
                  { borderBottomColor: colors.border },
                  index === LANGUAGES.length - 1 && styles.langOptionLast,
                ]}
                onPress={() => {
                  setLanguage(lang.id);
                  setLangExpanded(false);
                }}
                activeOpacity={0.7}
              >
                <Text style={styles.langOptionFlag}>{lang.flag}</Text>
                <Text style={[styles.langOptionName, { color: colors.text }]}>{lang.name}</Text>
                {language === lang.id && (
                  <Ionicons name="checkmark" size={20} color={colors.primary} />
                )}
              </TouchableOpacity>
            ))}
          </View>
        )}

        <View style={[styles.bottomSeparator, { backgroundColor: colors.border }]} />

        {/* Botón de tema */}
        <TouchableOpacity
          style={styles.themeButton}
          onPress={toggleTheme}
          activeOpacity={0.7}
        >
          <View style={styles.themeContent}>
            <Ionicons
              name={isDarkMode ? 'sunny' : 'moon'}
              size={24}
              color={isDarkMode ? '#f59e0b' : '#6366f1'}
            />
            <Text style={[styles.themeText, { color: colors.text }]}>
              {isDarkMode ? t.drawer.lightMode : t.drawer.darkMode}
            </Text>
          </View>
          <View style={[styles.themeIndicator, isDarkMode && styles.themeIndicatorActive]}>
            <View style={[styles.themeToggle, isDarkMode && styles.themeToggleActive]} />
          </View>
        </TouchableOpacity>
      </SafeAreaView>

      {/* Modal de confirmación de cierre de sesión (respeta tema) */}
      <Modal
        transparent
        visible={logoutConfirmOpen}
        animationType="fade"
        statusBarTranslucent
        onRequestClose={() => setLogoutConfirmOpen(false)}
      >
        <Pressable
          style={styles.modalBackdrop}
          onPress={() => setLogoutConfirmOpen(false)}
        >
          {/* Pressable interno con onPress vacío evita que un toque sobre el
              card cierre el modal por burbuja del onPress del backdrop. */}
          <Pressable
            style={[styles.modalCard, { backgroundColor: colors.card, borderColor: colors.border }]}
            onPress={() => {}}
          >
            <View style={[styles.modalIconWrap, { backgroundColor: '#fee2e2' }]}>
              <Ionicons name="log-out-outline" size={28} color="#ef4444" />
            </View>
            <Text style={[styles.modalTitle, { color: colors.text }]}>
              {t.auth.logoutConfirmTitle}
            </Text>
            <Text style={[styles.modalMessage, { color: colors.textSecondary }]}>
              {t.auth.logoutConfirmMessage}
            </Text>
            <View style={styles.modalButtonRow}>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnSecondary, { borderColor: colors.border }]}
                onPress={() => setLogoutConfirmOpen(false)}
                activeOpacity={0.7}
              >
                <Text style={[styles.modalBtnSecondaryText, { color: colors.text }]}>
                  {t.auth.cancel}
                </Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBtnDanger]}
                onPress={async () => {
                  setLogoutConfirmOpen(false);
                  props.navigation.closeDrawer();
                  await logout();
                }}
                activeOpacity={0.85}
              >
                <Text style={styles.modalBtnDangerText}>{t.auth.logout}</Text>
              </TouchableOpacity>
            </View>
          </Pressable>
        </Pressable>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  drawerContainer: {
    flex: 1,
  },
  scrollContent: {
    paddingBottom: 0,
  },
  separator: {
    height: 1,
    marginVertical: 10,
    marginHorizontal: 20,
  },

  // Contenedor inferior
  bottomContainer: {
    borderTopWidth: 1,
  },
  bottomSeparator: {
    height: 1,
  },

  // Selector de idioma
  langButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 16,
    paddingHorizontal: 20,
  },
  langContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  langFlag: {
    fontSize: 20,
  },
  langText: {
    fontSize: 16,
    fontWeight: '500',
  },
  langOptions: {
    borderTopWidth: 1,
    borderBottomWidth: 1,
  },
  langOption: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: 13,
    paddingHorizontal: 28,
    gap: 14,
    borderBottomWidth: 1,
  },
  langOptionLast: {
    borderBottomWidth: 0,
  },
  langOptionFlag: {
    fontSize: 22,
  },
  langOptionName: {
    fontSize: 15,
    fontWeight: '500',
    flex: 1,
  },

  // Botón de tema
  themeButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    paddingLeft: 20,
  },
  themeContent: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 15,
  },
  themeText: {
    fontSize: 16,
    fontWeight: '500',
  },
  themeIndicator: {
    width: 50,
    height: 28,
    borderRadius: 14,
    backgroundColor: '#e5e7eb',
    padding: 2,
    justifyContent: 'center',
  },
  themeIndicatorActive: {
    backgroundColor: '#3b82f6',
  },
  themeToggle: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: '#fff',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.2,
    shadowRadius: 2,
  },
  themeToggleActive: {
    alignSelf: 'flex-end',
  },

  // Modal de confirmación
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  modalCard: {
    width: '100%',
    maxWidth: 360,
    borderRadius: 16,
    borderWidth: 1,
    paddingVertical: 24,
    paddingHorizontal: 20,
    alignItems: 'center',
    elevation: 10,
    shadowColor:   '#000',
    shadowOffset:  { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius:  8,
  },
  modalIconWrap: {
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 14,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 6,
    textAlign: 'center',
  },
  modalMessage: {
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 20,
    lineHeight: 20,
  },
  modalButtonRow: {
    flexDirection: 'row',
    width: '100%',
    gap: 10,
  },
  modalBtn: {
    flex: 1,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  modalBtnSecondary: {
    borderWidth: 1,
  },
  modalBtnSecondaryText: {
    fontSize: 15,
    fontWeight: '600',
  },
  modalBtnDanger: {
    backgroundColor: '#ef4444',
  },
  modalBtnDangerText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '700',
  },
});

export default function DrawerLayout() {
  const colors = useThemeColors();

  return (
    <Drawer
      drawerContent={(props) => <CustomDrawerContent {...props} />}
      screenOptions={{
        headerShown: false,
        drawerStyle: {
          backgroundColor: colors.card,
          width: 280,
        },
      }}
    >
      <Drawer.Screen name="(tabs)" />
      <Drawer.Screen name="analysis" />
      <Drawer.Screen name="calibrate" />
      <Drawer.Screen name="settings" />
    </Drawer>
  );
}
