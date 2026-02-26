export const API_BASE_URL = 'https://conjugated-quintan-michel.ngrok-free.dev';

const HEADERS = {
  'ngrok-skip-browser-warning': 'true',
};

export async function uploadVideo(videoUri: string, fileName: string): Promise<{ file: string; id: string; message: string }> {
  const formData = new FormData();
  formData.append('video_file', {
    uri: videoUri,
    name: fileName,
    type: 'video/mp4',
  } as any);

  const response = await fetch(`${API_BASE_URL}/api/partidas/upload/`, {
    method: 'POST',
    headers: HEADERS,
    body: formData,
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.error || 'Error al subir el video');
  }

  return response.json();
}

export async function analyzeVideo(fileName: string): Promise<{ message: string; total_frames: number; analisis_id: string }> {
  const response = await fetch(`${API_BASE_URL}/api/partidas/analyze/`, {
    method: 'POST',
    headers: {
      ...HEADERS,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ video_file: fileName }),
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
  await fetch(`${API_BASE_URL}/api/partidas/delete/`, {
    method: 'DELETE',
    headers: {
      ...HEADERS,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ video_file: fileName }),
  });
}
