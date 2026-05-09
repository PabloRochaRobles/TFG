// ── Configuración de entorno ──────────────────────────────────────────────────
// LOCAL_MODE = true   → conexión por LAN (móvil + PC en la misma WiFi).
// LOCAL_MODE = false  → conexión por internet vía Cloudflare Tunnel
//                       (requiere `cloudflared tunnel --url http://localhost:8000`
//                       corriendo en el PC del backend).
//
// Cómo obtener tu IP local en Windows: `ipconfig` → "Dirección IPv4" del
// adaptador WiFi (p.ej. 192.168.1.42).
const LOCAL_MODE = false;
const LOCAL_IP   = '192.168.1.154';
const LOCAL_PORT = '8000';

// URL pública del Cloudflare Tunnel. Cada vez que arranques `cloudflared
// tunnel --url ...` se genera una distinta — actualízala aquí y vuelve a
// compilar el .apk. Para una URL fija, configurar un named tunnel con
// dominio propio en Cloudflare.
const TUNNEL_HOST = 'chessappanalyzer.onrender.com';

export const API_BASE_URL = LOCAL_MODE
  ? `http://${LOCAL_IP}:${LOCAL_PORT}`
  : `https://${TUNNEL_HOST}`;

// URL base para WebSockets (mismo host, protocolo ws:// / wss://)
export const WS_BASE_URL = LOCAL_MODE
  ? `ws://${LOCAL_IP}:${LOCAL_PORT}`
  : `wss://${TUNNEL_HOST}`;

// La cabecera `Authorization: Bearer <jwt>` la añade automáticamente
// `apiFetch`. `uploadVideo` la añade a mano porque usa XHR (para tener
// progreso de subida) y no puede pasar por `apiFetch`.
import { apiFetch } from '@/app/lib/apiFetch';
import { tokenStore } from '@/app/lib/tokenStorage';

// ── Tipos ─────────────────────────────────────────────────────────────────────

export type EngineResult      = { san: string; uci: string; score: number };
export type ChainStep         = {
  step: number;
  fen_before: string;
  consensus_san: string;
  consensus_uci: string;
  fen_after: string;
  full_agreement: boolean;
  engines: { stockfish: EngineResult; obsidian: EngineResult; plentychess: EngineResult };
};
export type PositionAnalysis  = { initial_fen: string; chain: ChainStep[] };

/** Eventos que puede recibir el callback de watchAnalysis */
export type AnalysisEvent =
  | { type: 'progress';  progress: number }
  | { type: 'fen_ready'; fen: string; index: number }
  | { type: 'complete';  analisis_id: string; total_fens: number; fens: string[]; message: string }
  | { type: 'error';     error: string };

// ── Subida de vídeo ───────────────────────────────────────────────────────────

