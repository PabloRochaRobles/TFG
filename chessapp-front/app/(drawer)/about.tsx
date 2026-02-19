import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function AboutScreen() {
  const router = useRouter();

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Acerca de</Text>
          <View style={styles.placeholder} />
        </View>
        
        <View style={styles.content}>
          <Text style={styles.text}>Chess Analyzer v1.0</Text>
        </View>
      </SafeAreaView>
    </>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: '#3b82f6' 
  },
  header: {
    height: 60,
    backgroundColor: '#3b82f6',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 15,
  },
  backButton: {
    padding: 5,
  },
  headerTitle: { 
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold',
    flex: 1,
    textAlign: 'center',
  },
  placeholder: {
    width: 38, // Mismo ancho que el botón de atrás para centrar el título
  },
  content: { 
    flex: 1, 
    backgroundColor: '#F8F9FA', 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  text: { 
    fontSize: 18, 
    color: '#666' 
  },
});