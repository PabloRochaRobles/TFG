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
        # Forzar determinismo en YOLO/PyTorch para reducir varianza run-a-run.
        # cuDNN auto-tuner y reducciones FP no deterministas son la causa principal
        # de que dos inferencias sobre la misma imagen den outputs distintos.
        try:
            import torch, random
            torch.manual_seed(42)
            np.random.seed(42)
            random.seed(42)
            torch.backends.cudnn.deterministic = True
            torch.backends.cudnn.benchmark    = False
            logger.info("[YOLO] Modo determinista activado (cudnn.deterministic=True)")
        except Exception as _det_exc:
            logger.warning("[YOLO] No se pudo activar modo determinista: %s", _det_exc)

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

def _grid_is_valid(boundaries: list[int], img_size: int) -> bool:
    """
    Comprueba que los 8 intervalos de la cuadrícula son razonablemente
    uniformes (dentro del ±40% del espaciado esperado). Una cuadrícula
    con casillas de tamaño muy dispar indica que Hough colocó líneas en
    posiciones incorrectas.
    """
    if len(boundaries) != 9:
        return False
    expected = img_size / 8
    return all(expected * 0.60 <= (boundaries[i + 1] - boundaries[i]) <= expected * 1.40
               for i in range(8))


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

    # Validar: si los intervalos son irregulares (Hough puso líneas en mal sitio)
    # caer al grid uniforme que es exactamente correcto para un warp 1000×1000.
    if not _grid_is_valid(col_boundaries, img_size):
        logger.debug("[HOUGH] col_boundaries inválido → usando uniforme")
        col_boundaries = uniform
    if not _grid_is_valid(row_boundaries, img_size):
        logger.debug("[HOUGH] row_boundaries inválido → usando uniforme")
        row_boundaries = uniform

    logger.debug(
        "[HOUGH] %d líneas H, %d líneas V → col=%s row=%s",
        len(h_pos), len(v_pos), col_boundaries, row_boundaries,
    )
    return col_boundaries, row_boundaries


# ── Caché de cuadrícula por análisis ─────────────────────────────────────────
# La cuadrícula se actualiza en cada frame hasta que Hough encuentre una
# válida (bordes equidistantes ±40%). Una vez encontrada, se congela.
# Si nunca se encuentra, se sigue usando la mejor vista hasta el momento.
_grid_cache:       dict[int, tuple[list[int], list[int]]] = {}
_grid_calibrated:  dict[int, bool]                        = {}


def _grid_for_frame(warped_image: np.ndarray) -> tuple[list[int], list[int]]:
    """
    Devuelve la mejor cuadrícula Hough disponible para este análisis.

    - Si ya hay una cuadrícula válida (bordes uniformes) en caché → devuélvela.
    - Si no, calcula una nueva desde este frame y guárdala si es mejor o si
      no había ninguna. Así la cuadrícula mejora frame a frame hasta que
      Hough encuentra las líneas del tablero con buena iluminación.
    """
    key = warped_image.shape[0]
    if _grid_calibrated.get(key, False):
        return _grid_cache[key]

    candidate = detect_grid_from_lines(warped_image)
    col_b, row_b = candidate
    img_size = key
    is_valid = _grid_is_valid(col_b, img_size) and _grid_is_valid(row_b, img_size)

    if key not in _grid_cache or is_valid:
        _grid_cache[key]      = candidate
        _grid_calibrated[key] = is_valid

    return _grid_cache[key]


def invalidate_grid_cache() -> None:
    """Limpia la caché de cuadrícula (útil entre análisis distintos)."""
    _grid_cache.clear()
    _grid_calibrated.clear()


# ── Auto-calibración del offset YOLO en el espacio warpeado ──────────────────
# Compensa el sesgo sistemático del bbox de YOLO: la base del bbox (y2) suele
# quedar unos píxeles por encima de donde la pieza realmente toca el tablero
# (las anotaciones del dataset cortan la base de la pieza). Al proyectar vía M
# este sesgo se traduce en un offset constante en el warped, frecuentemente
# del orden de 1 fila/columna. Calibramos una vez al inicio comparando las
# detecciones contra la posición inicial estándar.
_yolo_offset_x: float = 0.0
_yolo_offset_y: float = 0.0


def reset_yolo_offset() -> None:
    """Restablece el offset YOLO (entre análisis distintos)."""
    global _yolo_offset_x, _yolo_offset_y
    _yolo_offset_x = 0.0
    _yolo_offset_y = 0.0


