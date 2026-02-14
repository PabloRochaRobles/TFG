import { FontAwesome } from '@expo/vector-icons';
import { Tabs } from 'expo-router';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

export default function TabLayout() {
  const insets = useSafeAreaInsets();

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: '#3b82f6',
        tabBarInactiveTintColor: 'gray',
        tabBarShowLabel: false,
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopWidth: 1,
          borderTopColor: '#e5e7eb',
          height: 60 + insets.bottom, // Altura dinámica según el dispositivo
          paddingBottom: insets.bottom, // Padding inferior dinámico
          paddingTop: 8,
        },
        tabBarIconStyle: {
          marginTop: 0, // Ajusta la posición del ícono para que quede centrado
        },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Inicio',
          tabBarIcon: ({ color, size }) => (
            <FontAwesome name="home" size={size} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="upload"
        options={{
          title: 'Subir',
          tabBarIcon: ({ color, size }) => (
            <FontAwesome name="upload" size={size} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="camera"
        options={{
          title: 'Cámara',
          tabBarIcon: ({ color, size }) => (
            <FontAwesome name="camera" size={size} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="library"
        options={{
          title: 'Librería',
          tabBarIcon: ({ color, size }) => (
            <FontAwesome name="bookmark" size={size} color={color} />
          ),
        }}
      />

      <Tabs.Screen
        name="user"
        options={{
          title: 'Usuario',
          tabBarIcon: ({ color, size }) => (
            <FontAwesome name="user" size={size} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}