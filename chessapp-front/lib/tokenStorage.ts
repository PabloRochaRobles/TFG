/**
 * Singleton in-memory + persistencia en `expo-secure-store` para los
 * tokens de autenticación.
 *
 * Funciones puras (no hooks). Cualquier módulo (incluido `apiFetch.ts`,
 * que NO está dentro del árbol de React) puede leer el access token sin
 * acceder al AuthContext.
 *
 * El AuthContext se suscribe vía `subscribe()` para reaccionar a cambios
 * que vengan de fuera (típicamente: refresh fallido tras un 401, que
 * invalida la sesión).
 */

import * as SecureStore from 'expo-secure-store';

const ACCESS_KEY  = 'auth.access';
const REFRESH_KEY = 'auth.refresh';
const EMAIL_KEY   = 'auth.email';

let accessToken:  string | null = null;
let refreshToken: string | null = null;
let email:        string | null = null;

type Listener = () => void;
const listeners = new Set<Listener>();

const notify = () => listeners.forEach(l => l());

export const tokenStore = {
  getAccess():  string | null { return accessToken; },
  getRefresh(): string | null { return refreshToken; },
  getEmail():   string | null { return email; },

  /**
   * Carga los tokens persistidos en SecureStore. Llamar una vez al
   * arrancar la app desde el AuthProvider.
   */
  async hydrate(): Promise<void> {
    accessToken  = await SecureStore.getItemAsync(ACCESS_KEY);
    refreshToken = await SecureStore.getItemAsync(REFRESH_KEY);
    email        = await SecureStore.getItemAsync(EMAIL_KEY);
  },

  /** Guarda una sesión completa (tras login o registro exitoso). */
  async setSession(opts: { access: string; refresh: string; email: string }): Promise<void> {
    accessToken  = opts.access;
    refreshToken = opts.refresh;
    email        = opts.email;
    await SecureStore.setItemAsync(ACCESS_KEY,  opts.access);
    await SecureStore.setItemAsync(REFRESH_KEY, opts.refresh);
    await SecureStore.setItemAsync(EMAIL_KEY,   opts.email);
    notify();
  },

  /** Refresca sólo el access token (cuando renovamos por 401). */
  async setAccess(access: string): Promise<void> {
    accessToken = access;
    await SecureStore.setItemAsync(ACCESS_KEY, access);
  },

  /** Elimina toda la sesión. Logout local. */
  async clear(): Promise<void> {
    accessToken  = null;
    refreshToken = null;
    email        = null;
    await SecureStore.deleteItemAsync(ACCESS_KEY);
    await SecureStore.deleteItemAsync(REFRESH_KEY);
    await SecureStore.deleteItemAsync(EMAIL_KEY);
    notify();
  },

  /** Suscribirse a login/logout/refresh. Devuelve función de unsubscribe. */
  subscribe(listener: Listener): () => void {
    listeners.add(listener);
    return () => { listeners.delete(listener); };
  },
};
