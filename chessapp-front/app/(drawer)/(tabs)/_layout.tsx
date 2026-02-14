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
        tabBarInactiveTintColor: 'rgba(122, 122, 122, 0.5)',
        tabBarShowLabel: false,
        tabBarStyle: {
          backgroundColor: '#fff',
          borderTopWidth: 1,
          borderTopColor: '#000',
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

      <Tabs.Screen
        name="user"
        options={{
          title: 'Usuario',
          tabBarIcon: ({ color }) => (
            <FontAwesome name="user" size={32} color={color} />
          ),
        }}
      />
    </Tabs>
  );
}