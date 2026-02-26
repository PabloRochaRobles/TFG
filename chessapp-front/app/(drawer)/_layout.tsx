import { useThemeColors } from '@/hooks/use-theme-color';
import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { DrawerContentScrollView, DrawerItem } from '@react-navigation/drawer';
import { useRouter } from 'expo-router';
import { Drawer } from 'expo-router/drawer';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

function CustomDrawerContent(props: any) {
  const router = useRouter();
  const { isDarkMode, toggleTheme } = useTheme();
  const colors = useThemeColors();
  
  const DrawerSeparator = () => (
    <View style={[styles.separator, { backgroundColor: colors.border }]} />
  );

  return (
    <View style={[styles.drawerContainer, { backgroundColor: colors.card }]}>
      <DrawerContentScrollView {...props} contentContainerStyle={styles.scrollContent}>
        <DrawerItem
          label="Chess Analyzer"
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
          label="Inicio"
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
          label="Subir video"
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
          label="Grabar video"
          icon={({ color, size }) => (
            <FontAwesome name="camera" size={size} color={color} />
          )}
          onPress={() => {
            props.navigation.closeDrawer();
            router.push('/(drawer)/(tabs)/camera');
          }}
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
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
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
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
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
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
          activeTintColor={colors.primary}
          activeBackgroundColor={colors.primaryLight}
          inactiveTintColor={colors.text}
          labelStyle={{ fontSize: 18, fontWeight: '500' }}
          style={{ borderRadius: 0, marginVertical: 0, paddingVertical: 5, paddingLeft: 0 }}
        />
      </DrawerContentScrollView>

      {/* Botón de tema en la parte inferior */}
      <SafeAreaView edges={['bottom']} style={[styles.themeContainer, { backgroundColor: colors.card, borderTopColor: colors.border }]}>
        <View style={[styles.themeSeparator, { backgroundColor: colors.border }]} />
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
            <Text style={[styles.themeText, { color: colors.text }]}>
              {isDarkMode ? "Modo Claro" : "Modo Oscuro"}
            </Text>
          </View>
          <View style={[styles.themeIndicator, isDarkMode && styles.themeIndicatorActive]}>
            <View style={[styles.themeToggle, isDarkMode && styles.themeToggleActive]} />
          </View>
        </TouchableOpacity>
      </SafeAreaView>
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

  // Botón de tema
  themeContainer: {
    borderTopWidth: 1,
  },
  themeSeparator: {
    height: 1,
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
      <Drawer.Screen name="settings" />
      <Drawer.Screen name="about" />
    </Drawer>
  );
}