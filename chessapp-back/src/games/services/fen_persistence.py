"""
Persistencia en disco de la lista de FENs producida por un análisis.

Cada análisis genera un fichero `media/fens/<analysis_id>.json` con la forma:

    {"fens": ["rnbqkbnr/...", "..."], "total": N}

Sin caché en memoria — el TTL/cache de Django Channels ya lo gestiona
`views.py`. Este módulo es la fuente persistente para reanudar análisis
sin recalcular.
"""

import json
import os

from .config import FENS_LOCATION


def save_fens(fens, analysis_id):
    """
    Guarda la secuencia de FENs en media/fens/<analysis_id>.json asociada a un análisis previo.
    Crea el directorio si no existe.

    Parametros:
        - fens: Lista de FENs a guardar.
        - analysis_id: Identificador único del análisis para nombrar el archivo de FENs.

    Devuelve la ruta del archivo de FENs guardado.
    """
    os.makedirs(FENS_LOCATION, exist_ok=True)
    path = os.path.join(FENS_LOCATION, f"{analysis_id}.json")
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({'fens': fens, 'total': len(fens)}, f)
    print(f"[FEN] {len(fens)} FENs guardados en {path}")
    return path


def load_fens(analysis_id):
    """
    Carga la secuencia de FENs desde media/fens/<analysis_id>.json asociada a un análisis previo.

    Parametros:
        - analysis_id: Identificador único del análisis que se usó para guardar las FENs.

    Devuelve una lista de FENs o None si no se encuentra el archivo.
    """
    path = os.path.join(FENS_LOCATION, f"{analysis_id}.json")
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    return data.get('fens', [])


def delete_fens(analysis_id):
    """Elimina el archivo de FENs asociado a un analysis_id. Devuelve True si se borró, False si no existía."""
    path = os.path.join(FENS_LOCATION, f"{analysis_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"[DELETE] FENs {analysis_id}.json eliminados.")
            return True
        except Exception as e:
            print(f"[DELETE] Error al eliminar FENs {analysis_id}.json: {e}")
            return False
    return False
