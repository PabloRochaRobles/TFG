import { Tabs } from 'expo-router';
import React from 'react';

import { HapticTab } from '@/components/haptic-tab';
import { Colors } from '@/constants/theme';
import { useColorScheme } from '@/hooks/use-color-scheme';
import { FontAwesome, FontAwesome6, Ionicons, MaterialIcons } from '@expo/vector-icons';
import { DrawerContentScrollView } from '@react-navigation/drawer';
import { Drawer } from 'expo-router/drawer';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { GestureHandlerRootView } from 'react-native-gesture-handler';

function CustomDrawerContent(props: any) {
  return (
    <View style={{ flex: 1, backgroundColor: '#addbff' }}>
      {/* Espacio superior azul claro */}
      <View style={{ height: 100 }} /> 

      <DrawerContentScrollView {...props} contentContainerStyle={{ backgroundColor: 'white' }}>
        {/* Aquí puedes añadir ítems manuales o usar DrawerItemList */}
        <View style={styles.drawerItem}>
          <Ionicons name="menu" size={24} color="black" />
          <Text style={styles.drawerText}>Chess Analyzer</Text>
        </View>
        
        <View style={styles.separator} />

        <TouchableOpacity style={styles.drawerItem}>
          <MaterialIcons name="upload-file" size={24} color="black" />
          <Text style={styles.drawerText}>Subir vídeo</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.drawerItem}>
          <Ionicons name="camera" size={24} color="black" />
          <Text style={styles.drawerText}>Grabar vídeo</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.drawerItem}>
          <Ionicons name="bookmark" size={24} color="black" />
          <Text style={styles.drawerText}>Mi librería</Text>
        </TouchableOpacity>

        <View style={styles.separator} />

        <TouchableOpacity style={styles.drawerItem}>
          <Ionicons name="settings" size={24} color="black" />
          <Text style={styles.drawerText}>Ajustes</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.drawerItem}>
          <Ionicons name="information-circle" size={24} color="black" />
          <Text style={styles.drawerText}>Acerca de</Text>
        </TouchableOpacity>
      </DrawerContentScrollView>
      
      {/* Espacio inferior azul claro */}
      <View style={{ flex: 1, backgroundColor: '#addbff' }} />
    </View>
  );
}

export default function TabLayout() {
  const colorScheme = useColorScheme();

  return (

    <><GestureHandlerRootView style={{ flex: 1 }}>
      <Drawer
        drawerContent={(props) => <CustomDrawerContent {...props} />}
        screenOptions={{
          headerShown: false, // Lo ocultamos aquí para usar el tuyo personalizado
          drawerStyle: { width: '75%' },
        }} />
    </GestureHandlerRootView>
    
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: Colors[colorScheme ?? 'light'].tint,
        headerShown: false,
        tabBarButton: HapticTab,
      }}>

        <Tabs.Screen
          name="index"
          options={{
            title: 'Home',
            tabBarIcon: ({ color }) => <FontAwesome6 size={28} name="house" color={color} />,
          }} />

        <Tabs.Screen
          name="upload"
          options={{
            title: 'Subir',
            tabBarIcon: ({ color }) => <FontAwesome size={28} name="upload" color={color} />,
          }} />

        <Tabs.Screen
          name="camera"
          options={{
            title: 'Cámara',
            tabBarIcon: ({ color }) => <FontAwesome size={28} name="camera" color={color} />,
          }} />

        <Tabs.Screen
          name="saves"
          options={{
            title: 'Librería',
            tabBarIcon: ({ color }) => <FontAwesome size={28} name="bookmark" color={color} />,
          }} />

        <Tabs.Screen
          name="user"
          options={{
            title: 'Usuario',
            tabBarIcon: ({ color }) => <FontAwesome size={28} name="user" color={color} />,
          }} />
      </Tabs></>
  );
}

const styles = StyleSheet.create({
  drawerItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 15,
    backgroundColor: 'white',
  },
  drawerText: {
    marginLeft: 15,
    fontSize: 18,
    fontWeight: '500',
  },
  separator: {
    height: 20,
    backgroundColor: '#addbff',
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: '#8ecae6',
  },
});
