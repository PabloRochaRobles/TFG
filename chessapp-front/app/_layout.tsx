import { DarkTheme, DefaultTheme, ThemeProvider as NavThemeProvider } from '@react-navigation/native';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { useEffect } from 'react';
import { ActivityIndicator, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import 'react-native-reanimated';
import { AuthProvider, useAuth } from './contexts/AuthContext';
import { LanguageProvider } from './contexts/LanguageContext';
import { ThemeProvider } from './contexts/ThemeContext';

import { useColorScheme } from '@/hooks/use-color-scheme';
import { useThemeColors } from '@/hooks/use-theme-color';

/**
 * Componente que vive DENTRO del AuthProvider y redirige automáticamente
 * según el estado de la sesión:
 *   - Si la sesión sigue hidratándose → muestra un loader.
 *   - Si NO hay sesión y el usuario está fuera de (auth) → redirige a login.
 *   - Si HAY sesión y el usuario está en (auth) → redirige al home.
 */
function RouteGuard({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, loading } = useAuth();
  const segments = useSegments();
  const router   = useRouter();
  const colors   = useThemeColors();

  useEffect(() => {
    if (loading) return;
    const inAuthGroup = segments[0] === '(auth)';
    if (!isAuthenticated && !inAuthGroup) {
      router.replace('/(auth)/login');
    } else if (isAuthenticated && inAuthGroup) {
      router.replace('/(drawer)/(tabs)');
    }
  }, [isAuthenticated, loading, segments, router]);

  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.background }}>
        <ActivityIndicator color={colors.primary} size="large" />
      </View>
    );
  }
  return <>{children}</>;
}

export default function RootLayout() {
  const colorScheme = useColorScheme();

  return (
    <ThemeProvider>
      <LanguageProvider>
        <AuthProvider>
          <GestureHandlerRootView style={{ flex: 1 }}>
            <NavThemeProvider value={colorScheme === 'dark' ? DarkTheme : DefaultTheme}>
              <RouteGuard>
                <Stack screenOptions={{ headerShown: false }}>
                  <Stack.Screen name="(drawer)" />
                  <Stack.Screen name="(auth)" />
                </Stack>
              </RouteGuard>
              <StatusBar style="auto" />
            </NavThemeProvider>
          </GestureHandlerRootView>
        </AuthProvider>
      </LanguageProvider>
    </ThemeProvider>
  );
}