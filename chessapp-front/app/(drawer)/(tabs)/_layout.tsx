import { useThemeColors } from '@/hooks/use-theme-color';
import { useTranslation } from '@/hooks/use-translation';
import { FontAwesome } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../contexts/ThemeContext';

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  const { isDarkMode } = useTheme();
  const colors = useThemeColors();
  const t = useTranslation();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: isDarkMode ? 'rgba(156, 163, 175, 0.5)' : 'rgba(122, 122, 122, 0.5)',
        tabBarShowLabel: false,
        tabBarStyle: {
          backgroundColor: colors.tabBar,
          borderTopWidth: 1,
          borderTopColor: colors.tabBarBorder,
          height: 60 + insets.bottom,
          paddingBottom: insets.bottom,
          paddingTop: 8,
        },
        tabBarIconStyle: {
          marginTop: 0,
        },
      }}
    >

      {/* Botón para ir a Inicio */}
      <Tabs.Screen
        name="index"
        options={{
          title: t.tabs.home,
          tabBarIcon: ({ color }) => (
            <FontAwesome name="home" size={30} color={color} />
          ),
        }}
      />

      {/* Botón para ir a Subir vídeo */}
      <Tabs.Screen
        name="upload"
        options={{
          title: t.tabs.upload,
          tabBarIcon: ({ color }) => (
            <FontAwesome name="upload" size={30} color={color} />
          ),
        }}
      />

      {/* Botón para ir a Camara */}
      <Tabs.Screen
        name="camera"
        options={{
          title: t.tabs.camera,
          tabBarIcon: ({ color }) => (
            <FontAwesome name="camera" size={28} color={color} />
          ),
        }}
      />

      {/* Botón para ir a Librería */}
      <Tabs.Screen
        name="library"
        options={{
          title: t.tabs.library,
          tabBarIcon: ({ color }) => (
            <FontAwesome name="bookmark" size={30} color={color} />
          ),
        }}
      />

    </Tabs>
  );
}