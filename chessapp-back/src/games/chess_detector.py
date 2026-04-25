"""
chess_detector.py — Detección de piezas de ajedrez con YOLOv8.

Reemplaza la detección por deltas (qué celdas cambiaron) por reconocimiento de
estado absoluto (qué pieza hay en cada casilla). Cada frame es independiente:
un error de detección no se propaga al resto de la partida.

══════════════════════════════════════════════════════════════════════════════
 CÓMO OBTENER EL MODELO
══════════════════════════════════════════════════════════════════════════════

 OPCIÓN A — Descargar modelo pre-entrenado de Roboflow (recomendada):

   1. Instala el cliente:  pip install roboflow
   2. Crea una cuenta gratuita en https://roboflow.com
   3. En Python:
        from roboflow import Roboflow
        rf = Roboflow(api_key="TU_API_KEY")
        # Dataset: chess-pieces-svz8n (u otro equivalente)
        project = rf.workspace().project("chess-pieces-svz8n")
        version = project.version(1)
        version.download("yolov8")
   4. Entrena:
        yolo detect train data=chess-pieces-svz8n/data.yaml model=yolov8n.pt epochs=50 imgsz=640
   5. Copia best.pt a:  media/models/chess_yolo.pt

 OPCIÓN B — Entrenamiento propio con imágenes del tablero warpeado:
   1. Genera imágenes warpeadas (1000×1000) con el pipeline actual
   2. Anota las piezas usando Roboflow Annotate o LabelImg
   3. Usa las 12 clases del DEFAULT_CLASS_MAP
   4. Entrena: yolo detect train data=tu_dataset.yaml model=yolov8n.pt epochs=100

 OPCIÓN C — Usar chessvision.ai como validación previa:
   pip install chessvision-client
   (Útil para generar ground-truth antes de entrenar tu propio modelo)

══════════════════════════════════════════════════════════════════════════════
 CONFIGURACIÓN EN settings.py
══════════════════════════════════════════════════════════════════════════════

   # Ruta al modelo entrenado (por defecto: media/models/chess_yolo.pt)
   CHESS_YOLO_MODEL_PATH = os.path.join(MEDIA_ROOT, 'models', 'chess_yolo.pt')

   # Confianza mínima para aceptar una detección (0.0–1.0)
   CHESS_YOLO_CONFIDENCE = 0.4

   # Sobrescribir nombres de clase si tu modelo usa nombres distintos
   CHESS_YOLO_CLASS_MAP = {
       'wp': 'P', 'wr': 'R', ...   # tu mapeo personalizado
   }

══════════════════════════════════════════════════════════════════════════════
 SI EL MODELO NO EXISTE
══════════════════════════════════════════════════════════════════════════════

   El sistema cae automáticamente en la detección por deltas original.
   No es necesario ningún cambio de código para seguir usando la app.
"""

import bisect
import logging
import os
from typing import Optional

import chess
import cv2
import numpy as np
from django.conf import settings

logger = logging.getLogger(__name__)

# ── Rutas y configuración ─────────────────────────────────────────────────────

MODEL_PATH: str = getattr(
    settings,
    'CHESS_YOLO_MODEL_PATH',
    os.path.join(settings.MEDIA_ROOT, 'models', 'chess_yolo.pt'),
)

CONFIDENCE_THRESHOLD: float = getattr(settings, 'CHESS_YOLO_CONFIDENCE', 0.4)

# ── Mapeo clase → símbolo FEN ─────────────────────────────────────────────────
# Cubre los nombres más habituales en datasets públicos de Roboflow.
# Puedes añadir variantes extras via settings.CHESS_YOLO_CLASS_MAP.
_DEFAULT_CLASS_MAP: dict[str, str] = {
    # Formato "color-pieza" (el más común en Roboflow)
    'white-king':   'K', 'white-queen':  'Q', 'white-rook':   'R',
    'white-bishop': 'B', 'white-knight': 'N', 'white-pawn':   'P',
    'black-king':   'k', 'black-queen':  'q', 'black-rook':   'r',
    'black-bishop': 'b', 'black-knight': 'n', 'black-pawn':   'p',
    # Abreviaturas de dos letras
    'wK': 'K', 'wQ': 'Q', 'wR': 'R', 'wB': 'B', 'wN': 'N', 'wP': 'P',
    'bK': 'k', 'bQ': 'q', 'bR': 'r', 'bB': 'b', 'bN': 'n', 'bP': 'p',
    # Nombres largos con mayúscula
    'White King':   'K', 'White Queen':  'Q', 'White Rook':   'R',
    'White Bishop': 'B', 'White Knight': 'N', 'White Pawn':   'P',
    'Black King':   'k', 'Black Queen':  'q', 'Black Rook':   'r',
    'Black Bishop': 'b', 'Black Knight': 'n', 'Black Pawn':   'p',
    # Solo la inicial (algunos datasets minimalistas)
    'K': 'K', 'Q': 'Q', 'R': 'R', 'B': 'B', 'N': 'N', 'P': 'P',
    'k': 'k', 'q': 'q', 'r': 'r', 'b': 'b', 'n': 'n', 'p': 'p',
}