def calibrate_yolo_offset(initial_warped, original_initial, M, verbose: bool = True):
    """
    Detecta el sesgo sistemático entre las posiciones reportadas por
    YOLO+M+grid y las posiciones esperadas de la posición inicial estándar.

    Para cada pieza detectada, busca la casilla MÁS CERCANA del set esperado
    (32 piezas iniciales) que coincida en TIPO. El vector de desplazamiento
    desde la posición detectada hasta el centro de la casilla esperada es
    el offset. Tomamos la mediana sobre todas las detecciones (robusta a
    detecciones falsas o casillas mal mapeadas).

    Una vez calibrado, detect_board_state aplica este offset a la salida de
    cv2.perspectiveTransform para corregir el sesgo.
    """
    global _yolo_offset_x, _yolo_offset_y
    _yolo_offset_x = 0.0
    _yolo_offset_y = 0.0

    model = get_model()
    if model is None or original_initial is None or M is None:
        return

    orig_h, orig_w = original_initial.shape[:2]
    img_small = cv2.resize(original_initial, (INFERENCE_SIZE, INFERENCE_SIZE))
    sx = orig_w / INFERENCE_SIZE
    sy = orig_h / INFERENCE_SIZE
    results = model(img_small, verbose=False, conf=CONFIDENCE_THRESHOLD)[0]

    col_bounds, row_bounds = _grid_for_frame(initial_warped)

    initial_board = chess.Board()
    expected = [(sq, initial_board.piece_at(sq).symbol())
                for sq in chess.SQUARES if initial_board.piece_at(sq) is not None]

    offsets = []
    for box in results.boxes:
        cls_id   = int(box.cls[0])
        cls_name = model.names[cls_id]
        piece_sym = CLASS_MAP.get(cls_name)
        if not piece_sym:
            neutral = _COLOR_NEUTRAL_MAP.get(cls_name)
            if neutral:
                # No podemos resolver el color sin saber la posición. Omitimos.
                continue
        if not piece_sym:
            continue

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        base_x = ((x1 + x2) / 2) * sx
        base_y = y2 * sy
        pt = np.array([[[base_x, base_y]]], dtype=np.float32)
        wpt = cv2.perspectiveTransform(pt, M)[0][0]
        wx, wy = float(wpt[0]), float(wpt[1])

        if wx < -50 or wx > NORMALIZED_SIZE + 50 or wy < -50 or wy > NORMALIZED_SIZE + 50:
            continue

        # Casilla esperada más cercana del mismo tipo
        best_sq, best_dist = None, float('inf')
        for sq, sym in expected:
            if sym != piece_sym:
                continue
            file_idx = chess.square_file(sq)
            rank_idx = chess.square_rank(sq)
            cy = (row_bounds[file_idx] + row_bounds[file_idx + 1]) / 2
            cx = (col_bounds[rank_idx] + col_bounds[rank_idx + 1]) / 2
            dist = ((wx - cx) ** 2 + (wy - cy) ** 2) ** 0.5
            if dist < best_dist:
                best_dist = dist
                best_sq = sq

        # Solo usar emparejamientos cercanos (descartar si la pieza está muy lejos
        # de cualquier casilla esperada — probable detección falsa)
        if best_sq is None or best_dist > 1.5 * (NORMALIZED_SIZE / 8):
            continue

        file_idx = chess.square_file(best_sq)
        rank_idx = chess.square_rank(best_sq)
        cy = (row_bounds[file_idx] + row_bounds[file_idx + 1]) / 2
        cx = (col_bounds[rank_idx] + col_bounds[rank_idx + 1]) / 2
        offsets.append((cx - wx, cy - wy))

    if len(offsets) >= 6:
        _yolo_offset_x = float(np.median([o[0] for o in offsets]))
        _yolo_offset_y = float(np.median([o[1] for o in offsets]))
        if verbose:
            logger.info(
                "[YOLO-CALIB] %d piezas usadas → offset dx=%+.1fpx dy=%+.1fpx",
                len(offsets), _yolo_offset_x, _yolo_offset_y
            )
            print(f"[YOLO-CALIB] {len(offsets)} piezas usadas → "
                  f"offset dx={_yolo_offset_x:+.1f}px dy={_yolo_offset_y:+.1f}px")
    else:
        if verbose:
            logger.info("[YOLO-CALIB] solo %d piezas detectadas — offset sin calibrar", len(offsets))
            print(f"[YOLO-CALIB] solo {len(offsets)} piezas — offset NO calibrado")


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


