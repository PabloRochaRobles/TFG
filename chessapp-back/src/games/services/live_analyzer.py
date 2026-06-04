"""
live_analyzer.py — Sesión de análisis en directo (cámara en tiempo real).

Se introduce como una vía paralela al análisis sobre vídeo completo
(`effnet_adapter.analyze_video`); NO modifica esa lógica existente. Por
cada conexión WebSocket de análisis en directo se instancia una
`LiveSession`, que encapsula:

  - la calibración del tablero recibida por el cliente al inicio,
  - el clasificador EfficientNet-B0 (singleton compartido con el flujo
    offline a través de `effnet_adapter._get_classifier`),
  - el estado del juego (`chess.Board`) y la lista acumulada de FENs.

Por cada fotograma recibido, la sesión rectifica con la homografía,
clasifica las 64 casillas y consulta al inferidor de jugadas. La
decisión final replica los criterios del pipeline offline (`pipeline.py`):
"move", "no-move", "low-margin" o "garbage" según los mismos umbrales.

La selección de fotogramas estables (que en el flujo offline hace
`iter_stable_frames` sobre un vídeo completo) se delega aquí al
cliente: el dispositivo envía un fotograma únicamente cuando detecta
inmovilidad sobre el tablero. Eso evita refactorizar el selector y
mantiene la huella del servidor reducida.
"""
from __future__ import annotations

import chess
import cv2
import numpy as np

from ..chess_tracker.board_detector import BoardCalibration, warp_board
from ..chess_tracker.move_inferencer import infer_move
from ..chess_tracker.square_classifier.infer import SquareClassifierInference

from .effnet_adapter import _get_classifier


# Mismos umbrales que el pipeline offline para asegurar consistencia
# entre ambos modos de análisis.
_SCORE_FLOOR = -3.0
_MARGIN_THRESHOLD = 0.10


class LiveSession:
    """Estado de una sesión de análisis en directo, asociada a una
    conexión WebSocket del cliente.
    """

    def __init__(self, calibration: BoardCalibration) -> None:
        self.calibration = calibration
        self.classifier: SquareClassifierInference = _get_classifier()
        self.board = chess.Board()
        self.fens: list[str] = [self.board.fen()]
        # Permite filtrar fotogramas casi idénticos sin invocar al
        # clasificador (ahorro de CPU). Se rellena tras la primera
        # clasificación con éxito.
        self._last_warped_gray: np.ndarray | None = None

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def process_frame(self, bgr: np.ndarray) -> dict:
        """Procesa un fotograma y devuelve la decisión.

        El diccionario resultante tiene siempre las claves:
          - `decision` ∈ {'move', 'no-move', 'low-margin', 'garbage', 'duplicate'}
          - `score`, `margin`, `no_move_score` (cuando aplique)

        Si la decisión es `'move'`, además se incluyen:
          - `moves`: lista de jugadas en UCI aplicadas en este frame
            (puede ser más de una si el inferidor recupera 2 plies).
          - `fen`: FEN de la posición resultante tras aplicar las jugadas.
          - `index`: índice de esa nueva posición dentro de `self.fens`.
        """
        warped = warp_board(bgr, self.calibration)

        # Pre-filtro barato: si el frame es casi idéntico al último
        # aceptado, devuelve 'duplicate' sin pasar por la red. Evita
        # gastar CPU clasificando cuando el cliente envía la misma
        # imagen dos veces consecutivas.
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        if self._last_warped_gray is not None:
            diff = cv2.absdiff(gray, self._last_warped_gray)
            if float(diff.mean()) < 1.5:   # variación promedio < 1.5/255
                return {'decision': 'duplicate'}

        probs = self.classifier.classify_position(warped)
        result = infer_move(self.board, probs)

        out: dict = {
            'score': float(result.score),
            'margin': float(result.margin),
            'no_move_score': float(result.no_move_score),
        }

        if result.score < _SCORE_FLOOR:
            out['decision'] = 'garbage'
        elif not result.legal:
            out['decision'] = 'no-move'
            self._last_warped_gray = gray
        elif result.margin < _MARGIN_THRESHOLD:
            out['decision'] = 'low-margin'
        else:
            out['decision'] = 'move'
            applied_uci: list[str] = []
            for m in result.moves:
                self.board.push(m)
                self.fens.append(self.board.fen())
                applied_uci.append(m.uci())
            out['moves'] = applied_uci
            out['fen'] = self.board.fen()
            out['index'] = len(self.fens) - 1
            self._last_warped_gray = gray

        return out

    # ------------------------------------------------------------------
    # Utilidades
    # ------------------------------------------------------------------

    @staticmethod
    def decode_jpeg(buf: bytes) -> np.ndarray | None:
        """Decodifica un JPEG binario a BGR uint8. Devuelve None si falla."""
        arr = np.frombuffer(buf, dtype=np.uint8)
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)