# Clases sin información de color — el tipo de pieza se conoce pero no el bando.
# Se infiere por posición: y_center < mitad del tablero → negras, >= mitad → blancas.
# Clave: nombre_clase_minúsculas → (símbolo_blancas, símbolo_negras)
_COLOR_NEUTRAL_MAP: dict[str, tuple[str, str]] = {
    'king':   ('K', 'k'),
    'queen':  ('Q', 'q'),
    'rook':   ('R', 'r'),
    'bishop': ('B', 'b'),
    'knight': ('N', 'n'),
    'pawn':   ('P', 'p'),
    # Variantes con mayúscula inicial
    'King':   ('K', 'k'),
    'Queen':  ('Q', 'q'),
    'Rook':   ('R', 'r'),
    'Bishop': ('B', 'b'),
    'Knight': ('N', 'n'),
    'Pawn':   ('P', 'p'),
}

CLASS_MAP: dict[str, str] = {
    **_DEFAULT_CLASS_MAP,
    **getattr(settings, 'CHESS_YOLO_CLASS_MAP', {}),
}

# Tamaño de inferencia: más pequeño = más rápido sin pérdida notable de precisión.
# El modelo acepta cualquier resolución; 640 es el óptimo para YOLOv8.
INFERENCE_SIZE: int = 640
NORMALIZED_SIZE: int = 1000  # Coincide con services.NORMALIZED_SIZE
CELL_SIZE: float = NORMALIZED_SIZE / 8

# ── Caché del modelo (se carga una sola vez) ──────────────────────────────────
_model = None
_model_load_attempted = False

# Contador secuencial para imágenes de debug YOLO (se reinicia al inicio de cada análisis)
_yolo_debug_counter = 0


def get_model():
    """
    Carga el modelo YOLOv8 desde MODEL_PATH la primera vez y lo cachea.
    Devuelve None si el modelo no existe o no se pudo cargar.
    """
    global _model, _model_load_attempted
    if _model_load_attempted:
        return _model

    _model_load_attempted = True

    if not os.path.exists(MODEL_PATH):
        logger.warning(
            "[YOLO] Modelo no encontrado en '%s'. "
            "Usando detección por deltas (fallback). "
            "Consulta chess_detector.py para instrucciones de descarga.",
            MODEL_PATH,
        )
        return None

    try:
        from ultralytics import YOLO  # Importación diferida para no fallar sin el paquete
        _model = YOLO(MODEL_PATH)
        class_names = list(_model.names.values())
        unknown = [c for c in class_names if c not in CLASS_MAP and c not in _COLOR_NEUTRAL_MAP]
        if unknown:
            logger.warning(
                "[YOLO] Clases desconocidas en el modelo (no mapeadas): %s. "
                "Añádelas a settings.CHESS_YOLO_CLASS_MAP.",
                unknown,
            )
        logger.info("[YOLO] Modelo cargado: %s — clases: %s", MODEL_PATH, class_names)
        return _model

    except ImportError:
        logger.error(
            "[YOLO] 'ultralytics' no instalado. Ejecuta: pip install ultralytics"
        )
        return None

    except Exception as exc:
        logger.error("[YOLO] Error al cargar el modelo: %s", exc)
        return None


def is_available() -> bool:
    """Devuelve True si el modelo YOLOv8 está disponible y listo para usar."""
    return get_model() is not None


def reset_model_cache() -> None:
    """Fuerza la recarga del modelo en la próxima llamada (útil para tests)."""
    global _model, _model_load_attempted
    _model = None
    _model_load_attempted = False


