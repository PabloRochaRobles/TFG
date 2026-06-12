/**
 * AuthContext — estado global de autenticación.
 *
 * Expone:
 *   email             → email del usuario actual o null
 *   loading           → true mientras se hidrata el SecureStore al arranque
 *   isAuthenticated   → email !== null
 *   login(email, pw)
 *   register(email, pw)
 *   logout()
 *
 * El estado vive aquí, pero los tokens en sí los gestiona `tokenStore`
 * (singleton fuera del árbol React) para que `apiFetch` pueda leerlos
 * sin acceder al contexto.
 */

import React, { createContext, ReactNode, useContext, useEffect, useState } from 'react';

import { API_BASE_URL } from '@/constants/api';
import { tokenStore }   from '@/lib/tokenStorage';

type AuthState = {
  email:           string | null;
  loading:         boolean;
  isAuthenticated: boolean;
  login:    (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout:   () => Promise<void>;
};

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [email,   setEmail]   = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Hidratar tokens persistidos al arrancar la app.
  useEffect(() => {
    let mounted = true;
    (async () => {
      await tokenStore.hydrate();
      if (mounted) {
        setEmail(tokenStore.getEmail());
        setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  // Reaccionar a cambios externos en el tokenStore (p.ej. el refresh
  // automático de apiFetch falla y limpia la sesión).
  useEffect(() => {
    return tokenStore.subscribe(() => {
      setEmail(tokenStore.getEmail());
    });
  }, []);

  const login = async (emailInput: string, password: string) => {
    const r = await fetch(`${API_BASE_URL}/api/auth/login/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email: emailInput, password }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({} as any));
      throw new Error(data.detail || 'Credenciales incorrectas.');
    }
    const data = await r.json();
    await tokenStore.setSession({
      access:  data.access,
      refresh: data.refresh,
      email:   emailInput,
    });
    setEmail(emailInput);
  };

  const register = async (emailInput: string, password: string) => {
    const r = await fetch(`${API_BASE_URL}/api/auth/register/`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email: emailInput, password }),
    });
    if (!r.ok) {
      const data = await r.json().catch(() => ({} as any));
      const msg =
        (Array.isArray(data.email)    && data.email[0])    ||
        (Array.isArray(data.password) && data.password[0]) ||
        data.detail ||
        'Error al registrar.';
      throw new Error(msg);
    }
    const data = await r.json();
    await tokenStore.setSession({
      access:  data.access,
      refresh: data.refresh,
      email:   data.email,
    });
    setEmail(data.email);
  };

  const logout = async () => {
    await tokenStore.clear();
    setEmail(null);
  };

  return (
    <AuthContext.Provider value={{
      email,
      loading,
      isAuthenticated: email !== null,
      login,
      register,
      logout,
    }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth debe usarse dentro de un AuthProvider.');
  return ctx;
}
