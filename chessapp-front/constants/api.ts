// ── Configuración de entorno ──────────────────────────────────────────────────
// LOCAL_MODE = true   → conexión por LAN (móvil + PC en la misma WiFi).
// LOCAL_MODE = false  → conexión por internet vía Cloudflare Tunnel
//                       (requiere `cloudflared tunnel --url http://localhost:8000`
//                       corriendo en el PC del backend).
//
// Cómo obtener tu IP local en Windows: `ipconfig` → "Dirección IPv4" del
// adaptador WiFi (p.ej. 192.168.1.42).
const LOCAL_MODE = true;
const LOCAL_IP   = '192.168.1.156';
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
// Se usa `expo-file-system` (entrypoint legacy) en lugar de XHR + FormData.
// Motivo: con la Nueva Arquitectura de React Native (Expo SDK 54), el upload
// multipart vía `XMLHttpRequest` con `{ uri, name, type }` NO transmite el
// cuerpo del fichero — solo enviaba un stub de ~28 bytes (la cabecera `ftyp`
// del MP4), que el backend rechazaba con "moov atom not found".
// `createUploadTask` hace streaming nativo del fichero desde disco y además
// expone progreso real de subida.
import * as LegacyFileSystem from 'expo-file-system/legacy';

export function uploadVideo(
  videoUri: string,
  fileName: string,
  onProgress?: (pct: number) => void,
): Promise<{ file: string; id: string; message: string }> {
  return new Promise((resolve, reject) => {
    // El backend solo usa la extensión del nombre para nombrar el fichero
    // (genera su propio UUID), así que basta con preservar `.mp4`.
    const access = tokenStore.getAccess();

    // DIAGNÓSTICO: tamaño real del fichero que vamos a subir.
    LegacyFileSystem.getInfoAsync(videoUri)
      .then((info) =>
        console.log('[upload] (expo-file-system) fichero a subir:', JSON.stringify(info)),
      )
      .catch((e) => console.warn('[upload] getInfoAsync falló:', e));

    const task = LegacyFileSystem.createUploadTask(
      `${API_BASE_URL}/api/partidas/upload/`,
      videoUri,
      {
        httpMethod: 'POST',
        uploadType: LegacyFileSystem.FileSystemUploadType.MULTIPART,
        fieldName: 'video_file',
        mimeType: 'video/mp4',
        // El backend deriva el nombre real del fichero de su extensión; aquí
        // solo importa que termine en .mp4.
        parameters: {},
        headers: access ? { Authorization: `Bearer ${access}` } : {},
      },
      (p) => {
        if (onProgress && p.totalBytesExpectedToSend > 0) {
          onProgress(
            Math.min(100, Math.round(
              (p.totalBytesSent / p.totalBytesExpectedToSend) * 100,
            )),
          );
        }
      },
    );

    task
      .uploadAsync()
      .then((res) => {
        if (!res) {
          reject(new Error('Subida cancelada.'));
          return;
        }
        let data: any = {};
        try {
          data = JSON.parse(res.body || '{}');
        } catch {
          reject(new Error('Respuesta inesperada del servidor.'));
          return;
        }
        if (res.status >= 200 && res.status < 300) resolve(data);
        else reject(new Error(data.error || 'Error al subir el vídeo'));
      })
      .catch((e) =>
        reject(e instanceof Error ? e : new Error('Error de red al subir el vídeo')),
      );
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

/**
 * Devuelve el frame rectificado (vista cenital) que el pipeline asoció a
 * la posición `index` de un análisis, como data URL para `<Image>`.
 *
 * El índice 0 (posición inicial) no tiene keyframe: el backend responde
 * 404 y esta función devuelve null. El llamante debe tratar null como
 * "no hay frame real para esta posición".
 */
export async function getKeyframeUrl(
  analysisId: string,
  index: number,
): Promise<string | null> {
  const response = await apiFetch(
    `/api/partidas/keyframe/${encodeURIComponent(analysisId)}/${index}/`,
  );
  if (!response.ok) return null;
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

// ── Análisis en directo desde la cámara ──────────────────────────────────────
// Vía paralela al análisis de vídeo offline. El backend expone:
//   POST /api/partidas/live-session/   → devuelve un task_id (capacidad)
//   WS   /ws/live/<task_id>/           → canal bidireccional para la sesión
// El cliente abre el WS, envía un mensaje `init` con las 4 esquinas del
// tablero, y a partir de ahí remite fotogramas JPEG cuando detecta
// inmovilidad. El servidor responde con eventos `frame_result` y
// `fen_ready`. Para más detalle ver `LiveAnalysisConsumer` en el backend.

export type LiveDecision =
  | 'move'
  | 'no-move'
  | 'low-margin'
  | 'garbage'
  | 'duplicate';

export type LiveEvent =
  | { type: 'ready';        fen: string }
  | { type: 'frame_result';
      decision: LiveDecision;
      score?: number; margin?: number; no_move_score?: number;
      moves?: string[]; fen?: string; index?: number }
  | { type: 'fen_ready';    fen: string; uci_moves: string[]; index: number }
  | { type: 'error';        error: string };

/**
 * Crea una sesión de análisis en directo en el backend y devuelve el
 * `task_id` con el que abrir el WebSocket correspondiente.
 */
export async function createLiveSession(): Promise<string> {
  const response = await apiFetch('/api/partidas/live-session/', {
    method: 'POST',
  });
  if (!response.ok) {
    throw new Error('No se pudo iniciar la sesión en directo.');
  }
  const data = await response.json();
  if (!data.task_id) {
    throw new Error('El servidor no devolvió un task_id válido.');
  }
  return data.task_id as string;
}

/**
 * Abre el WebSocket de análisis en directo y devuelve una API mínima
 * para gobernar la sesión desde el componente de cámara.
 *
 * - `init(corners)` envía las 4 esquinas en píxeles absolutos del
 *   fotograma. Se debe llamar UNA vez tras abrir la conexión.
 * - `sendFrame(buffer)` envía un fotograma JPEG (ArrayBuffer/Uint8Array).
 *   Llamar tras `init`, idealmente solo cuando el dispositivo detecte
 *   inmovilidad sobre el tablero.
 * - `close()` cierra el canal limpiamente.
 * - `isOpen()` indica si el canal está abierto.
 */
export function openLiveAnalysisWS(
  taskId: string,
  onEvent: (event: LiveEvent) => void,
): {
  init:      (corners: [number, number][]) => void;
  sendFrame: (jpeg: ArrayBuffer | Uint8Array) => void;
  close:     () => void;
  isOpen:    () => boolean;
} {
  const url = `${WS_BASE_URL}/ws/live/${taskId}/`;
  const ws  = new WebSocket(url);

  ws.onmessage = (e) => {
    try {
      onEvent(JSON.parse(e.data) as LiveEvent);
    } catch {
      // mensaje no JSON: ignorar
    }
  };
  ws.onerror = () => {
    onEvent({ type: 'error', error: 'Error de conexión WebSocket en directo.' });
  };
  ws.onclose = (e) => {
    if (e.code !== 1000 && e.code !== 1001) {
      onEvent({
        type:  'error',
        error: `WebSocket de directo cerrado inesperadamente (${e.code}).`,
      });
    }
  };

  return {
    init: (corners) => {
      const payload = JSON.stringify({ type: 'init', corners });
      // Si el socket aún no abrió, encolar el envío al abrir.
      if (ws.readyState === WebSocket.OPEN) ws.send(payload);
      else ws.addEventListener('open', () => ws.send(payload), { once: true });
    },
    sendFrame: (jpeg) => {
      if (ws.readyState !== WebSocket.OPEN) return;
      ws.send(jpeg as any);
    },
    close:  () => { if (ws.readyState <= 1) ws.close(1000, 'Cliente cierra sesión en directo'); },
    isOpen: () => ws.readyState === WebSocket.OPEN,
  };
}
