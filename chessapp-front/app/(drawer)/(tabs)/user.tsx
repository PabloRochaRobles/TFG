import { FontAwesome5, Ionicons } from '@expo/vector-icons';
import { DrawerActions } from '@react-navigation/native';
import { useNavigation, useRouter } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { Alert, Image, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

export default function UserScreen() {
  const router = useRouter();
  const navigation = useNavigation();

  // Datos del usuario (mock data - reemplazar con backend)
  const userData = {
    name: 'Juan Pérez',
    email: 'juan.perez@email.com',
    avatar: 'https://via.placeholder.com/150', // URL del avatar
    // O usa una imagen local: require('../../../assets/images/default-avatar.png')
    level: 'Intermedio',
    elo: 1650,
    gamesPlayed: 42,
    gamesWon: 28,
    gamesLost: 10,
    gamesDraw: 4,
    memberSince: 'Enero 2026',
    streak: 7, // Días consecutivos
  };

  const handleEditProfile = () => {
    Alert.alert('Editar perfil', 'Función próximamente disponible');
  };

  const handleLogout = () => {
    Alert.alert(
      'Cerrar sesión',
      '¿Estás seguro de que quieres cerrar sesión?',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'Cerrar sesión', onPress: () => console.log('Sesión cerrada'), style: 'destructive' },
      ]
    );
  };

  const winRate = ((userData.gamesWon / userData.gamesPlayed) * 100).toFixed(1);

  return (
    <>
      <StatusBar style="light" />
      <SafeAreaView style={styles.container} edges={['top']}>
        {/* Header */}
        <View style={styles.header}>
          <TouchableOpacity 
            style={styles.menuButton}
            onPress={() => navigation.dispatch(DrawerActions.openDrawer())}
          >
            <Ionicons name="menu" size={30} color="white" />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Mi Perfil</Text>
          <TouchableOpacity 
            style={styles.settingsButton}
            onPress={() => router.push('/settings')}
          >
            <Ionicons name="settings-outline" size={28} color="white" />
          </TouchableOpacity>
        </View>

        <ScrollView style={styles.scrollView} contentContainerStyle={styles.content}>
          {/* Tarjeta de perfil principal */}
          <View style={styles.profileCard}>
            {/* Avatar y nombre */}
            <View style={styles.profileHeader}>
              <View style={styles.avatarContainer}>
                <Image 
                  source={{ uri: userData.avatar }}
                  // O local: source={require('../../../assets/images/default-avatar.png')}
                  style={styles.avatar}
                />
                <TouchableOpacity style={styles.editAvatarButton}>
                  <Ionicons name="camera" size={18} color="white" />
                </TouchableOpacity>
              </View>
              
              <View style={styles.profileInfo}>
                <Text style={styles.userName}>{userData.name}</Text>
                <Text style={styles.userEmail}>{userData.email}</Text>
                <View style={styles.levelBadge}>
                  <FontAwesome5 name="chess-knight" size={14} color="#3b82f6" />
                  <Text style={styles.levelText}>{userData.level}</Text>
                </View>
              </View>
            </View>

            {/* Botón editar perfil */}
            <TouchableOpacity style={styles.editButton} onPress={handleEditProfile}>
              <Ionicons name="create-outline" size={20} color="#3b82f6" />
              <Text style={styles.editButtonText}>Editar perfil</Text>
            </TouchableOpacity>
          </View>

          {/* Estadísticas principales */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Estadísticas</Text>
            
            <View style={styles.statsGrid}>
              {/* ELO Rating */}
              <View style={styles.statCard}>
                <View style={styles.statIconContainer}>
                  <FontAwesome5 name="trophy" size={24} color="#f59e0b" />
                </View>
                <Text style={styles.statValue}>{userData.elo}</Text>
                <Text style={styles.statLabel}>Rating ELO</Text>
              </View>

              {/* Partidas jugadas */}
              <View style={styles.statCard}>
                <View style={styles.statIconContainer}>
                  <FontAwesome5 name="chess" size={24} color="#3b82f6" />
                </View>
                <Text style={styles.statValue}>{userData.gamesPlayed}</Text>
                <Text style={styles.statLabel}>Partidas</Text>
              </View>

              {/* Win rate */}
              <View style={styles.statCard}>
                <View style={styles.statIconContainer}>
                  <Ionicons name="trending-up" size={28} color="#10b981" />
                </View>
                <Text style={styles.statValue}>{winRate}%</Text>
                <Text style={styles.statLabel}>Victoria</Text>
              </View>

              {/* Racha */}
              <View style={styles.statCard}>
                <View style={styles.statIconContainer}>
                  <Ionicons name="flame" size={28} color="#ef4444" />
                </View>
                <Text style={styles.statValue}>{userData.streak}</Text>
                <Text style={styles.statLabel}>Días racha</Text>
              </View>
            </View>
          </View>

          {/* Resultados detallados */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Resultados</Text>
            
            <View style={styles.resultsCard}>
              {/* Victorias */}
              <View style={styles.resultRow}>
                <View style={styles.resultLeft}>
                  <View style={[styles.resultDot, { backgroundColor: '#10b981' }]} />
                  <Text style={styles.resultLabel}>Victorias</Text>
                </View>
                <Text style={styles.resultValue}>{userData.gamesWon}</Text>
              </View>

              {/* Derrotas */}
              <View style={styles.resultRow}>
                <View style={styles.resultLeft}>
                  <View style={[styles.resultDot, { backgroundColor: '#ef4444' }]} />
                  <Text style={styles.resultLabel}>Derrotas</Text>
                </View>
                <Text style={styles.resultValue}>{userData.gamesLost}</Text>
              </View>

              {/* Empates */}
              <View style={styles.resultRow}>
                <View style={styles.resultLeft}>
                  <View style={[styles.resultDot, { backgroundColor: '#6b7280' }]} />
                  <Text style={styles.resultLabel}>Empates</Text>
                </View>
                <Text style={styles.resultValue}>{userData.gamesDraw}</Text>
              </View>
            </View>
          </View>

          {/* Información de la cuenta */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Información de la cuenta</Text>
            
            <View style={styles.infoCard}>
              <View style={styles.infoRow}>
                <View style={styles.infoLeft}>
                  <Ionicons name="calendar-outline" size={22} color="#6b7280" />
                  <Text style={styles.infoLabel}>Miembro desde</Text>
                </View>
                <Text style={styles.infoValue}>{userData.memberSince}</Text>
              </View>

              <View style={styles.infoRow}>
                <View style={styles.infoLeft}>
                  <Ionicons name="mail-outline" size={22} color="#6b7280" />
                  <Text style={styles.infoLabel}>Email</Text>
                </View>
                <Text style={styles.infoValue}>{userData.email}</Text>
              </View>

              <TouchableOpacity style={styles.infoRow}>
                <View style={styles.infoLeft}>
                  <Ionicons name="shield-checkmark-outline" size={22} color="#6b7280" />
                  <Text style={styles.infoLabel}>Verificación</Text>
                </View>
                <View style={styles.verifiedBadge}>
                  <Ionicons name="checkmark-circle" size={20} color="#10b981" />
                  <Text style={styles.verifiedText}>Verificado</Text>
                </View>
              </TouchableOpacity>
            </View>
          </View>

          {/* Acciones rápidas */}
          <View style={styles.section}>
            <Text style={styles.sectionTitle}>Acciones</Text>
            
            <View style={styles.actionsCard}>
              <TouchableOpacity style={styles.actionItem} onPress={() => router.push('/library')}>
                <View style={styles.actionLeft}>
                  <Ionicons name="folder-open-outline" size={24} color="#3b82f6" />
                  <Text style={styles.actionText}>Mis partidas</Text>
                </View>
                <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.actionItem}>
                <View style={styles.actionLeft}>
                  <Ionicons name="bar-chart-outline" size={24} color="#3b82f6" />
                  <Text style={styles.actionText}>Ver estadísticas completas</Text>
                </View>
                <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
              </TouchableOpacity>

              <TouchableOpacity style={styles.actionItem}>
                <View style={styles.actionLeft}>
                  <Ionicons name="share-social-outline" size={24} color="#3b82f6" />
                  <Text style={styles.actionText}>Compartir perfil</Text>
                </View>
                <Ionicons name="chevron-forward" size={24} color="#9ca3af" />
              </TouchableOpacity>
            </View>
          </View>

          {/* Botón cerrar sesión */}
          <TouchableOpacity style={styles.logoutButton} onPress={handleLogout}>
            <Ionicons name="log-out-outline" size={24} color="#ef4444" />
            <Text style={styles.logoutText}>Cerrar sesión</Text>
          </TouchableOpacity>

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
  menuButton: { 
    padding: 5,
  },
  settingsButton: {
    padding: 5,
  },
  headerTitle: { 
    color: 'white', 
    fontSize: 22, 
    fontWeight: 'bold' 
  },
  scrollView: {
    flex: 1,
    backgroundColor: '#F8F9FA',
  },
  content: {
    paddingTop: 20,
    paddingHorizontal: 20,
  },

  // Tarjeta de perfil principal
  profileCard: {
    backgroundColor: '#fff',
    borderRadius: 16,
    padding: 20,
    marginBottom: 20,
    elevation: 3,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 3.84,
  },
  profileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 20,
  },
  avatarContainer: {
    position: 'relative',
    marginRight: 20,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#e5e7eb',
  },
  editAvatarButton: {
    position: 'absolute',
    bottom: 0,
    right: 0,
    backgroundColor: '#3b82f6',
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#fff',
  },
  profileInfo: {
    flex: 1,
  },
  userName: {
    fontSize: 22,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 4,
  },
  userEmail: {
    fontSize: 14,
    color: '#6b7280',
    marginBottom: 8,
  },
  levelBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#eff6ff',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 20,
    alignSelf: 'flex-start',
    gap: 6,
  },
  levelText: {
    fontSize: 13,
    fontWeight: '600',
    color: '#3b82f6',
  },
  editButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 12,
    backgroundColor: '#eff6ff',
    borderRadius: 10,
    gap: 8,
  },
  editButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#3b82f6',
  },

  // Secciones
  section: {
    marginBottom: 20,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 12,
  },

  // Grid de estadísticas
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
  },
  statCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
    width: '48%',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  statIconContainer: {
    width: 50,
    height: 50,
    borderRadius: 25,
    backgroundColor: '#f9fafb',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 10,
  },
  statValue: {
    fontSize: 24,
    fontWeight: 'bold',
    color: '#1f2937',
    marginBottom: 4,
  },
  statLabel: {
    fontSize: 13,
    color: '#6b7280',
  },

  // Resultados
  resultsCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    gap: 12,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  resultRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  resultLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  resultDot: {
    width: 12,
    height: 12,
    borderRadius: 6,
  },
  resultLabel: {
    fontSize: 16,
    color: '#4b5563',
  },
  resultValue: {
    fontSize: 18,
    fontWeight: 'bold',
    color: '#1f2937',
  },

  // Información de cuenta
  infoCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 16,
    gap: 16,
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  infoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  infoLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  infoLabel: {
    fontSize: 15,
    color: '#4b5563',
  },
  infoValue: {
    fontSize: 15,
    fontWeight: '500',
    color: '#1f2937',
  },
  verifiedBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  verifiedText: {
    fontSize: 14,
    fontWeight: '600',
    color: '#10b981',
  },

  // Acciones
  actionsCard: {
    backgroundColor: '#fff',
    borderRadius: 12,
    overflow: 'hidden',
    elevation: 2,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
  },
  actionItem: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#f3f4f6',
  },
  actionLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  actionText: {
    fontSize: 16,
    color: '#1f2937',
  },

  // Cerrar sesión
  logoutButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#fff',
    paddingVertical: 16,
    borderRadius: 12,
    gap: 10,
    marginTop: 10,
    borderWidth: 1,
    borderColor: '#fecaca',
  },
  logoutText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#ef4444',
  },
}); 