# ── Bayes filter: confianza por casilla ──────────────────────────────────────
# Acumula evidencia a lo largo de los frames de un mismo análisis.
# _square_beliefs[square][symbol] = peso acumulado (decae con el tiempo).
_square_beliefs: dict[int, dict[str, float]] = {}
_BELIEF_DECAY   = 0.6   # Cuánto se preserva la creencia previa (0=olvida, 1=jamás olvida)
_BELIEF_BOOST   = 1.0   # Peso que añade una nueva detección YOLO


def reset_square_beliefs() -> None:
    """Limpia el Bayes filter entre análisis distintos."""
    _square_beliefs.clear()


def _update_square_beliefs(raw_state: BoardState) -> None:
    """Actualiza las creencias por casilla con una nueva detección YOLO."""
    for sq in list(_square_beliefs.keys()):
        for sym in list(_square_beliefs[sq].keys()):
            _square_beliefs[sq][sym] *= _BELIEF_DECAY
    for sq, sym in raw_state.items():
        if sq not in _square_beliefs:
            _square_beliefs[sq] = {}
        _square_beliefs[sq][sym] = _square_beliefs[sq].get(sym, 0.0) + _BELIEF_BOOST


def _apply_square_beliefs(raw_state: BoardState) -> BoardState:
    """
    Fusiona la detección YOLO actual con las creencias acumuladas.
    Para casillas donde YOLO no detectó nada, añade la pieza más creíble
    si la creencia supera el umbral. Para casillas detectadas, confirma o
    corrige basándose en la confianza acumulada.
    """
    _update_square_beliefs(raw_state)

    result = dict(raw_state)

    # Casillas con creencia fuerte pero sin detección YOLO este frame → recuperar
    RECOVERY_THRESHOLD = 1.8
    for sq, beliefs in _square_beliefs.items():
        if sq in result:
            continue
        best_sym = max(beliefs, key=beliefs.__getitem__)
        if beliefs[best_sym] >= RECOVERY_THRESHOLD:
            result[sq] = best_sym

    return result


# ── Helpers para FEN agreement scoring ───────────────────────────────────────

def _board_to_state(board: chess.Board) -> BoardState:
    """Extrae el estado completo de un chess.Board como {square: símbolo}."""
    return {sq: board.piece_at(sq).symbol() for sq in chess.SQUARES if board.piece_at(sq)}


def _fen_agreement_score(candidate_state: BoardState, yolo_state: BoardState) -> float:
    """
    Cuantifica el acuerdo entre el estado candidato (derivado de python-chess)
    y la detección YOLO. Por cada casilla:
      +1.0  → ambos coinciden en la pieza (o ambos vacíos, no contabilizado)
      -0.50 → ambos ven pieza pero discrepan en tipo/color
      -0.30 → YOLO ve pieza, candidato está vacío (falso positivo YOLO)
      -0.15 → candidato tiene pieza, YOLO no la detecta (miss YOLO — penalización suave)
    """
    score = 0.0
    all_squares = set(candidate_state.keys()) | set(yolo_state.keys())
    for sq in all_squares:
        c_sym = candidate_state.get(sq, '')
        y_sym = yolo_state.get(sq, '')
        if c_sym == y_sym:
            score += 1.0
        elif c_sym and y_sym:
            score -= 0.50
        elif y_sym:
            score -= 0.30
        else:
            score -= 0.15
    return score



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
            # Punto base: intentar primero con el centro inferior del bbox
            # (donde la pieza toca el tablero), y si cae fuera del tablero usar
            # el centro del bbox como fallback (útil para piezas en bordes del frame).
            base_x_raw = ((x1 + x2) / 2) * sx
            # Candidatos de base_y: 100% bottom, 85% bottom / 15% top (near-bottom), 50% center
            base_y_candidates = [y2 * sy, (y1 * 0.15 + y2 * 0.85) * sy, ((y1 + y2) / 2) * sy]

            x_center = y_center = None
            for base_y_candidate in base_y_candidates:
                pt = np.array([[[base_x_raw, base_y_candidate]]], dtype=np.float32)
                warped_pt = cv2.perspectiveTransform(pt, M)[0][0]
                wpt_x = warped_pt[0] + _yolo_offset_x
                wpt_y = warped_pt[1] + _yolo_offset_y

                if wpt_x < -50 or wpt_x > NORMALIZED_SIZE + 50 or \
                   wpt_y < -50 or wpt_y > NORMALIZED_SIZE + 50:
                    continue  # fuera del tablero, probar siguiente candidato

                x_center = float(np.clip(wpt_x, 0, NORMALIZED_SIZE))
                y_center = float(np.clip(wpt_y, 0, NORMALIZED_SIZE))
                break  # primer candidato válido dentro del tablero

            if x_center is None:
                continue  # ningún candidato cae dentro del tablero → ignorar
        else:
            x_center = ((x1 + x2) / 2) * scale_factor
            y_center = ((y1 + y2) / 2) * scale_factor

        # Mapeo de clase → símbolo FEN
        piece = CLASS_MAP.get(cls_name)
        if not piece:
            neutral = _COLOR_NEUTRAL_MAP.get(cls_name)
            if neutral:
                white_sym, black_sym = neutral
                # x_center < 500 -> Blancas (ranks 1 y 2). x_center >= 500 -> Negras.
                piece = white_sym if x_center < (NORMALIZED_SIZE / 2) else black_sym
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
    board_state = _apply_square_beliefs(board_state)

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
                # Aplicar offset de auto-calibración (igual que en la detección)
                wx_adj = wpt[0] + _yolo_offset_x
                wy_adj = wpt[1] + _yolo_offset_y

                # Ignorar también en la visualización de debug
                if wx_adj < -50 or wx_adj > NORMALIZED_SIZE + 50 or \
                   wy_adj < -50 or wy_adj > NORMALIZED_SIZE + 50:
                    continue

                wx = float(np.clip(wx_adj, 0, NORMALIZED_SIZE))
                wy = float(np.clip(wy_adj, 0, NORMALIZED_SIZE))
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
        try:
            from .services import save_debug_image
        except ImportError:
            from services import save_debug_image
        global _yolo_debug_counter
        save_debug_image(f"yolo_detect_{_yolo_debug_counter:04d}", debug_img)
        _yolo_debug_counter += 1
    except Exception:
        pass

    return board_state


