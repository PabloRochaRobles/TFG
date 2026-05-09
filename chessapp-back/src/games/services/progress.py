"""
Tracking del progreso de análisis (0-100) por clave de vídeo.

El estado vive en este módulo — quien necesite leer/escribir progreso debe
importar `set_progress` / `get_progress` desde aquí (o desde `services` vía el
barrel) en vez de mantener su propia variable global. Eso garantiza que tanto
el hilo de fondo del análisis como el endpoint de polling y el WebSocket
consumer ven el mismo estado.
"""

_analysis_progress: dict = {}


def set_progress(key: str, pct: int) -> None:
    """Actualiza el progreso de análisis para la clave dada (0-100)."""
    _analysis_progress[key] = min(100, max(0, pct))


def get_progress(key: str) -> int:
    """Devuelve el progreso actual para la clave dada (0-100)."""
    return _analysis_progress.get(key, 0)
