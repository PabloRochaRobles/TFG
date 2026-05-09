import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { Link, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';

import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';

export default function LoginScreen() {
  const t            = useTranslation();
  const router       = useRouter();
  const colors       = useThemeColors();
  const { isDarkMode } = useTheme();
  const { login }    = useAuth();

  const [email,    setEmail]    = useState('');
  const [password, setPassword] = useState('');
  const [showPwd,  setShowPwd]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [loading,  setLoading]  = useState(false);

  const handleSubmit = async () => {
    if (!email.trim() || !password) {
      setError(t.auth.errorRequired);
      return;
    }
    setError(null);
    setLoading(true);
    try {
      await login(email.trim(), password);
      router.replace('/(drawer)/(tabs)');
    } catch (e: any) {
      setError(e.message ?? t.auth.errorGeneric);
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <StatusBar style={isDarkMode ? 'light' : 'dark'} />
      <KeyboardAvoidingView
        style={[styles.container, { backgroundColor: colors.background }]}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <ScrollView
          contentContainerStyle={styles.scroll}
          keyboardShouldPersistTaps="handled"
          showsVerticalScrollIndicator={false}
        >
          {/* Hero: icono de ajedrez sobre círculo azul */}
          <View style={styles.hero}>
            <View style={[styles.heroBadge, { backgroundColor: colors.primary }]}>
              <FontAwesome5 name="chess-king" size={48} color="#fff" />
            </View>
            <Text style={[styles.title, { color: colors.text }]}>
              {t.auth.loginTitle}
            </Text>
            <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
              {t.auth.loginSubtitle}
            </Text>
          </View>

          {/* Card del formulario */}
          <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
            <Text style={[styles.label, { color: colors.text }]}>{t.auth.email}</Text>
            <View style={[styles.inputWrapper, { backgroundColor: colors.inputBg, borderColor: colors.border }]}>
              <Ionicons name="mail-outline" size={20} color={colors.textSecondary} style={styles.inputIcon} />
              <TextInput
                style={[styles.input, { color: colors.text }]}
                value={email}
                onChangeText={setEmail}
                placeholder="ejemplo@correo.com"
                placeholderTextColor={colors.textSecondary}
                autoCapitalize="none"
                autoCorrect={false}
                keyboardType="email-address"
                editable={!loading}
              />
            </View>

            <Text style={[styles.label, { color: colors.text, marginTop: 16 }]}>{t.auth.password}</Text>
            <View style={[styles.inputWrapper, { backgroundColor: colors.inputBg, borderColor: colors.border }]}>
              <Ionicons name="lock-closed-outline" size={20} color={colors.textSecondary} style={styles.inputIcon} />
              <TextInput
                style={[styles.input, { color: colors.text }]}
                value={password}
                onChangeText={setPassword}
                placeholder="••••••••"
                placeholderTextColor={colors.textSecondary}
                secureTextEntry={!showPwd}
                editable={!loading}
              />
              <TouchableOpacity
                onPress={() => setShowPwd((v) => !v)}
                style={styles.eyeBtn}
                hitSlop={{ top: 10, bottom: 10, left: 10, right: 10 }}
                accessibilityRole="button"
                accessibilityLabel={showPwd ? 'Ocultar contraseña' : 'Mostrar contraseña'}
              >
                <Ionicons
                  name={showPwd ? 'eye-off-outline' : 'eye-outline'}
                  size={22}
                  color={colors.textSecondary}
                />
              </TouchableOpacity>
            </View>

            {error && (
              <View style={styles.errorRow}>
                <Ionicons name="alert-circle" size={16} color="#ef4444" />
                <Text style={styles.errorText}>{error}</Text>
              </View>
            )}

            <TouchableOpacity
              style={[styles.submitBtn, { backgroundColor: colors.buttonBg, opacity: loading ? 0.6 : 1 }]}
              onPress={handleSubmit}
              disabled={loading}
              activeOpacity={0.85}
            >
              {loading
                ? <ActivityIndicator color={colors.buttonText} />
                : <Text style={[styles.submitText, { color: colors.buttonText }]}>{t.auth.login}</Text>
              }
            </TouchableOpacity>
          </View>

          {/* Footer: enlace a registro */}
          <View style={styles.footer}>
            <Text style={{ color: colors.textSecondary }}>{t.auth.noAccount}{' '}</Text>
            <Link href="/(auth)/register" replace>
              <Text style={[styles.linkText, { color: colors.primary }]}>{t.auth.register}</Text>
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
  scroll:    { flexGrow: 1, padding: 24, justifyContent: 'center' },

  hero:       { alignItems: 'center', marginBottom: 28 },
  heroBadge:  {
    width: 96,
    height: 96,
    borderRadius: 48,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
    elevation: 5,
    shadowColor:   '#000',
    shadowOffset:  { width: 0, height: 2 },
    shadowOpacity: 0.25,
    shadowRadius:  3.84,
  },
  title:      { fontSize: 28, fontWeight: 'bold' },
  subtitle:   { fontSize: 14, marginTop: 4, textAlign: 'center' },

  card: {
    borderWidth: 1,
    borderRadius: 16,
    padding: 20,
    elevation: 3,
    shadowColor:   '#000',
    shadowOffset:  { width: 0, height: 1 },
    shadowOpacity: 0.15,
    shadowRadius:  3,
  },

  label:        { fontSize: 14, fontWeight: '600', marginBottom: 6 },
  inputWrapper: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderRadius: 12,
    paddingHorizontal: 12,
  },
  inputIcon: { marginRight: 8 },
  input:     { flex: 1, paddingVertical: 12, fontSize: 16 },
  eyeBtn:    { padding: 4, marginLeft: 4 },

  errorRow:  { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12 },
  errorText: { color: '#ef4444', fontSize: 14, flex: 1 },

  submitBtn: {
    borderRadius: 12,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 24,
    elevation: 4,
    shadowColor:   '#000',
    shadowOffset:  { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius:  3,
  },
  submitText: { fontSize: 16, fontWeight: 'bold' },

  footer:   { flexDirection: 'row', justifyContent: 'center', marginTop: 20 },
  linkText: { fontSize: 14, fontWeight: '700' },
});