# ── Detección de la cuadrícula mediante líneas de Hough ──────────────────────

def _cluster_lines(positions: list[float], n: int, img_size: int) -> list[int]:
    """
    Agrupa una lista de posiciones en n clusters equiespaciados y devuelve
    los centroides ordenados. Si hay menos posiciones que clusters, devuelve
    la cuadrícula uniforme de fallback.
    """
    if len(positions) < max(3, n // 2):
        return [int(round(img_size / n * i)) for i in range(n + 1)]

    arr = np.array(sorted(positions), dtype=float)
    # Centros iniciales: cuadrícula uniforme
    centers = np.array([img_size / n * (i + 0.5) for i in range(n)], dtype=float)

    for _ in range(20):
        dists = np.abs(arr[:, None] - centers[None, :])  # (M, n)
        labels = np.argmin(dists, axis=1)
        new_centers = np.array([
            arr[labels == i].mean() if np.any(labels == i) else centers[i]
            for i in range(n)
        ])
        if np.allclose(centers, new_centers, atol=1.0):
            break
        centers = new_centers

    # Convertir centros de celda a bordes de celda (n+1 bordes)
    centers_sorted = sorted(centers)
    boundaries = [0]
    for i in range(len(centers_sorted) - 1):
        boundaries.append(int(round((centers_sorted[i] + centers_sorted[i + 1]) / 2)))
    boundaries.append(img_size)
    return boundaries


def detect_grid_from_lines(
    warped_image: np.ndarray,
    n_cells: int = 8,
) -> tuple[list[int], list[int]]:
    """
    Detecta las líneas del tablero en la imagen warpeada mediante la transformada
    de Hough y devuelve (col_boundaries, row_boundaries), listas de n_cells+1
    posiciones de píxel que delimitan las columnas y filas respectivamente.

    Si la detección falla (pocas líneas visibles), devuelve la cuadrícula
    uniforme estándar (equivalente al comportamiento anterior).
    """
    img_size = warped_image.shape[0]  # Suponemos imagen cuadrada (NORMALIZED_SIZE)
    uniform = [int(round(img_size / n_cells * i)) for i in range(n_cells + 1)]

    gray  = cv2.cvtColor(warped_image, cv2.COLOR_BGR2GRAY)
    blur  = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 30, 100)

    min_line_len = img_size // 3   # al menos 1/3 del tablero
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 180,
        threshold=80,
        minLineLength=min_line_len,
        maxLineGap=40,
    )

    if lines is None or len(lines) < 6:
        return uniform, uniform

    h_pos: list[float] = []
    v_pos: list[float] = []

    for line in lines:
        x1, y1, x2, y2 = line[0]
        dx, dy = abs(x2 - x1), abs(y2 - y1)
        if dx == 0 and dy == 0:
            continue
        angle_deg = abs(np.degrees(np.arctan2(dy, dx)))

        if angle_deg < 20:           # línea casi horizontal
            h_pos.append((y1 + y2) / 2.0)
        elif angle_deg > 70:         # línea casi vertical
            v_pos.append((x1 + x2) / 2.0)

    col_boundaries = _cluster_lines(v_pos, n_cells, img_size) if len(v_pos) >= 3 else uniform
    row_boundaries = _cluster_lines(h_pos, n_cells, img_size) if len(h_pos) >= 3 else uniform

    logger.debug(
        "[HOUGH] %d líneas H, %d líneas V → col=%s row=%s",
        len(h_pos), len(v_pos), col_boundaries, row_boundaries,
    )
    return col_boundaries, row_boundaries


# ── Caché de cuadrícula por análisis ─────────────────────────────────────────
# Evita recalcular Hough en cada frame de la misma partida.
_grid_cache: dict[int, tuple[list[int], list[int]]] = {}


def _grid_for_frame(warped_image: np.ndarray) -> tuple[list[int], list[int]]:
    """Devuelve la cuadrícula Hough, usando caché basada en shape de la imagen."""
    key = warped_image.shape[0]
    if key not in _grid_cache:
        _grid_cache[key] = detect_grid_from_lines(warped_image)
    return _grid_cache[key]


def invalidate_grid_cache() -> None:
    """Limpia la caché de cuadrícula (útil entre análisis distintos)."""
    _grid_cache.clear()


# ── Detección de estado del tablero ──────────────────────────────────────────

