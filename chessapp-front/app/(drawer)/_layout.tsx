import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { DrawerContentScrollView, DrawerItem } from '@react-navigation/drawer';
import { useRouter } from 'expo-router';
import { Drawer } from 'expo-router/drawer';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { useTheme } from '../contexts/ThemeContext';

function CustomDrawerContent(props: any) {
  const router = useRouter();
  const { isDarkMode, toggleTheme } = useTheme();
  const DrawerSeparator = () => (<View style={styles.separator} />);

  return (
    <View style={styles.drawerContainer}>
      <DrawerContentScrollView {...props} contentContainerStyle={styles.scrollContent}>
        <DrawerItem
          label="Chess Analyzer"
          icon={({ color, size }) => (
            <Ionicons name="menu" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerSeparator />
        
        <DrawerItem
          label="Inicio"
          icon={({ color, size }) => (
            <FontAwesome name="home" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerItem
          label="Subir video"
          icon={({ color, size }) => (
            <FontAwesome name="upload" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/upload');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />
        
        <DrawerItem
          label="Grabar video"
          icon={({ color, size }) => (
            <FontAwesome name="camera" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/camera');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />
        
        <DrawerItem
          label="Mi librería"
          icon={({ color, size }) => (
            <FontAwesome name="bookmark" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/library');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerItem
          label="Usuario"
          icon={({ color, size }) => (
            <FontAwesome name="user" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/user');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />

        <DrawerSeparator />

        <DrawerItem
          label="Ajustes"
          icon={({ color, size }) => (
            <Ionicons name="settings" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/settings');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />
        
        <DrawerItem
          label="Acerca de"
          icon={({ color, size }) => (
            <Ionicons name="information-circle" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/about');
          }}
          activeTintColor="#3b82f6"
          activeBackgroundColor="#e0f2fe"
          inactiveTintColor="#000"
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />
      </DrawerContentScrollView>

      {/* Botón de tema en la parte inferior */}
      <View style={styles.themeContainer}>
        <View style={styles.themeSeparator} />
        <TouchableOpacity 
          style={styles.themeButton}
          onPress={toggleTheme}
          activeOpacity={0.7}
        >
          <View style={styles.themeContent}>
            <Ionicons 
              name={isDarkMode ? "sunny" : "moon"} 
              size={24} 
              color={isDarkMode ? "#f59e0b" : "#6366f1"} 
            />
            <Text style={styles.themeText}>
              {isDarkMode ? "Modo Claro" : "Modo Oscuro"}
            </Text>
          </View>
          <View style={[styles.themeIndicator, isDarkMode && styles.themeIndicatorActive]}>
            <View style={[styles.themeToggle, isDarkMode && styles.themeToggleActive]} />
          </View>
        </TouchableOpacity>
      </View>
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
    backgroundColor: '#e5e7eb',
    marginVertical: 10,
    marginHorizontal: 20,
  },

  // Botón de tema
  themeContainer: {
    backgroundColor: '#fff',
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
    paddingBottom: 20,
  },
  themeSeparator: {
    height: 1,
    backgroundColor: '#e5e7eb',
  },
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
    color: '#1f2937',
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
});

export default function DrawerLayout() {
  return (
    <Drawer
      drawerContent={(props) => <CustomDrawerContent {...props} />}
      screenOptions={{
        headerShown: false,
        drawerStyle: {
          backgroundColor: '#fff',
          width: 280,
        },
      }}
    >
      <Drawer.Screen name="(tabs)" />
      <Drawer.Screen name="settings" />
      <Drawer.Screen name="about" />
    </Drawer>
  );
}