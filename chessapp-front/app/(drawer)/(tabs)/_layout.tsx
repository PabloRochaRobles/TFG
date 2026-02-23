import { useThemeColors } from '@/hooks/use-theme-color';
import { FontAwesome } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../contexts/ThemeContext';

export default function TabLayout() {
  const insets = useSafeAreaInsets();
  const { isDarkMode } = useTheme();
  const colors = useThemeColors();

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
      <Tabs.Screen
        name="index"
        options={{
          title: 'Inicio',
          tabBarIcon: ({ color }) => (
            <FontAwesome name="home" size={32} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="upload"
        options={{
          title: 'Subir',
          tabBarIcon: ({ color }) => (
            <FontAwesome name="upload" size={32} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="camera"
        options={{
          title: 'Cámara',
          tabBarIcon: ({ color }) => (
            <FontAwesome name="camera" size={32} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="library"
        options={{
          title: 'Librería',
          tabBarIcon: ({ color }) => (
            <FontAwesome name="bookmark" size={32} color={color} />
          ),
        }}
      />

    </Tabs>
  );
}