BoardState = dict[int, str]  # {chess.Square: símbolo_FEN}


def validate_board_state(raw: dict[int, tuple[str, float]]) -> BoardState:
    """
    Filtra el estado bruto detectado por YOLO para garantizar que sea
    ajedrecísticamente válido:
      - Máximo 1 rey por bando (se conserva el de mayor confianza).
      - Máximo 8 peones por bando (se conservan los de mayor confianza).
      - Máximo 9 damas/torres/alfiles/caballos (con coronaciones).
    Cuando hay más piezas de las permitidas, se descartan las de menor confianza.
    """
    MAX_COUNTS: dict[str, int] = {
        'K': 1,  'k': 1,   # Reyes: exactamente 1 por bando
        'P': 8,  'p': 8,   # Peones: máximo 8 por bando
        'Q': 9,  'q': 9,   # Damas: 1 original + hasta 8 coronaciones
        'R': 10, 'r': 10,
        'B': 10, 'b': 10,
        'N': 10, 'n': 10,
    }
    by_piece: dict[str, list[tuple[int, float]]] = {}
    for sq, (sym, conf) in raw.items():
        by_piece.setdefault(sym, []).append((sq, conf))

    result: BoardState = {}
    for sym, detections in by_piece.items():
        limit = MAX_COUNTS.get(sym, 10)
        detections.sort(key=lambda x: x[1], reverse=True)
        for sq, _ in detections[:limit]:
            result[sq] = sym
    return result


