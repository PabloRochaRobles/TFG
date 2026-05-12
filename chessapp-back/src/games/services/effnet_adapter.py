"""
effnet_adapter.py — Adapta el pipeline EfficientNet-B0 al contrato del backend.

Sustituye el bloque WHEN + WHICH + reconstrucción de FENs anterior (basado en
YOLO + creencias bayesianas) por una única llamada al pipeline end-to-end
implementado en `games.chess_tracker.pipeline.process_video`.

Funciones públicas:
  - analyze_video(video_path, corners_abs, progress_key, fens_stream_setter=None)
        → (fens, moves, stats)

El clasificador EfficientNet-B0 se carga una vez por proceso mediante un
singleton protegido por lock (las vistas ejecutan el análisis en threads de
fondo, así que dos peticiones simultáneas podrían entrar en `_get_classifier`
a la vez sin la protección).
"""

import os
import threading

import chess
import cv2
import numpy as np

from ..chess_tracker.board_detector import BoardCalibration
from ..chess_tracker.pipeline import process_video as _process_video
from ..chess_tracker.square_classifier.infer import SquareClassifierInference

from .config import MODEL_PATH
from .progress import set_progress


_classifier_lock = threading.Lock()
_classifier: SquareClassifierInference | None = None


def _get_classifier() -> SquareClassifierInference:
    """Carga el clasificador EfficientNet-B0 una sola vez por proceso.

    Doble check con lock: el `if` externo evita pagar el coste del lock en el
    caso común (modelo ya cargado), el interno garantiza que dos hilos no
    inicialicen simultáneamente.
    """
    global _classifier
    if _classifier is None:
        with _classifier_lock:
            if _classifier is None:
                if not os.path.exists(MODEL_PATH):
                    raise FileNotFoundError(
                        f"Modelo no encontrado en {MODEL_PATH}. Confirma que el "
                        "fichero existe en local o que el Dockerfile lo descarga "
                        "durante el build."
                    )
                _classifier = SquareClassifierInference.load(
                    MODEL_PATH, device="cpu",
                )
    return _classifier


def _corners_to_calibration(corners_abs: np.ndarray) -> BoardCalibration:
    """Convierte un array (4, 2) en orden [a1, a8, h8, h1] a BoardCalibration.

    El frontend ya manda las 4 esquinas relativas y `views.py` las convierte a
    píxeles absolutos antes de llamar al adapter. Aquí sólo se hace el último
    paso: construir el objeto que el pipeline espera.
    """
    if corners_abs.shape != (4, 2):
        raise ValueError(
            f"corners_abs debe tener forma (4, 2); recibido {corners_abs.shape}"
        )
    return BoardCalibration(
        a1=(float(corners_abs[0, 0]), float(corners_abs[0, 1])),
        a8=(float(corners_abs[1, 0]), float(corners_abs[1, 1])),
        h8=(float(corners_abs[2, 0]), float(corners_abs[2, 1])),
        h1=(float(corners_abs[3, 0]), float(corners_abs[3, 1])),
    )


def _video_duration_seconds(video_path: str) -> float:
    """Duración del vídeo en segundos, con fallback a 1 s si no se puede leer."""
    cap = cv2.VideoCapture(video_path)
    try:
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frames = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
        return max(0.1, frames / max(fps, 1.0))
    finally:
        cap.release()


def analyze_video(
    video_path: str,
    corners_abs: np.ndarray,
    progress_key: str,
    fens_stream_setter=None,
) -> tuple[list[str], list, dict]:
    """Pipeline end-to-end: vídeo + 4 esquinas → (FENs, moves, stats).

    Args:
        video_path: ruta absoluta al fichero de vídeo subido por el usuario.
        corners_abs: array float32 de forma (4, 2) en píxeles absolutos, en
            el orden a1, a8, h8, h1 (la misma convención que ya usaba la
            pipeline antigua).
        progress_key: clave bajo la cual se escribe el progreso 0-100 en
            `services.progress`. Tipicamente es `file_name` (el nombre del
            vídeo en disco).
        fens_stream_setter: callback opcional `(list[str]) -> None` que
            recibe la lista acumulada de FENs cada vez que el pipeline aplica
            un movimiento. La vista la usa para empujar FENs a la caché de
            Django, desde donde el WebSocket consumer los emite al frontend
            en tiempo real.

    Returns:
        (fens, moves, stats):
          - fens: lista completa de posiciones FEN, la primera es la posición
            inicial y cada elemento posterior corresponde a una jugada
            aplicada.
          - moves: lista de `chess.Move` en orden de juego.
          - stats: dict con contadores `{"move": n, "no-move": n,
            "low-margin": n, "garbage": n}` de las decisiones del pipeline.
    """
    calib = _corners_to_calibration(corners_abs)
    clf = _get_classifier()
    duration = _video_duration_seconds(video_path)

    # Reproducción local del estado del pipeline para alimentar el streaming
    # incremental al WebSocket. Al final del análisis el pipeline devuelve su
    # propia lista en `result.fens` (idéntica a la nuestra por construcción)
    # — la usamos como fuente final de verdad.
    streaming_board = chess.Board()
    streaming_fens: list[str] = [streaming_board.fen()]
    if fens_stream_setter is not None:
        fens_stream_setter(streaming_fens[:])

    def _on_stable_frame(decision, stable) -> None:
        # Streaming incremental de FENs si la decisión fue "move".
        if decision.decision == "move" and decision.moves:
            for mv in decision.moves:
                streaming_board.push(mv)
                streaming_fens.append(streaming_board.fen())
            if fens_stream_setter is not None:
                fens_stream_setter(streaming_fens[:])

        # Progreso: el pipeline no conoce el total de frames estables a
        # priori, así que linealizamos por timestamp respecto a la duración
        # del vídeo. Capamos a 95 para reservar el último 5 % a la
        # persistencia final que hace la vista.
        pct = int(min(95, max(0, stable.timestamp / duration * 95)))
        set_progress(progress_key, pct)

    # `anomaly_min_changed=10` activa el filtro de manos en `iter_stable_frames`.
    # Es el mismo valor que el CLI `scripts/process_video.py` usa por defecto;
    # sin él la pipeline ingiere frames con la mano del jugador encima del
    # tablero y degrada notablemente la reconstrucción de la partida (test1
    # baja de 23/23 a 19/23). Mantenemos exactamente los mismos parámetros con
    # los que se midió el 100 % de precisión en el TFG.
    stable_frame_kwargs = {'anomaly_min_changed': 10}

    result = _process_video(
        video_path, calib, clf,
        progress=_on_stable_frame,
        stable_frame_kwargs=stable_frame_kwargs,
    )

    set_progress(progress_key, 100)
    return result.fens, result.moves, result.stats()
