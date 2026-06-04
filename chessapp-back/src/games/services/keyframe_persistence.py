"""
Persistencia en disco de los frames clave rectificados por jugada.

Cada vez que el pipeline acepta una jugada a partir de un frame estable,
guarda la vista cenital rectificada (el warpeado 800×800 que vio el
clasificador) en:

    media/keyframes/<analysis_id>/<fen_index>.jpg

donde `fen_index` es el índice de la posición resultante en la lista de
FENs (la posición inicial es el índice 0 y no tiene frame asociado).

Esto alimenta el switch "tablero reconstruido vs frame real del vídeo"
de la pantalla de análisis: permite al usuario ver de qué imagen
concreta del vídeo se dedujo cada movimiento.

El guardado usa `cv2.imencode` + `open()` en lugar de `cv2.imwrite`
porque este último falla silenciosamente en Windows con rutas que
contienen caracteres no ASCII (el proyecto vive bajo una ruta con
tildes).
"""

import os
import shutil

import cv2

from .config import KEYFRAMES_LOCATION


def _dir_for(analysis_id: str) -> str:
    """Carpeta de keyframes de un análisis concreto."""
    return os.path.join(KEYFRAMES_LOCATION, analysis_id)


def save_keyframe(analysis_id: str, index: int, bgr_image) -> str | None:
    """Guarda `bgr_image` (BGR uint8) como media/keyframes/<id>/<index>.jpg.

    Devuelve la ruta escrita o None si la codificación falló. No lanza
    excepción: el guardado del keyframe es accesorio y nunca debe
    interrumpir el análisis.
    """
    try:
        d = _dir_for(analysis_id)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, f"{index}.jpg")
        ok, buf = cv2.imencode('.jpg', bgr_image, [cv2.IMWRITE_JPEG_QUALITY, 85])
        if not ok:
            return None
        with open(path, 'wb') as f:
            f.write(buf.tobytes())
        return path
    except Exception as e:
        print(f"[KEYFRAME] Error al guardar {analysis_id}/{index}.jpg: {e}")
        return None


def keyframe_path(analysis_id: str, index: int) -> str | None:
    """Ruta del keyframe si existe en disco, None en caso contrario."""
    path = os.path.join(_dir_for(analysis_id), f"{index}.jpg")
    return path if os.path.exists(path) else None


def delete_keyframes(analysis_id: str) -> bool:
    """Elimina la carpeta de keyframes de un análisis. Devuelve True si
    existía y se borró, False si no existía."""
    d = _dir_for(analysis_id)
    if os.path.isdir(d):
        shutil.rmtree(d, ignore_errors=True)
        print(f"[DELETE] Keyframes de {analysis_id} eliminados.")
        return True
    return False