def detect_board_state_consensus(
    warped_frames: list,
    original_frames: Optional[list] = None,
    M: Optional[np.ndarray] = None,
    min_vote_ratio: float = 0.5,
) -> Optional[BoardState]:
    """
    Ejecuta detect_board_state sobre N frames estables consecutivos y devuelve
    el estado consensuado: una pieza se incluye sólo si aparece en al menos
    min_vote_ratio de las detecciones válidas.

    Reduce errores aleatorios de YOLO al requerir consistencia entre frames.
    Si todos los frames fallan (modelo no disponible), devuelve None.
    """
    if not warped_frames:
        return None

    n = len(warped_frames)
    if original_frames is None:
        original_frames = [None] * n

    votes: dict[int, dict[str, int]] = {}
    valid_detections = 0

    for warped, orig in zip(warped_frames, original_frames):
        state = detect_board_state(warped, orig, M)
        if state is None:
            continue
        valid_detections += 1
        for sq, sym in state.items():
            if sq not in votes:
                votes[sq] = {}
            votes[sq][sym] = votes[sq].get(sym, 0) + 1

    if valid_detections == 0:
        return None

    threshold = max(1, round(valid_detections * min_vote_ratio))
    result: BoardState = {}
    for sq, sym_counts in votes.items():
        best_sym = max(sym_counts, key=sym_counts.__getitem__)
        if sym_counts[best_sym] >= threshold:
            result[sq] = best_sym

    logger.debug(
        "[YOLO-CONSENSUS] %d/%d frames válidos → %d piezas consensuadas (threshold=%d)",
        valid_detections, n, len(result), threshold,
    )
    return result if result else None


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
    flow_squares: Optional[set] = None,
) -> Optional[chess.Move]:
    """
    Dadas las posiciones antes y después detectadas por YOLO, deduce el
    movimiento legal de python-chess que mejor explica la transición.

    Estrategia en 4 niveles:
      1. Exacto: identifica casillas fuente/destino; si hay varios candidatos,
         usa FEN agreement scoring para elegir el mejor.
      2. Enroque: solapamiento con las 4 casillas implicadas.
      3. Solapamiento máximo (fallback rápido).
      4. FEN agreement scoring sobre todos los movimientos legales, con bonus
         por casillas con flujo óptico significativo (flow_squares).
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

    castling_extras: dict[int, set[int]] = {
        chess.G1: {chess.H1, chess.F1},
        chess.C1: {chess.A1, chess.D1},
        chess.G8: {chess.H8, chess.F8},
        chess.C8: {chess.A8, chess.D8},
    }

    # ── Nivel 1: movimiento exacto con FEN scoring para desempate ────────────
    if sources and dests:
        candidates_1 = [
            move for move in board.legal_moves
            if move.from_square in sources and move.to_square in dests
        ]
        if len(candidates_1) == 1:
            return candidates_1[0]
        elif len(candidates_1) > 1:
            best = max(
                candidates_1,
                key=lambda m: _fen_agreement_score(_board_to_state(_push_copy(board, m)), state_after),
            )
            logger.debug("[YOLO] Nivel 1 desempate FEN: %s", best)
            return best

    # ── Nivel 2: enroque (4 casillas implicadas) ─────────────────────────────
    for move in board.legal_moves:
        if board.is_castling(move):
            involved = {move.from_square, move.to_square} | castling_extras.get(move.to_square, set())
            if len(involved & changed) >= 3:
                return move

    # ── Nivel 3: máximo solapamiento ─────────────────────────────────────────
    best_move, best_overlap = None, 0
    for move in board.legal_moves:
        involved = {move.from_square, move.to_square}
        if board.is_castling(move):
            involved |= castling_extras.get(move.to_square, set())
        overlap = len(involved & changed)
        if overlap > best_overlap:
            best_overlap, best_move = overlap, move

    if best_overlap >= 2:
        logger.debug("[YOLO] Nivel 3 solapamiento: %s (overlap=%d)", best_move, best_overlap)
        return best_move

    # ── Nivel 4: FEN agreement scoring sobre todos los movimientos legales ────
    # Se activa cuando los niveles anteriores no encontraron candidato (YOLO
    # detectó estado pero las casillas cambiadas no coinciden con ningún
    # movimiento legal exacto). El flujo óptico bonus (+0.5) desempata entre
    # movimientos con puntuación similar.
    if len(state_after) >= 4:    # Solo si YOLO detectó suficientes piezas
        best_fen_move, best_fen_score = None, -float('inf')
        for move in board.legal_moves:
            candidate = _board_to_state(_push_copy(board, move))
            score = _fen_agreement_score(candidate, state_after)
            if flow_squares and (move.from_square in flow_squares or move.to_square in flow_squares):
                score += 0.5
            if score > best_fen_score:
                best_fen_score, best_fen_move = score, move
        if best_fen_move is not None:
            logger.debug(
                "[YOLO] Nivel 4 FEN-scoring: %s (score=%.2f, flow=%s)",
                best_fen_move, best_fen_score,
                bool(flow_squares and (best_fen_move.from_square in flow_squares or best_fen_move.to_square in flow_squares)),
            )
            return best_fen_move

    return None


def _push_copy(board: chess.Board, move: chess.Move) -> chess.Board:
    """Devuelve una copia del tablero con el movimiento aplicado."""
    b = board.copy()
    b.push(move)
    return b


# ══════════════════════════════════════════════════════════════════════════════
# CLASIFICADOR DE CELDAS (alternativa al detector YOLO+proyección)
# ══════════════════════════════════════════════════════════════════════════════
#
# Funciona sobre la imagen WARPEADA 1000×1000 directamente:
#   1. Corta las 64 celdas de 125×125 px.
#   2. Clasifica cada celda con un MobileNetV2 entrenado con
#      generate_training_data.py + train_cell_classifier.py.
#   3. Devuelve {chess.Square → símbolo_FEN}, igual que detect_board_state.
#
# Ventaja: no hay proyección de perspectiva → no hay error de casilla adyacente.
# Para activarlo: asegúrate de que CELL_MODEL_PATH apunta al .pt entrenado.
# ══════════════════════════════════════════════════════════════════════════════

CELL_MODEL_PATH: str = getattr(
    settings,
    'CHESS_CELL_MODEL_PATH',
    os.path.join(settings.MEDIA_ROOT, 'models', 'cell_classifier.pt'),
)

_cell_model             = None
_cell_model_attempted   = False
_cell_class_names: list = []
_cell_img_size: int     = 128
_cell_device            = None
_cell_transform         = None


def _load_cell_model():
    """Carga el clasificador de celdas (una sola vez, con caché)."""
    global _cell_model, _cell_model_attempted, _cell_class_names
    global _cell_img_size, _cell_device, _cell_transform

    if _cell_model_attempted:
        return _cell_model

    _cell_model_attempted = True

    if not os.path.exists(CELL_MODEL_PATH):
        logger.info(
            "[CELL] Modelo de celdas no encontrado en '%s'. "
            "Entrénalo con train_cell_classifier.py.",
            CELL_MODEL_PATH,
        )
        return None

    try:
        import torch
        from torchvision import models as tvm, transforms

        checkpoint = torch.load(CELL_MODEL_PATH, map_location='cpu')
        _cell_class_names = checkpoint['class_names']
        n_classes          = checkpoint['n_classes']
        _cell_img_size     = checkpoint.get('img_size', 128)

        net = tvm.mobilenet_v2(weights=None)
        net.classifier[1] = torch.nn.Linear(net.last_channel, n_classes)
        net.load_state_dict(checkpoint['model_state_dict'])
        net.eval()

        _cell_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        _cell_model  = net.to(_cell_device)

        _cell_transform = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((_cell_img_size, _cell_img_size)),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225]),
        ])

        val_acc = checkpoint.get('val_acc', '?')
        logger.info(
            "[CELL] Clasificador de celdas cargado: %d clases, val_acc=%.3f, device=%s",
            n_classes, val_acc if isinstance(val_acc, float) else 0.0, _cell_device,
        )
        return _cell_model

    except Exception as exc:
        logger.error("[CELL] Error al cargar el clasificador de celdas: %s", exc)
        return None


def is_cell_classifier_available() -> bool:
    """Devuelve True si el clasificador de celdas está listo para usar."""
    return _load_cell_model() is not None


def _cut_cells_warped(warped: np.ndarray) -> dict:
    """Corta la imagen warpeada 1000×1000 en 64 celdas {chess.Square → BGR 125×125}."""
    cells = {}
    cs = int(CELL_SIZE)
    for col in range(8):      # eje X → rank
        for row in range(8):  # eje Y → file
            sq = chess.square(row, col)
            y1 = row * cs
            x1 = col * cs
            cells[sq] = warped[y1:y1 + cs, x1:x1 + cs]
    return cells


def detect_board_state_cells(warped: np.ndarray) -> Optional[BoardState]:
    """
    Detecta el estado completo del tablero clasificando cada celda individualmente.

    A diferencia de detect_board_state (YOLO + proyección de perspectiva),
    esta función opera directamente sobre la imagen warpeada 1000×1000:
    no hay proyección → no hay error de casilla adyacente.

    Devuelve {chess.Square → símbolo_FEN} o None si el modelo no está disponible.
    Formato idéntico a detect_board_state para compatibilidad total.
    """
    import torch

    model = _load_cell_model()
    if model is None:
        return None

    cells  = _cut_cells_warped(warped)
    result: BoardState = {}

    imgs_batch = []
    sqs_batch  = []

    for sq, cell_bgr in cells.items():
        cell_rgb = cv2.cvtColor(cell_bgr, cv2.COLOR_BGR2RGB)
        tensor   = _cell_transform(cell_rgb)
        imgs_batch.append(tensor)
        sqs_batch.append(sq)

    batch = torch.stack(imgs_batch).to(_cell_device)

    with torch.no_grad():
        logits = model(batch)
        preds  = logits.argmax(dim=1).cpu().numpy()

    # Mapa de labels del clasificador → símbolo FEN.
    # Los labels usan prefijos w/b (wR, bR...) para evitar el problema de
    # Windows con carpetas insensibles a mayúsculas (R/ == r/).
    _LABEL_TO_FEN = {
        'wK': 'K', 'wQ': 'Q', 'wR': 'R', 'wB': 'B', 'wN': 'N', 'wP': 'P',
        'bK': 'k', 'bQ': 'q', 'bR': 'r', 'bB': 'b', 'bN': 'n', 'bP': 'p',
        # Compatibilidad con modelos entrenados sin prefijos (versión antigua)
        'K': 'K', 'Q': 'Q', 'R': 'R', 'B': 'B', 'N': 'N', 'P': 'P',
        'k': 'k', 'q': 'q', 'r': 'r', 'b': 'b', 'n': 'n', 'p': 'p',
    }

    for sq, pred_idx in zip(sqs_batch, preds):
        label = _cell_class_names[pred_idx]
        fen_sym = _LABEL_TO_FEN.get(label)
        if fen_sym:
            result[sq] = fen_sym

    logger.debug(
        "[CELL] %d piezas detectadas: %s",
        len(result),
        {chess.square_name(sq): sym for sq, sym in result.items()},
    )
    return result


def invalidate_cell_model_cache() -> None:
    """Fuerza la recarga del clasificador de celdas en la próxima llamada."""
    global _cell_model, _cell_model_attempted
    _cell_model           = None
    _cell_model_attempted = False
