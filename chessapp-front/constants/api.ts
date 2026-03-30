export const API_BASE_URL = 'https://conjugated-quintan-michel.ngrok-free.dev';

const HEADERS = {
  'ngrok-skip-browser-warning': 'true',
};

export function uploadVideo(
  videoUri: string,
  fileName: string,
  onProgress?: (pct: number) => void
): Promise<{ file: string; id: string; message: string }> {
  return new Promise((resolve, reject) => {
    const formData = new FormData();
    formData.append('video_file', { uri: videoUri, name: fileName, type: 'video/mp4' } as any);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE_URL}/api/partidas/upload/`);
    Object.entries(HEADERS).forEach(([k, v]) => xhr.setRequestHeader(k, v));

    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(Math.min(100, Math.round((e.loaded / e.total) * 100)));
    };

    xhr.onload = () => {
      try {
        const data = JSON.parse(xhr.responseText);
        if (xhr.status >= 200 && xhr.status < 300) resolve(data);
        else reject(new Error(data.error || 'Error al subir el video'));
      } catch {
        reject(new Error('Respuesta inesperada del servidor'));
      }
    };

    xhr.onerror = () => reject(new Error('Error de red al subir el video'));
    xhr.send(formData);
  });
}

export async function getAnalysisProgress(fileName: string): Promise<number> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/progress/${encodeURIComponent(fileName)}/`, {
    headers: HEADERS,
  });
  if (!response.ok) return 0;
  const data = await response.json();
  return data.progress ?? 0;
}

export async function analyzeVideo(
  fileName: string,
  corners?: [number, number][]
): Promise<{ message: string; total_frames: number; analisis_id: string; total_fens: number; fens: string[] }> {
  const body: Record<string, unknown> = { video_file: fileName };
  if (corners) body.corners = corners;

  const response = await fetch(`${API_BASE_URL}/api/partidas/analyze/`, {
    method: 'POST',
    headers: {
      ...HEADERS,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Error al analizar el video');
  }

  return response.json();
}

export async function listVideos(): Promise<string[]> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/list/`, {
    headers: HEADERS,
  });

  if (!response.ok) {
    throw new Error('Error al obtener la lista de vídeos');
  }

  const data = await response.json();
  return data.videos as string[];
}

export async function deleteVideo(fileName: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/delete/${encodeURIComponent(fileName)}/`, {
    method: 'DELETE',
    headers: HEADERS,
  });

  if (!response.ok) {
    throw new Error('Error al eliminar el vídeo');
  }
}

export function getFirstFrameUrl(fileName: string): string {
  return `${API_BASE_URL}/api/partidas/first-frame/${encodeURIComponent(fileName)}/`;
}

// ── Tipos de análisis de motores ────────────────────────────────────────────
export type EngineResult = { san: string; uci: string; score: number };
export type ChainStep = {
  step: number;
  fen_before: string;
  consensus_san: string;
  consensus_uci: string;
  fen_after: string;
  full_agreement: boolean;
  engines: { stockfish: EngineResult; obsidian: EngineResult; plentychess: EngineResult };
};
export type PositionAnalysis = { initial_fen: string; chain: ChainStep[] };

export async function analysisChain(
  fens: string[],
  depth: number = 5
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
  const response = await fetch(`${API_BASE_URL}/api/partidas/engine-analysis/${encodeURIComponent(analysisId)}/`, {
    headers: HEADERS,
  });
  if (response.status === 404) return null;
  if (!response.ok) return null;
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

export async function fetchWarpedPreview(
  fileName: string,
  corners: [number, number][]
): Promise<string> {
  const response = await fetch(
    `${API_BASE_URL}/api/partidas/warped-preview/${encodeURIComponent(fileName)}/`,
    {
      method: 'POST',
      headers: { ...HEADERS, 'Content-Type': 'application/json' },
      body: JSON.stringify({ corners }),
    }
  );
  if (!response.ok) throw new Error('No se pudo obtener la previsualización');
  const blob = await response.blob();
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export async function calibrateCorners(
  corners: [number, number][]
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
