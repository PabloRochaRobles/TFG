import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Alert, Linking, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function AboutScreen() {
  const router = useRouter();
  const navigation = useNavigation();

  const appVersion = '1.0.0';
  const buildNumber = '2026.02.15';

  const handleOpenWebsite = () => {
    Linking.openURL('https://chessvision.app');
  };

  const handleSendEmail = () => {
    Linking.openURL('mailto:soporte@chessvision.app');
  };

  const handleOpenPrivacy = () => {
    Alert.alert('Política de Privacidad', 'Abriendo política de privacidad...');
    // Linking.openURL('https://chessvision.app/privacy');
  };

  const handleOpenTerms = () => {
    Alert.alert('Términos de Uso', 'Abriendo términos de uso...');
    // Linking.openURL('https://chessvision.app/terms');
  };

  const handleOpenLicenses = () => {
    Alert.alert('Licencias', 'Mostrando licencias de código abierto...');
  };

  const handleRateApp = () => {
    Alert.alert('Valorar App', '¡Gracias por tu apoyo! Redirigiendo a la tienda...');
    // Linking.openURL('market://details?id=com.chessvision.app');
  };

  const handleShare = () => {
    Alert.alert('Compartir', '¿Quieres compartir ChessVision con tus amigos?');
  };

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Acerca de</Text>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={28} color="white" />
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
          {/* Logo y nombre de la app */}
          <View style={styles.appInfo}>
            <View style={styles.logoContainer}>
              <FontAwesome5 name="chess" size={60} color="#3b82f6" />
            </View>
            <Text style={styles.appName}>ChessVision</Text>
            <Text style={styles.tagline}>Analiza tus partidas con IA</Text>
            <Text style={styles.version}>Versión {appVersion}</Text>
            <Text style={styles.buildNumber}>Build {buildNumber}</Text>
          </View>

          {/* Descripción */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>¿Qué es ChessVision?</Text>
            <View style={styles.card}>
              <Text style={styles.description}>
                ChessVision es una aplicación innovadora que utiliza inteligencia artificial para 
                analizar partidas de ajedrez grabadas en video. Simplemente graba tu partida con 
                tu smartphone y nuestra IA detectará automáticamente los movimientos, proporcionándote 
                un análisis completo con sugerencias de mejora.
              </Text>
            </View>
          </View>

          {/* Características */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Características principales</Text>
            <View style={styles.card}>
              <View style={styles.featureItem}>
                <FontAwesome5 name="video" size={20} color="#3b82f6" />
                <Text style={styles.featureText}>
                  Detección automática de movimientos mediante grabación de video
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="brain" size={20} color="#3b82f6" />
                <Text style={styles.featureText}>
                  Análisis con motor de ajedrez Stockfish integrado
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="chart-line" size={20} color="#3b82f6" />
                <Text style={styles.featureText}>
                  Estadísticas detalladas de tu progreso y ELO
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="cloud" size={20} color="#3b82f6" />
                <Text style={styles.featureText}>
                  Almacenamiento en la nube de tus partidas
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="book" size={20} color="#3b82f6" />
                <Text style={styles.featureText}>
                  Biblioteca de aperturas y consejos personalizados
                </Text>
              </View>
            </View>
          </View>

          {/* Equipo */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Desarrollado por</Text>
            <View style={styles.card}>
              <Text style={styles.teamInfo}>
                <Text style={styles.bold}>Universidad de Málaga</Text>{'\n'}
                Trabajo Fin de Grado{'\n'}
                Grado en Ingeniería Informática{'\n\n'}
                
                <Text style={styles.bold}>Autor:</Text> [Tu Nombre]{'\n'}
                <Text style={styles.bold}>Tutor:</Text> [Nombre del Tutor]{'\n'}
                <Text style={styles.bold}>Año:</Text> 2026
              </Text>
            </View>
          </View>

          {/* Tecnologías */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Tecnologías utilizadas</Text>
            <View style={styles.techGrid}>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>React Native</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>Expo</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>TensorFlow</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>OpenCV</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>Stockfish</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>Node.js</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>Python</Text>
              </View>
              <View style={styles.techBadge}>
                <Text style={styles.techText}>PostgreSQL</Text>
              </View>
            </View>
          </View>

          {/* Contacto y enlaces */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Contacto y soporte</Text>
            <View style={styles.card}>
              <TouchableOpacity style={styles.linkItem} onPress={handleOpenWebsite}>
                <View style={styles.linkLeft}>
                  <Ionicons name="globe-outline" size={24} color="#3b82f6" />
                  <Text style={styles.linkText}>Sitio web</Text>
                </View>
                <Ionicons name="open-outline" size={20} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.linkItem} onPress={handleSendEmail}>
                <View style={styles.linkLeft}>
                  <Ionicons name="mail-outline" size={24} color="#3b82f6" />
                  <Text style={styles.linkText}>soporte@chessvision.app</Text>
                </View>
                <Ionicons name="open-outline" size={20} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.linkItem}>
                <View style={styles.linkLeft}>
                  <FontAwesome5 name="twitter" size={22} color="#3b82f6" />
                  <Text style={styles.linkText}>@ChessVisionApp</Text>
                </View>
                <Ionicons name="open-outline" size={20} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.linkItem}>
                <View style={styles.linkLeft}>
                  <FontAwesome5 name="instagram" size={22} color="#3b82f6" />
                  <Text style={styles.linkText}>@chessvision</Text>
                </View>
                <Ionicons name="open-outline" size={20} color="#9ca3af" />
              </TouchableOpacity>
            </View>
          </View>

          {/* Legal */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Legal</Text>
            <View style={styles.card}>
              <TouchableOpacity style={styles.linkItem} onPress={handleOpenPrivacy}>
                <View style={styles.linkLeft}>
                  <Ionicons name="shield-checkmark-outline" size={24} color="#6b7280" />
                  <Text style={styles.linkText}>Política de Privacidad</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.linkItem} onPress={handleOpenTerms}>
                <View style={styles.linkLeft}>
                  <Ionicons name="document-text-outline" size={24} color="#6b7280" />
                  <Text style={styles.linkText}>Términos de Uso</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.linkItem} onPress={handleOpenLicenses}>
                <View style={styles.linkLeft}>
                  <Ionicons name="code-slash-outline" size={24} color="#6b7280" />
                  <Text style={styles.linkText}>Licencias de código abierto</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color="#9ca3af" />
              </TouchableOpacity>
            </View>
          </View>

          {/* Acciones */}
          <View style={styles.section}>
            <TouchableOpacity style={styles.actionButton} onPress={handleRateApp}>
              <Ionicons name="star" size={24} color="#f59e0b" />
              <Text style={styles.actionButtonText}>Valorar en la tienda</Text>
            </TouchableOpacity>

            <TouchableOpacity style={[styles.actionButton, styles.secondaryButton]} onPress={handleShare}>
              <Ionicons name="share-social" size={24} color="#3b82f6" />
              <Text style={[styles.actionButtonText, styles.secondaryButtonText]}>
                Compartir con amigos
              </Text>
            </TouchableOpacity>
          </View>

          {/* Copyright */}
          <View style={styles.footer}>
            <Text style={styles.copyright}>
              © 2026 ChessVision. Todos los derechos reservados.
            </Text>
            <Text style={styles.madeWith}>
              Hecho con ♟️ para la comunidad de ajedrez
            </Text>
          </View>

          {/* Espacio inferior */}
          <View style={{ height: 40 }} />
        </ScrollView>
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
  menuButton: {
    padding: 5,
  },
  headerTitle: { 
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold',
  },
  scrollView: {
    flex: 1,
    backgroundColor: '#F8F9FA',
  },
  content: {
    paddingTop: 30,
    paddingHorizontal: 20,
  },

  // Info de la app
  appInfo: {
    alignItems: 'center',
    marginBottom: 30,
  },
  logoContainer: {
    width: 100,
    height: 100,
    borderRadius: 50,
    backgroundColor: '#eff6ff',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 15,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
  },
  appName: {
    fontSize: 32,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 8,
  },
  tagline: {
    fontSize: 16,
    color: '#6b7280',
    marginBottom: 15,
  },
  version: {
    fontSize: 15,
    color: '#3b82f6',
    fontWeight: '600',
  },
  buildNumber: {
    fontSize: 12,
    color: '#9ca3af',
    marginTop: 4,
  },

  // Secciones
  section: {
    marginBottom: 25,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 12,
  },
  card: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },

  // Descripción
  description: {
    fontSize: 15,
    color: '#4b5563',
    lineHeight: 24,
  },

  // Características
  featureItem: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    marginBottom: 16,
    gap: 12,
  },
  featureText: {
    flex: 1,
    fontSize: 15,
    color: '#4b5563',
    lineHeight: 22,
  },

  // Equipo
  teamInfo: {
    fontSize: 15,
    color: '#4b5563',
    lineHeight: 24,
  },
  bold: {
    fontWeight: '700',
    color: '#1f2937',
  },

  // Tecnologías
  techGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  techBadge: {
    backgroundColor: '#eff6ff',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
    borderColor: '#bfdbfe',
  },
  techText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#3b82f6',
  },

  // Enlaces
  linkItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  linkLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  linkText: {
    fontSize: 15,
    color: '#1f2937',
  },

  // Botones de acción
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#3b82f6',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
    marginBottom: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  actionButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  secondaryButton: {
    backgroundColor: '#fff',
    borderWidth: 2,
    borderColor: '#3b82f6',
  },
  secondaryButtonText: {
    color: '#3b82f6',
  },

  // Footer
  footer: {
    alignItems: 'center',
    marginTop: 20,
    paddingTop: 20,
    borderTopWidth: 1,
    borderTopColor: '#e5e7eb',
  },
  copyright: {
    fontSize: 13,
    color: '#6b7280',
    marginBottom: 8,
    textAlign: 'center',
  },
  madeWith: {
    fontSize: 14,
    color: '#9ca3af',
    textAlign: 'center',
  },
});