// ── Configuración de entorno ──────────────────────────────────────────────────
// Cambia LOCAL_MODE a true para usar la red WiFi local (subida instantánea).
// Cambia LOCAL_MODE a false para usar ngrok (acceso desde fuera de la red).
//
// Para obtener tu IP local en Windows: ejecuta `ipconfig` en la terminal
// y busca "Dirección IPv4" bajo tu adaptador WiFi (p.ej. 192.168.1.42).
const LOCAL_MODE = true;
const LOCAL_IP   = '192.168.1.154';
const LOCAL_PORT = '8000';

export const API_BASE_URL = LOCAL_MODE
  ? `http://${LOCAL_IP}:${LOCAL_PORT}`
  : 'https://conjugated-quintan-michel.ngrok-free.dev';

// URL base para WebSockets (mismo host, protocolo ws:// / wss://)
export const WS_BASE_URL = LOCAL_MODE
  ? `ws://${LOCAL_IP}:${LOCAL_PORT}`
  : 'wss://conjugated-quintan-michel.ngrok-free.dev';

const HEADERS: Record<string, string> = LOCAL_MODE
  ? {}
  : { 'ngrok-skip-browser-warning': 'true' };

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
    Object.entries(HEADERS).forEach(([k, v]) => xhr.setRequestHeader(k, v));

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

  const response = await fetch(`${API_BASE_URL}/api/partidas/analyze/`, {
    method: 'POST',
    headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Error al iniciar el análisis');
  }

  return response.json();
}

/**
 * Conecta al WebSocket de progreso y llama a `onEvent` con cada actualización.
 * Devuelve una función `disconnect()` para cerrar la conexión manualmente.
 *
 * Ejemplo de uso:
 *   const disconnect = watchAnalysis(taskId, (event) => {
 *     if (event.type === 'progress')  setProgress(event.progress);
 *     if (event.type === 'complete')  setFens(event.fens);
 *     if (event.type === 'error')     showError(event.error);
 *   });
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
  const response = await fetch(
    `${API_BASE_URL}/api/partidas/progress/${encodeURIComponent(fileName)}/`,
    { headers: HEADERS },
  );
  if (!response.ok) return 0;
  const data = await response.json();
  return data.progress ?? 0;
}

// ── Listado y borrado de vídeos ───────────────────────────────────────────────

export async function listVideos(): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/list/`, { headers: HEADERS });
  if (!response.ok) throw new Error('Error al obtener la lista de vídeos');
  const data = await response.json();
  return data.videos as string[];
}

export async function deleteVideo(fileName: string): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/partidas/delete/${encodeURIComponent(fileName)}/`,
    { method: 'DELETE', headers: HEADERS },
  );
  if (!response.ok) throw new Error('Error al eliminar el vídeo');
}

// ── Calibración ───────────────────────────────────────────────────────────────

export function getFirstFrameUrl(fileName: string): string {
  return `${API_BASE_URL}/api/partidas/first-frame/${encodeURIComponent(fileName)}/`;
}

export async function fetchWarpedPreview(
  fileName: string,
  corners: [number, number][],
): Promise<string> {
  const response = await fetch(
    `${API_BASE_URL}/api/partidas/warped-preview/${encodeURIComponent(fileName)}/`,
    {
      method: 'POST',
      headers: { ...HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners }),
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

export async function calibrateCorners(
  corners: [number, number][],
): Promise<{ message: string }> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/calibrate/`, {
    method: 'POST',
    headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({ corners }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Error al guardar la calibración');
  }
  return response.json();
}

// ── Análisis de motores ───────────────────────────────────────────────────────

export async function analysisChain(
  fens: string[],
  depth: number = 5,
): Promise<PositionAnalysis[]> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/analysis-chain/`, {
    method: 'POST',
    headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({ fens, depth }),
  });
  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Error al calcular las mejores jugadas');
  }
  const data = await response.json();
  return data.results as PositionAnalysis[];
}

export async function getEngineAnalysis(analysisId: string): Promise<PositionAnalysis[] | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/partidas/engine-analysis/${encodeURIComponent(analysisId)}/`,
    { headers: HEADERS },
  );
  if (response.status === 404) return null;
  if (!response.ok)            return null;
  const data = await response.json();
  return data.results as PositionAnalysis[];
}

export async function saveEngineAnalysis(analysisId: string, results: PositionAnalysis[]): Promise<void> {
  await fetch(`${API_BASE_URL}/api/partidas/engine-analysis/`, {
    method: 'POST',
    headers: { ...HEADERS, 'Content-Type': 'application/json' },
    body: JSON.stringify({ analysis_id: analysisId, results }),
  });
}