def detect_board_state(
    warped_image: np.ndarray,
    original_frame: Optional[np.ndarray] = None,
    M: Optional[np.ndarray] = None,
) -> Optional[BoardState]:
    """
    Ejecuta YOLOv8 y devuelve {chess.Square → símbolo_pieza_FEN}.

    Cuando se proporcionan `original_frame` y `M`:
      - YOLO corre sobre el frame original sin deformar (más fiel al dataset
        de entrenamiento: las piezas altas no sufren distorsión por warp).
      - El punto base de cada bbox (centro inferior, donde la pieza toca el
        tablero físico) se transforma al espacio 1000×1000 mediante M.
      - La cuadrícula Hough sigue usando el frame warpeado para determinar
        los bordes de las 64 casillas.

    Sin `original_frame`/`M`: comportamiento previo (YOLO sobre warped).

    Devuelve None si el modelo no está disponible (fallback por deltas).
    """
    model = get_model()
    if model is None:
        return None

    # Cuadrícula Hough siempre sobre la imagen warpeada (espacio normalizado)
    col_bounds, row_bounds = _grid_for_frame(warped_image)

    # ── Selección de imagen para YOLO ────────────────────────────────────────
    use_original = original_frame is not None and M is not None

    if use_original:
        orig_h, orig_w = original_frame.shape[:2]
        img_small = cv2.resize(original_frame, (INFERENCE_SIZE, INFERENCE_SIZE))
        sx = orig_w / INFERENCE_SIZE   # Factor de escala X para volver a píxeles originales
        sy = orig_h / INFERENCE_SIZE
    else:
        img_small    = cv2.resize(warped_image, (INFERENCE_SIZE, INFERENCE_SIZE))
        scale_factor = NORMALIZED_SIZE / INFERENCE_SIZE

    results = model(img_small, verbose=False, conf=CONFIDENCE_THRESHOLD)[0]

    # {square: (símbolo, confianza)} — guardamos confianza para resolver conflictos
    raw: dict[int, tuple[str, float]] = {}

    for box in results.boxes:
        cls_id   = int(box.cls[0])
        cls_name = model.names[cls_id]

        x1, y1, x2, y2 = box.xyxy[0].tolist()

        if use_original:
            # Punto base: centro inferior del bbox = donde la pieza apoya en el tablero
            base_x = ((x1 + x2) / 2) * sx
            base_y = y2 * sy
            # Proyectar al espacio warpeado (0–NORMALIZED_SIZE) con la homografía M
            pt = np.array([[[base_x, base_y]]], dtype=np.float32)
            warped_pt = cv2.perspectiveTransform(pt, M)[0][0]
            
            # IGNORAR piezas que caen fuera del tablero físico (ej. tablero digital en el vídeo)
            # Margen de 50px por si la base asoma ligeramente del borde de la casilla
            if warped_pt[0] < -50 or warped_pt[0] > NORMALIZED_SIZE + 50 or \
               warped_pt[1] < -50 or warped_pt[1] > NORMALIZED_SIZE + 50:
                continue

            x_center = float(np.clip(warped_pt[0], 0, NORMALIZED_SIZE))
            y_center = float(np.clip(warped_pt[1], 0, NORMALIZED_SIZE))
        else:
            x_center = ((x1 + x2) / 2) * scale_factor
            y_center = ((y1 + y2) / 2) * scale_factor

        # Mapeo de clase → símbolo FEN
        piece = CLASS_MAP.get(cls_name)
        if not piece:
            neutral = _COLOR_NEUTRAL_MAP.get(cls_name)
            if neutral:
                white_sym, black_sym = neutral
                # Mitad superior → negras, mitad inferior → blancas (en espacio warpeado)
                piece = white_sym if y_center >= (NORMALIZED_SIZE / 2) else black_sym
        if not piece:
            continue

        # Mapear coordenada warpeada a casilla usando bordes Hough
        col = max(0, min(bisect.bisect_right(col_bounds, x_center) - 1, 7))
        row = max(0, min(bisect.bisect_right(row_bounds, y_center) - 1, 7))
        square = chess.square(row, col)
        conf   = float(box.conf[0])

        if square in raw:
            if conf > raw[square][1]:
                raw[square] = (piece, conf)
        else:
            raw[square] = (piece, conf)

    board_state = validate_board_state(raw)

    logger.debug(
        "[YOLO] %d piezas detectadas (%s): %s",
        len(board_state),
        "original+M" if use_original else "warped",
        {chess.square_name(sq): sym for sq, sym in board_state.items()},
    )

    # ── Debug visual: bbox + casilla + confianza sobre el frame usado por YOLO ─
    try:
        debug_img = img_small.copy()
        for box in results.boxes:
            cls_id   = int(box.cls[0])
            cls_name = model.names[cls_id]
            conf     = float(box.conf[0])
            x1, y1, x2, y2 = [int(v) for v in box.xyxy[0].tolist()]
            if use_original:
                bx = ((x1 + x2) / 2) * sx
                by = y2 * sy
                pt = np.array([[[bx, by]]], dtype=np.float32)
                wpt = cv2.perspectiveTransform(pt, M)[0][0]
                
                # Ignorar también en la visualización de debug
                if wpt[0] < -50 or wpt[0] > NORMALIZED_SIZE + 50 or \
                   wpt[1] < -50 or wpt[1] > NORMALIZED_SIZE + 50:
                    continue

                wx = float(np.clip(wpt[0], 0, NORMALIZED_SIZE))
                wy = float(np.clip(wpt[1], 0, NORMALIZED_SIZE))
                col_d = max(0, min(bisect.bisect_right(col_bounds, wx) - 1, 7))
                row_d = max(0, min(bisect.bisect_right(row_bounds, wy) - 1, 7))
            else:
                col_d = max(0, min(bisect.bisect_right(col_bounds, ((x1+x2)/2)*scale_factor) - 1, 7))
                row_d = max(0, min(bisect.bisect_right(row_bounds, ((y1+y2)/2)*scale_factor) - 1, 7))
            sq_name = chess.square_name(chess.square(row_d, col_d))
            piece_d = CLASS_MAP.get(cls_name) or cls_name
            color   = (0, 200, 0) if conf >= CONFIDENCE_THRESHOLD else (0, 0, 200)
            cv2.rectangle(debug_img, (x1, y1), (x2, y2), color, 2)
            cv2.putText(debug_img, f"{piece_d}@{sq_name} {conf:.2f}",
                        (x1, max(y1 - 4, 10)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
        from .services import save_debug_image
        global _yolo_debug_counter
        save_debug_image(f"yolo_detect_{_yolo_debug_counter:04d}", debug_img)
        _yolo_debug_counter += 1
    except Exception:
        pass

    return board_state


# ── Conversión de estado → FEN ────────────────────────────────────────────────

def board_state_to_fen_placement(board_state: BoardState) -> str:
    """
    Convierte {square → symbol} en la parte de colocación de piezas del FEN.
    Ejemplo: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR'
    """
    rows: list[str] = []
    for rank in range(7, -1, -1):          # Ranks 8 → 1 (orden FEN: arriba primero)
        row_str = ''
        empty   = 0
        for file in range(8):              # Files a → h
            piece = board_state.get(chess.square(file, rank), '')
            if piece:
                if empty:
                    row_str += str(empty)
                    empty = 0
                row_str += piece
            else:
                empty += 1
        if empty:
            row_str += str(empty)
        rows.append(row_str)
    return '/'.join(rows)


def build_full_fen(board_state: BoardState, board: chess.Board) -> str:
    """
    Construye un FEN completo fusionando la colocación detectada por YOLO con
    el estado lógico (turno, enroque, al-paso, contadores) del tablero python-chess.

    Así garantizamos FENs válidos aunque la detección tenga algún error menor,
    porque python-chess mantiene la lógica del juego correctamente.
    """
    placement = board_state_to_fen_placement(board_state)
    parts     = board.fen().split(' ')
    parts[0]  = placement
    return ' '.join(parts)


# ── Inferencia de movimiento desde dos estados ────────────────────────────────

def infer_move_from_states(
    board: chess.Board,
    state_before: BoardState,
    state_after: BoardState,
) -> Optional[chess.Move]:
    """
    Dadas las posiciones antes y después detectadas por YOLO, deduce el
    movimiento legal de python-chess que mejor explica la transición.

    Estrategia en 3 niveles:
      1. Exacto: identifica casillas fuente (pieza desapareció) y destino
         (pieza apareció/cambió), busca movimiento legal from→to exacto.
      2. Enroque: comprueba solapamiento con las 4 casillas implicadas.
      3. Fallback por solapamiento máximo: útil cuando la detección es
         imprecisa y algunas casillas no se detectan correctamente.
    """
    all_squares = set(state_before.keys()) | set(state_after.keys())

    # Casillas que cambiaron de estado (pieza distinta, aparición o desaparición)
    changed: set[int] = {
        sq for sq in all_squares
        if state_before.get(sq, '') != state_after.get(sq, '')
    }

    if not changed:
        return None

    # Clasificar casillas como fuente o destino
    sources: set[int] = set()
    dests:   set[int] = set()

    for sq in changed:
        piece_b = state_before.get(sq, '')
        piece_a = state_after.get(sq,  '')

        if piece_b and not piece_a:
            # La pieza desapareció → casilla fuente
            sources.add(sq)
        elif piece_a and not piece_b:
            # Apareció una pieza → casilla destino
            dests.add(sq)
        elif piece_b and piece_a:
            # La pieza cambió de tipo (captura al paso, coronación, captura normal)
            # La casilla activa es la que pasó a contener la pieza del turno actual
            if piece_a.isupper() == board.turn:
                # La pieza del turno actual llegó aquí → es destino
                dests.add(sq)
            else:
                # La pieza del turno actual salió → es fuente
                sources.add(sq)

    logger.debug(
        "[YOLO] Cambios: %s | fuentes=%s | destinos=%s",
        [chess.square_name(s) for s in changed],
        [chess.square_name(s) for s in sources],
        [chess.square_name(s) for s in dests],
    )

    # ── Nivel 1: movimiento exacto ───────────────────────────────────────────
    if sources and dests:
        for move in board.legal_moves:
            if move.from_square in sources and move.to_square in dests:
                return move

    # ── Nivel 2: enroque (4 casillas implicadas) ─────────────────────────────
    castling_extras: dict[int, set[int]] = {
        chess.G1: {chess.H1, chess.F1},
        chess.C1: {chess.A1, chess.D1},
        chess.G8: {chess.H8, chess.F8},
        chess.C8: {chess.A8, chess.D8},
    }
    for move in board.legal_moves:
        if board.is_castling(move):
            involved = {move.from_square, move.to_square} | castling_extras.get(move.to_square, set())
            if len(involved & changed) >= 3:
                return move

    # ── Nivel 3: máximo solapamiento (fallback) ──────────────────────────────
    best_move, best_overlap = None, 0
    for move in board.legal_moves:
        involved = {move.from_square, move.to_square}
        if board.is_castling(move):
            involved |= castling_extras.get(move.to_square, set())
        overlap = len(involved & changed)
        if overlap > best_overlap:
            best_overlap, best_move = overlap, move

    if best_overlap >= 2:
        logger.debug("[YOLO] Movimiento por solapamiento: %s (overlap=%d)", best_move, best_overlap)
        return best_move

    return None
