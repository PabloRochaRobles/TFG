/**
 * Wrapper sobre `fetch` que automáticamente:
 *  - Añade `Authorization: Bearer <access>` si hay sesión.
 *  - On 401, intenta renovar el access vía `/api/auth/refresh/` y reintenta.
 *  - Si el refresh falla, limpia la sesión (el AuthContext, suscrito al
 *    tokenStore, recibe la notificación y dispara la redirección a login).
 *
 * Las llamadas existentes en `constants/api.ts` se migrarán a este helper
 * progresivamente. Acepta tanto rutas relativas (`/api/partidas/list/`)
 * como URLs absolutas.
 */

import { API_BASE_URL } from '@/constants/api';
import { tokenStore } from './tokenStorage';

let refreshInFlight: Promise<boolean> | null = null;

async function tryRefresh(): Promise<boolean> {
  // Si ya hay un refresh en marcha, esperamos a ese (evita N peticiones
  // simultáneas que pidan refresh todas a la vez).
  if (refreshInFlight) return refreshInFlight;

  const refresh = tokenStore.getRefresh();
  if (!refresh) return false;

  refreshInFlight = (async () => {
    try {
      const r = await fetch(`${API_BASE_URL}/api/auth/refresh/`, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json' },
        body:    JSON.stringify({ refresh }),
      });
      if (!r.ok) return false;
      const data = await r.json();
      if (!data.access) return false;
      await tokenStore.setAccess(data.access);
      return true;
    } catch {
      return false;
    } finally {
      // Permitir nuevos refresh tras este (en el siguiente tick).
      setTimeout(() => { refreshInFlight = null; }, 0);
    }
  })();

  return refreshInFlight;
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE_URL}${path}`;

  const buildHeaders = (): Record<string, string> => {
    const headers: Record<string, string> = {
      ...(init.headers as Record<string, string> | undefined ?? {}),
    };
    const access = tokenStore.getAccess();
    if (access) headers['Authorization'] = `Bearer ${access}`;
    return headers;
  };

  let res = await fetch(url, { ...init, headers: buildHeaders() });

  if (res.status === 401) {
    const refreshed = await tryRefresh();
    if (refreshed) {
      res = await fetch(url, { ...init, headers: buildHeaders() });
    } else {
      // Refresh fallido o ausente: limpia sesión. El AuthContext escucha
      // este cambio y redirigirá al login.
      await tokenStore.clear();
    }
  }

  return res;
}

/** Helper para POST JSON con manejo de error y deserialización. */
export async function apiPostJson<T = unknown>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch(path, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`POST ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

/** Helper para GET JSON. */
export async function apiGetJson<T = unknown>(path: string): Promise<T> {
  const res = await apiFetch(path);
  if (!res.ok) {
    const text = await res.text().catch(() => '');
    throw new Error(`GET ${path} → ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}
