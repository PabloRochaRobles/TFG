import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useState } from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '@/contexts/ThemeContext';

const STARTING_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// Validador estricto de FEN: 6 campos, 8 rangos de 8 casillas, ambos reyes,
// turno y enroques bien formados, casilla de captura al paso válida y relojes numéricos.
function isValidFEN(rawFen: string): boolean {
  const fen = rawFen.trim();
  if (!fen) return false;

  const parts = fen.split(/\s+/);
  if (parts.length !== 6) return false;

  const [position, turn, castling, enPassant, halfmove, fullmove] = parts;

  const ranks = position.split('/');
  if (ranks.length !== 8) return false;

  let whiteKings = 0;
  let blackKings = 0;
  for (const rank of ranks) {
    if (rank.length === 0) return false;
    let count = 0;
    let prevWasDigit = false;
    for (const ch of rank) {
      if (/[1-8]/.test(ch)) {
        if (prevWasDigit) return false;
        count += parseInt(ch, 10);
        prevWasDigit = true;
      } else if (/[prnbqkPRNBQK]/.test(ch)) {
        count += 1;
        prevWasDigit = false;
        if (ch === 'K') whiteKings++;
        if (ch === 'k') blackKings++;
      } else {
        return false;
      }
    }
    if (count !== 8) return false;
  }
  if (whiteKings !== 1 || blackKings !== 1) return false;

  if (turn !== 'w' && turn !== 'b') return false;

  if (castling !== '-' && !/^(?!.*(.).*\1)[KQkq]{1,4}$/.test(castling)) return false;

  if (enPassant !== '-') {
    if (!/^[a-h][36]$/.test(enPassant)) return false;
    if (turn === 'w' && enPassant[1] !== '6') return false;
    if (turn === 'b' && enPassant[1] !== '3') return false;
  }

  if (!/^\d+$/.test(halfmove)) return false;
  if (!/^[1-9]\d*$/.test(fullmove)) return false;

  return true;
}

export default function AnalyzePositionScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();
  const t = useTranslation();

  const [fen, setFen] = useState('');
  const [errorKey, setErrorKey] = useState<'invalidFen' | 'emptyFen' | null>(null);

  const handleAnalyze = () => {
    const trimmed = fen.trim();
    if (!trimmed) {
      setErrorKey('emptyFen');
      return;
    }
    if (!isValidFEN(trimmed)) {
      setErrorKey('invalidFen');
      return;
    }
    setErrorKey(null);
    router.push({ pathname: '/(drawer)/analysis', params: { fen: trimmed } });
  };

  const handleChangeText = (value: string) => {
    setFen(value);
    if (errorKey) setErrorKey(null);
  };

  const handleUseStarting = () => {
    setFen(STARTING_FEN);
    setErrorKey(null);
  };

  const handleClear = () => {
    setFen('');
    setErrorKey(null);
  };

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
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>
            {t.analyzePosition.title}
          </Text>
        </View>

        <KeyboardAvoidingView
          style={{ flex: 1, backgroundColor: colors.background }}
          behavior={Platform.OS === 'ios' ? 'padding' : undefined}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 60 : 0}
        >
          <ScrollView
            style={styles.scrollView}
            contentContainerStyle={styles.content}
            keyboardShouldPersistTaps="handled"
          >
            <View style={[styles.card, { backgroundColor: colors.card, borderColor: colors.border }]}>
              <Text style={[styles.heading, { color: colors.text }]}>
                {t.analyzePosition.heading}
              </Text>
              <Text style={[styles.description, { color: colors.textSecondary }]}>
                {t.analyzePosition.description}
              </Text>

              <Text style={[styles.label, { color: colors.text }]}>
                {t.analyzePosition.inputLabel}
              </Text>

              <TextInput
                style={[
                  styles.input,
                  {
                    backgroundColor: colors.inputBg,
                    color: colors.text,
                    borderColor: errorKey ? '#ef4444' : colors.border,
                  },
                ]}
                value={fen}
                onChangeText={handleChangeText}
                placeholder={t.analyzePosition.placeholder}
                placeholderTextColor={colors.textSecondary}
                autoCapitalize="none"
                autoCorrect={false}
                multiline
                numberOfLines={3}
                textAlignVertical="top"
              />

              {errorKey && (
                <View style={styles.errorRow}>
                  <Ionicons name="alert-circle" size={16} color="#ef4444" />
                  <Text style={styles.errorText}>{t.analyzePosition[errorKey]}</Text>
                </View>
              )}

              <View style={styles.secondaryRow}>
                <TouchableOpacity
                  style={[styles.secondaryButton, { borderColor: colors.primary, backgroundColor: colors.primaryLight }]}
                  onPress={handleUseStarting}
                  activeOpacity={0.7}
                >
                  <Ionicons name="reload-outline" size={16} color={colors.primary} />
                  <Text style={[styles.secondaryText, { color: colors.primary }]}>
                    {t.analyzePosition.useStartPosition}
                  </Text>
                </TouchableOpacity>
                <TouchableOpacity
                  style={[
                    styles.secondaryButton,
                    {
                      borderColor: '#ef4444',
                      backgroundColor: isDarkMode ? '#3f1f1f' : '#fee2e2',
                      opacity: fen ? 1 : 0.5,
                    },
                  ]}
                  onPress={handleClear}
                  activeOpacity={0.7}
                  disabled={!fen}
                >
                  <Ionicons name="trash-outline" size={16} color="#ef4444" />
                  <Text style={[styles.secondaryText, { color: '#ef4444' }]}>
                    {t.analyzePosition.clear}
                  </Text>
                </TouchableOpacity>
              </View>

              <TouchableOpacity
                style={[styles.primaryButton, { backgroundColor: colors.buttonBg }]}
                onPress={handleAnalyze}
                activeOpacity={0.85}
              >
                <Ionicons name="search" size={20} color={colors.buttonText} />
                <Text style={[styles.primaryButtonText, { color: colors.buttonText }]}>
                  {t.analyzePosition.analyzeButton}
                </Text>
              </TouchableOpacity>
            </View>

          </ScrollView>
        </KeyboardAvoidingView>
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
    padding: 20,
    gap: 16,
    paddingBottom: 40,
  },
  card: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 18,
    gap: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  heading: {
    fontSize: 20,
    fontWeight: '700',
  },
  description: {
    fontSize: 14,
    lineHeight: 20,
  },
  label: {
    fontSize: 14,
    fontWeight: '600',
    marginTop: 4,
  },
  input: {
    borderWidth: 1.5,
    borderRadius: 10,
    padding: 12,
    fontSize: 13,
    fontFamily: Platform.select({ ios: 'Menlo', android: 'monospace', default: 'monospace' }),
    minHeight: 80,
  },
  errorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginTop: -4,
  },
  errorText: {
    color: '#ef4444',
    fontSize: 13,
    fontWeight: '600',
    flex: 1,
  },
  secondaryRow: {
    flexDirection: 'row',
    gap: 10,
  },
  secondaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderRadius: 10,
    borderWidth: 1,
    flex: 1,
  },
  secondaryText: {
    fontSize: 13,
    fontWeight: '600',
  },
  primaryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 14,
    borderRadius: 12,
    marginTop: 4,
  },
  primaryButtonText: {
    fontSize: 16,
    fontWeight: '700',
  },
});
