import { useThemeColors } from '@/hooks/use-theme-color';
import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Alert, Linking, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

export default function AboutScreen() {
  const router = useRouter();
  const navigation = useNavigation();
  const colors = useThemeColors();
  const { isDarkMode } = useTheme();

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
  };

  const handleOpenTerms = () => {
    Alert.alert('Términos de Uso', 'Abriendo términos de uso...');
  };

  const handleOpenLicenses = () => {
    Alert.alert('Licencias', 'Mostrando licencias de código abierto...');
  };

  const handleRateApp = () => {
    Alert.alert('Valorar App', '¡Gracias por tu apoyo! Redirigiendo a la tienda...');
  };

  const handleShare = () => {
    Alert.alert('Compartir', '¿Quieres compartir ChessVision con tus amigos?');
  };

  return (
    <>
      <StatusBar style={isDarkMode ? "light" : "dark"} />
      <SafeAreaView style={[styles.container, { backgroundColor: colors.headerBg }]} edges={['top']}>
        {/* Header */}
        <View style={[styles.header, { backgroundColor: colors.headerBg }]}>
          <TouchableOpacity 
            style={styles.backButton}
            onPress={() => router.back()}
          >
            <Ionicons name="arrow-back" size={28} color={colors.headerText} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.headerText }]}>Acerca de</Text>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={28} color={colors.headerText} />
          </TouchableOpacity>
        </View>

        <ScrollView style={[styles.scrollView, { backgroundColor: colors.background }]} contentContainerStyle={styles.content}>
          {/* Logo y nombre de la app */}
          <View style={styles.appInfo}>
            <View style={[styles.logoContainer, { backgroundColor: colors.primaryLight }]}>
              <FontAwesome5 name="chess" size={60} color={colors.primary} />
            </View>
            <Text style={[styles.appName, { color: colors.text }]}>ChessVision</Text>
            <Text style={[styles.tagline, { color: colors.textSecondary }]}>Analiza tus partidas con IA</Text>
            <Text style={[styles.version, { color: colors.primary }]}>Versión {appVersion}</Text>
            <Text style={[styles.buildNumber, { color: colors.textSecondary }]}>Build {buildNumber}</Text>
          </View>

          {/* Descripción */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>¿Qué es ChessVision?</Text>
            <View style={[styles.card, { backgroundColor: colors.card }]}>
              <Text style={[styles.description, { color: colors.textSecondary }]}>
                ChessVision es una aplicación innovadora que utiliza inteligencia artificial para 
                analizar partidas de ajedrez grabadas en video. Simplemente graba tu partida con 
                tu smartphone y nuestra IA detectará automáticamente los movimientos, proporcionándote 
                un análisis completo con sugerencias de mejora.
              </Text>
            </View>
          </View>

          {/* Características */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Características principales</Text>
            <View style={[styles.card, { backgroundColor: colors.card }]}>
              <View style={styles.featureItem}>
                <FontAwesome5 name="video" size={20} color={colors.primary} />
                <Text style={[styles.featureText, { color: colors.textSecondary }]}>
                  Detección automática de movimientos mediante grabación de video
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="brain" size={20} color={colors.primary} />
                <Text style={[styles.featureText, { color: colors.textSecondary }]}>
                  Análisis con motor de ajedrez Stockfish integrado
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="chart-line" size={20} color={colors.primary} />
                <Text style={[styles.featureText, { color: colors.textSecondary }]}>
                  Estadísticas detalladas de tu progreso y ELO
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="cloud" size={20} color={colors.primary} />
                <Text style={[styles.featureText, { color: colors.textSecondary }]}>
                  Almacenamiento en la nube de tus partidas
                </Text>
              </View>
              <View style={styles.featureItem}>
                <FontAwesome5 name="book" size={20} color={colors.primary} />
                <Text style={[styles.featureText, { color: colors.textSecondary }]}>
                  Biblioteca de aperturas y consejos personalizados
                </Text>
              </View>
            </View>
          </View>

          {/* Equipo */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Desarrollado por</Text>
            <View style={[styles.card, { backgroundColor: colors.card }]}>
              <Text style={[styles.teamInfo, { color: colors.textSecondary }]}>
                <Text style={[styles.bold, { color: colors.text }]}>Universidad de Málaga</Text>{'\n'}
                Trabajo Fin de Grado{'\n'}
                Grado en Ingeniería Informática{'\n\n'}
                
                <Text style={[styles.bold, { color: colors.text }]}>Autor:</Text> [Tu Nombre]{'\n'}
                <Text style={[styles.bold, { color: colors.text }]}>Tutor:</Text> [Nombre del Tutor]{'\n'}
                <Text style={[styles.bold, { color: colors.text }]}>Año:</Text> 2026
              </Text>
            </View>
          </View>

          {/* Tecnologías */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Tecnologías utilizadas</Text>
            <View style={styles.techGrid}>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>React Native</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>Expo</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>TensorFlow</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>OpenCV</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>Stockfish</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>Node.js</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>Python</Text>
              </View>
              <View style={[styles.techBadge, { backgroundColor: colors.primaryLight, borderColor: colors.primary }]}>
                <Text style={[styles.techText, { color: colors.primary }]}>PostgreSQL</Text>
              </View>
            </View>
          </View>

          {/* Contacto y enlaces */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Contacto y soporte</Text>
            <View style={[styles.card, { backgroundColor: colors.card }]}>
              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]} onPress={handleOpenWebsite}>
                <View style={styles.linkLeft}>
                  <Ionicons name="globe-outline" size={24} color={colors.primary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>Sitio web</Text>
                </View>
                <Ionicons name="open-outline" size={20} color={colors.textSecondary} />
              </TouchableOpacity>

              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]} onPress={handleSendEmail}>
                <View style={styles.linkLeft}>
                  <Ionicons name="mail-outline" size={24} color={colors.primary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>soporte@chessvision.app</Text>
                </View>
                <Ionicons name="open-outline" size={20} color={colors.textSecondary} />
              </TouchableOpacity>

              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]}>
                <View style={styles.linkLeft}>
                  <FontAwesome5 name="twitter" size={22} color={colors.primary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>@ChessVisionApp</Text>
                </View>
                <Ionicons name="open-outline" size={20} color={colors.textSecondary} />
              </TouchableOpacity>

              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]}>
                <View style={styles.linkLeft}>
                  <FontAwesome5 name="instagram" size={22} color={colors.primary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>@chessvision</Text>
                </View>
                <Ionicons name="open-outline" size={20} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Legal */}
          <View style={styles.section}>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Legal</Text>
            <View style={[styles.card, { backgroundColor: colors.card }]}>
              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]} onPress={handleOpenPrivacy}>
                <View style={styles.linkLeft}>
                  <Ionicons name="shield-checkmark-outline" size={24} color={colors.textSecondary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>Política de Privacidad</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
              </TouchableOpacity>

              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]} onPress={handleOpenTerms}>
                <View style={styles.linkLeft}>
                  <Ionicons name="document-text-outline" size={24} color={colors.textSecondary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>Términos de Uso</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
              </TouchableOpacity>

              <TouchableOpacity style={[styles.linkItem, { borderBottomColor: colors.border }]} onPress={handleOpenLicenses}>
                <View style={styles.linkLeft}>
                  <Ionicons name="code-slash-outline" size={24} color={colors.textSecondary} />
                  <Text style={[styles.linkText, { color: colors.text }]}>Licencias de código abierto</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
              </TouchableOpacity>
            </View>
          </View>

          {/* Acciones */}
          <View style={styles.section}>
            <TouchableOpacity style={[styles.actionButton, { backgroundColor: colors.primary }]} onPress={handleRateApp}>
              <Ionicons name="star" size={24} color="#f59e0b" />
              <Text style={styles.actionButtonText}>Valorar en la tienda</Text>
            </TouchableOpacity>

            <TouchableOpacity style={[styles.actionButton, styles.secondaryButton, { backgroundColor: colors.card, borderColor: colors.primary }]} onPress={handleShare}>
              <Ionicons name="share-social" size={24} color={colors.primary} />
              <Text style={[styles.actionButtonText, styles.secondaryButtonText, { color: colors.primary }]}>
                Compartir con amigos
              </Text>
            </TouchableOpacity>
          </View>

          {/* Copyright */}
          <View style={[styles.footer, { borderTopColor: colors.border }]}>
            <Text style={[styles.copyright, { color: colors.textSecondary }]}>
              © 2026 ChessVision. Todos los derechos reservados.
            </Text>
            <Text style={[styles.madeWith, { color: colors.textSecondary }]}>
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
  },
  header: {
    height: 60,
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
    fontSize: 22, 
    fontWeight: 'bold',
  },
  scrollView: {
    flex: 1,
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
    marginBottom: 8,
  },
  tagline: {
    fontSize: 16,
    marginBottom: 15,
  },
  version: {
    fontSize: 15,
    fontWeight: '600',
  },
  buildNumber: {
    fontSize: 12,
    marginTop: 4,
  },

  // Secciones
  section: {
    marginBottom: 25,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    marginBottom: 12,
  },
  card: {
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
    lineHeight: 22,
  },

  // Equipo
  teamInfo: {
    fontSize: 15,
    lineHeight: 24,
  },
  bold: {
    fontWeight: '700',
  },

  // Tecnologías
  techGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  techBadge: {
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 20,
    borderWidth: 1,
  },
  techText: {
    fontSize: 13,
    fontWeight: '600',
  },

  // Enlaces
  linkItem: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  linkLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  linkText: {
    fontSize: 15,
  },

  // Botones de acción
  actionButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
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
    borderWidth: 2,
  },
  secondaryButtonText: {
    // Color aplicado inline
  },

  // Footer
  footer: {
    alignItems: 'center',
    marginTop: 20,
    paddingTop: 20,
    borderTopWidth: 1,
  },
  copyright: {
    fontSize: 13,
    marginBottom: 8,
    textAlign: 'center',
  },
  madeWith: {
    fontSize: 14,
    textAlign: 'center',
  },
});