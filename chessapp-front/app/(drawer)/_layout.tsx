import { FontAwesome, Ionicons } from '@expo/vector-icons';
import { DrawerContentScrollView, DrawerItem } from '@react-navigation/drawer';
import { useRouter } from 'expo-router';
import { Drawer } from 'expo-router/drawer';
import { StyleSheet, View } from 'react-native';

function CustomDrawerContent(props: any) {
  const router = useRouter();
  const DrawerSeparator = () => (<View style={styles.separator} />);

  return (
    <DrawerContentScrollView {...props}>

      
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
  );
}

const styles = StyleSheet.create({
  separator: {
    height: 1,
    backgroundColor: '#e5e7eb',
    marginVertical: 10,
    marginHorizontal: 20,
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