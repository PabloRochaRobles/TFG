"""
Utilidades de I/O de vídeo y frames.

Cubre todo lo que toca disco o `cv2.VideoCapture`:
  - Borrado de vídeos temporales subidos por el frontend.
  - Apertura defensiva de `VideoCapture` (devuelve dict de error en lugar
    de lanzar excepción).
  - Preprocesado de frames (gris + Gaussian blur) para el detector de
    movimiento por absdiff.
  - Cálculo de la matriz homográfica del warp a partir de las 4 esquinas
    del tablero.
  - Guardado/borrado de keyframes como `.npz` comprimido.
  - Guardado de imágenes de debug (con compatibilidad para rutas con
    caracteres no-ASCII en Windows).

Sin estado global. Sólo depende de las constantes de paths definidas en
`services.config`.
"""

import logging
import os

import cv2
import numpy as np
from rest_framework import status
from rest_framework.response import Response

from .config import (
    TEMP_VIDEOS_LOCATION, TEMP_FRAMES_LOCATION, DEBUG_LOCATION,
    NORMALIZED_SIZE,
)

logger = logging.getLogger(__name__)


# Función de borrado de los videos obtenidos del FrontEnd y almacenados.
def delete_temporary_videos(file_name):
    file_path = os.path.join(TEMP_VIDEOS_LOCATION, file_name)                   # Almacena en la variable la ruta hasta el archivo que se quiere borrar
    logger.info("[DELETE] Buscando archivo en: %s", file_path)
    logger.info("[DELETE] Archivo existe: %s", os.path.exists(file_path))
    try:
        if os.path.exists(file_path):                                           # Si el archivo existe:
            os.remove(file_path)                                                    # Se elimina el video especificado por la ruta
            logger.info("[DELETE] El video %s ha sido eliminado", file_name)        # Se notifica que el video ha sido eliminado
            return True                                                             # Devuelve verdadero

        else:                                                                   # Si no existe:
            logger.warning("[DELETE] Archivo no encontrado: %s", file_path)
            return False                                                             # Devuelve falso

    except Exception as e:                                                      # Si algo falla, salta la excepción
        logger.error("[DELETE] Excepción al borrar: %s", e)
        return False                                                                 # Devuelve falso


# Función de apertura del video de ajedrez
def open_video(video_path):
    video = cv2.VideoCapture(video_path)                    # Abre el video y se almacena el manejador en la variable
    if not video.isOpened():                                # Si no se ha conseguido abrir el video
        return {"error": "No se pudo abrir el video."}      # Se notifica del error
    else:                                                   # Si se consigue abrir el video
        return video                                        # Se devuelve el manejador


# Función para el procesamiento de una imagen eliminando ruido y facilitando la detección de movimiento para recopilar los frames claves
def process_image(frame):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)              # Se tranforma el frame al formato de escala de grises
    blur = cv2.GaussianBlur(gray, ksize=(21, 21), sigmaX=0)     # Se le aplica un filtro Gaussiano a la imagen en escala de grises
    return blur                                                 # Devuelve el frame con estos filtros aplicados


# Función que transforma el cómo se ve el tablero tras aplicarle el cambio de perspectiva arreglando que la imagen no se distorsione
def get_matriz(coords):
    # coords llega en orden [a1, a8, h8, h1] tal como los toca el usuario en la calibración.
    # Orientación de la imagen tal como la ve la cámara lateral (blancas a la izquierda):
    #   a1 = arriba-izquierda,  a8 = arriba-derecha
    #   h1 = abajo-izquierda,   h8 = abajo-derecha
    #
    # Mapeo de destino en la imagen normalizada (NORMALIZED_SIZE × NORMALIZED_SIZE):
    #   coords[0] (a1) → (0, 0)   arriba-izquierda
    #   coords[1] (a8) → (N, 0)   arriba-derecha
    #   coords[2] (h8) → (N, N)   abajo-derecha
    #   coords[3] (h1) → (0, N)   abajo-izquierda
    #
    # Ejes resultantes:
    #   x (columnas, izq→der): rank 1 → rank 8  (rank_index = col = i%8)
    #   y (filas, arr→abj):    file a → file h   (file_index  = row = i//8)
    # → cell_index_to_square(i) = chess.square(i//8, i%8)
    N = NORMALIZED_SIZE - 1
    destination_points = np.float32([
        [0, 0  ],   # coords[0] (a1) → arriba-izquierda
        [N, 0  ],   # coords[1] (a8) → arriba-derecha
        [N, N  ],   # coords[2] (h8) → abajo-derecha
        [0, N  ],   # coords[3] (h1) → abajo-izquierda
    ])

    mat = cv2.getPerspectiveTransform(coords, destination_points)       # Transformación de los puntos marcados por el usuario a los puntos de destino
    return mat                                                          # Devuelve la matriz ya transformada