export function uploadVideo(
  videoUri: string,
  fileName: string,
  onProgress?: (pct: number) => void,
): Promise<{ file: string; id: string; message: string }> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('video_file', { uri: videoUri, name: fileName, type: 'video/mp4' } as any);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/api/partidas/upload/`);

    // XHR no pasa por apiFetch (queremos progreso de subida): añadimos
    // el Bearer manualmente. Si el access ha caducado, el backend
    // devolverá 401 y el usuario tendrá que reautenticarse.
    const access = tokenStore.getAccess();
    if (access) xhr.setRequestHeader('Authorization', `Bearer ${access}`);

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress)
        onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)));
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || 'Error al subir el vídeo'));
      } catch {
        reject(new Error('Respuesta inesperada del servidor'));
      }
    };

    xhr.onerror = () => reject(new Error('Error de red al subir el vídeo'));
    xhr.send(formData);
  });
}

// ── Análisis de vídeo (asíncrono con WebSocket) ───────────────────────────────

/**
 * Inicia el análisis de un vídeo en segundo plano.
 * Devuelve inmediatamente con el task_id para monitorizar vía WebSocket.
 *
 * Casos especiales:
 *  - Si ya existe el análisis en caché y no se envían esquinas nuevas, el
 *    servidor devuelve {from_cache: true, fens: [...]} directamente.
 *  - En ese caso task_id será null y los fens vendrán en la respuesta.
 */
export async function startAnalysis(
  fileName: string,
  corners?: [number, number][],
): Promise<{
  task_id: string | null;
  analisis_id: string;
  message: string;
  from_cache?: boolean;
  fens?: string[];
  total_fens?: number;
}> {
  const body: Record<string, unknown> = { video_file: fileName };
  if (corners) body.corners = corners;

  const response = await apiFetch('/api/partidas/analyze/', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Error al iniciar el análisis');
  }

  return response.json();
}

/**
 * Conecta al WebSocket de progreso y llama a `onEvent` con cada actualización.
 * Devuelve una función `disconnect()` para cerrar la conexión manualmente.
 *
 * Auth del canal: el `task_id` es un UUID generado por el backend y solo se
 * entrega al usuario propietario del análisis tras pasar por `apiFetch`.
 * Nos apoyamos en su unicidad como secret. Si en el futuro queremos
 * endurecer la auth aquí, una opción es pasar el access token como query
 * string (`?token=<jwt>`) y validar en `consumers.py`.
 */
export function watchAnalysis(
  taskId: string,
  onEvent: (event: AnalysisEvent) => void,
): () => void {
  const url = `${WS_BASE_URL}/ws/progress/${taskId}/`;
  const ws  = new WebSocket(url);

  ws.onmessage = (e) => {
    try {
      const data = JSON.parse(e.data) as AnalysisEvent;
      onEvent(data);
    } catch {
      // Mensaje no JSON — ignorar
    }
  };

  ws.onerror = () => {
    onEvent({ type: 'error', error: 'Error de conexión WebSocket' });
  };

  ws.onclose = (e) => {
    // Solo reportar error si el cierre fue inesperado (código ≠ 1000 normal)
    if (e.code !== 1000 && e.code !== 1001) {
      onEvent({ type: 'error', error: `WebSocket cerrado inesperadamente (${e.code})` });
    }
  };

  return () => {
    if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
      ws.close(1000, 'Cliente desconectado voluntariamente');
    }
  };
}

/**
 * Función de alto nivel que combina startAnalysis + watchAnalysis.
 * Gestiona automáticamente el caso de caché (respuesta inmediata sin WebSocket).
 *
 * @param fileName  - Nombre del fichero de vídeo subido
 * @param corners   - Esquinas del tablero (opcional, usa auto-detección si se omite)
 * @param onProgress - Callback con el porcentaje de progreso (0–100)
 * @param onComplete - Callback con el resultado final
 * @param onError    - Callback de error
 * @returns Función para cancelar el análisis en curso
 */
export function analyzeVideoWithProgress(
  fileName: string,
  corners: [number, number][] | undefined,
  onProgress: (pct: number) => void,
  onComplete: (analisisId: string, fens: string[]) => void,
  onError: (message: string) => void,
  onFenReady?: (fen: string, index: number) => void,
): () => void {
  let disconnectWs: (() => void) | null = null;

  startAnalysis(fileName, corners)
    .then((response) => {
      // ── Resultado directo desde caché ──────────────────────────────────────
      if (response.from_cache && response.fens) {
        onProgress(100);
        onComplete(response.analisis_id, response.fens);
        return;
      }

      // ── Análisis asíncrono: seguimiento vía WebSocket ─────────────────────
      if (!response.task_id) {
        onError('El servidor no devolvió un task_id.');
        return;
      }

      disconnectWs = watchAnalysis(response.task_id, (event) => {
        if (event.type === 'progress') {
          onProgress(event.progress);
        } else if (event.type === 'fen_ready') {
          onFenReady?.(event.fen, event.index);
        } else if (event.type === 'complete') {
          onProgress(100);
          onComplete(event.analisis_id, event.fens);
        } else if (event.type === 'error') {
          onError(event.error);
        }
      });
    })
    .catch((err: Error) => onError(err.message));

  return () => { disconnectWs?.(); };
}

// ── Compatibilidad con código antiguo ─────────────────────────────────────────
// analyzeVideo sigue exportada para no romper las pantallas que todavía la usen.
// Internamente usa analyzeVideoWithProgress con una Promise.

export function analyzeVideo(
  fileName: string,
  corners?: [number, number][],
): Promise<{ message: string; total_frames: number; analisis_id: string; total_fens: number; fens: string[] }> {
  return new Promise((resolve, reject) => {
    analyzeVideoWithProgress(
      fileName,
      corners,
      () => {},   // progreso ignorado en modo promesa (usa getAnalysisProgress para polling)
      (analisisId, fens) => resolve({
        message:      'Análisis completado con éxito.',
        total_frames: fens.length - 1,
        analisis_id:  analisisId,
        total_fens:   fens.length,
        fens,
      }),
      (err) => reject(new Error(err)),
    );
  });
}

// ── Progreso HTTP (compatibilidad con código que no use WebSocket) ─────────────

export async function getAnalysisProgress(fileName: string): Promise<number> {
  const response = await apiFetch(
    `/api/partidas/progress/${encodeURIComponent(fileName)}/`,
  );
  if (!response.ok) return 0;
  const data = await response.json();
  return data.progress ?? 0;
}

// ── Listado y borrado de vídeos ───────────────────────────────────────────────

export async function listVideos(): Promise<string[]> {
  const response = await apiFetch('/api/partidas/list/');
  if (!response.ok) throw new Error('Error al obtener la lista de vídeos');
  const data = await response.json();
  return data.videos as string[];
}

export async function deleteVideo(fileName: string): Promise<void> {
  const response = await apiFetch(
    `/api/partidas/delete/${encodeURIComponent(fileName)}/`,
    { method: 'DELETE' },
  );
  if (!response.ok) throw new Error('Error al eliminar el vídeo');
}

// ── Calibración ───────────────────────────────────────────────────────────────

/**
 * Devuelve la primera imagen del vídeo como data URL
 * (`data:image/jpeg;base64,...`) para usar en `<Image source={{ uri }}/>`.
 *
 * Antes era una URL HTTP plana, pero ahora el endpoint requiere el JWT y
 * `<Image>` no permite añadir cabeceras, así que descargamos el blob con
 * `apiFetch` y lo convertimos a base64 (mismo patrón que
 * `fetchWarpedPreview`).
 */
export async function getFirstFrameUrl(fileName: string): Promise<string> {
  const response = await apiFetch(
    `/api/partidas/first-frame/${encodeURIComponent(fileName)}/`,
  );
  if (!response.ok) throw new Error('No se pudo obtener el primer frame');
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror   = reject;
    reader.readAsDataURL(blob);
  });
}

export async function fetchWarpedPreview(
  fileName: string,
  corners: [number, number][],
): Promise<string> {
  const response = await apiFetch(
    `/api/partidas/warped-preview/${encodeURIComponent(fileName)}/`,
    {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ corners }),
    },
  );
  if (!response.ok) throw new Error('No se pudo obtener la previsualización');
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror   = reject;
    reader.readAsDataURL(blob);
  });
}

// ── Análisis de motores ───────────────────────────────────────────────────────

export async function analysisChain(
  fens: string[],
  depth: number = 5,
): Promise<PositionAnalysis[]> {
  const response = await apiFetch('/api/partidas/analysis-chain/', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ fens, depth }),
  });
  if (!response.ok) {
    const error = await response.json().catch(() => ({}));
    throw new Error(error.error || 'Error al calcular las mejores jugadas');
  }
  const data = await response.json();
  return data.results as PositionAnalysis[];
}

export async function getEngineAnalysis(analysisId: string): Promise<PositionAnalysis[] | null> {
  const response = await apiFetch(
    `/api/partidas/engine-analysis/${encodeURIComponent(analysisId)}/`,
  );
  if (response.status === 404) return null;
  if (!response.ok)            return null;
  const data = await response.json();
  return data.results as PositionAnalysis[];
}

export async function saveEngineAnalysis(analysisId: string, results: PositionAnalysis[]): Promise<void> {
  await apiFetch('/api/partidas/engine-analysis/', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify({ analysis_id: analysisId, results }),
  });
}
