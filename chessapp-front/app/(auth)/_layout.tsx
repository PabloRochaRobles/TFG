import { Stack } from 'expo-router';

/**
 * Layout del grupo de rutas no autenticadas (login/registro).
 * Sin drawer ni tabs — sólo un Stack mínimo.
 */
export default function AuthLayout() {
  return <Stack screenOptions={{ headerShown: false }} />;
}