# Función para el guardado de todos los frames detectados como clave (en los que se han realizado movimiento)
def save_key_frames(key_frames, file_name):
    if not key_frames:                                              # Si la lista de frames esta
        logger.warning("Lista de frames vacia")
        return False
    try:
        os.makedirs(TEMP_FRAMES_LOCATION, exist_ok=True)       # Creación si fuera necesario de la carpeta donde se almacenan los frames clave
    except Exception as e:
        logger.error("Error en la creación del directorio %s", e)   # Si da algún error en la creación de la carpeta, salta esta excepción
        return False

    path = os.path.join(TEMP_FRAMES_LOCATION, file_name)             # Variable que almacena el path completo incluyendo el nombre del archivo por ser creado

    try:
        key_frames_array = np.array(key_frames)
        np.savez_compressed(path, frames=key_frames_array)          # Guarda el array en el path indicado en un archivo tipo .npz
        logger.info("[FRAMES] Frames clave almacenados en %s", path)
        return True

    except Exception as e:
        logger.error("[FRAMES] Error al guardar los frames clave %s", e)  # Si da fallo en el almacenamiento, salta esta excepción
        return False


# Función para el borrado del archivo que contiene los frames clave
def delete_key_frames(file_name):
    path_frames = os.path.join(TEMP_FRAMES_LOCATION, f"{file_name}.npz")
    try:
        if os.path.exists(path_frames):
            os.remove(path_frames)
            logger.info("Frames clave %s.npz eliminados.", file_name)
            return True
        else:
            logger.warning("No se encontraron frames clave para %s", file_name)
            return False

    except Exception as e:                                                                                      # Si da fallo en el borrado salta la excepción
        return Response({'error': f"Fallo interno en el procesamiento: {str(e)}"},
                        status=status.HTTP_500_INTERNAL_SERVER_ERROR)                                               # Se notifica del fallo y devuelve 500 INTERNAL SERVER ERROR


def save_debug_image(name, image):
    """
    Guarda una imagen en media/debug/<name>.jpg para diagnóstico visual.
    No lanza excepción si falla (el debug no debe interrumpir el análisis).
    """
    try:
        os.makedirs(DEBUG_LOCATION, exist_ok=True)
        path = os.path.join(DEBUG_LOCATION, f"{name}.jpg")
        # cv2.imwrite falla silenciosamente en Windows con rutas que contienen caracteres
        # no-ASCII (tildes, etc.). Se usa imencode + open() para evitarlo.
        ret, buf = cv2.imencode('.jpg', image)
        if ret:
            with open(path, 'wb') as f:
                f.write(buf.tobytes())
            logger.debug("[DEBUG] Imagen guardada: %s", path)
        else:
            logger.warning("[DEBUG] imencode falló para '%s'", name)
    except Exception as e:
        logger.error("[DEBUG] No se pudo guardar imagen de debug '%s': %s", name, e)


def get_first_frame(video_path):
    """Lee y devuelve el primer frame del video sin mantenerlo abierto."""
    cap = open_video(video_path)
    if isinstance(cap, dict):
        return None
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def get_warped_frame_preview(video_path, corners_rel):
    """Devuelve el primer frame warpeado con las esquinas relativas dadas (para previsualización)."""
    frame = get_first_frame(video_path)
    if frame is None:
        return None
    h, w = frame.shape[:2]
    corners = np.float32([[rx * w, ry * h] for rx, ry in corners_rel])
    mat = get_matriz(corners)
    return cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
