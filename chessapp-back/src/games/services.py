import json
import logging
import math
import os
import sys
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# Daphne/Twisted establece SelectorEventLoopPolicy en Windows, que no soporta
# subprocess_exec. Forzamos ProactorEventLoop para que los engines UCI puedan
# lanzar subprocesos desde los hilos del ThreadPoolExecutor.
if sys.platform == 'win32':
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsProactorEventLoopPolicy())

import cv2
import chess
import chess.engine
import numpy as np
from django.conf import settings
from rest_framework.response import Response
from rest_framework import status

logger = logging.getLogger(__name__)

_MEDIAPIPE_IMPORT_ERROR = None
_MEDIAPIPE_VERSION = None
try:
    import mediapipe as _mp
    _MEDIAPIPE_VERSION = getattr(_mp, '__version__', '?')
    # Algunas builds de mediapipe en Windows (Python Store) NO exponen el alias
    # corto `mediapipe.solutions` aunque sí incluyen el módulo en
    # `mediapipe.python.solutions`. Probamos ambos paths para ser robustos.
    try:
        import mediapipe.solutions.hands as _mp_hands           # path estándar
    except ModuleNotFoundError:
        try:
            import mediapipe.python.solutions.hands as _mp_hands  # fallback Windows
        except ModuleNotFoundError:
            # Fallback final: en algunas builds (mediapipe 0.10.14+) el __init__
            # ejecuta `del python` tras exponer el alias, lo que rompe el path
            # `import mediapipe.X.Y` pero deja accesible `mp.solutions.hands`
            # como atributo. Lo recuperamos así.
            _mp_hands = _mp.solutions.hands  # type: ignore[attr-defined]
    _MEDIAPIPE_AVAILABLE = True
except BaseException as _e:
    # Capturamos también BaseException porque algunas versiones de mediapipe en
    # Windows pueden lanzar errores nativos (DLL load failed, etc.) que no son
    # ImportError puros. Guardamos la traza completa para diagnosticar luego,
    # cuando el logger ya tenga handlers (la importación es muy temprana).
    import traceback as _tb
    _mp = None
    _mp_hands = None
    _MEDIAPIPE_AVAILABLE = False
    _MEDIAPIPE_IMPORT_ERROR = (
        f"{type(_e).__name__}: {_e}\n"
        f"Traceback:\n{''.join(_tb.format_exception(type(_e), _e, _e.__traceback__))}"
    )

TEMP_VIDEOS_LOCATION     = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
TEMP_FRAMES_LOCATION     = os.path.join(settings.MEDIA_ROOT, 'temp_frames')
ENGINES_DIR              = os.path.join(settings.BASE_DIR, 'misc', 'engines')
DEBUG_LOCATION           = os.path.join(settings.MEDIA_ROOT, 'debug')
FENS_LOCATION            = os.path.join(settings.MEDIA_ROOT, 'fens')
ENGINE_ANALYSIS_LOCATION = os.path.join(settings.MEDIA_ROOT, 'engine_analysis')
CORNERS_CONFIG_PATH      = os.path.join(settings.MEDIA_ROOT, 'corners_config.json')
FRAMES_CONFIG_PATH       = os.path.join(settings.MEDIA_ROOT, 'frames_config.json')

NORMALIZED_SIZE = 1000
CELL_CHANGE_THRESHOLD = 10          # Diferencia media de píxeles para considerar una celda cambiada

# ROI interior de cada celda para el análisis de cambios.
# Las piezas tienen altura y su parte superior sangra hacia la celda adyacente
# incluso después del warp (el warp sólo corrige el plano del tablero).
# Recortando los bordes superior e inferior de cada celda se analiza sólo la
# zona donde realmente reside la base de la pieza.
#
# Fracción del alto de la celda a descartar por arriba (0.0–1.0).
# Subir si las cimas de piezas altas contaminan la celda de encima.
CELL_ROI_TOP    = 0.25
# Fracción del alto de la celda a descartar por abajo (0.0–1.0, debe ser > CELL_ROI_TOP).
# Bajar para incluir más zona inferior si las piezas no se detectan.
CELL_ROI_BOTTOM = 0.92

# -----------------------------------------
# Progreso de análisis (por clave de vídeo)
# -----------------------------------------
_analysis_progress: dict = {}

def set_progress(key: str, pct: int) -> None:
    """Actualiza el progreso de análisis para la clave dada (0-100)."""
    _analysis_progress[key] = min(100, max(0, pct))

def get_progress(key: str) -> int:
    """Devuelve el progreso actual para la clave dada (0-100)."""
    return _analysis_progress.get(key, 0)

# -----------------------------------------
# Funciones de Manejo de Video
# -----------------------------------------

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

_mp_hands_instance = None

_hand_in_frame_logged = False


def _hand_in_frame(frame) -> bool:
    """Devuelve True si se detecta una mano/brazo en el frame (BGR).
    Usa MediaPipe si está disponible y HAND_FILTER_ENABLED=True; si no,
    devuelve False y deja actuar los filtros de estabilidad temporal."""
    global _mp_hands_instance, _hand_in_frame_logged
    if not HAND_FILTER_ENABLED:
        return False
    if not _MEDIAPIPE_AVAILABLE:
        if not _hand_in_frame_logged:
            logger.warning("[HANDS] MediaPipe no disponible (versión %s sin API solutions) "
                           "— filtro de manos desactivado; protección via LONG_MOTION_EXTRA_STABLE.",
                           _MEDIAPIPE_VERSION or "desconocida")
            if _MEDIAPIPE_IMPORT_ERROR:
                logger.debug("[HANDS] Detalle del fallo de import:\n%s", _MEDIAPIPE_IMPORT_ERROR)
            _hand_in_frame_logged = True
        return False
    try:
        if _mp_hands_instance is None:
            logger.info("[HANDS] Inicializando MediaPipe Hands (versión=%s, "
                        "min_confidence=%.2f)", _MEDIAPIPE_VERSION,
                        HAND_DETECTION_MIN_CONFIDENCE)
            _mp_hands_instance = _mp_hands.Hands(
                static_image_mode=True,
                max_num_hands=1,
                min_detection_confidence=HAND_DETECTION_MIN_CONFIDENCE,
            )
            logger.info("[HANDS] MediaPipe Hands inicializado correctamente")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = _mp_hands_instance.process(rgb)
        detected = bool(result.multi_hand_landmarks)
        if detected:
            # DEBUG (no INFO): si la mano está mucho rato, se acumulan miles
            # de líneas. El recuento agregado se loguea en el resumen final
            # del pipeline ([OCC] Finalizado: rej_hand=N).
            logger.debug("[HANDS] Mano detectada — esperando retirada")
        return detected
    except Exception as e:
        # Antes era logger.debug (silencioso). Ahora WARNING + traza completa la
        # PRIMERA vez para que el fallo sea visible. Si vuelve a fallar después,
        # bajamos a debug para no inundar el log.
        if not _hand_in_frame_logged:
            logger.warning("[HANDS] Excepción en detección de manos (primera ocurrencia): %s: %s",
                           type(e).__name__, e, exc_info=True)
            _hand_in_frame_logged = True
        else:
            logger.debug("[HANDS] Error en detección de manos: %s", e)
        return False

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

# ── Trigger temporal por absdiff ─────────────────────────────────────────────
# Sobre el WARPED 1000×1000 con blur. Sin zona neutra:
#   ratio < MOTION ⇒ estable (incrementa stable_run)
#   ratio ≥ MOTION ⇒ movimiento (resetea stable_run)
ABSDIFF_BIN_THRESHOLD   = 15      # umbral de binarización por pixel
MOTION_PIXEL_RATIO      = 0.003   # > 0.3% píxeles cambiados → movimiento real
STABLE_FRAMES_REQUIRED  = 4       # frames estables antes de analizar (más laxo: capturar
                                  # momentos breves de estabilidad entre movimientos rápidos)
COOLDOWN_AFTER_CAPTURE  = 5       # ~0.20s a 25fps — permite detectar movimientos consecutivos
                                  # rápidos. Filtros (repeat, lighting, Jaccard) descartan falsos.

# Filtro de estabilidad post-movimiento (Fase 1 — estabilidad temporal)
# Si el brazo/mano estuvo en movimiento durante más de LONG_MOTION_THRESHOLD frames
# consecutivos, se trata de un movimiento largo (brazo cruzando el tablero, no solo
# colocar una pieza). En ese caso se exigen frames de estabilidad adicionales antes
# de empezar la ventana YOLO, para dar tiempo a que el brazo se retire completamente.
# Este mecanismo actúa como fallback cuando MediaPipe no está disponible.
LONG_MOTION_THRESHOLD   = 20     # frames de movimiento continuo → brazo largo
LONG_MOTION_EXTRA_STABLE = 6     # frames de estabilidad adicionales para movimiento largo

# ── Scorer por ocupación/Jaccard ─────────────────────────────────────────────
# No necesita clasificar el tipo de pieza: usa varianza por celda para detectar
# qué casillas cambiaron de ocupación, y luego Jaccard contra los movimientos
# legales para identificar el movimiento. Más robusto que YOLO+proyección.
STABLE_WINDOW_SIZE     = 2      # frames estables a acumular antes de analizar (era 3)
OCC_VARIANCE_TOP_K     = 8      # top-K casillas con mayor cambio de varianza
OCC_VARIANCE_MIN_THR   = 40.0   # cambio mínimo de varianza para considerar casilla modificada
JACCARD_ACCEPT_THR     = 0.12   # fracción mínima de varianza total para aceptar un movimiento
JACCARD_MARGIN_REQ     = 0.06   # margen mínimo entre el mejor y el segundo candidato
RECOVERY_REJECT_THR    = 10     # rechazos consecutivos para intentar recuperación
RECOVERY_MATCH_THR     = 0.86   # fracción de casillas que deben coincidir (≈55/64)
RECOVERY_DEPTH         = 3      # profundidad BFS (hasta 3 movimientos adelante)

# ── Modo WHEN-only ───────────────────────────────────────────────────────────
# Cuando WHEN_ONLY_MODE = True el pipeline detecta SÓLO cuándo se produjo un
# movimiento (Fases 1-2c) y no intenta identificar cuál fue (Fase 3 y posteriores
# quedan cortocircuitadas). El identificador (WHICH) se aborda en una segunda
# etapa que consume la lista de keyframes producida aquí.
# Con WHEN_ONLY_MODE = False se mantiene el comportamiento clásico (Jaccard +
# multi-move + recovery + actualización de legal_board).
WHEN_ONLY_MODE = True

# ── Filtro refractario (post-aceptación) ─────────────────────────────────────
# Tras un movimiento real, durante los siguientes REFRACTORY_WINDOW frames es
# habitual que el sistema dispare un segundo evento "phantom" provocado por
# residuos de mano, sombras o pequeñas variaciones de iluminación. Esos eventos
# tienen como firma una varianza top notablemente MENOR que la del evento real
# previo (ratios típicos 0.1–0.4 frente a ≈1.0 de jugadas rápidas reales).
# Dentro de la ventana refractaria, exigimos top_var ≥ ratio · prev_top_var.
REFRACTORY_WINDOW         = 30    # frames tras la última aceptación
REFRACTORY_MIN_VAR_RATIO  = 0.4   # umbral relativo al evento previo

# ── Fusión de keyframes duplicados (post-extracción) ─────────────────────────
# Phantoms residuales (que pasan los filtros en tiempo real) pueden detectarse
# globalmente comparando pares de keyframes consecutivos. La firma de un
# phantom es un cambio DIFUSO y de baja-moderada magnitud: varias casillas con
# varianzas similares en 400-700, sin un pico claro. Un movimiento REAL produce
# una sola casilla dominante (>1000) y las demás mucho menores.
# Criterios para fusionar dos keyframes consecutivos:
#   (a) top1 < FUSE_WEAK_TOP_VAR (cambio insignificante)
#   (b) top1 < FUSE_MODERATE_TOP_VAR Y top1/top2 < FUSE_CONCENTRATION_RATIO
#       (cambio difuso de magnitud moderada)
# Si NO se cumple ninguno, los keyframes representan estados distintos y se
# conservan ambos.
FUSE_DUPLICATES             = True
FUSE_WEAK_TOP_VAR           = 500.0   # umbral de "cambio insignificante"
FUSE_MODERATE_TOP_VAR       = 1000.0  # umbral para aplicar el test de concentración
FUSE_CONCENTRATION_RATIO    = 1.8     # top1/top2 mínimo para considerar concentrado
# Fusión por proximidad temporal: dos kfs separados por < FUSE_TEMPORAL_FRAMES
# son casi siempre el mismo movimiento físico capturado dos veces (frame
# intermedio + frame final). Una jugada humana real consume ≥ 1.5 s tras la
# anterior, así que con fps=24 hay margen >35 frames; usamos 25 (~1 s) como
# umbral conservador. El kf KEPT es el ÚLTIMO del par — su estado post-mov
# está más estabilizado (la mano del jugador ya retirada, peón asentado).
#
# Histórico: probado a 60 (~2.5 s) en sesión 2026-05-06 para fusionar las
# cadenas de SKIPs ruidosos del test9 (kfs #46-#50). Resultado: regresión
# catastrófica — test1 perdió 10 movs LCS (42.5 % → 28.8 %), test9 perdió
# 2 movs (35 % → 25 %). En test1-3 las jugadas reales sí están separadas
# <2.5 s a veces y el bump las fusionaba indebidamente. Revertido a 25.
FUSE_TEMPORAL_FRAMES        = 25

# ── Filtro de manos (MediaPipe) ──────────────────────────────────────────────
# HAND_FILTER_ENABLED: kill switch global. MediaPipe procesa el frame entero
# (mesa, paredes, fondo) y en cámaras con encuadre lateral genera muchísimos
# falsos positivos sobre piezas y texturas no-mano. En las pruebas con 5
# vídeos, activarlo a confianza 0.85 quitaba phantoms de test1/test2 pero
# perdía movimientos reales en test4 (-3) y test5 (-35). Para un detector
# WHEN orientado a recall (la fase WHICH posterior puede fusionar duplicados
# pero no puede recuperar eventos perdidos) sale neto negativo, así que se
# desactiva por defecto. Ponlo a True si tu setup de cámara es restringido
# y quieres ganar precisión a costa de algún recall.
# HAND_DETECTION_MIN_CONFIDENCE: umbral de confianza de MediaPipe Hands.
HAND_FILTER_ENABLED            = False
HAND_DETECTION_MIN_CONFIDENCE  = 0.85

# Filtro de concentración: discrimina "movimiento real" de "cambio difuso".
# Un movimiento real concentra la varianza en 2-4 casillas (origen + destino +
# alguna phantom). Un cambio de iluminación o brazo sin retirar genera varianza
# moderada distribuida sobre muchas casillas.
LIGHTING_REJECT_TOP_VAR   = 400.0  # varianza mínima de la casilla más cambiada
LIGHTING_REJECT_RATIO     = 4.0    # top_var debe ser ≥ 4× mediana

# Multi-move: para aceptar una secuencia (mvA, mvB) en lugar de un único
# movimiento, exigimos evidencia robusta de que SE PRODUJERON DOS movimientos.
# Las casillas de mvB que no comparte con mvA ("extras") deben tener cada una
# varianza alta absoluta — si alguna es phantom (varianza baja), el multi se
# está "inventando" el segundo movimiento basándose en ruido de proyección.
MULTI_MIN_EXTRA_VAR        = 600.0  # cada casilla extra de mvB ≥ este valor
MULTI_MARGIN_OVER_SINGLE   = 0.30   # multi_score debe superar single_score por
MULTI_MIN_FALLBACK_SCORE_BONUS = 0.30  # si single rechazó, multi necesita
                                       # JACCARD_ACCEPT_THR + este bonus

def _pixel_changed_squares(prev_warped, curr_warped, top_k=6, threshold=5):
    """
    Identifica los chess.Square con mayor diferencia de píxeles entre dos
    frames warpeados usando la MISMA grid Hough que detect_board_state.

    La diferencia con get_changed_cells es fundamental: get_changed_cells usa
    la grid UNIFORME de 125px por celda, que puede no coincidir con las
    líneas reales del tablero. Si la homografía coloca el tablero ligeramente
    desplazado respecto al grid uniforme, las casillas se asignan erróneamente
    (off-by-one). Usando la grid Hough (que detecta las líneas reales) ambas
    funciones (pixel-diff y YOLO) operan en el mismo sistema de casillas.
    """
    try:
        from .chess_detector import _grid_for_frame
    except ImportError:
        from chess_detector import _grid_for_frame

    col_bounds, row_bounds = _grid_for_frame(curr_warped)

    gray_prev = cv2.cvtColor(prev_warped, cv2.COLOR_BGR2GRAY) if len(prev_warped.shape) == 3 else prev_warped
    gray_curr = cv2.cvtColor(curr_warped, cv2.COLOR_BGR2GRAY) if len(curr_warped.shape) == 3 else curr_warped

    cell_diffs = []
    for file_idx in range(8):
        r0 = row_bounds[file_idx]
        r1 = row_bounds[file_idx + 1]
        for rank_idx in range(8):
            c0 = col_bounds[rank_idx]
            c1 = col_bounds[rank_idx + 1]
            if r1 <= r0 or c1 <= c0:
                cell_diffs.append((chess.square(file_idx, rank_idx), 0.0))
                continue
            cb = gray_prev[r0:r1, c0:c1].astype(np.float32)
            ca = gray_curr[r0:r1, c0:c1].astype(np.float32)
            diff = float(np.mean(np.abs(
                (ca - np.mean(ca)) - (cb - np.mean(cb))
            )))
            cell_diffs.append((chess.square(file_idx, rank_idx), diff))

    if not cell_diffs:
        return set()

    # Compensar variaciones globales de iluminación (mismo método que get_changed_cells)
    diffs_only = [d for _, d in cell_diffs]
    median_diff = float(np.median(diffs_only))

    significant = [(sq, d - median_diff) for sq, d in cell_diffs if d - median_diff > threshold]
    significant.sort(key=lambda x: x[1], reverse=True)
    return {sq: diff for sq, diff in significant[:top_k]}


def _move_changed_squares(legal_board, move):
    """
    Devuelve el conjunto de casillas (chess.Square) que el move cambia
    físicamente: origen, destino, peón capturado al paso, y casillas de
    torre en enroque.
    """
    squares = {move.from_square, move.to_square}

    if legal_board.is_castling(move):
        rank = chess.square_rank(move.from_square)
        if chess.square_file(move.to_square) == 6:   # enroque corto
            squares.add(chess.square(7, rank))       # torre origen (h)
            squares.add(chess.square(5, rank))       # torre destino (f)
        else:                                         # enroque largo
            squares.add(chess.square(0, rank))       # torre origen (a)
            squares.add(chess.square(3, rank))       # torre destino (d)

    elif legal_board.is_en_passant(move):
        # El peón capturado está en la misma fila que el atacante antes del move
        if legal_board.turn == chess.WHITE:
            squares.add(move.to_square - 8)
        else:
            squares.add(move.to_square + 8)

    return squares


def _consecutive_keyframes_are_duplicates(frame_a: np.ndarray,
                                          frame_b: np.ndarray) -> tuple[bool, float, float]:
    """
    Determina si dos warped frames consecutivos representan visualmente el
    mismo estado del tablero (phantom de un evento previo o drift de
    iluminación). Devuelve (es_duplicado, top1, ratio_top1_top2).

    Criterios para "mismo estado":
      (a) top1 < FUSE_WEAK_TOP_VAR      → cambio insignificante
      (b) top1 < FUSE_MODERATE_TOP_VAR  Y  top1/top2 < FUSE_CONCENTRATION_RATIO
          → cambio difuso de magnitud moderada (varias casillas con
            varianzas similares, sin pico claro = lighting/sombra)
    """
    diffs = _variance_diff_all(frame_a, frame_b)
    sorted_vals = sorted(diffs.values(), reverse=True)
    top1 = sorted_vals[0]
    top2 = sorted_vals[1] if len(sorted_vals) > 1 else 1.0
    ratio = top1 / max(top2, 1.0)

    if top1 < FUSE_WEAK_TOP_VAR:
        return True, top1, ratio
    if top1 < FUSE_MODERATE_TOP_VAR and ratio < FUSE_CONCENTRATION_RATIO:
        return True, top1, ratio
    return False, top1, ratio


def _fuse_consecutive_duplicate_keyframes(key_frames, key_frames_orig,
                                          key_frame_indices, detected_states,
                                          accepted_moves):
    """
    Pasada de post-proceso: recorre la lista de keyframes y elimina los que
    sean visualmente equivalentes al último keyframe conservado (phantoms o
    drifts de iluminación que pasaron los filtros en tiempo real).

    Compara cada keyframe contra el ÚLTIMO conservado, no contra el inmediato
    anterior — así colapsa cadenas de phantoms (A, A', A'' → A).
    """
    if len(key_frames) < 2:
        return (key_frames, key_frames_orig, key_frame_indices,
                detected_states, accepted_moves)

    # ── Pasada 1: fusión temporal ───────────────────────────────────────
    # Si dos kfs están a < FUSE_TEMPORAL_FRAMES de distancia (≈1 s a 24 fps),
    # casi seguro son el mismo mov físico capturado dos veces. Mantenemos el
    # SEGUNDO (estado post-mov más estabilizado, mano del jugador retirada).
    # Esto resuelve el caso patológico de test1 #1-#2 (frames 173 y 183, Δ=10).
    keep_temporal = [True] * len(key_frames)
    fused_temporal = 0
    if len(key_frame_indices) == len(key_frames):
        for i in range(1, len(key_frames)):
            if not keep_temporal[i]:
                continue
            # Buscar el último kf retenido antes de i
            j = i - 1
            while j >= 0 and not keep_temporal[j]:
                j -= 1
            if j < 0:
                continue
            df = int(key_frame_indices[i]) - int(key_frame_indices[j])
            if 0 < df < FUSE_TEMPORAL_FRAMES:
                # Descartar j (el ANTERIOR), mantener i (el más tardío).
                keep_temporal[j] = False
                fused_temporal += 1
                logger.info("[OCC] Fusión temporal: keyframe #%d (frame %d) "
                            "descartado vs #%d (frame %d) — Δ=%d < %d frames",
                            j + 1, int(key_frame_indices[j]),
                            i + 1, int(key_frame_indices[i]),
                            df, FUSE_TEMPORAL_FRAMES)

    if fused_temporal:
        key_frames        = [key_frames[i]        for i in range(len(key_frames))      if keep_temporal[i]]
        key_frames_orig   = [key_frames_orig[i]   for i in range(len(key_frames_orig)) if keep_temporal[i]]
        key_frame_indices = [key_frame_indices[i] for i in range(len(key_frame_indices)) if keep_temporal[i]]
        detected_states   = [detected_states[i]   for i in range(len(detected_states)) if keep_temporal[i]]
        if accepted_moves:
            accepted_moves = [accepted_moves[i] for i in range(len(accepted_moves))
                              if i < len(keep_temporal) and keep_temporal[i]]

    if len(key_frames) < 2:
        return (key_frames, key_frames_orig, key_frame_indices,
                detected_states, accepted_moves)

    # ── Pasada 2: fusión visual (sin cambio significativo entre kfs) ────
    keep = [False] * len(key_frames)
    keep[0] = True
    last_kept = 0
    fused_count = 0

    for i in range(1, len(key_frames)):
        is_dup, top1, ratio = _consecutive_keyframes_are_duplicates(
            key_frames[last_kept], key_frames[i])
        if is_dup:
            fused_count += 1
            logger.info("[OCC] Fusión: keyframe #%d descartado vs #%d "
                        "(top1=%.0f, ratio=%.2f, frame=%d)",
                        i + 1, last_kept + 1, top1, ratio,
                        key_frame_indices[i] if i < len(key_frame_indices) else -1)
        else:
            keep[i] = True
            last_kept = i

    if fused_count == 0 and fused_temporal == 0:
        return (key_frames, key_frames_orig, key_frame_indices,
                detected_states, accepted_moves)
    if fused_count == 0:
        # Solo se aplicó fusión temporal — devolvemos el resultado de pasada 1.
        return (key_frames, key_frames_orig, key_frame_indices,
                detected_states, accepted_moves)

    logger.info("[OCC] Fusión completada: %d duplicados eliminados de %d "
                "→ %d keyframes finales",
                fused_count, len(key_frames), len(key_frames) - fused_count)

    new_kf      = [key_frames[i]        for i in range(len(key_frames))      if keep[i]]
    new_kf_orig = [key_frames_orig[i]   for i in range(len(key_frames_orig)) if keep[i]]
    new_kf_idx  = [key_frame_indices[i] for i in range(len(key_frame_indices)) if keep[i]]
    new_states  = [detected_states[i]   for i in range(len(detected_states)) if keep[i]]
    new_moves   = ([accepted_moves[i]   for i in range(len(accepted_moves))
                    if i < len(keep) and keep[i]]
                   if accepted_moves else accepted_moves)

    return new_kf, new_kf_orig, new_kf_idx, new_states, new_moves


# ══════════════════════════════════════════════════════════════════════════════
# SCORER POR OCUPACIÓN / JACCARD
# No usa YOLO ni clasificador de celdas para detectar movimientos.
# Solo necesita varianza por celda + reglas de ajedrez (python-chess).
# ══════════════════════════════════════════════════════════════════════════════

def _cell_variance_map(warped: np.ndarray) -> dict:
    """
    Devuelve {chess.Square → varianza} para cada una de las 64 celdas.
    Aplica CELL_ROI vertical para enfocar la zona de la base de la pieza,
    descartando la parte superior de cada celda donde aparecen proyecciones
    visuales de piezas altas situadas en filas inferiores (más cercanas a la
    cámara). Esto reduce el "phantom variance" causado por el ángulo elevado.
    """
    cs       = NORMALIZED_SIZE // 8                  # 125 px
    roi_top  = int(cs * CELL_ROI_TOP)                # 31  → descarta el 25 % superior
    roi_bot  = int(cs * CELL_ROI_BOTTOM)             # 115 → descarta el 8 % inferior
    gray     = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY).astype(np.float32)
    result   = {}
    for col in range(8):      # rank (eje X)
        for row in range(8):  # file (eje Y)
            sq   = chess.square(row, col)
            y1   = row * cs + roi_top
            y2   = row * cs + roi_bot
            x1   = col * cs
            x2   = (col + 1) * cs
            cell = gray[y1:y2, x1:x2]
            result[sq] = float(np.var(cell))
    return result


def _variance_diff_all(ref_warped: np.ndarray, curr_warped: np.ndarray) -> dict:
    """Devuelve {sq → |var_actual - var_referencia|} para las 64 casillas."""
    ref_v  = _cell_variance_map(ref_warped)
    curr_v = _cell_variance_map(curr_warped)
    return {sq: abs(curr_v[sq] - ref_v[sq]) for sq in chess.SQUARES}


def _changed_squares_occ(ref_warped: np.ndarray, curr_warped: np.ndarray,
                          top_k: int = OCC_VARIANCE_TOP_K,
                          min_thr: float = OCC_VARIANCE_MIN_THR) -> dict:
    """
    Devuelve las top_k casillas con mayor cambio de varianza entre la referencia
    y el frame actual, filtradas por encima de la mediana + min_thr.
    Si min_thr no se pasa, se usa el valor por defecto del módulo.
    Retorna {sq → var_diff}.
    """
    diffs  = _variance_diff_all(ref_warped, curr_warped)
    median = float(np.median(list(diffs.values())))
    threshold = median + min_thr
    significant = {sq: d for sq, d in diffs.items() if d > threshold}
    sorted_sqs = sorted(significant, key=significant.__getitem__, reverse=True)
    return {sq: significant[sq] for sq in sorted_sqs[:top_k]}


# ══════════════════════════════════════════════════════════════════════════════
# YOLO-based move matching helpers (motor primario de la fase WHICH)
#
# Filosofía: YOLO observa el ESTADO ABSOLUTO del tablero en cada keyframe ("qué
# pieza hay en cada casilla, con su color"). El movimiento se deduce comparando
# el estado CANÓNICO del legal_board (autoritativo) contra el estado OBSERVADO
# por YOLO en el keyframe de después.
#
# El modelo YOLO disponible tiene 12 clases con color (white-king...black-pawn),
# así que comparamos por COLOR + TIPO (símbolo FEN exacto, mayúsculas=blancas,
# minúsculas=negras). Esto rompe ambigüedades entre piezas iguales de bandos
# distintos y captura información completa de cada captura (cambia color y tipo
# en la casilla destino).
# ══════════════════════════════════════════════════════════════════════════════

def _board_to_state_symbols(board: 'chess.Board') -> dict:
    """{square: símbolo_FEN} (case=color) para todas las piezas del tablero."""
    return {sq: board.piece_at(sq).symbol()
            for sq in chess.SQUARES if board.piece_at(sq) is not None}


def _yolo_state_agreement(expected: dict, observed: dict) -> tuple:
    """
    Cuenta coincidencias y desacuerdos entre estado esperado y observado.

    Devuelve (agree_full, agree_color, agree_type, disagree, missed, extra):
      - agree_full:   misma pieza Y mismo color en la misma casilla.
      - agree_color:  mismo COLOR pero tipo distinto (la señal más robusta
                      cuando el modelo confunde tipos de pieza dentro del
                      mismo bando — ej: peón clasificado como caballo).
      - agree_type:   mismo TIPO pero color distinto (evidencia más débil:
                      sugeriría error de bando, lo cual sería sospechoso
                      pero no imposible).
      - disagree:     ambos ven pieza, distinto color Y distinto tipo
                      (caso muy poco frecuente — error grave del modelo).
      - missed:       expected tiene pieza pero observed la perdió.
      - extra:        observed reporta pieza donde expected no tiene.
    """
    all_sqs = set(expected.keys()) | set(observed.keys())
    agree_full = agree_color = agree_type = disagree = missed = extra = 0
    for sq in all_sqs:
        e = expected.get(sq)
        o = observed.get(sq)
        if e and o:
            if e == o:
                agree_full += 1
            else:
                # e[0].isupper() distingue mayúsculas (blancas) de minúsculas (negras)
                same_color = (e.isupper() == o.isupper())
                same_type  = (e.upper() == o.upper())
                if same_color:
                    agree_color += 1
                elif same_type:
                    agree_type += 1
                else:
                    disagree += 1
        elif e and not o:
            missed += 1
        elif o and not e:
            extra += 1
    return agree_full, agree_color, agree_type, disagree, missed, extra


def _yolo_score_state(expected: dict, observed: dict,
                      focus_sqs: set | None = None,
                      focus_weight: float = 3.0) -> float:
    """
    Score de acuerdo entre estado esperado y observado [aprox. -∞..1].

    Si se pasa `focus_sqs` (típicamente las casillas afectadas por el mov
    candidato — origen y destino), esas casillas pesan `focus_weight` (×3 por
    defecto) y el resto del tablero pesa ×1. Esto amplifica la discriminación
    entre candidatos: el ruido del modelo en piezas no-relacionadas (típico
    en back rank, donde confunde N↔B↔Q) deja de empatar candidatos.

    Pesos calibrados al comportamiento observado del modelo: acierta colores
    casi siempre, pero confunde tipos dentro del mismo bando con frecuencia.

    +1.00 por coincidencia exacta (mismo color y tipo).
    +0.80 por coincidencia de COLOR (mismo bando, tipo distinto).
    +0.20 por coincidencia de tipo (color distinto). Caso raro.
    -0.50 por desacuerdo total (ambos ven pieza pero ni color ni tipo).
    -0.30 por extra (YOLO ve pieza donde no la hay).
    -0.10 por miss (penalización SUAVE: oclusiones son frecuentes).

    Normalizado al nº de piezas esperadas (con peso por focus).
    """
    if focus_sqs is None:
        # Camino rápido: pesos uniformes (compatibilidad hacia atrás).
        agree_full, agree_color, agree_type, disagree, missed, extra = \
            _yolo_state_agreement(expected, observed)
        raw = (1.0 * agree_full
               + 0.8 * agree_color
               + 0.2 * agree_type
               - 0.5 * disagree
               - 0.3 * extra
               - 0.1 * missed)
        n_expected = max(1, len(expected))
        return raw / n_expected

    # Variante focalizada: peso extra para las casillas del mov candidato.
    raw = 0.0
    norm = 0.0
    all_sqs = set(expected.keys()) | set(observed.keys())
    for sq in all_sqs:
        e = expected.get(sq)
        o = observed.get(sq)
        w = focus_weight if sq in focus_sqs else 1.0
        if e and o:
            if e == o:
                raw += w * 1.0
            else:
                same_color = (e.isupper() == o.isupper())
                same_type  = (e.upper() == o.upper())
                if same_color:
                    raw += w * 0.8
                elif same_type:
                    raw += w * 0.2
                else:
                    raw += w * (-0.5)
        elif e and not o:
            raw += w * (-0.1)
        elif o and not e:
            raw += w * (-0.3)
        if e:
            norm += w
    return raw / max(1.0, norm)


# ── YOLO-DIFF matcher: usa la diferencia entre dos estados YOLO (before/after) ─
# La intuición: si YOLO confunde sistemáticamente el tipo de una pieza en ambos
# estados (p.ej. dama blanca etiquetada como "R" en before y after), la
# confusión se cancela en el diff. Sólo aparecen las casillas REALMENTE
# afectadas por el movimiento. Esto evita el problema de "varios movimientos
# del mismo bando dan exactamente el mismo score" porque la mayor parte del
# tablero no cambia y los pesos de _yolo_score_state los empujan al mismo valor.

def _yolo_color_map(yolo_state: dict) -> dict:
    """{square: 'W' | 'B'} solo con presencia/color (ignora tipo)."""
    if not yolo_state:
        return {}
    return {sq: ('W' if sym.isupper() else 'B') for sq, sym in yolo_state.items()}


def _yolo_diff_squares(state_before: dict, state_after: dict) -> set:
    """Conjunto de casillas que cambiaron presencia o color entre dos estados YOLO."""
    cb = _yolo_color_map(state_before)
    ca = _yolo_color_map(state_after)
    all_sqs = set(cb.keys()) | set(ca.keys())
    return {sq for sq in all_sqs if cb.get(sq) != ca.get(sq)}


def _yolo_diff_score_move(
    legal_board: 'chess.Board',
    move: 'chess.Move',
    yolo_diff: set,
    yolo_state_after: dict,
) -> float:
    """
    Puntúa un movimiento candidato según cómo de bien coinciden sus casillas
    afectadas con el diff observado por YOLO.

    Componentes:
      • Jaccard(move_affected, yolo_diff)   → similitud de los conjuntos.
      • Bonus +0.3 si la casilla destino del movimiento aparece con la pieza
        del color correcto en yolo_state_after (señal positiva específica).
      • Bonus +0.2 si la casilla origen está vacía en yolo_state_after.
    """
    move_sqs = _move_changed_squares(legal_board, move)
    if not move_sqs and not yolo_diff:
        return 0.0
    if not move_sqs:
        return 0.0
    inter = move_sqs & yolo_diff
    union = move_sqs | yolo_diff
    jaccard = len(inter) / len(union) if union else 0.0

    bonus = 0.0
    moving_white = legal_board.turn  # True si toca blanco mover
    to_obs = yolo_state_after.get(move.to_square)
    if to_obs and (to_obs.isupper() == moving_white):
        bonus += 0.30
    from_obs = yolo_state_after.get(move.from_square)
    if from_obs is None:
        bonus += 0.20

    return jaccard + bonus


def _yolo_match_single_move_diff(
    legal_board: 'chess.Board',
    yolo_state_before: dict,
    yolo_state_after: dict,
    top_k: int = 5,
) -> tuple | None:
    """
    Variante DIFF del matcher: encuentra el movimiento legal cuyas casillas
    afectadas mejor coinciden con el diff color/presencia entre los dos
    estados YOLO. Solo se usa si hay al menos 1 casilla cambiada.
    """
    if not yolo_state_after:
        return None
    legal_moves = list(legal_board.legal_moves)
    if not legal_moves:
        return None

    yolo_diff = _yolo_diff_squares(yolo_state_before or {}, yolo_state_after)
    if not yolo_diff:
        return None  # YOLO no vio cambios — devolver None para que caiga al matcher de estado

    scored: list = []
    for mv in legal_moves:
        s = _yolo_diff_score_move(legal_board, mv, yolo_diff, yolo_state_after)
        scored.append((mv, s))
    scored.sort(key=lambda x: x[1], reverse=True)
    best_mv, best_score = scored[0]
    runner = scored[1][1] if len(scored) > 1 else float('-inf')
    margin = best_score - runner
    alts = [(m.uci(), s) for m, s in scored[:top_k]]
    return best_mv, best_score, margin, alts


# ── Desempate por varianza píxel-a-píxel (señal independiente de YOLO) ───────
# Cuando YOLO no diferencia entre varios movimientos candidatos (margen 0),
# la varianza por celda entre los frames warpeados ANTES y DESPUÉS del evento
# sigue dando una señal clara: las casillas que físicamente cambiaron tienen
# varianza alta. Esta función reordena los candidatos YOLO usando esa señal.

def _variance_score_for_move(
    legal_board: 'chess.Board',
    move: 'chess.Move',
    diffs: dict,
) -> float:
    """
    Fracción de la varianza total que se concentra en las casillas afectadas
    por el movimiento. Score alto → alta evidencia visual de que ese
    movimiento es el responsable del cambio observado.
    """
    total = sum(diffs.values()) + 1e-6
    move_sqs = _move_changed_squares(legal_board, move)
    captured = sum(diffs.get(sq, 0.0) for sq in move_sqs)
    return captured / total


def _pure_variance_match(
    legal_board: 'chess.Board',
    ref_warped: 'np.ndarray',
    curr_warped: 'np.ndarray',
    top_k: int = 5,
) -> tuple | None:
    """
    Busca el movimiento legal cuya casillas afectadas concentran la mayor
    fracción de la varianza píxel-a-píxel observada entre los dos frames.

    Útil como rescate cuando YOLO no aporta señal de discriminación entre
    candidatos (margen 0 entre múltiples movs) o no detecta el movimiento
    real (típicamente knight moves donde YOLO no ve la pieza nueva en su
    casilla destino, pero la varianza del píxel sí muestra el cambio).

    Devuelve (best_move, var_score, margin, alts_top_k) o None.
    """
    legal_moves = list(legal_board.legal_moves)
    if not legal_moves:
        return None
    diffs = _variance_diff_all(ref_warped, curr_warped)
    scored = [(m, _variance_score_for_move(legal_board, m, diffs))
              for m in legal_moves]
    scored.sort(key=lambda x: x[1], reverse=True)
    best_mv, best_score = scored[0]
    runner = scored[1][1] if len(scored) > 1 else 0.0
    margin = best_score - runner
    alts = [(m.uci(), s) for m, s in scored[:top_k]]
    return best_mv, best_score, margin, alts


def _break_tie_by_variance(
    legal_board: 'chess.Board',
    candidates: list,
    ref_warped: 'np.ndarray',
    curr_warped: 'np.ndarray',
    score_eps: float = 0.005,
) -> tuple | None:
    """
    Dado un conjunto de candidatos YOLO (lista [(move, yolo_score), ...]
    ordenada por yolo_score desc), filtra los empatados con el primero
    (score dentro de `score_eps`) y elige el que mejor concentra varianza
    píxel en sus casillas afectadas.

    Devuelve (best_move, var_score, var_margin) o None si no hay candidatos.
    """
    if not candidates:
        return None
    top_score = candidates[0][1]
    tied = [(m, s) for m, s in candidates if (top_score - s) <= score_eps]
    if len(tied) <= 1:
        return None  # un único líder claro → desempate innecesario

    diffs = _variance_diff_all(ref_warped, curr_warped)
    scored_var = [(m, _variance_score_for_move(legal_board, m, diffs)) for m, _ in tied]
    scored_var.sort(key=lambda x: x[1], reverse=True)
    best_mv, best_var = scored_var[0]
    runner_var = scored_var[1][1] if len(scored_var) > 1 else 0.0
    return best_mv, best_var, best_var - runner_var


def _intelligent_tiebreak(
    legal_board: 'chess.Board',
    candidates: list,
    yolo_state_after: dict,
    ref_warped: 'np.ndarray',
    curr_warped: 'np.ndarray',
    score_eps: float = 0.01,
) -> tuple | None:
    """
    Desempate inteligente entre candidatos YOLO empatados (margen 0).

    Cuando 3+ jugadas devuelven el mismo state-match score (típico cuando YOLO
    no detecta la pieza nueva en su destino y los movs candidatos producen
    estados YOLO-observables similares), `_break_tie_by_variance` solo mira la
    varianza física. Esta función combina TRES señales independientes para
    discriminar mejor:

      1. **Varianza física** (peso 1.0): la pareja origen/destino real
         concentra la mayor parte del cambio píxel-a-píxel.
      2. **Coherencia en destino** (peso 0.4): la casilla destino del mov
         candidato debería coincidir con el color de la pieza que YOLO
         observa en `yolo_state_after` (mismo color = +0.6, exacto = +1.0).
      3. **Coherencia en origen** (peso 0.2): la casilla origen debería
         estar VACÍA en `yolo_state_after` (la pieza ya se movió de ahí).

    El score combinado discrimina mucho mejor que cualquier señal aislada.

    Devuelve `(best_move, combined_margin, var_score, dest_score, from_empty)`
    o None si no hay candidatos empatados.
    """
    if not candidates:
        return None
    top_score = candidates[0][1]
    tied = [(m, s) for m, s in candidates if (top_score - s) <= score_eps]
    if len(tied) <= 1:
        return None

    diffs = _variance_diff_all(ref_warped, curr_warped)
    yolo_after = yolo_state_after or {}

    scored: list = []
    for mv, _ in tied:
        # Componente 1: fracción de varianza física en casillas afectadas.
        var_score = _variance_score_for_move(legal_board, mv, diffs)

        # Componente 2: coherencia en destino. Lo que la pieza que se mueve
        # ESPERA dejar en el destino vs lo que YOLO observa allí.
        moving_piece = legal_board.piece_at(mv.from_square)
        if moving_piece is None:
            dest_score = 0.0
        else:
            expected_at_dest = moving_piece.symbol()
            obs_at_dest = yolo_after.get(mv.to_square)
            if obs_at_dest:
                if obs_at_dest == expected_at_dest:
                    dest_score = 1.0   # coincidencia exacta color+tipo
                elif obs_at_dest.isupper() == expected_at_dest.isupper():
                    dest_score = 0.6   # mismo color (frecuente en YOLO)
                else:
                    dest_score = 0.0
            else:
                dest_score = 0.0

        # Componente 3: la casilla origen debería estar VACÍA tras el mov.
        obs_at_from = yolo_after.get(mv.from_square)
        from_empty = 1.0 if obs_at_from is None else 0.0

        combined = var_score * 1.0 + dest_score * 0.4 + from_empty * 0.2
        scored.append((mv, combined, var_score, dest_score, from_empty))

    scored.sort(key=lambda x: x[1], reverse=True)
    best = scored[0]
    runner = scored[1] if len(scored) > 1 else None
    margin = (best[1] - runner[1]) if runner is not None else best[1]
    return best[0], margin, best[2], best[3], best[4]


def _yolo_change_centroid_tiebreak(
    candidates: list,
    yolo_state_before: dict | None,
    yolo_state_after: dict | None,
    score_eps: float = 0.01,
) -> tuple | None:
    """
    Desempate por centroide del cambio YOLO. Última red antes de SKIP.

    Cuando varianza física + coherencia destino/origen + lookahead no logran
    discriminar, recurrimos a la geometría del cambio observado por YOLO:
    calculamos el centroide (file, rank) de las casillas donde YOLO ve
    diferencia entre los estados antes/después, y elegimos el candidato cuyas
    casillas (origen, destino) están en promedio MÁS CERCA de ese centroide.

    Idea: si YOLO ve cambios reales en una zona del tablero, el mov correcto
    debería tener al menos uno de sus extremos en esa zona. Movimientos cuyos
    extremos caen lejos del centroide son geométricamente incoherentes con la
    observación, aunque su state-match score empate.

    Devuelve `(best_move, mean_distance, margin)` donde `margin` es la
    diferencia en unidades-de-casilla con el segundo candidato (mayor =
    mejor discriminación). None si no se puede aplicar.
    """
    if not candidates or not yolo_state_before or not yolo_state_after:
        return None
    top_score = candidates[0][1]
    tied = [(m, s) for m, s in candidates if (top_score - s) <= score_eps]
    if len(tied) <= 1:
        return None

    all_sqs = set(yolo_state_before) | set(yolo_state_after)
    changed = [sq for sq in all_sqs
               if yolo_state_before.get(sq) != yolo_state_after.get(sq)]
    if len(changed) < 2:
        return None  # sin señal geométrica útil

    cx = sum(chess.square_file(sq) for sq in changed) / len(changed)
    cy = sum(chess.square_rank(sq) for sq in changed) / len(changed)

    scored: list = []
    for mv, _ in tied:
        f_from = chess.square_file(mv.from_square)
        r_from = chess.square_rank(mv.from_square)
        f_to = chess.square_file(mv.to_square)
        r_to = chess.square_rank(mv.to_square)
        d_from = ((f_from - cx) ** 2 + (r_from - cy) ** 2) ** 0.5
        d_to = ((f_to - cx) ** 2 + (r_to - cy) ** 2) ** 0.5
        # Promedio de distancias de ambos extremos al centroide.
        mean_d = (d_from + d_to) / 2.0
        scored.append((mv, mean_d))

    scored.sort(key=lambda x: x[1])  # menor distancia = mejor
    best_mv, best_d = scored[0]
    runner_d = scored[1][1] if len(scored) > 1 else best_d + 100.0
    margin = runner_d - best_d
    return best_mv, best_d, margin


def _yolo_match_single_move(
    legal_board: 'chess.Board',
    yolo_state_after: dict,
    top_k: int = 5,
) -> tuple | None:
    """
    Encuentra el movimiento legal cuya posición resultante mejor coincide con
    el estado YOLO observado.

    Devuelve (best_move, best_score, best_margin, alts_top_k, all_scored) o
    None si no hay movs legales / yolo_state vacío. `all_scored` es la lista
    completa [(move, score), ...] ordenada — útil para desempates externos.
    """
    if not yolo_state_after:
        return None

    legal_moves = list(legal_board.legal_moves)
    if not legal_moves:
        return None

    scored: list = []
    for mv in legal_moves:
        b = legal_board.copy()
        b.push(mv)
        expected = _board_to_state_symbols(b)
        # Score focalizado: dar peso ×3 a las casillas afectadas por el mov.
        focus = _move_changed_squares(legal_board, mv)
        score = _yolo_score_state(expected, yolo_state_after,
                                   focus_sqs=focus, focus_weight=3.0)
        scored.append((mv, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    best_mv, best_score = scored[0]
    runner_score = scored[1][1] if len(scored) > 1 else float('-inf')
    margin = best_score - runner_score
    alts = [(m.uci(), s) for m, s in scored[:top_k]]
    return best_mv, best_score, margin, alts, scored


def _yolo_match_double_move(
    legal_board: 'chess.Board',
    yolo_state_after: dict,
    max_pairs: int = 600,
) -> tuple | None:
    """
    Busca la pareja consecutiva (mvA, mvB) que mejor explica el estado YOLO
    observado, cuando un solo movimiento no encaja (caso de WHEN que se saltó
    una jugada intermedia).

    Devuelve (mvA, mvB, score) o None. `max_pairs` acota el coste.
    """
    if not yolo_state_after:
        return None

    legal_moves_a = list(legal_board.legal_moves)
    if not legal_moves_a:
        return None

    # Heurística: ordena mvA por encaje parcial para podar más rápido.
    intermediate_scores = []
    for mvA in legal_moves_a:
        bA = legal_board.copy()
        bA.push(mvA)
        intermediate_scores.append((
            mvA, bA,
            _yolo_score_state(_board_to_state_symbols(bA), yolo_state_after),
        ))
    intermediate_scores.sort(key=lambda x: x[2], reverse=True)

    best = None
    best_score = float('-inf')
    pairs_explored = 0

    for mvA, bA, _ in intermediate_scores:
        if pairs_explored >= max_pairs:
            break
        for mvB in bA.legal_moves:
            pairs_explored += 1
            if pairs_explored > max_pairs:
                break
            bB = bA.copy()
            bB.push(mvB)
            score = _yolo_score_state(_board_to_state_symbols(bB), yolo_state_after)
            if score > best_score:
                best_score = score
                best = (mvA, mvB, score)

    return best


def _match_move_by_jaccard(
    legal_board: chess.Board,
    ref_warped:  np.ndarray,
    curr_warped: np.ndarray,
    force_accept: bool = False,
    noise_floor: dict | None = None,
    accept_thr: float | None = None,
    margin_req: float | None = None,
) -> tuple | None:
    """
    Identifica el movimiento legal usando solo varianza por celda + Jaccard.
    No necesita YOLO ni clasificador de piezas.

    Puntuación = fracción de la varianza total que explica cada movimiento.
    Los movimientos que cubren las casillas con mayor cambio ganan.

    Si se pasa `noise_floor` (dict {square: float}), se RESTA al diff de cada
    casilla antes de scoring. Sirve para neutralizar ruido persistente en
    celdas concretas (ej. esquinas con artefactos de calibración) que de otro
    modo dominarían el matching.

    Retorna (move, score, top_alts) o None si no hay candidato aceptable.
    """
    # Varianza de todas las casillas (con magnitud) para ponderación
    all_diffs_raw = _variance_diff_all(ref_warped, curr_warped)
    if noise_floor is not None:
        all_diffs = {sq: max(0.0, all_diffs_raw[sq] - noise_floor.get(sq, 0.0))
                     for sq in chess.SQUARES}
    else:
        all_diffs = all_diffs_raw

    # Filtro top-K: solo las K casillas con MAYOR diff de varianza contribuyen
    # al scoring; el resto se ponen a 0. Esto descarta movimientos candidatos
    # cuya casilla "fantasma" (la que no se mueve realmente) tiene diff bajo.
    # Combinado con balance², los movs falsos por proyección de pieza alta
    # tienen una casilla en el top y otra fuera → balance=0 → score=0.
    # K=10 da margen para enroques (4 sq), en passant (3 sq), multi (8 sq).
    SINGLE_TOP_K = 10
    sorted_sqs   = sorted(all_diffs.keys(), key=lambda sq: -all_diffs[sq])
    top_k_set    = set(sorted_sqs[:SINGLE_TOP_K])
    all_diffs    = {sq: (all_diffs[sq] if sq in top_k_set else 0.0)
                    for sq in chess.SQUARES}
    total_var  = sum(all_diffs.values()) + 1e-6

    # Mapa de varianza ABSOLUTA del frame actual (para verificación de dirección).
    # Casillas ocupadas tienen varianza alta (textura de pieza), vacías la tienen baja.
    curr_var_map  = _cell_variance_map(curr_warped)
    median_curr   = float(np.median(list(curr_var_map.values())))
    occupied_thr  = median_curr * 1.25   # umbral para considerar casilla "ocupada"
    empty_thr     = median_curr * 0.85   # umbral para considerar casilla "vacía"

    # Señal secundaria: pixel-diff (más sensible a pequeños cambios)
    try:
        pixel_changed = _pixel_changed_squares(ref_warped, curr_warped, top_k=8, threshold=3)
    except Exception:
        pixel_changed = {}

    candidates = []
    for move in legal_board.legal_moves:
        move_sqs = _move_changed_squares(legal_board, move)
        move_diffs = [all_diffs.get(sq, 0.0) for sq in move_sqs]

        # Score primario: fracción de varianza total cubierta por las casillas del movimiento
        occ_score_raw = sum(move_diffs) / total_var

        # ── Modulador de BALANCE entre las casillas del movimiento ───────────
        # Un movimiento real concentra cambios EQUILIBRADOS entre src y dst
        # (origen vacío + destino ocupado, ambos con variación significativa).
        # Una jugada falsa que se "cuela" suele tener UNA casilla con varianza
        # enorme (proyección de pieza alta sobre una casilla adyacente debido
        # al ángulo de cámara) y la otra con varianza pequeña.
        # balance = media_geometrica / media_aritmetica de las varianzas del
        # movimiento. Vale 1.0 si están perfectamente equilibradas y tiende a
        # 0 cuando una domina. Multiplicamos al cuadrado para penalizar
        # fuertemente los desbalanceados (factor x^2 amplifica diferencias).
        if move_diffs and sum(move_diffs) > 0:
            arith = sum(move_diffs) / len(move_diffs)
            log_sum = sum(math.log(max(d, 1.0)) for d in move_diffs)
            geom   = math.exp(log_sum / len(move_diffs))
            balance = geom / max(arith, 1.0)
        else:
            balance = 0.0
        occ_score = occ_score_raw * (balance ** 2)

        # Bonus por pixel-diff: peso ELEVADO (0.20 vs 0.04 original) porque
        # _pixel_changed_squares usa el grid HOUGH (líneas reales del tablero)
        # en vez del grid uniforme. Es inmune al desplazamiento de homografía
        # que contamina las varianzas en el grid uniforme. Cuando los datos
        # de varianza están saturados por artefactos (ej. a1, d2 con
        # variaciones persistentes), el pixel-diff sigue siendo confiable
        # para detectar las casillas que realmente cambiaron.
        pixel_overlap = len(move_sqs & set(pixel_changed.keys()))
        pixel_bonus   = pixel_overlap / max(len(move_sqs), 1) * 0.20

        # miss_penalty se DESACTIVA: con el filtro top-K las casillas fuera del
        # top ya tienen diff=0 (penalización implícita en occ_score). Aplicar
        # también miss_penalty era una doble penalización que mataba los
        # movimientos correctos cuya señal de varianza estaba enmascarada por
        # artefactos en otras celdas (ej. a1).
        miss_penalty = 0.0

        # ── Verificación absoluta de dirección ───────────────────────────────
        # Tras un movimiento m: origen debe quedar VACÍO, destino debe quedar OCUPADO.
        # Si la varianza absoluta del frame actual lo confirma, hay bonus; si la
        # contradice (origen ocupado, destino vacío) hay penalización fuerte.
        src_var = curr_var_map.get(move.from_square, median_curr)
        dst_var = curr_var_map.get(move.to_square, median_curr)
        dir_bonus = 0.0
        if dst_var > occupied_thr and src_var < empty_thr:
            dir_bonus = 0.08          # destino ocupado y origen vacío → coherente
        elif dst_var > src_var:
            dir_bonus = 0.03          # al menos la dirección es correcta
        elif dst_var < src_var:
            dir_bonus = -0.10         # dirección invertida → penalización fuerte

        score = occ_score + pixel_bonus - miss_penalty + dir_bonus
        candidates.append((score, move))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_move = candidates[0]
    second_score = candidates[1][0] if len(candidates) > 1 else 0.0
    margin = best_score - second_score

    try:
        top_alts = [(legal_board.san(m), round(s, 3)) for s, m in candidates[1:4]]
    except Exception:
        top_alts = [(m.uci(), round(s, 3)) for s, m in candidates[1:4]]

    # Permite override de los umbrales por parámetro (usado por la fase WHICH
    # que aplica balance² → scores reducidos → necesita umbrales más laxos).
    if accept_thr is None:
        accept_thr = JACCARD_ACCEPT_THR * 0.5 if force_accept else JACCARD_ACCEPT_THR
    if margin_req is None:
        margin_req = 0.0 if force_accept else JACCARD_MARGIN_REQ

    if best_score < accept_thr or margin < margin_req:
        # Log diagnóstico: muestra qué candidato fue el mejor y por qué se rechazó.
        try:
            best_san = legal_board.san(best_move)
        except Exception:
            best_san = best_move.uci()
        reason = []
        if best_score < accept_thr:
            reason.append(f"score={best_score:.3f} < {accept_thr:.3f}")
        if margin < margin_req:
            reason.append(f"margin={margin:.3f} < {margin_req:.3f}")
        logger.debug("[JACCARD] Rechazado: best=%s [%s] %s, alts=%s",
                     best_san, best_move.uci(), " y ".join(reason),
                     [(s, round(sc, 3)) for s, sc in top_alts])
        return None

    return best_move, best_score, top_alts


def _try_multi_move_jaccard(
    legal_board: chess.Board,
    ref_warped:  np.ndarray,
    curr_warped: np.ndarray,
    noise_floor: dict | None = None,
) -> tuple | None:
    """
    Busca el mejor PAR (moveA, moveB) consecutivo que explica los cambios
    observados. Útil cuando el jugador encadena dos movimientos antes de que
    el sistema haya tenido tiempo de detectar el primero.

    Retorna (moveA, moveB, score) o None si ningún par destaca.
    El score es la fracción de varianza total cubierta por las 4-8 casillas
    de los dos movimientos combinados.

    `noise_floor` (opcional): igual que en _match_move_by_jaccard, dict por
    casilla que se resta del diff antes de scorear, para neutralizar ruido
    persistente.
    """
    all_diffs_raw = _variance_diff_all(ref_warped, curr_warped)
    if noise_floor is not None:
        all_diffs = {sq: max(0.0, all_diffs_raw[sq] - noise_floor.get(sq, 0.0))
                     for sq in chess.SQUARES}
    else:
        all_diffs = all_diffs_raw

    # Filtro top-K (mismo razonamiento que en _match_move_by_jaccard).
    # Para multi-move usamos K=12: cubre pares con hasta ~8 casillas
    # implicadas (multi de 2 movs ≤ 4-8 sq) más margen.
    MULTI_TOP_K = 12
    sorted_sqs  = sorted(all_diffs.keys(), key=lambda sq: -all_diffs[sq])
    top_k_set   = set(sorted_sqs[:MULTI_TOP_K])
    all_diffs   = {sq: (all_diffs[sq] if sq in top_k_set else 0.0)
                   for sq in chess.SQUARES}
    total_var = sum(all_diffs.values()) + 1e-6

    best_score, best_pair = 0.0, None

    for moveA in list(legal_board.legal_moves):
        sqs_A = _move_changed_squares(legal_board, moveA)
        legal_board.push(moveA)
        try:
            for moveB in list(legal_board.legal_moves):
                sqs_B    = _move_changed_squares(legal_board, moveB)
                combined = sqs_A | sqs_B
                combined_diffs = [all_diffs.get(sq, 0.0) for sq in combined]
                raw_score = sum(combined_diffs) / total_var

                # Modulador de balance: penaliza pares donde una sola casilla
                # domina la varianza (proyección de pieza alta), igual que en
                # el matching single-move.
                if combined_diffs and sum(combined_diffs) > 0:
                    arith = sum(combined_diffs) / len(combined_diffs)
                    log_sum = sum(math.log(max(d, 1.0)) for d in combined_diffs)
                    geom = math.exp(log_sum / len(combined_diffs))
                    balance = geom / max(arith, 1.0)
                else:
                    balance = 0.0
                score = raw_score * (balance ** 2)

                if score > best_score:
                    best_score, best_pair = score, (moveA, moveB)
        finally:
            legal_board.pop()

    if best_pair is None:
        return None
    return (best_pair[0], best_pair[1], best_score)


def _get_occupied_squares_estimate(warped: np.ndarray) -> set:
    """
    Estima qué casillas tienen piezas usando varianza por celda.
    Las celdas con pieza tienen varianza significativamente mayor que las vacías.
    Usa un umbral adaptativo basado en la mediana de varianzas.
    """
    var_map = _cell_variance_map(warped)
    values  = list(var_map.values())
    median  = float(np.median(values))
    # Las casillas ocupadas suelen tener varianza al menos 1.4× la mediana
    threshold = median * 1.4
    return {sq for sq, v in var_map.items() if v > threshold}


def _try_state_recovery(
    legal_board: chess.Board,
    curr_warped: np.ndarray,
    depth: int = RECOVERY_DEPTH,
) -> tuple | None:
    """
    Intenta recuperar el estado del tablero cuando hay demasiados rechazos
    consecutivos. Busca en BFS hasta `depth` movimientos desde la posición
    actual qué estado canónico coincide mejor con la ocupación observada.

    Retorna (recovered_board, moves_list) o None si no hay recuperación fiable.
    """
    observed_occupied = _get_occupied_squares_estimate(curr_warped)
    observed_empty    = set(chess.SQUARES) - observed_occupied

    from collections import deque

    queue = deque([(legal_board.copy(), [])])
    visited_fens = {legal_board.board_fen()}
    best_score, best_board, best_moves = 0.0, None, []

    while queue:
        board, moves = queue.popleft()

        if len(moves) > depth:
            continue

        expected_occupied = {sq for sq in chess.SQUARES if board.piece_at(sq)}
        expected_empty    = set(chess.SQUARES) - expected_occupied

        correct = (len(expected_occupied & observed_occupied) +
                   len(expected_empty    & observed_empty))
        score = correct / 64.0

        if score > best_score:
            best_score, best_board, best_moves = score, board.copy(), list(moves)

        if len(moves) < depth:
            for mv in list(board.legal_moves):
                nb = board.copy()
                nb.push(mv)
                fen = nb.board_fen()
                if fen not in visited_fens:
                    visited_fens.add(fen)
                    queue.append((nb, moves + [mv]))

    if best_score >= RECOVERY_MATCH_THR and len(best_moves) > 0:
        logger.info("[RECOVERY] Coincidencia %.1f%% con %d movimiento(s) adelante",
                    best_score * 100, len(best_moves))
        return best_board, best_moves

    return None


def _extract_key_frames_occupancy(video_path, coords, progress_key=None):
    """
    Pipeline de detección de movimientos basado en ocupación por varianza + Jaccard.
    No usa YOLO ni clasificador de piezas para identificar el movimiento.

    Fase 1 — Absdiff: detecta cuándo hay movimiento y cuándo el tablero se estabiliza.
    Fase 2 — Estabilidad de ocupación: compara varianza de celdas contra la referencia.
             Si no hubo cambio real (brazo pasó), descarta el evento.
    Fase 3 — Jaccard: encuentra el movimiento legal que mejor explica las casillas
             con mayor cambio de varianza. Sin necesidad de conocer el tipo de pieza.
    Fase 4 — Recuperación: si hay demasiados rechazos consecutivos, intenta
             resincronizar el tablero con BFS sobre posiciones alcanzables.

    Retorna (key_frames, key_frames_orig, detected_states, mat, accepted_moves,
             key_frame_indices, bootstrap_warped).
    bootstrap_warped es el frame warpeado capturado por la fase de bootstrap
    (primer frame estable + sharpness selection). Se expone para que la fase
    WHICH pueda usar EXACTAMENTE la misma referencia visual que WHEN al
    comparar el primer evento, evitando contaminación por jitter del frame 0.
    """
    try:
        from .chess_detector import invalidate_grid_cache
    except ImportError:
        from chess_detector import invalidate_grid_cache

    mat   = get_matriz(coords)
    video = open_video(video_path)

    if isinstance(video, dict):
        return video

    invalidate_grid_cache()

    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps          = video.get(cv2.CAP_PROP_FPS) or 30.0

    key_frames:        list = []
    key_frames_orig:   list = []
    detected_states:   list = []
    accepted_moves:    list[chess.Move] = []
    key_frame_indices: list[int] = []   # frame_idx en que cada keyframe fue aceptado

    # Frame warpeado capturado por el bootstrap (primer frame estable + sharpness
    # selection). Se expone para que la fase WHICH pueda usar EXACTAMENTE la
    # misma referencia que WHEN al comparar diferencias contra el primer evento.
    # Sin esto, WHICH usaba el frame 0 crudo (get_initial_board_frame), que
    # difiere del bootstrap en jitter de cámara/iluminación y produce diffs
    # contaminados que penalizan los movimientos correctos en la primera
    # comparación → cascada de errores.
    bootstrap_warped: np.ndarray | None = None
    bootstrap_orig:   np.ndarray | None = None

    legal_board = chess.Board()

    # ── Fase 1: variables de trigger absdiff ─────────────────────────────────
    gray_prev   = None
    stable_run  = 0
    cooldown    = 0
    seen_motion_since_capture = True   # bootstrap: capturar posición inicial

    motion_frames_count  = 0
    last_motion_duration = 0

    # ── Fase 2 / 3 / 4: variables de estado ─────────────────────────────────
    voting_buffer: list = []           # (warped, frame_orig) durante estabilidad
    last_accepted_warped = None        # frame warpeado de referencia (última posición aceptada)
    last_analyzed_warped = None        # último frame que pasó por el scorer (acepte o rechace).
                                       # Evita re-analizar el mismo estado en bucle tras rechazo.

    accepted             = 0
    rejected_occ         = 0          # descartados por ausencia de cambio de ocupación
    rejected_jaccard     = 0          # descartados por Jaccard bajo
    rejected_repeat      = 0          # descartados por estado idéntico al último análisis
    rejected_diffuse     = 0          # descartados por cambio difuso (iluminación/brazo)
    rejected_refractory  = 0          # descartados dentro de la ventana refractaria (WHEN-only)
    rejected_hand        = 0          # descartados por mano detectada en el frame
    consecutive_rejects  = 0

    # Estado del filtro refractario (sólo se usa con WHEN_ONLY_MODE = True)
    last_accept_frame_idx = -10**9    # frame_idx del último evento aceptado
    last_accept_top_var   = 0.0       # top_var del último evento aceptado

    # Umbrales adaptativos — se calibran al capturar la referencia inicial.
    # Hasta entonces se usan los valores por defecto. Se derivan de la varianza
    # típica de casillas vacías vs ocupadas en la posición inicial, lo que
    # auto-ajusta el sistema a la iluminación, contraste y resolución del vídeo.
    adaptive_lighting_top_var = LIGHTING_REJECT_TOP_VAR
    adaptive_multi_min_extra  = MULTI_MIN_EXTRA_VAR
    adaptive_occ_min_thr      = OCC_VARIANCE_MIN_THR

    FORCE_ACCEPT_AFTER = 15

    # ── Carpeta para guardar keyframes detectados (inspección visual) ────────
    keyframes_dir = os.path.join(DEBUG_LOCATION, 'keyframes')
    try:
        os.makedirs(keyframes_dir, exist_ok=True)
        # Limpiar carpeta de ejecuciones anteriores
        for _f in os.listdir(keyframes_dir):
            if _f.lower().endswith('.png'):
                try:
                    os.remove(os.path.join(keyframes_dir, _f))
                except OSError:
                    pass
        logger.info("[OCC] Carpeta de keyframes lista: %s", keyframes_dir)
    except Exception as _e:
        logger.warning("[OCC] No se pudo preparar carpeta de keyframes: %s", _e)

    def _save_keyframe(idx: int, warped: np.ndarray, frame_num: int,
                       move_uci: str, tag: str = ""):
        """Guarda warped anotado para inspección visual.
        Usa imencode + open(wb) porque cv2.imwrite falla silenciosamente con
        paths que contienen caracteres no-ASCII en Windows (ej. 'Málaga')."""
        try:
            suffix   = f"_{tag}" if tag else ""
            fname    = f"kf_{idx:03d}_f{frame_num:06d}_{move_uci}{suffix}.png"
            filepath = os.path.join(keyframes_dir, fname)
            ok, buf  = cv2.imencode('.png', warped)
            if ok:
                with open(filepath, 'wb') as fh:
                    fh.write(buf.tobytes())
            else:
                logger.warning("[OCC] cv2.imencode falló para keyframe %d", idx)
        except Exception as _e:
            logger.warning("[OCC] No se pudo guardar keyframe %d: %s", idx, _e)

    logger.info("[OCC] Pipeline ocupación/Jaccard iniciado (fps=%.1f, STABLE=%d, "
                "WINDOW=%d, JACCARD_THR=%.2f) — keyframes en %s",
                fps, STABLE_FRAMES_REQUIRED, STABLE_WINDOW_SIZE, JACCARD_ACCEPT_THR,
                keyframes_dir)

    frame_idx = 0
    while video.isOpened():
        ret, frame = video.read()
        if not ret:
            break

        frame_idx += 1
        if progress_key:
            set_progress(progress_key, int(frame_idx / total_frames * 50))

        warped     = cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        gray_board = process_image(warped)

        if gray_prev is None:
            gray_prev = gray_board
            continue

        # ── Fase 1: clasificación de movimiento por absdiff ──────────────────
        diff_pixels = cv2.absdiff(gray_board, gray_prev)
        _, mask     = cv2.threshold(diff_pixels, ABSDIFF_BIN_THRESHOLD, 255, cv2.THRESH_BINARY)
        ratio       = float(np.count_nonzero(mask)) / mask.size
        gray_prev   = gray_board

        if frame_idx % 60 == 0:
            logger.debug("[OCC] frame=%d ratio=%.5f stable=%d cooldown=%d buf=%d kf=%d",
                         frame_idx, ratio, stable_run, cooldown, len(voting_buffer), len(key_frames))

        if cooldown > 0:
            cooldown -= 1
            if ratio > MOTION_PIXEL_RATIO:
                seen_motion_since_capture = True
            continue

        if ratio > MOTION_PIXEL_RATIO:
            motion_frames_count += 1
            stable_run = 0
            seen_motion_since_capture = True
            voting_buffer.clear()
            continue

        # Frame pixel-estable: detectar transición movimiento→estabilidad
        if motion_frames_count > 0:
            last_motion_duration = motion_frames_count
            motion_frames_count  = 0
            if last_motion_duration > LONG_MOTION_THRESHOLD:
                logger.debug("[OCC] Movimiento largo (%d frames) — exigiendo %d frames extra",
                             last_motion_duration, LONG_MOTION_EXTRA_STABLE)

        stable_run += 1

        extra_stable = (LONG_MOTION_EXTRA_STABLE
                        if not _MEDIAPIPE_AVAILABLE and last_motion_duration > LONG_MOTION_THRESHOLD
                        else 0)

        if stable_run < STABLE_FRAMES_REQUIRED + extra_stable or not seen_motion_since_capture:
            continue

        # Filtro de mano
        if _hand_in_frame(frame):
            rejected_hand += 1
            voting_buffer.clear()
            continue

        # Acumular frames estables para elegir el mejor
        voting_buffer.append((warped, frame.copy()))

        if len(voting_buffer) < STABLE_WINDOW_SIZE:
            continue

        # Elegir el frame con mayor nitidez (menos blur) del buffer
        warped_chosen, frame_chosen = max(
            voting_buffer,
            key=lambda t: cv2.Laplacian(
                cv2.cvtColor(t[0], cv2.COLOR_BGR2GRAY), cv2.CV_64F
            ).var()
        )
        voting_buffer.clear()

        # ── Bootstrap: capturar referencia inicial + CALIBRAR baselines ──────
        if last_accepted_warped is None:
            last_accepted_warped = warped_chosen.copy()
            bootstrap_warped     = warped_chosen.copy()
            bootstrap_orig       = frame_chosen.copy()

            # Calibración adaptativa: la posición inicial tiene 32 casillas
            # ocupadas y 32 vacías. Usamos esa distribución conocida para
            # estimar la varianza típica de cada categoría y derivar umbrales
            # adaptados al vídeo (luz, contraste, resolución, distancia cámara).
            init_var_map  = _cell_variance_map(warped_chosen)
            sorted_vars   = sorted(init_var_map.values())
            median_empty  = float(np.median(sorted_vars[:32]))
            median_occ    = float(np.median(sorted_vars[32:]))
            base_change   = max(median_occ - median_empty, 80.0)

            # Sanidad: si la separación es demasiado pequeña, mantener defaults
            # (probablemente la calibración de esquinas está mal o hay bruma)
            if base_change < 100.0:
                logger.warning("[OCC] Calibración débil (Δvar=%.0f). Usando umbrales "
                               "por defecto. Revisa esquinas/iluminación.", base_change)
            else:
                # Los factores se calibraron sobre un vídeo "buen contraste" (Δ≈1800)
                # para reproducir los defaults conocidos (400, 600, 40):
                #   lighting_top = Δ * 0.22 → 396 (≈ default 400)
                #   multi_extra  = Δ * 0.33 → 594 (≈ default 600)
                #   occ_min      = Δ * 0.022 → 40
                # En vídeos con bajo contraste (Δ pequeño) los umbrales bajan
                # proporcionalmente. Cota superior para evitar strictness excesiva
                # en vídeos high-contrast (Δ muy grande).
                # Pisos elevados (280/420/28) tras observar que en vídeos de
                # bajo contraste (Δ<1000, ej. test2 con Δ=844) los pisos previos
                # (120/180/18) dejaban pasar muchos eventos phantom con top_var
                # del orden del propio ruido. test4 (Δ=1761, gold standard) no
                # produce ningún evento por debajo de 1000 — los pisos sólo
                # afectan a setups con baja Δ.
                adaptive_lighting_top_var = min(600.0, max(280.0, base_change * 0.22))
                adaptive_multi_min_extra  = min(800.0, max(420.0, base_change * 0.33))
                adaptive_occ_min_thr      = min( 80.0, max( 28.0, base_change * 0.022))

            logger.info("[OCC] Referencia inicial capturada (frame %d). "
                        "Var: empty=%.0f, occ=%.0f, Δ=%.0f",
                        frame_idx, median_empty, median_occ, base_change)
            logger.info("[OCC] Umbrales adaptativos: lighting_top=%.0f (def %.0f), "
                        "multi_extra=%.0f (def %.0f), occ_min=%.0f (def %.0f)",
                        adaptive_lighting_top_var, LIGHTING_REJECT_TOP_VAR,
                        adaptive_multi_min_extra, MULTI_MIN_EXTRA_VAR,
                        adaptive_occ_min_thr, OCC_VARIANCE_MIN_THR)

            stable_run = 0
            seen_motion_since_capture = False
            continue

        # ── Fase 2a: evitar re-analizar el mismo estado tras un rechazo ─────
        # Si el frame estable actual es prácticamente idéntico al último que ya
        # analizamos (acepte o rechace), no tiene sentido volver a procesarlo —
        # daría el mismo resultado. Solo se vuelve a analizar si el estado del
        # tablero ha cambiado meaningfully entre el rechazo anterior y ahora.
        if last_analyzed_warped is not None:
            diff_from_last = _changed_squares_occ(last_analyzed_warped, warped_chosen,
                                                  top_k=4, min_thr=adaptive_occ_min_thr)
            if not diff_from_last:
                rejected_repeat += 1
                stable_run = 0
                continue

        # ── Fase 2b: verificar cambio de ocupación vs referencia ─────────────
        occ_changed = _changed_squares_occ(last_accepted_warped, warped_chosen,
                                           top_k=OCC_VARIANCE_TOP_K,
                                           min_thr=adaptive_occ_min_thr)
        if not occ_changed:
            rejected_occ += 1
            logger.info("[OCC] Sin cambio de ocupación vs referencia (frame %d) — "
                        "posible brazo o vibración. Ignorado.", frame_idx)
            stable_run = 0
            seen_motion_since_capture = False
            last_analyzed_warped = warped_chosen.copy()
            continue

        # ── Fase 2c: filtro de concentración ─────────────────────────────────
        # Un movimiento real concentra la varianza en 2-4 casillas. Un cambio
        # de iluminación o un brazo aún visible distribuyen la varianza sobre
        # muchas celdas con valores moderados, sin un pico claro.
        # Mediana de fondo (no global): excluimos las 4 casillas con mayor
        # cambio para que las propias casillas que se mueven no contaminen el
        # estimador del nivel de ruido. Con la mediana global, en vídeos de
        # bajo contraste la jugada infla la mediana y el rátio top/median falla
        # con falsos negativos (ej. test5 frame 19970: top=4842, median=1488 →
        # ratio=3.25 < 4.0 rechazaba un movimiento real).
        all_diffs   = _variance_diff_all(last_accepted_warped, warped_chosen)
        sorted_vals = sorted(all_diffs.values(), reverse=True)
        top_var     = sorted_vals[0]
        bg_median   = float(np.median(sorted_vals[4:]))  # excluye top-4

        if top_var < adaptive_lighting_top_var or top_var < bg_median * LIGHTING_REJECT_RATIO:
            rejected_diffuse += 1
            logger.info("[OCC] Cambio difuso (top=%.1f, bg_median=%.1f, ratio=%.2f, "
                        "umbral=%.1f) — iluminación/brazo. Ignorado (frame %d).",
                        top_var, bg_median, top_var / max(bg_median, 1.0),
                        adaptive_lighting_top_var, frame_idx)
            stable_run = 0
            seen_motion_since_capture = False
            last_analyzed_warped = warped_chosen.copy()
            continue

        logger.debug("[OCC] Casillas con cambio: %s",
                     {chess.square_name(sq): round(v, 1) for sq, v in
                      sorted(occ_changed.items(), key=lambda x: x[1], reverse=True)[:6]})

        # ── Modo WHEN-only ───────────────────────────────────────────────────
        # Si WHEN_ONLY_MODE está activo, registramos el evento sin pasar por
        # Jaccard / multi-move / recovery. La identificación del movimiento
        # (WHICH) se aborda en una etapa posterior que consume key_frames y
        # key_frame_indices. legal_board no se actualiza (no se sabe qué
        # movimiento fue) y accepted_moves queda vacío — la salida del WHEN
        # es puramente la lista de momentos en que ocurrió un movimiento.
        if WHEN_ONLY_MODE:
            # Filtro refractario: si estamos dentro de la ventana inmediata
            # tras un evento aceptado, exigimos que la nueva varianza top sea
            # comparable a la del evento previo. Los eventos "phantom" tienen
            # ratios bajos (residuo tras la jugada real); las jugadas rápidas
            # legítimas mantienen la magnitud.
            frames_since_accept = frame_idx - last_accept_frame_idx
            if frames_since_accept < REFRACTORY_WINDOW and last_accept_top_var > 0:
                min_required = REFRACTORY_MIN_VAR_RATIO * last_accept_top_var
                if top_var < min_required:
                    rejected_refractory += 1
                    logger.info("[OCC] Refractario: evento descartado (frame %d, "
                                "top_var=%.0f < %.0f, prev_top=%.0f, Δframes=%d)",
                                frame_idx, top_var, min_required,
                                last_accept_top_var, frames_since_accept)
                    stable_run = 0
                    seen_motion_since_capture = False
                    last_analyzed_warped = warped_chosen.copy()
                    continue

            accepted += 1
            logger.info("[OCC] ✓ Evento WHEN #%d (frame %d, top_var=%.0f, "
                        "bg_median=%.0f, casillas_cambiadas=%d)",
                        len(key_frames) + 1, frame_idx, top_var, bg_median,
                        len(occ_changed))
            key_frames.append(warped_chosen)
            key_frames_orig.append(frame_chosen)
            detected_states.append({})
            key_frame_indices.append(frame_idx)
            _save_keyframe(len(key_frames), warped_chosen, frame_idx, "when",
                           tag="WHEN_ONLY")
            last_accepted_warped  = warped_chosen.copy()
            last_analyzed_warped  = warped_chosen.copy()
            last_accept_frame_idx = frame_idx
            last_accept_top_var   = top_var
            cooldown   = COOLDOWN_AFTER_CAPTURE
            stable_run = 0
            seen_motion_since_capture = False
            continue

        # ── Fase 3: Jaccard — identificar movimiento legal ───────────────────
        _force = consecutive_rejects >= FORCE_ACCEPT_AFTER
        result = _match_move_by_jaccard(legal_board, last_accepted_warped,
                                        warped_chosen, force_accept=_force)

        # ── Fase 3b: multi-move check ────────────────────────────────────────
        # Si el jugador encadenó 2 movimientos antes de que el sistema detectara
        # el primero, el cambio observado cubre 4-8 casillas en lugar de 2-4.
        # Probamos si una secuencia (moveA, moveB) explica los cambios mejor.
        # IMPORTANTE: el multi solo se acepta si las casillas EXTRA (las de mvB
        # que no comparte con mvA) tienen cada una varianza alta absoluta. Si
        # alguna es phantom (varianza baja), el multi se está "inventando" el
        # segundo movimiento a partir de ruido de proyección.
        single_score = result[1] if result is not None else 0.0
        multi_pair = _try_multi_move_jaccard(legal_board, last_accepted_warped,
                                             warped_chosen)
        use_multi = False
        if multi_pair is not None:
            mvA, mvB, multi_score = multi_pair
            # Calcular las casillas extra de mvB (no compartidas con mvA)
            sqs_A = _move_changed_squares(legal_board, mvA)
            legal_board.push(mvA)
            try:
                sqs_B = _move_changed_squares(legal_board, mvB)
            finally:
                legal_board.pop()
            extra_sqs = sqs_B - sqs_A

            # Cada casilla extra debe tener varianza alta para considerar real
            # el segundo movimiento (no phantom).
            extra_min_var = (min(all_diffs.get(sq, 0.0) for sq in extra_sqs)
                             if extra_sqs else 0.0)

            multi_qualifies = (
                len(extra_sqs) >= 2 and
                extra_min_var >= adaptive_multi_min_extra
            )

            if multi_qualifies:
                # Multi gana si: (a) supera single por margen sustancial, o
                # (b) single fue rechazado y multi pasa el umbral con extra-bonus
                if multi_score >= single_score + MULTI_MARGIN_OVER_SINGLE:
                    use_multi = True
                elif result is None and multi_score >= JACCARD_ACCEPT_THR + MULTI_MIN_FALLBACK_SCORE_BONUS:
                    use_multi = True
            else:
                logger.debug("[OCC] Multi-move descartado (frame %d): extra_sqs=%d, "
                             "extra_min_var=%.1f (umbral=%.1f)", frame_idx,
                             len(extra_sqs), extra_min_var, adaptive_multi_min_extra)

        if use_multi:
            mvA, mvB, multi_score = multi_pair
            try:
                sanA = legal_board.san(mvA)
            except Exception:
                sanA = mvA.uci()
            legal_board.push(mvA)
            try:
                sanB = legal_board.san(mvB)
            except Exception:
                sanB = mvB.uci()
            legal_board.pop()

            logger.info("[OCC] ✓✓ Keyframes %d-%d (multi-move %s+%s, "
                        "multi_score=%.3f vs single=%.3f, frame %d)",
                        len(key_frames) + 1, len(key_frames) + 2,
                        sanA, sanB, multi_score, single_score, frame_idx)

            first_kf_idx = len(key_frames) + 1
            for mv in (mvA, mvB):
                legal_board.push(mv)
                key_frames.append(warped_chosen)
                key_frames_orig.append(frame_chosen)
                detected_states.append({})
                accepted_moves.append(mv)
            accepted += 2
            consecutive_rejects = 0
            combined_uci = f"{mvA.uci()}+{mvB.uci()}"
            _save_keyframe(first_kf_idx, warped_chosen, frame_idx,
                           combined_uci, tag="MULTI_x2")
            last_accepted_warped = warped_chosen.copy()
            last_analyzed_warped = warped_chosen.copy()
            cooldown  = COOLDOWN_AFTER_CAPTURE
            stable_run = 0
            seen_motion_since_capture = False
            continue

        if result is None:
            rejected_jaccard += 1
            consecutive_rejects += 1
            logger.info("[OCC] Sin movimiento legal compatible (Jaccard) frame %d "
                        "(consec_rejects=%d)", frame_idx, consecutive_rejects)
            stable_run = 0
            # Guardamos el estado rechazado: si el siguiente periodo estable
            # es idéntico (jugador aún no se ha movido), Fase 2a lo descartará
            # sin re-analizarlo. Pero si el estado cambia (nuevo movimiento),
            # se procesará normalmente.
            last_analyzed_warped = warped_chosen.copy()

            # ── Fase 4: recuperación de estado ───────────────────────────────
            if consecutive_rejects >= RECOVERY_REJECT_THR:
                recovered = _try_state_recovery(legal_board, warped_chosen, RECOVERY_DEPTH)
                if recovered is not None:
                    recovered_board, recovery_moves = recovered
                    logger.info("[OCC] Recuperación: %d movimiento(s) aplicados",
                                len(recovery_moves))
                    # Guardamos UNA SOLA imagen por evento de recovery (los frames
                    # de cada movimiento recuperado serían idénticos visualmente).
                    # El nombre del fichero incluye todos los movimientos inferidos.
                    first_kf_idx = len(key_frames) + 1
                    for mv in recovery_moves:
                        try:
                            san = legal_board.san(mv)
                        except Exception:
                            san = mv.uci()
                        legal_board.push(mv)
                        key_frames.append(warped_chosen)
                        key_frames_orig.append(frame_chosen)
                        detected_states.append({})
                        accepted_moves.append(mv)
                        logger.info("[OCC] [RECOVERY] Movimiento recuperado: %s [%s]",
                                    san, mv.uci())
                    combined_uci = "+".join(m.uci() for m in recovery_moves)
                    _save_keyframe(first_kf_idx, warped_chosen, frame_idx,
                                   combined_uci, tag=f"RECOVERY_x{len(recovery_moves)}")
                    last_accepted_warped = warped_chosen.copy()
                    consecutive_rejects  = 0
                    cooldown = COOLDOWN_AFTER_CAPTURE
                    stable_run = 0
                    seen_motion_since_capture = False
                else:
                    logger.warning("[OCC] Recuperación fallida (frame %d) — "
                                   "tablero posiblemente desincronizado.", frame_idx)
            continue

        move, score, top_alts = result

        try:
            move_san = legal_board.san(move)
        except Exception:
            move_san = move.uci()

        legal_board.push(move)
        accepted += 1
        consecutive_rejects = 0

        alts_str = ", ".join(f"{s}({sc:.3f})" for s, sc in top_alts)
        logger.info("[OCC] ✓ Keyframe #%d confirmado (frame %d, move=%s [%s], "
                    "score=%.3f, alts=[%s]%s)",
                    len(key_frames) + 1, frame_idx, move_san, move.uci(),
                    score, alts_str, " [FORCED]" if _force else "")

        key_frames.append(warped_chosen)
        key_frames_orig.append(frame_chosen)
        detected_states.append({})
        accepted_moves.append(move)
        _save_keyframe(len(key_frames), warped_chosen, frame_idx, move.uci(),
                       tag="FORCED" if _force else "")
        last_accepted_warped = warped_chosen.copy()
        last_analyzed_warped = warped_chosen.copy()
        cooldown  = COOLDOWN_AFTER_CAPTURE
        stable_run = 0
        seen_motion_since_capture = False

    video.release()

    initial_count = len(key_frames)

    # ── Pasada de fusión post-proceso ─────────────────────────────────────────
    # Sólo en WHEN_ONLY_MODE: fusiona keyframes consecutivos visualmente
    # equivalentes (phantoms residuales de un evento real anterior).
    if WHEN_ONLY_MODE and FUSE_DUPLICATES and len(key_frames) > 1:
        (key_frames, key_frames_orig, key_frame_indices,
         detected_states, accepted_moves) = _fuse_consecutive_duplicate_keyframes(
            key_frames, key_frames_orig, key_frame_indices,
            detected_states, accepted_moves)
        accepted = len(key_frames)

    fused_count = initial_count - len(key_frames)
    logger.info("[OCC] Finalizado — aceptados=%d (pre-fusión=%d, fusionados=%d), "
                "rej_occ=%d, rej_jaccard=%d, rej_repeat=%d, rej_diffuse=%d, "
                "rej_refractory=%d, rej_hand=%d",
                accepted, initial_count, fused_count,
                rejected_occ, rejected_jaccard, rejected_repeat,
                rejected_diffuse, rejected_refractory, rejected_hand)

    return (key_frames, key_frames_orig, detected_states, mat, accepted_moves,
            key_frame_indices, bootstrap_warped, bootstrap_orig)


# ══════════════════════════════════════════════════════════════════════════════
# FASE WHICH — Identificación de movimientos a partir de la lista de keyframes
# que la fase WHEN ha producido. Procesa la lista offline, manteniendo dos
# referencias (último warped y último board ACEPTADOS) que NO avanzan cuando
# un keyframe no se puede interpretar — eso evita la cascada de fallos: el
# siguiente keyframe se compara contra el último estado válido, y la búsqueda
# multi/recovery encuentra naturalmente la secuencia de 2-N movimientos
# saltados.
#
# Multi-hipótesis bajo demanda (sesión 2026-05-04 ext.):
# Se mantiene UNA hipótesis (modo lineal, comportamiento clásico). Cuando se
# detectan N keyframes consecutivos con scores YOLO bajos (< CASCADE_LOW_SCORE_THR),
# se asume que `legal_board` está desincronizado y se ramifica en K hipótesis,
# cada una reemplazando el último mov aceptado por una alternativa del top-K
# del state-match YOLO. Las hipótesis viven en paralelo hasta que una domina;
# la ganadora final se elige por MÁXIMA PRECISIÓN (nº movs con score ≥ 0.50,
# desempate por score medio).
# ══════════════════════════════════════════════════════════════════════════════


class MatcherResult:
    """Resultado de evaluar las capas WHICH sobre 1 keyframe.

    moves: lista de movs aceptados (0/1/2). Vacía si accepted=False.
    source: matcher ganador. Valores:
        'YOLO-DIFF', 'STATE', 'CONSENSUS', 'YOLO+VAR', 'YOLO-DOUBLE',
        'PURE-VAR', 'JACCARD', 'MULTI', 'RECOVERY', 'FORCED',
        'PHANTOM' (no avanza estado, no es skip), 'SKIP'.
    score: score [0..1] del matcher ganador.
    accepted: True si se han aceptado movs (PHANTOM y SKIP → False).
    state_alts: top-K [(move, score)] del state-match YOLO en este kf, para
        que el orquestador pueda usarlas al ramificar tras una cascada.
    log_msg / log_level: mensaje y nivel para el logger del orquestador.
    """
    __slots__ = ('moves', 'source', 'score', 'accepted', 'state_alts',
                 'log_msg', 'log_level')

    def __init__(self, moves=None, source='SKIP', score=0.0, accepted=False,
                 state_alts=None, log_msg='', log_level='debug'):
        self.moves = moves or []
        self.source = source
        self.score = score
        self.accepted = accepted
        self.state_alts = state_alts or []
        self.log_msg = log_msg
        self.log_level = log_level


class Hypothesis:
    """Una secuencia candidata de movs aceptados con su estado de tablero.

    En modo lineal hay UNA hipótesis. Tras detectar cascada, se ramifican K
    hipótesis con orígenes distintos (alternativas del último accept). Cada
    una mantiene su propio `legal_board`, historial y stats — todas comparten
    los mismos kfs y la misma cache de inferencias YOLO.
    """
    __slots__ = ('legal_board', 'label', 'moves', 'sources', 'scores',
                 'cumulative_score', 'high_quality_count', 'recent_scores',
                 'skipped_indices', 'chain_skipped', 'last_accepted_warped',
                 'last_accepted_kf_idx', 'branched_at_kf', 'leader_streak',
                 'state_alts_at_last_accept', 'stats')

    def __init__(self, legal_board, label='H0', initial_warped=None,
                 initial_kf_idx=0):
        self.legal_board = legal_board.copy()
        self.label = label
        self.moves = []
        self.sources = []
        self.scores = []
        self.cumulative_score = 0.0
        self.high_quality_count = 0
        self.recent_scores = deque(maxlen=8)
        self.skipped_indices = []
        self.chain_skipped = 0
        self.last_accepted_warped = initial_warped
        self.last_accepted_kf_idx = initial_kf_idx
        self.branched_at_kf = None
        self.leader_streak = 0
        self.state_alts_at_last_accept = []
        self.stats = {
            'phantom': 0, 'single': 0, 'multi': 0, 'recovery': 0,
            'skipped': 0, 'max_skipped_chain': 0,
            'yolo_single': 0, 'yolo_double': 0, 'yolo_forced': 0,
        }

    def apply(self, result: 'MatcherResult', kf_idx: int, kf_warped,
              hq_thr: float = 0.50) -> None:
        """Aplica un MatcherResult a esta hipótesis (modifica in place)."""
        # PHANTOM: no avanza estado, NO es skip (no incrementa chain_skipped)
        if result.source == 'PHANTOM':
            self.stats['phantom'] += 1
            return
        if not result.accepted:
            self.skipped_indices.append(kf_idx)
            self.stats['skipped'] += 1
            self.chain_skipped += 1
            if self.chain_skipped > self.stats['max_skipped_chain']:
                self.stats['max_skipped_chain'] = self.chain_skipped
            self.recent_scores.append(0.0)
            return
        for mv in result.moves:
            self.legal_board.push(mv)
            self.moves.append(mv)
            self.sources.append(result.source)
            self.scores.append(result.score)
            self.cumulative_score += result.score
            if result.score >= hq_thr:
                self.high_quality_count += 1
        self.recent_scores.append(result.score)
        self.chain_skipped = 0
        self.last_accepted_warped = kf_warped
        self.last_accepted_kf_idx = kf_idx
        self.state_alts_at_last_accept = list(result.state_alts)
        if result.source == 'JACCARD':
            self.stats['single'] += 1
        elif result.source == 'MULTI':
            self.stats['multi'] += 1
        elif result.source == 'RECOVERY':
            self.stats['recovery'] += 1
        elif result.source == 'FORCED':
            self.stats['yolo_forced'] += 1
        elif len(result.moves) == 2:
            self.stats['yolo_double'] += 1
        else:
            self.stats['yolo_single'] += 1

    def low_streak(self, threshold: float = 0.40) -> int:
        """Cuenta scores recientes consecutivos (de cola) por debajo del umbral.

        SKIPs cuentan como score 0.0 → también caen bajo el umbral.
        PHANTOMs no se registran (no aparecen en recent_scores).
        """
        c = 0
        for s in reversed(self.recent_scores):
            if s < threshold:
                c += 1
            else:
                break
        return c

    def precision_metric(self) -> tuple:
        """Devuelve (high_quality_count, avg_score, num_moves)."""
        if not self.scores:
            return (0, 0.0, 0)
        avg = self.cumulative_score / len(self.scores)
        return (self.high_quality_count, avg, len(self.moves))


def _lookahead_score_for_candidate(
    legal_board: 'chess.Board',
    candidate_mv: 'chess.Move',
    yolo_state_next: dict | None,
) -> float:
    """Coherencia del candidato con el siguiente kf observado por YOLO.

    Lógica: aplicamos `candidate_mv` al tablero canónico y, sobre el estado
    resultante, buscamos el mejor encaje de cualquier mov legal contra el
    `yolo_state_next` (estado YOLO observado en el kf SIGUIENTE). Si el
    candidato es correcto, alguno de los siguientes movs legales explicará
    bien el siguiente kf → score alto. Si el candidato es incorrecto, el
    estado canónico estará desincronizado y NINGÚN mov legal encajará → score
    bajo. Sirve como desempate entre candidatos con margen pequeño.

    Devuelve el mejor score (0..1 aprox) o 0.0 si no hay info.
    """
    if not yolo_state_next:
        return 0.0
    try:
        b = legal_board.copy()
        b.push(candidate_mv)
    except Exception:
        return 0.0
    legal_next = list(b.legal_moves)
    if not legal_next:
        return 0.0
    best = 0.0
    for nxt in legal_next:
        b2 = b.copy()
        b2.push(nxt)
        expected = _board_to_state_symbols(b2)
        focus = _move_changed_squares(b, nxt)
        s = _yolo_score_state(expected, yolo_state_next,
                              focus_sqs=focus, focus_weight=3.0)
        if s > best:
            best = s
    return best


def _run_kf_matchers(
    hyp: 'Hypothesis',
    kf_idx: int,
    kf_cur_warped,
    kf_prev_warped,
    yolo_state_before,
    yolo_state_after,
    yolo_available: bool,
    allow_forced: bool = True,
    allow_recovery: bool = True,
    recovery_depth: int = 3,
    max_recovery_chain: int = 3,
    recovery_min_var_match: float = 0.45,
    noise_floor=None,
    yolo_state_next: dict | None = None,
) -> 'MatcherResult':
    """Ejecuta las 7 capas de matching del WHICH sobre 1 keyframe y devuelve
    un MatcherResult con la decisión.

    Replica la lógica del bucle clásico (sesión 2026-05-04) pero como función
    pura: en lugar de mutar legal_board y hacer 'continue', devuelve el
    resultado para que el orquestador decida cómo aplicarlo. Esto es lo que
    permite multi-hipótesis: la misma kf se evalúa sobre N tableros distintos.
    """
    legal_board = hyp.legal_board
    cur = kf_cur_warped
    last_accepted_warped = hyp.last_accepted_warped

    YOLO_DIFF_ACCEPT_THR   = 0.50
    YOLO_DIFF_MARGIN_REQ   = 0.10
    YOLO_SINGLE_ACCEPT_THR = 0.40
    YOLO_SINGLE_MARGIN_REQ = 0.03
    # Bajado 0.45 → 0.40 tras ver que en test8 el WHEN fusiona dos movs
    # consecutivos en un solo kf (ej. b1c3+d7d5, g8f6+f2f3). En esos casos el
    # single state-match da score moderado (~0.30) sin alcanzar accept, y el
    # double con el par real estaba en ~0.40-0.45. Con 0.40 damos al double
    # margen para rescatar estas fusiones; la verificación física por varianza
    # (DOUBLE_VAR_MIN=0.20) sigue bloqueando pares fantasma.
    YOLO_DOUBLE_ACCEPT_THR = 0.40
    # 18 era demasiado restrictivo para test1/test2/test8 (modelo YOLO sólo ve
    # 14-17 piezas en mid-game con oclusiones) — generaba 42 SKIPs en test1.
    # Bajado a 15 como compromiso: con FORCED+SMART (desempate inteligente) +
    # YOLO_FORCED_MIN_MARGIN=0.05, los empates ya se filtran post-decisión, y
    # podemos permitir FORCED en kfs con menos visibilidad sin meter basura.
    YOLO_FORCED_MIN_PIECES = 15
    # Subido 0.15 → 0.30 tras analizar logs: FORCED con score < 0.30 producía
    # casi siempre movs incorrectos (margin=0, ej: "FORCED — Ra1 score=0.239")
    # que desincronizaban el legal_board y arruinaban los siguientes 5-10 kfs.
    YOLO_FORCED_MIN_SCORE  = 0.30
    # Margen mínimo TRAS el desempate inteligente. Si tras combinar varianza,
    # coherencia de destino y de origen sigue habiendo empate (margen < 0.05),
    # SKIP en lugar de aceptar uno arbitrario. Esto elimina los movs aleatorios
    # entre 3 candidatos empatados que eran ~50-70 % de los FORCED basura.
    YOLO_FORCED_MIN_MARGIN = 0.05
    YOLO_VAR_FALLBACK_THR  = 0.30
    YOLO_VAR_TIE_MARGIN    = 0.03
    YOLO_PHYSICAL_VAR_MIN  = 0.03
    YOLO_CONSENSUS_VAR_MIN = 0.05
    DOUBLE_VAR_MIN         = 0.20
    VAR_ACCEPT_SCORE       = 0.15
    VAR_ACCEPT_MARGIN      = 0.05
    # Jaccard fallback estricto. Subido 0.30 → 0.40 tras ver en test3 kf #9
    # que `Nbd2 score=0.337` se aceptó pese a no ser el mov real.
    WHICH_ACCEPT_THR       = 0.40
    WHICH_MARGIN_REQ       = 0.05
    WHICH_MULTI_THR        = 0.35
    WHICH_PHANTOM_TOP1     = 150
    # Phantom inicial: si en el primer kf (kf #1) la varianza máxima respecto
    # al bootstrap es < esta cifra, asumimos frame de calentamiento sin mov
    # real (común al inicio de los videos). Calibrado: movs reales tienen
    # top1 > 800; phantoms iniciales aparecen con top1 < 600.
    PHANTOM_INITIAL_TOP1   = 600

    state_alts_for_branch: list = []
    label = hyp.label

    # ── Paso 0: detección de phantom inicial ─────────────────────────────
    # En el primer kf (kf_idx == 1) sin movs aceptados todavía, si la
    # varianza máxima respecto al frame anterior es despreciable, asumimos
    # frame de calentamiento sin movimiento real. Análisis de logs (test1)
    # mostró que kf #1 a veces capturaba un frame phantom cuya PURE-VAR
    # acepta cualquier mov plausible (d2d4 con var=0.262) desincronizando
    # legal_board desde el inicio. Bloqueando estos phantoms preservamos
    # la sincronía con la partida real.
    if kf_idx == 1 and not hyp.moves:
        diffs_initial = _variance_diff_all(kf_prev_warped, cur)
        sorted_init = sorted(diffs_initial.values(), reverse=True)
        top1_init = sorted_init[0] if sorted_init else 0.0
        if top1_init < PHANTOM_INITIAL_TOP1:
            msg = (f"[WHICH] {label} kf #{kf_idx}: phantom inicial "
                   f"(top1={top1_init:.0f} < {PHANTOM_INITIAL_TOP1}). "
                   f"Frame de calentamiento — estado no avanza.")
            return MatcherResult(
                moves=[], source='PHANTOM', score=0.0, accepted=False,
                state_alts=[], log_msg=msg, log_level='info',
            )

    # Precomputamos el state-match aunque luego acepte otro matcher: las alts
    # del state-match son la base para el branching multi-hipótesis tras una
    # cascada, así que las queremos disponibles en TODOS los retornos. Coste:
    # una pasada extra sobre los movs legales (~ms).
    yolo_single_result = None
    if yolo_available and yolo_state_after:
        yolo_single_result = _yolo_match_single_move(legal_board, yolo_state_after)
        if yolo_single_result is not None:
            state_alts_for_branch = list(yolo_single_result[4])

    # ── Paso 0a': YOLO-DOUBLE prioritario si hay evidencia de cambio múltiple ─
    # Si el diff color/presencia entre los dos estados YOLO marca 4+ casillas,
    # un solo movimiento NO puede explicarlo (un single afecta 2 casillas; sólo
    # enroque afecta 4 — pero enroques son raros y `_yolo_match_double_move`
    # devolverá None si no hay par legal coherente, así que volvemos a la
    # cascada normal). Esto resuelve el patrón "WHEN funde 2 jugadas
    # consecutivas en un kf" donde el single matcher acepta sólo la mitad
    # del cambio con score muy alto y eclipsa al doble real.
    DOUBLE_TRIGGER_DIFF_SQS = 4    # nº mín. de casillas en yolo_diff para activar
    DOUBLE_PRIORITY_THR     = 0.55 # umbral del score doble (state_score)
    DOUBLE_PRIORITY_VAR_MIN = 0.20 # mismo que DOUBLE_VAR_MIN clásico
    if (yolo_available and yolo_state_after
            and yolo_state_before is not None and len(yolo_state_before) > 0):
        diff_set = _yolo_diff_squares(yolo_state_before, yolo_state_after)
        if len(diff_set) >= DOUBLE_TRIGGER_DIFF_SQS:
            yolo_double_pri = _yolo_match_double_move(legal_board, yolo_state_after)
            if yolo_double_pri is not None:
                mvA_p, mvB_p, dscore_p = yolo_double_pri
                if dscore_p >= DOUBLE_PRIORITY_THR:
                    # Verificación física por varianza: las casillas del par
                    # deben absorber la mayor parte del cambio observado en
                    # el warped (evita aceptar pares fantasma cuando el yolo
                    # tiene ruido).
                    diffs_dp = _variance_diff_all(kf_prev_warped, cur)
                    pair_sqs_p = (_move_changed_squares(legal_board, mvA_p)
                                  | _move_changed_squares(legal_board, mvB_p))
                    total_dp = sum(diffs_dp.values()) + 1e-6
                    pair_var_p = sum(diffs_dp.get(sq, 0.0) for sq in pair_sqs_p) / total_dp
                    # Cobertura del yolo_diff por el par: filtra pares que no
                    # explican lo que YOLO ve cambiar.
                    pair_diff_cover = (len(pair_sqs_p & diff_set) / len(diff_set)
                                       if diff_set else 0.0)
                    if pair_var_p >= DOUBLE_PRIORITY_VAR_MIN and pair_diff_cover >= 0.75:
                        try:
                            sanA_p = legal_board.san(mvA_p)
                        except Exception:
                            sanA_p = mvA_p.uci()
                        bA_prev_p = legal_board.copy()
                        bA_prev_p.push(mvA_p)
                        try:
                            sanB_p = bA_prev_p.san(mvB_p)
                        except Exception:
                            sanB_p = mvB_p.uci()
                        msg = (f"[WHICH/YOLO-DOUBLE-PRI] {label} kf #{kf_idx}: "
                               f"2 movs — {sanA_p}+{sanB_p} "
                               f"[{mvA_p.uci()}+{mvB_p.uci()}] "
                               f"score={dscore_p:.3f} var={pair_var_p:.3f} "
                               f"diff_sqs={len(diff_set)} cover={pair_diff_cover:.2f}")
                        return MatcherResult(
                            moves=[mvA_p, mvB_p], source='YOLO-DOUBLE',
                            score=dscore_p, accepted=True,
                            state_alts=state_alts_for_branch,
                            log_msg=msg, log_level='info',
                        )

    # ── Paso 0a: YOLO-DIFF ────────────────────────────────────────────────
    yolo_diff_top_uci = None
    yolo_diff_top_score = -1.0
    if yolo_available and yolo_state_after:
        yolo_diff_result = _yolo_match_single_move_diff(
            legal_board, yolo_state_before or {}, yolo_state_after,
        )
        if yolo_diff_result is not None:
            ymv, yscore, ymargin, yalts = yolo_diff_result
            yolo_diff_top_uci = ymv.uci()
            yolo_diff_top_score = yscore
            alts_str = ", ".join(f"{u}({s:.3f})" for u, s in yalts[:3])
            if (yscore >= YOLO_DIFF_ACCEPT_THR
                    and ymargin >= YOLO_DIFF_MARGIN_REQ):
                diffs_check = _variance_diff_all(kf_prev_warped, cur)
                diff_var = _variance_score_for_move(legal_board, ymv, diffs_check)
                if diff_var >= YOLO_PHYSICAL_VAR_MIN:
                    try:
                        san = legal_board.san(ymv)
                    except Exception:
                        san = ymv.uci()
                    msg = (f"[WHICH/YOLO-DIFF] {label} kf #{kf_idx}: 1 mov — "
                           f"{san} [{ymv.uci()}] score={yscore:.3f} "
                           f"margen={ymargin:.3f} var={diff_var:.3f} "
                           f"alts=[{alts_str}]")
                    return MatcherResult(
                        moves=[ymv], source='YOLO-DIFF', score=yscore,
                        accepted=True, state_alts=state_alts_for_branch,
                        log_msg=msg, log_level='info',
                    )

    # ── Paso 0b: YOLO state-match single-move ─────────────────────────────
    if yolo_available and yolo_state_after and yolo_single_result is not None:
        ymv, yscore, ymargin, yalts, yall_scored = yolo_single_result
        alts_str = ", ".join(f"{u}({s:.3f})" for u, s in yalts[:3])
        state_passed_thr = (yscore >= YOLO_SINGLE_ACCEPT_THR
                            and ymargin >= YOLO_SINGLE_MARGIN_REQ)
        state_var_failed = False
        if state_passed_thr:
            diffs_check = _variance_diff_all(kf_prev_warped, cur)
            state_var = _variance_score_for_move(legal_board, ymv, diffs_check)
            if state_var >= YOLO_PHYSICAL_VAR_MIN:
                try:
                    san = legal_board.san(ymv)
                except Exception:
                    san = ymv.uci()
                msg = (f"[WHICH/YOLO] {label} kf #{kf_idx}: 1 mov — {san} "
                       f"[{ymv.uci()}] score={yscore:.3f} "
                       f"margen={ymargin:.3f} var={state_var:.3f} "
                       f"piezas={len(yolo_state_after)} alts=[{alts_str}]")
                return MatcherResult(
                    moves=[ymv], source='STATE', score=yscore,
                    accepted=True, state_alts=state_alts_for_branch,
                    log_msg=msg, log_level='info',
                )
            else:
                state_var_failed = True

        if (not state_passed_thr) or state_var_failed:
            # Consenso DIFF + STATE-MATCH + verificación física
            if (yolo_diff_top_uci is not None
                    and yolo_diff_top_uci == ymv.uci()
                    and yscore >= YOLO_VAR_FALLBACK_THR
                    and yolo_diff_top_score >= 0.30):
                diffs_check = _variance_diff_all(kf_prev_warped, cur)
                consensus_var = _variance_score_for_move(legal_board, ymv, diffs_check)
                if consensus_var >= YOLO_CONSENSUS_VAR_MIN:
                    try:
                        san = legal_board.san(ymv)
                    except Exception:
                        san = ymv.uci()
                    msg = (f"[WHICH/YOLO-CONSENSUS] {label} kf #{kf_idx}: "
                           f"1 mov — {san} [{ymv.uci()}] state={yscore:.3f} "
                           f"diff={yolo_diff_top_score:.3f} "
                           f"var={consensus_var:.3f} "
                           f"piezas={len(yolo_state_after)}")
                    return MatcherResult(
                        moves=[ymv], source='CONSENSUS', score=yscore,
                        accepted=True, state_alts=state_alts_for_branch,
                        log_msg=msg, log_level='info',
                    )

            # Desempate por varianza
            consider_var_tiebreak = (
                yscore >= YOLO_VAR_FALLBACK_THR
                and ymargin < YOLO_SINGLE_MARGIN_REQ
            )
            if consider_var_tiebreak:
                tie_result = _break_tie_by_variance(
                    legal_board, yall_scored,
                    last_accepted_warped, cur,
                    score_eps=0.01,
                )
                if tie_result is not None:
                    tmv, tvar, tvar_margin = tie_result
                    if tvar_margin >= YOLO_VAR_TIE_MARGIN:
                        try:
                            san = legal_board.san(tmv)
                        except Exception:
                            san = tmv.uci()
                        msg = (f"[WHICH/YOLO+VAR] {label} kf #{kf_idx}: "
                               f"1 mov — {san} [{tmv.uci()}] "
                               f"yolo={yscore:.3f} var={tvar:.3f} "
                               f"var_margin={tvar_margin:.3f} "
                               f"piezas={len(yolo_state_after)}")
                        return MatcherResult(
                            moves=[tmv], source='YOLO+VAR', score=yscore,
                            accepted=True, state_alts=state_alts_for_branch,
                            log_msg=msg, log_level='info',
                        )

            # ── Paso 0b'': LOOKAHEAD tiebreak ─────────────────────────────
            # Cuando la varianza tampoco discrimina pero hay varios candidatos
            # con state-score parecido (margin pequeño), simular cada uno y
            # ver cuál lleva a un estado canónico que el yolo_state_next puede
            # explicar. Coste: O(K × M) inferencias triviales (sin llamadas
            # a YOLO, solo scoring de estados).
            LA_STATE_TIE_EPS = 0.05
            LA_STATE_MIN_MARGIN = 0.04
            tied_state = [(m, s) for m, s in yall_scored
                           if (yscore - s) <= LA_STATE_TIE_EPS]
            if (yolo_state_next is not None
                    and yscore >= YOLO_VAR_FALLBACK_THR
                    and 2 <= len(tied_state) <= 6):
                la_scored = [
                    (m, _lookahead_score_for_candidate(
                        legal_board, m, yolo_state_next))
                    for m, _ in tied_state
                ]
                la_scored.sort(key=lambda x: x[1], reverse=True)
                best_la_mv, best_la_sc = la_scored[0]
                second_la_sc = la_scored[1][1] if len(la_scored) > 1 else 0.0
                la_margin = best_la_sc - second_la_sc
                if la_margin >= LA_STATE_MIN_MARGIN and best_la_sc >= 0.50:
                    try:
                        san = legal_board.san(best_la_mv)
                    except Exception:
                        san = best_la_mv.uci()
                    la_str = ", ".join(f"{m.uci()}({s:.3f})" for m, s in la_scored[:3])
                    msg = (f"[WHICH/YOLO+LA] {label} kf #{kf_idx}: 1 mov — "
                           f"{san} [{best_la_mv.uci()}] yolo={yscore:.3f} "
                           f"la={best_la_sc:.3f} la_margin={la_margin:.3f} "
                           f"alts=[{la_str}] piezas={len(yolo_state_after)}")
                    return MatcherResult(
                        moves=[best_la_mv], source='STATE', score=yscore,
                        accepted=True, state_alts=state_alts_for_branch,
                        log_msg=msg, log_level='info',
                    )

    # ── Paso 0c: YOLO double-move ────────────────────────────────────────
    if yolo_available and yolo_state_after:
        yolo_double = _yolo_match_double_move(legal_board, yolo_state_after)
        if yolo_double is not None:
            mvA, mvB, dscore = yolo_double
            single_best = yolo_single_result[1] if yolo_single_result else float('-inf')
            if dscore >= YOLO_DOUBLE_ACCEPT_THR and dscore > single_best + 0.05:
                diffs_d = _variance_diff_all(kf_prev_warped, cur)
                pair_sqs = (_move_changed_squares(legal_board, mvA)
                            | _move_changed_squares(legal_board, mvB))
                total_d = sum(diffs_d.values()) + 1e-6
                pair_var = sum(diffs_d.get(sq, 0.0) for sq in pair_sqs) / total_d
                if pair_var >= DOUBLE_VAR_MIN:
                    try:
                        sanA = legal_board.san(mvA)
                    except Exception:
                        sanA = mvA.uci()
                    bA_preview = legal_board.copy()
                    bA_preview.push(mvA)
                    try:
                        sanB = bA_preview.san(mvB)
                    except Exception:
                        sanB = mvB.uci()
                    msg = (f"[WHICH/YOLO] {label} kf #{kf_idx}: 2 movs — "
                           f"{sanA}+{sanB} [{mvA.uci()}+{mvB.uci()}] "
                           f"score={dscore:.3f} var={pair_var:.3f}")
                    return MatcherResult(
                        moves=[mvA, mvB], source='YOLO-DOUBLE', score=dscore,
                        accepted=True, state_alts=state_alts_for_branch,
                        log_msg=msg, log_level='info',
                    )

    # ── Paso 0d: PURE-VAR ────────────────────────────────────────────────
    # Cross-check con YOLO state-match: si PURE-VAR elige un mov que YOLO ni
    # siquiera considera (state-score < 0.20), exigimos umbrales más estrictos
    # (var ≥ 0.25, margin ≥ 0.15). Esto bloquea casos como test1 kf #9 donde
    # PURE-VAR aceptó b8c6 (mov #16) cuando WHEN saltó d7d6 (mov #8): la
    # varianza física era espuria y YOLO no apoyaba ese mov.
    PURE_VAR_NOYOLO_VAR_MIN    = 0.25
    PURE_VAR_NOYOLO_MARGIN_MIN = 0.15
    PURE_VAR_YOLO_SUPPORT_THR  = 0.20

    var_match = _pure_variance_match(legal_board, kf_prev_warped, cur)
    if var_match is not None:
        vmv, vscore, vmargin, valts = var_match
        valts_str = ", ".join(f"{u}({s:.3f})" for u, s in valts[:3])

        # ¿YOLO apoya el mov elegido por varianza?
        yolo_support = 0.0
        if yolo_single_result is not None:
            for mv_cand, sc_cand in yolo_single_result[4]:
                if mv_cand.uci() == vmv.uci():
                    yolo_support = sc_cand
                    break

        # Decidir umbrales según apoyo YOLO:
        if yolo_support >= PURE_VAR_YOLO_SUPPORT_THR:
            # YOLO también lo considera plausible → umbrales normales.
            need_var, need_margin = VAR_ACCEPT_SCORE, VAR_ACCEPT_MARGIN
            support_tag = f" yolo={yolo_support:.3f}"
        else:
            # YOLO ni siquiera lo ve (probable mov fantasma o WHEN saltado).
            # Exigir señal de varianza MUY fuerte para aceptar.
            need_var, need_margin = PURE_VAR_NOYOLO_VAR_MIN, PURE_VAR_NOYOLO_MARGIN_MIN
            support_tag = f" yolo={yolo_support:.3f} (sin apoyo, umbrales estrictos)"

        if vscore >= need_var and vmargin >= need_margin:
            try:
                san = legal_board.san(vmv)
            except Exception:
                san = vmv.uci()
            msg = (f"[WHICH/PURE-VAR] {label} kf #{kf_idx}: 1 mov — {san} "
                   f"[{vmv.uci()}] var={vscore:.3f} margen={vmargin:.3f}"
                   f"{support_tag} alts=[{valts_str}]")
            return MatcherResult(
                moves=[vmv], source='PURE-VAR', score=vscore, accepted=True,
                state_alts=state_alts_for_branch,
                log_msg=msg, log_level='info',
            )

    # ── Paso 1: phantom residual (no avanza estado, no es skip) ──────────
    diffs_phantom = _variance_diff_all(last_accepted_warped, cur)
    sorted_p = sorted(diffs_phantom.values(), reverse=True)
    top1_phantom = sorted_p[0] if sorted_p else 0.0
    if top1_phantom < WHICH_PHANTOM_TOP1:
        msg = (f"[WHICH] {label} kf #{kf_idx}: phantom (top1={top1_phantom:.0f} "
               f"< {WHICH_PHANTOM_TOP1}). Sin movimiento — estado no avanza.")
        return MatcherResult(
            moves=[], source='PHANTOM', score=0.0, accepted=False,
            state_alts=state_alts_for_branch,
            log_msg=msg, log_level='info',
        )

    # ── Paso 2: Jaccard single (fallback) ───────────────────────────────
    result = _match_move_by_jaccard(
        legal_board, last_accepted_warped, cur,
        force_accept=False,
        noise_floor=noise_floor or None,
        accept_thr=WHICH_ACCEPT_THR,
        margin_req=WHICH_MARGIN_REQ,
    )
    if result is not None:
        move, score, alts = result
        try:
            san = legal_board.san(move)
        except Exception:
            san = move.uci()
        alts_str = ", ".join(f"{s}({sc:.3f})" for s, sc in alts)
        msg = (f"[WHICH] {label} kf #{kf_idx}: 1 movimiento — {san} "
               f"[{move.uci()}] score={score:.3f} alts=[{alts_str}]")
        return MatcherResult(
            moves=[move], source='JACCARD', score=score, accepted=True,
            state_alts=state_alts_for_branch,
            log_msg=msg, log_level='info',
        )

    # ── Paso 3: Jaccard multi (2 movs) ───────────────────────────────────
    multi = _try_multi_move_jaccard(legal_board, last_accepted_warped, cur,
                                     noise_floor=noise_floor or None)
    if multi is not None and multi[2] >= WHICH_MULTI_THR:
        mvA, mvB, multi_score = multi
        try:
            sanA = legal_board.san(mvA)
        except Exception:
            sanA = mvA.uci()
        bA_preview = legal_board.copy()
        bA_preview.push(mvA)
        try:
            sanB = bA_preview.san(mvB)
        except Exception:
            sanB = mvB.uci()
        msg = (f"[WHICH] {label} kf #{kf_idx}: 2 movimientos — {sanA}+{sanB} "
               f"[{mvA.uci()}+{mvB.uci()}] score={multi_score:.3f}")
        return MatcherResult(
            moves=[mvA, mvB], source='MULTI', score=multi_score,
            accepted=True, state_alts=state_alts_for_branch,
            log_msg=msg, log_level='info',
        )

    # ── Paso 4: BFS recovery ─────────────────────────────────────────────
    if hyp.chain_skipped >= max_recovery_chain or not allow_recovery:
        recovered = None
    else:
        recovered = _try_state_recovery(legal_board, cur, depth=recovery_depth)

    if recovered is not None:
        _, recovery_moves = recovered
        all_move_sqs: set = set()
        preview_board = legal_board.copy()
        for m in recovery_moves:
            all_move_sqs |= _move_changed_squares(preview_board, m)
            preview_board.push(m)
        seq_diffs_raw = _variance_diff_all(last_accepted_warped, cur)
        if noise_floor:
            seq_diffs = {sq: max(0.0, seq_diffs_raw[sq] - noise_floor.get(sq, 0.0))
                         for sq in chess.SQUARES}
        else:
            seq_diffs = seq_diffs_raw
        total_seq_var = sum(seq_diffs.values()) + 1e-6
        captured_var = sum(seq_diffs.get(sq, 0.0) for sq in all_move_sqs)
        variance_match = captured_var / total_seq_var
        if variance_match >= recovery_min_var_match:
            sans = []
            preview_board2 = legal_board.copy()
            for m in recovery_moves:
                try:
                    sans.append(preview_board2.san(m))
                except Exception:
                    sans.append(m.uci())
                preview_board2.push(m)
            msg = (f"[WHICH] {label} kf #{kf_idx}: {len(recovery_moves)} "
                   f"movimientos via recovery — {'+'.join(sans)} "
                   f"(var_match={variance_match:.2f})")
            return MatcherResult(
                moves=list(recovery_moves), source='RECOVERY',
                score=variance_match, accepted=True,
                state_alts=state_alts_for_branch,
                log_msg=msg, log_level='info',
            )

    # ── Paso 5a: FORCED (best-effort YOLO) ───────────────────────────────
    # Sólo si YOLO ve suficientes piezas (calibración bien anclada). Cuando
    # margen=0 (alts empatadas), aplicamos desempate inteligente combinando
    # varianza física + coherencia destino + casilla origen vacía. Si el
    # desempate tampoco da margen claro (≥ YOLO_FORCED_MIN_MARGIN), SKIP en
    # lugar de empujar un mov aleatorio.
    if (allow_forced and yolo_single_result is not None
            and yolo_state_after is not None
            and len(yolo_state_after) >= YOLO_FORCED_MIN_PIECES):
        ymv, yscore, ymargin, yalts, yall_scored_f = yolo_single_result
        if yscore >= YOLO_FORCED_MIN_SCORE:
            final_mv = ymv
            source_label = "FORCED"
            tie_diag = ""
            if ymargin < YOLO_FORCED_MIN_MARGIN:
                # Desempate inteligente (varianza + coherencia destino + origen).
                smart = _intelligent_tiebreak(
                    legal_board, yall_scored_f, yolo_state_after,
                    last_accepted_warped, cur, score_eps=0.01,
                )
                if smart is not None:
                    smv, smargin, svar, sdest, sfrom = smart
                    if smargin >= YOLO_FORCED_MIN_MARGIN:
                        final_mv = smv
                        source_label = "FORCED+SMART"
                        tie_diag = (f" smart(var={svar:.3f}, dest={sdest:.2f}, "
                                    f"from={sfrom:.2f}, margin={smargin:.3f})")
                    else:
                        # Empate persistente tras desempate inteligente.
                        # Antes de SKIP, intentar lookahead: ¿qué candidato
                        # lleva a un estado canónico que el siguiente kf
                        # YOLO observado pueda explicar mejor?
                        LOOKAHEAD_TIE_EPS = 0.02
                        LOOKAHEAD_MIN_MARGIN = 0.05
                        tied_for_la = [(m, s) for m, s in yall_scored_f
                                        if (yscore - s) <= LOOKAHEAD_TIE_EPS]
                        if (yolo_state_next is not None
                                and len(tied_for_la) >= 2
                                and len(tied_for_la) <= 6):
                            la_scored = [
                                (m, _lookahead_score_for_candidate(
                                    legal_board, m, yolo_state_next))
                                for m, _ in tied_for_la
                            ]
                            la_scored.sort(key=lambda x: x[1], reverse=True)
                            best_la_mv, best_la_sc = la_scored[0]
                            second_la_sc = la_scored[1][1] if len(la_scored) > 1 else 0.0
                            la_margin = best_la_sc - second_la_sc
                            if la_margin >= LOOKAHEAD_MIN_MARGIN:
                                final_mv = best_la_mv
                                source_label = "FORCED+LA"
                                tie_diag = (f" lookahead(la={best_la_sc:.3f}, "
                                            f"runner={second_la_sc:.3f}, "
                                            f"margin={la_margin:.3f})")
                            else:
                                # Lookahead tampoco discrimina → último intento:
                                # desempate por centroide del cambio YOLO.
                                cent = _yolo_change_centroid_tiebreak(
                                    yall_scored_f, yolo_state_before,
                                    yolo_state_after, score_eps=LOOKAHEAD_TIE_EPS,
                                )
                                CENTROID_MIN_MARGIN = 0.8  # casillas
                                if cent is not None and cent[2] >= CENTROID_MIN_MARGIN:
                                    final_mv = cent[0]
                                    source_label = "FORCED+CENT"
                                    tie_diag = (f" centroid(d={cent[1]:.2f}, "
                                                f"margin={cent[2]:.2f})")
                                else:
                                    alts_str = ", ".join(f"{u}({s:.3f})" for u, s in yalts[:3])
                                    la_str = ", ".join(f"{m.uci()}({s:.3f})" for m, s in la_scored[:3])
                                    cent_str = (f" cent_margin={cent[2]:.2f}"
                                                 if cent is not None else "")
                                    msg = (f"[WHICH/YOLO] {label} kf #{kf_idx}: FORCED "
                                           f"BLOQUEADO — empate persistente tras desempate "
                                           f"inteligente, lookahead y centroide "
                                           f"(la_margin={la_margin:.3f}{cent_str}). "
                                           f"best={ymv.uci()} score={yscore:.3f} "
                                           f"alts=[{alts_str}] la=[{la_str}]. SKIP.")
                                    return MatcherResult(
                                        moves=[], source='SKIP', score=0.0,
                                        accepted=False,
                                        state_alts=state_alts_for_branch,
                                        log_msg=msg, log_level='warning',
                                    )
                        else:
                            # Sin yolo_state_next: probar centroide antes de SKIP.
                            cent = _yolo_change_centroid_tiebreak(
                                yall_scored_f, yolo_state_before,
                                yolo_state_after, score_eps=0.02,
                            )
                            CENTROID_MIN_MARGIN = 0.8  # casillas
                            if cent is not None and cent[2] >= CENTROID_MIN_MARGIN:
                                final_mv = cent[0]
                                source_label = "FORCED+CENT"
                                tie_diag = (f" centroid(d={cent[1]:.2f}, "
                                            f"margin={cent[2]:.2f})")
                            else:
                                alts_str = ", ".join(f"{u}({s:.3f})" for u, s in yalts[:3])
                                cent_str = (f" cent_margin={cent[2]:.2f}"
                                             if cent is not None else "")
                                msg = (f"[WHICH/YOLO] {label} kf #{kf_idx}: FORCED "
                                       f"BLOQUEADO — empate persistente tras desempate "
                                       f"inteligente y centroide "
                                       f"(margin={smargin:.3f} < "
                                       f"{YOLO_FORCED_MIN_MARGIN}{cent_str}). "
                                       f"best={ymv.uci()} score={yscore:.3f} "
                                       f"alts=[{alts_str}]. SKIP.")
                                return MatcherResult(
                                    moves=[], source='SKIP', score=0.0,
                                    accepted=False,
                                    state_alts=state_alts_for_branch,
                                    log_msg=msg, log_level='warning',
                                )
                # Si smart=None (sólo 1 candidato no empatado), aceptamos ymv.
            try:
                san = legal_board.san(final_mv)
            except Exception:
                san = final_mv.uci()
            alts_str = ", ".join(f"{u}({s:.3f})" for u, s in yalts[:3])
            msg = (f"[WHICH/YOLO] {label} kf #{kf_idx}: {source_label} — {san} "
                   f"[{final_mv.uci()}] score={yscore:.3f} margen={ymargin:.3f} "
                   f"alts=[{alts_str}]{tie_diag} (piezas={len(yolo_state_after)})")
            return MatcherResult(
                moves=[final_mv], source='FORCED', score=yscore,
                accepted=True, state_alts=state_alts_for_branch,
                log_msg=msg, log_level='warning',
            )

    # ── Paso 5b: skip silencioso (último recurso) ────────────────────────
    msg = (f"[WHICH] {label} kf #{kf_idx}: sin encaje a profundidad "
           f"≤{recovery_depth}. Saltado (cadena_skips={hyp.chain_skipped + 1}).")
    return MatcherResult(
        moves=[], source='SKIP', score=0.0, accepted=False,
        state_alts=state_alts_for_branch,
        log_msg=msg, log_level='warning',
    )


def _spawn_alternatives_from_history(
    main_hyp: 'Hypothesis',
    initial_board: 'chess.Board',
    key_frames: list,
    get_yolo_state,
    current_kf_idx: int,
    K: int = 4,
    score_min_for_branch: float = 0.20,
    yolo_available: bool = True,
    recovery_depth: int = 5,
    max_recovery_chain: int = 3,
    recovery_min_var_match: float = 0.45,
) -> list:
    """Cuando se detecta cascada en `current_kf_idx`, ramifica `main_hyp` en
    hasta K hipótesis alternativas reemplazando el ÚLTIMO mov aceptado por
    candidatos del top-K state-match YOLO en ese kf. Cada hipótesis alternativa
    replay los kfs intermedios (last_accept_kf+1..current_kf-1) para llegar
    al mismo punto temporal con un legal_board distinto.

    Devuelve [main_hyp, alt1, alt2, ...] con K elementos como máximo.
    Si no hay alternativas válidas, devuelve [main_hyp].
    """
    if not main_hyp.moves or not main_hyp.state_alts_at_last_accept:
        return [main_hyp]
    last_kf_idx = main_hyp.last_accepted_kf_idx
    if last_kf_idx <= 0 or last_kf_idx >= current_kf_idx:
        return [main_hyp]

    last_move_uci = main_hyp.moves[-1].uci()

    alternatives: list = []
    for mv, sc in main_hyp.state_alts_at_last_accept[:K * 4]:
        if mv.uci() == last_move_uci:
            continue
        if sc < score_min_for_branch:
            break
        alternatives.append((mv, sc))
        if len(alternatives) >= K - 1:
            break

    if not alternatives:
        return [main_hyp]

    main_hyp.label = "H0-ORIG"
    main_hyp.branched_at_kf = current_kf_idx
    new_hyps: list = [main_hyp]

    for idx, (alt_mv, alt_sc) in enumerate(alternatives):
        alt_label = f"H{idx + 1}"
        alt_board = initial_board.copy()
        for mv in main_hyp.moves[:-1]:
            alt_board.push(mv)
        if alt_mv not in list(alt_board.legal_moves):
            continue

        alt_hyp = Hypothesis(
            alt_board, label=alt_label,
            initial_warped=key_frames[last_kf_idx],
            initial_kf_idx=last_kf_idx,
        )
        alt_hyp.moves = list(main_hyp.moves[:-1])
        alt_hyp.sources = list(main_hyp.sources[:-1])
        alt_hyp.scores = list(main_hyp.scores[:-1])
        alt_hyp.cumulative_score = sum(alt_hyp.scores)
        alt_hyp.high_quality_count = sum(1 for s in alt_hyp.scores if s >= 0.50)
        alt_hyp.skipped_indices = list(main_hyp.skipped_indices)
        alt_hyp.stats = dict(main_hyp.stats)

        alt_hyp.legal_board.push(alt_mv)
        alt_hyp.moves.append(alt_mv)
        alt_hyp.sources.append("BRANCH")
        alt_hyp.scores.append(alt_sc)
        alt_hyp.cumulative_score += alt_sc
        if alt_sc >= 0.50:
            alt_hyp.high_quality_count += 1
        alt_hyp.last_accepted_warped = key_frames[last_kf_idx]
        alt_hyp.last_accepted_kf_idx = last_kf_idx
        alt_hyp.branched_at_kf = current_kf_idx
        alt_hyp.recent_scores.append(alt_sc)
        alt_hyp.stats['yolo_single'] += 1

        for kf_replay in range(last_kf_idx + 1, current_kf_idx):
            cur_replay = key_frames[kf_replay]
            prev_replay = key_frames[kf_replay - 1]
            yolo_b = get_yolo_state(kf_replay - 1)
            yolo_a = get_yolo_state(kf_replay)
            res = _run_kf_matchers(
                alt_hyp, kf_replay, cur_replay, prev_replay,
                yolo_b, yolo_a, yolo_available=yolo_available,
                allow_forced=False,
                allow_recovery=True,
                recovery_depth=recovery_depth,
                max_recovery_chain=max_recovery_chain,
                recovery_min_var_match=recovery_min_var_match,
            )
            alt_hyp.apply(res, kf_idx=kf_replay, kf_warped=cur_replay)

        new_hyps.append(alt_hyp)

    return new_hyps


def _select_winner_by_precision(hypotheses: list) -> 'Hypothesis':
    """Elige la hipótesis ganadora por máxima precisión.

    Criterio lexicográfico: (high_quality_count, avg_score, num_moves).
    """
    if not hypotheses:
        return None
    return max(hypotheses, key=lambda h: h.precision_metric())


def identify_moves_from_keyframes(
    key_frames: list,
    initial_board: chess.Board | None = None,
    recovery_depth: int = 3,
    max_recovery_chain: int = 3,
    recovery_min_var_match: float = 0.45,
    key_frames_orig: list | None = None,
    homography_M: 'np.ndarray | None' = None,
    yolo_force_one_per_kf: bool = True,
    bootstrap_warped: 'np.ndarray | None' = None,
    bootstrap_orig: 'np.ndarray | None' = None,
    enable_cascade_recovery: bool = False,
):
    """
    Identifica la secuencia de movimientos jugados a partir de los keyframes
    producidos por la fase WHEN.

    Arquitectura (sesión 2026-05-04 ext.): orquestador modal multi-hipótesis.

      • Modo LINEAL (default): UNA hipótesis. En cada kf se aplican las 7
        capas de matching (`_run_kf_matchers`): YOLO-DIFF → STATE → CONSENSUS
        → YOLO+VAR → YOLO-DOUBLE → PURE-VAR → PHANTOM → JACCARD → MULTI →
        RECOVERY → FORCED → SKIP. Comportamiento idéntico al previo.
      • Modo MULTI (bajo demanda): tras `CASCADE_TRIGGER` kfs consecutivos
        con score < `CASCADE_LOW_SCORE_THR` (asume cascada por desincro de
        legal_board), se ramifica en hasta `K_HYPOTHESES` hipótesis. Cada
        alternativa reemplaza el último mov aceptado por una candidata del
        top-K state-match YOLO y replay los kfs intermedios.
      • Colapso a lineal: si una hipótesis domina al resto durante
        `LEADER_WINDOW` kfs (HQ count + avg score) → se descarta el resto.
      • Selección final: hipótesis ganadora por MÁXIMA PRECISIÓN
        (high_quality_count, avg_score, n_movs).

    Args:
        key_frames: lista warpeada; [0] es la posición inicial, [1:] eventos.
        initial_board: estado inicial (default chess.Board()).
        recovery_depth: BFS depth en modo lineal (default 3).
        max_recovery_chain: corte de recovery por cadena de skips.
        recovery_min_var_match: fracción mínima de varianza explicada por la
            secuencia de recovery propuesta.
        key_frames_orig: lista paralela de frames originales (para YOLO).
        homography_M: matriz 3×3 para proyectar bbox YOLO al grid warpeado.
        yolo_force_one_per_kf: si True (default), en modo LINEAL fuerza el
            mejor candidato YOLO cuando ningún matcher converge. En modo
            MULTI se desactiva siempre (un FORCED en una hipótesis perdedora
            ensucia la métrica de precisión).
        bootstrap_warped, bootstrap_orig: par para calibrar offset YOLO.

    Returns:
        Tupla (moves, skipped_indices, stats). `stats` incluye además los
        contadores `cascade_events`, `leader_collapses`, `final_hypotheses` y
        `winner_label`.
    """
    moves: list = []
    skipped_indices: list[int] = []
    stats = {
        'phantom':            0,
        'single':             0,
        'multi':              0,
        'recovery':           0,
        'skipped':            0,
        'max_skipped_chain':  0,
        'yolo_single':        0,
        'yolo_double':        0,
        'yolo_forced':        0,
    }

    if not key_frames:
        return moves, skipped_indices, stats

    # ── Inicialización YOLO (motor primario WHICH) ────────────────────────────
    yolo_available = False
    yolo_states_cache: dict[int, dict] = {}
    detect_state_fn = None
    try:
        try:
            from .chess_detector import (
                detect_board_state, is_available, calibrate_yolo_offset,
                reset_yolo_offset, reset_square_beliefs, invalidate_grid_cache,
            )
        except ImportError:
            from chess_detector import (
                detect_board_state, is_available, calibrate_yolo_offset,
                reset_yolo_offset, reset_square_beliefs, invalidate_grid_cache,
            )
        if is_available():
            yolo_available = True
            detect_state_fn = detect_board_state
            invalidate_grid_cache()
            reset_yolo_offset()
            reset_square_beliefs()
            # Calibración multi-frame del offset YOLO.
            #
            # Antes: usábamos sólo el par (bootstrap_warped, bootstrap_orig).
            # Problema observado en test2: ese frame solo daba 8-10 piezas YOLO
            # (bajo contraste, oclusiones), produciendo offset rota dx=+105 px.
            # Ahora: probamos hasta CALIB_MAX_CANDIDATES pares cercanos al
            # bootstrap y elegimos el que YOLO detecte MÁS piezas. La intuición
            # es que un frame con más detecciones representa mejor la
            # distribución espacial real de las piezas, dando una mediana
            # robusta del offset.
            calib_candidates: list = []
            if bootstrap_warped is not None and bootstrap_orig is not None:
                calib_candidates.append(("bootstrap", bootstrap_warped, bootstrap_orig))
            if key_frames_orig is not None:
                CALIB_MAX_CANDIDATES = 5
                for ci in range(min(CALIB_MAX_CANDIDATES, len(key_frames))):
                    if ci < len(key_frames_orig) and key_frames_orig[ci] is not None:
                        calib_candidates.append(
                            (f"kf#{ci}", key_frames[ci], key_frames_orig[ci])
                        )

            best_label = None
            best_pair = None
            best_count = -1
            if calib_candidates and homography_M is not None:
                for label, warp_c, orig_c in calib_candidates:
                    try:
                        reset_yolo_offset()
                        state_test = detect_board_state(warp_c, orig_c, homography_M)
                        count = len(state_test) if state_test else 0
                    except Exception as e:
                        logger.debug("[WHICH/YOLO] candidato %s falló: %s", label, e)
                        count = 0
                    logger.debug("[WHICH/YOLO] candidato %s: %d piezas YOLO",
                                 label, count)
                    if count > best_count:
                        best_count = count
                        best_label = label
                        best_pair = (warp_c, orig_c)
                reset_yolo_offset()

            if best_pair is not None and homography_M is not None and best_count > 0:
                logger.info("[WHICH/YOLO] mejor candidato calibración: %s "
                            "(%d piezas)", best_label, best_count)
                try:
                    calibrate_yolo_offset(
                        best_pair[0], best_pair[1], homography_M, verbose=True,
                    )
                except Exception as e:
                    logger.warning("[WHICH/YOLO] calibración falló: %s", e)
            else:
                logger.warning("[WHICH/YOLO] no hay datos para calibrar offset "
                               "(candidatos=%d, M=%s) — proyección puede "
                               "salir desplazada.",
                               len(calib_candidates),
                               bool(homography_M is not None))
            logger.info("[WHICH/YOLO] motor YOLO ACTIVO. Comparación color+tipo "
                        "(símbolo FEN exacto).")
        else:
            logger.info("[WHICH/YOLO] modelo no disponible — sólo Jaccard.")
    except Exception as e:
        logger.warning("[WHICH/YOLO] error al inicializar: %s — sólo Jaccard.", e)

    # ── TTA + consenso para reducir ruido del modelo ────────────────────────
    # Generamos N variaciones determinísticas (brillo/contraste) del frame
    # original, hacemos inferencia YOLO sobre cada una y votamos por casilla.
    # El modelo es sensible a iluminación → cada variación da predicciones
    # ligeramente distintas; el voto retiene solo lo consistente. Resuelve
    # el caso típico que vimos en test9 kf #1, donde el modelo no detectó
    # claramente el cambio e2→e4 y los candidatos quedaron empatados a 0.878.
    YOLO_TTA_ENABLED = True
    YOLO_TTA_VOTE_RATIO = 0.4   # casilla aceptada si ≥ 40% inferencias coinciden
    # 5 variaciones: original + 4 perturbaciones suaves de brillo/contraste.
    YOLO_TTA_VARIANTS = [
        # (alpha=contraste, beta=brillo)
        (1.00, 0),     # frame tal cual
        (1.10, 8),     # más brillo+contraste suave
        (0.92, -8),    # menos brillo+contraste suave
        (1.00, 12),    # más brillo neutro
        (1.00, -12),   # menos brillo neutro
    ]

    def _yolo_tta_consensus(warped, orig):
        """Consenso por voto sobre N variaciones del frame original.

        Si `orig` es None, hacemos solo 1 inferencia (no hay nada que augmentar).
        """
        if orig is None or not YOLO_TTA_ENABLED:
            try:
                return detect_state_fn(warped, orig, homography_M)
            except Exception:
                return None

        votes: dict = {}
        valid = 0
        for alpha, beta in YOLO_TTA_VARIANTS:
            if alpha == 1.0 and beta == 0:
                orig_v = orig
            else:
                orig_v = cv2.convertScaleAbs(orig, alpha=alpha, beta=beta)
            try:
                state_v = detect_state_fn(warped, orig_v, homography_M)
            except Exception:
                state_v = None
            if not state_v:
                continue
            valid += 1
            for sq, sym in state_v.items():
                if sq not in votes:
                    votes[sq] = {}
                votes[sq][sym] = votes[sq].get(sym, 0) + 1

        if valid == 0:
            return None
        threshold = max(1, round(valid * YOLO_TTA_VOTE_RATIO))
        result: dict = {}
        for sq, sym_counts in votes.items():
            best_sym = max(sym_counts, key=sym_counts.__getitem__)
            if sym_counts[best_sym] >= threshold:
                result[sq] = best_sym
        return result if result else None

    def _yolo_state_for_kf(idx: int):
        """Inferencia YOLO con caché por índice de keyframe (TTA + consenso)."""
        if not yolo_available:
            return None
        if idx in yolo_states_cache:
            return yolo_states_cache[idx]
        if idx < 0 or idx >= len(key_frames):
            return None
        warped = key_frames[idx]
        orig = (key_frames_orig[idx]
                if (key_frames_orig is not None and idx < len(key_frames_orig))
                else None)
        try:
            state = _yolo_tta_consensus(warped, orig)
        except Exception as e:
            logger.warning("[WHICH/YOLO] inferencia kf #%d falló: %s", idx, e)
            state = None
        yolo_states_cache[idx] = state or {}
        return yolo_states_cache[idx]

    # noise_floor por celda: queda como parámetro opcional sin valor por defecto.
    # La discriminación de proyección se confía al filtro top-K dentro de
    # _match_move_by_jaccard / _try_multi_move_jaccard.
    noise_floor: dict | None = None

    # ── Constantes de la maquinaria multi-hipótesis ───────────────────────────
    # CASCADE_LOW_SCORE_THR: por debajo de este score (incluyendo SKIPs=0.0),
    #   un kf cuenta como "cascada potencial".
    # CASCADE_TRIGGER: nº de scores bajos consecutivos para activar multi.
    # K_HYPOTHESES: nº máximo de hipótesis vivas simultáneas. Coste lineal.
    # LEADER_DOMINANCE: ratio de avg score para colapsar cuando hay empate HQ.
    # LEADER_WINDOW: kfs consecutivos de liderazgo necesarios para colapsar.
    # RECOVERY_DEPTH_MULTI: en multi mantenemos el mismo depth que en lineal
    #   (extenderlo a 5 es la causa principal del coste exponencial — un BFS
    #   depth=5 sobre 30+ legal moves por hyp llamada por K hipótesis es lo
    #   que estaba causando el bloqueo de varios minutos).
    # CASCADE_MAX_KFS_IN_MULTI: timeout por kfs sin colapsar — fuerza ganador
    #   por precisión y vuelve a lineal. Garantía dura del coste superior.
    # CASCADE_MAX_TIME_SECONDS: timeout por tiempo absoluto en modo multi.
    # HQ_THR: score mínimo para contar como "movimiento de alta calidad" en
    #   la métrica de máxima precisión.
    CASCADE_LOW_SCORE_THR    = 0.40
    CASCADE_TRIGGER          = 3
    K_HYPOTHESES             = 3
    LEADER_DOMINANCE         = 1.3
    LEADER_WINDOW            = 2
    RECOVERY_DEPTH_MULTI     = recovery_depth
    CASCADE_MAX_KFS_IN_MULTI = 6
    CASCADE_MAX_TIME_SECONDS = 25.0
    HQ_THR                   = 0.50

    logger.info("[WHICH] Identificación iniciada — %d keyframes (incluyendo "
                "posición inicial), recovery_depth=%d, max_recovery_chain=%d, "
                "recovery_min_var_match=%.2f, K=%d, cascade_thr=%.2f, "
                "cascade_trigger=%d, hq_thr=%.2f, force_one_per_kf=%s",
                len(key_frames), recovery_depth, max_recovery_chain,
                recovery_min_var_match, K_HYPOTHESES,
                CASCADE_LOW_SCORE_THR, CASCADE_TRIGGER, HQ_THR,
                yolo_force_one_per_kf)

    initial_board_for_branching = (initial_board.copy()
                                    if initial_board is not None
                                    else chess.Board())

    main_hyp = Hypothesis(
        legal_board=initial_board_for_branching,
        label="H0",
        initial_warped=key_frames[0],
        initial_kf_idx=0,
    )
    hypotheses: list = [main_hyp]
    mode = "linear"
    cascade_events = 0
    leader_collapses = 0
    timeout_collapses = 0
    multi_entry_kf: int | None = None
    multi_entry_time: float | None = None

    def _emit(result: 'MatcherResult') -> None:
        if not result.log_msg:
            return
        if result.log_level == 'info':
            logger.info(result.log_msg)
        elif result.log_level == 'warning':
            logger.warning(result.log_msg)
        else:
            logger.debug(result.log_msg)

    for i in range(1, len(key_frames)):
        cur = key_frames[i]
        prev = key_frames[i - 1]
        yolo_state_after = _yolo_state_for_kf(i) if yolo_available else None
        yolo_state_before = _yolo_state_for_kf(i - 1) if yolo_available else None
        # Estado YOLO del kf siguiente (lookahead) si existe.
        yolo_state_next = (_yolo_state_for_kf(i + 1)
                           if (yolo_available and (i + 1) < len(key_frames))
                           else None)

        if mode == "linear":
            hyp = hypotheses[0]
            result = _run_kf_matchers(
                hyp, kf_idx=i, kf_cur_warped=cur, kf_prev_warped=prev,
                yolo_state_before=yolo_state_before,
                yolo_state_after=yolo_state_after,
                yolo_available=yolo_available,
                allow_forced=yolo_force_one_per_kf,
                allow_recovery=True,
                recovery_depth=recovery_depth,
                max_recovery_chain=max_recovery_chain,
                recovery_min_var_match=recovery_min_var_match,
                noise_floor=noise_floor,
                yolo_state_next=yolo_state_next,
            )
            _emit(result)

            hyp.apply(result, kf_idx=i, kf_warped=cur, hq_thr=HQ_THR)

            # Detección de cascada: si los últimos N scores son bajos y existen
            # alternativas razonables del último accept, ramificamos.
            # Gateado por `enable_cascade_recovery`: en logs reales el branching
            # no diverge (las K hipótesis convergen al mismo HQ count) y los
            # falsos positivos generan spam con `sin alternativas válidas`,
            # disparando el detector en cada kf consecutivo. Mantenemos la
            # maquinaria pero por defecto desactivada hasta tener un mejor
            # criterio de divergencia.
            if (enable_cascade_recovery
                    and yolo_available
                    and hyp.low_streak(CASCADE_LOW_SCORE_THR) >= CASCADE_TRIGGER
                    and len(hyp.state_alts_at_last_accept) >= 2
                    and hyp.last_accepted_kf_idx > 0):
                logger.warning("[WHICH/CASCADE] kf #%d: %d kfs consecutivos con "
                               "score < %.2f → ramificando (último accept en "
                               "kf #%d, hipótesis %s)",
                               i, hyp.low_streak(CASCADE_LOW_SCORE_THR),
                               CASCADE_LOW_SCORE_THR,
                               hyp.last_accepted_kf_idx, hyp.label)
                cascade_events += 1
                hypotheses = _spawn_alternatives_from_history(
                    hyp, initial_board_for_branching, key_frames,
                    _yolo_state_for_kf, current_kf_idx=i + 1,
                    K=K_HYPOTHESES,
                    yolo_available=yolo_available,
                    recovery_depth=RECOVERY_DEPTH_MULTI,
                    max_recovery_chain=max_recovery_chain,
                    recovery_min_var_match=recovery_min_var_match,
                )
                if len(hypotheses) > 1:
                    mode = "multi"
                    multi_entry_kf = i
                    multi_entry_time = time.time()
                    logger.info("[WHICH/CASCADE] kf #%d: %d hipótesis activas "
                                "tras ramificación: %s",
                                i, len(hypotheses),
                                [h.label for h in hypotheses])
                else:
                    # Spawn no encontró alternativas viables. Reseteamos la
                    # ventana de scores para no re-disparar la cascada en cada
                    # kf consecutivo (causa de los "18 eventos sin alternativas
                    # válidas" en test2).
                    hyp.recent_scores.clear()
                    logger.info("[WHICH/CASCADE] kf #%d: sin alternativas "
                                "válidas, continúo en modo lineal.", i)
        else:
            # ── Timeout duro (kfs / tiempo): si llevamos demasiado en multi
            # sin que ninguna hipótesis se imponga, forzamos colapso al
            # ganador por precisión y volvemos a lineal. Sin esto el modo
            # multi puede consumir minutos en partidas con cascadas largas.
            kfs_in_multi = (i - multi_entry_kf) if multi_entry_kf is not None else 0
            elapsed_in_multi = (time.time() - multi_entry_time) if multi_entry_time else 0.0
            if (kfs_in_multi >= CASCADE_MAX_KFS_IN_MULTI
                    or elapsed_in_multi >= CASCADE_MAX_TIME_SECONDS):
                forced_winner = _select_winner_by_precision(hypotheses)
                pm = forced_winner.precision_metric()
                logger.warning("[WHICH/CASCADE] kf #%d: TIMEOUT (kfs=%d/%d, "
                               "tiempo=%.1fs/%.1fs) → forzando ganador %s "
                               "(HQ=%d, avg=%.3f) y volviendo a lineal.",
                               i, kfs_in_multi, CASCADE_MAX_KFS_IN_MULTI,
                               elapsed_in_multi, CASCADE_MAX_TIME_SECONDS,
                               forced_winner.label, pm[0], pm[1])
                timeout_collapses += 1
                forced_winner.leader_streak = 0
                # Limpiar la ventana de scores para evitar disparar otra
                # cascada inmediatamente con la cola de scores bajos heredada.
                forced_winner.recent_scores.clear()
                hypotheses = [forced_winner]
                mode = "linear"
                multi_entry_kf = None
                multi_entry_time = None
                # Reprocesamos este kf en lineal
                hyp = hypotheses[0]
                result = _run_kf_matchers(
                    hyp, kf_idx=i, kf_cur_warped=cur, kf_prev_warped=prev,
                    yolo_state_before=yolo_state_before,
                    yolo_state_after=yolo_state_after,
                    yolo_available=yolo_available,
                    allow_forced=yolo_force_one_per_kf,
                    allow_recovery=True,
                    recovery_depth=recovery_depth,
                    max_recovery_chain=max_recovery_chain,
                    recovery_min_var_match=recovery_min_var_match,
                    noise_floor=noise_floor,
                    yolo_state_next=yolo_state_next,
                )
                _emit(result)
                hyp.apply(result, kf_idx=i, kf_warped=cur, hq_thr=HQ_THR)
                continue

            # Modo multi: cada hipótesis evalúa el mismo kf con su propio
            # legal_board. Tras aplicar resultados, se podan a top-K y se
            # comprueba si hay un líder claro para colapsar a lineal.
            for hyp in hypotheses:
                result = _run_kf_matchers(
                    hyp, kf_idx=i, kf_cur_warped=cur, kf_prev_warped=prev,
                    yolo_state_before=yolo_state_before,
                    yolo_state_after=yolo_state_after,
                    yolo_available=yolo_available,
                    allow_forced=False,  # forced desactivado en multi
                    allow_recovery=True,
                    recovery_depth=RECOVERY_DEPTH_MULTI,
                    max_recovery_chain=max_recovery_chain,
                    recovery_min_var_match=recovery_min_var_match,
                    noise_floor=noise_floor,
                    yolo_state_next=yolo_state_next,
                )
                _emit(result)
                hyp.apply(result, kf_idx=i, kf_warped=cur, hq_thr=HQ_THR)

            # Pruning: ordenamos por (HQ count, avg score, n_movs) desc y
            # mantenemos las K mejores.
            hypotheses.sort(key=lambda h: h.precision_metric(), reverse=True)
            hypotheses = hypotheses[:K_HYPOTHESES]

            # Detección de líder dominante (criterio de colapso a lineal):
            #   - HQ count del líder ≥ HQ count del segundo + 1, O
            #   - HQ count empatado y avg score del líder ≥ LEADER_DOMINANCE ×
            #     avg score del segundo.
            if len(hypotheses) >= 2:
                lead = hypotheses[0]
                second = hypotheses[1]
                pm_lead = lead.precision_metric()
                pm_second = second.precision_metric()
                hq_lead, avg_lead = pm_lead[0], pm_lead[1]
                hq_second, avg_second = pm_second[0], pm_second[1]
                avg_second_pos = max(0.001, avg_second)
                dominates = (hq_lead >= hq_second + 1
                             or (hq_lead == hq_second
                                 and avg_lead >= LEADER_DOMINANCE * avg_second_pos))
                if dominates:
                    lead.leader_streak += 1
                else:
                    lead.leader_streak = 0
                if lead.leader_streak >= LEADER_WINDOW:
                    logger.info("[WHICH/CASCADE] kf #%d: hipótesis %s domina "
                                "por %d kfs consecutivos (HQ=%d vs %d, "
                                "avg=%.3f vs %.3f) → colapsando a lineal.",
                                i, lead.label, lead.leader_streak,
                                hq_lead, hq_second, avg_lead, avg_second)
                    leader_collapses += 1
                    hypotheses = [lead]
                    mode = "linear"
                    lead.leader_streak = 0
                    multi_entry_kf = None
                    multi_entry_time = None
            elif len(hypotheses) == 1:
                hypotheses[0].leader_streak = 0
                mode = "linear"
                multi_entry_kf = None
                multi_entry_time = None

    # ── Selección final por máxima precisión ─────────────────────────────────
    winner = _select_winner_by_precision(hypotheses)
    if winner is None:
        winner = main_hyp

    if cascade_events > 0 or len(hypotheses) > 1:
        logger.info("[WHICH/CASCADE] resumen: %d eventos de cascada, "
                    "%d colapsos a líder, %d colapsos por timeout, "
                    "%d hipótesis vivas al final",
                    cascade_events, leader_collapses, timeout_collapses,
                    len(hypotheses))
        for h in hypotheses:
            pm = h.precision_metric()
            logger.info("[WHICH/CASCADE]   %s: HQ=%d, avg=%.3f, n_movs=%d, "
                        "skipped=%d, branched_at_kf=%s",
                        h.label, pm[0], pm[1], pm[2],
                        h.stats.get('skipped', 0),
                        str(h.branched_at_kf) if h.branched_at_kf else "—")
        logger.info("[WHICH/CASCADE] ganadora: %s (HQ=%d, avg=%.3f, n_movs=%d)",
                    winner.label, winner.precision_metric()[0],
                    winner.precision_metric()[1], len(winner.moves))

    moves = list(winner.moves)
    skipped_indices = list(winner.skipped_indices)
    stats = dict(winner.stats)
    stats['cascade_events']    = cascade_events
    stats['leader_collapses']  = leader_collapses
    stats['timeout_collapses'] = timeout_collapses
    stats['final_hypotheses']  = len(hypotheses)
    stats['winner_label']      = winner.label

    logger.info("[WHICH] Identificación completada — total movs=%d, "
                "yolo_single=%d, yolo_double=%d, yolo_forced=%d, "
                "single=%d, multi=%d, recovery=%d, phantoms=%d, skipped=%d, "
                "max_chain=%d, cascade_events=%d, ganadora=%s",
                len(moves),
                stats.get('yolo_single', 0), stats.get('yolo_double', 0),
                stats.get('yolo_forced', 0), stats.get('single', 0),
                stats.get('multi', 0), stats.get('recovery', 0),
                stats.get('phantom', 0), stats.get('skipped', 0),
                stats.get('max_skipped_chain', 0),
                cascade_events, winner.label)

    return moves, skipped_indices, stats


def extract_key_frames(video_path, coords, progress_key=None):
    """
    Wrapper público que delega en `_extract_key_frames_occupancy`
    (pipeline ocupación/Jaccard sin YOLO).

    Retorna (key_frames, key_frames_orig, detected_states, mat, accepted_moves,
             key_frame_indices, bootstrap_warped, bootstrap_orig).

    Nota: con WHEN_ONLY_MODE=True (modo por defecto), accepted_moves vendrá
    vacío y detected_states contendrá dicts vacíos. Sólo se garantiza que
    key_frames, key_frames_orig y key_frame_indices estén poblados con un
    elemento por evento detectado.

    bootstrap_warped: frame warpeado capturado por la fase de bootstrap (primer
    frame estable + sharpness selection). Es la referencia que la fase WHEN usa
    para comparar contra el primer evento. Pásalo a la fase WHICH como
    `which_input[0]` para que ambas fases usen la MISMA referencia visual.
    Puede ser None si el vídeo no tuvo frames estables suficientes para hacer
    bootstrap (caso patológico).
    """
    logger.info("[TRIGGER] Usando pipeline de ocupación/Jaccard (sin YOLO en detección de movimientos)")
    return _extract_key_frames_occupancy(video_path, coords, progress_key)


# -----------------------------------------
# Utilidad de debug: guardado de imágenes de diagnóstico
# -----------------------------------------

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


# -----------------------------------------
# Calibración manual de esquinas del tablero
# -----------------------------------------

def save_corners_config(corners_rel):
    """
    Guarda las 4 esquinas del tablero como coordenadas relativas [0-1] en CORNERS_CONFIG_PATH.
    corners_rel: lista de 4 pares [[rx0,ry0], [rx1,ry1], [rx2,ry2], [rx3,ry3]]
    Orden: [TL=a1, TR=a8, BR=h8, BL=h1] (orientación lateral estándar).
    """
    data = {'corners_rel': [[float(x), float(y)] for x, y in corners_rel]}
    with open(CORNERS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f)
    logger.info("[CORNERS] Calibración guardada: %s", data['corners_rel'])


def load_corners_config(image_size):
    """
    Carga las esquinas guardadas y las escala al tamaño de imagen dado.
    image_size: (width, height) del frame de vídeo.
    Devuelve np.float32 con 4 esquinas en píxeles, o None si no hay config.
    """
    if not os.path.exists(CORNERS_CONFIG_PATH):
        return None
    try:
        with open(CORNERS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            data = json.load(f)
        corners_rel = data.get('corners_rel')
        if not corners_rel or len(corners_rel) != 4:
            return None
        w, h = image_size
        corners = np.float32([[rx * w, ry * h] for rx, ry in corners_rel])
        logger.info("[CORNERS] Calibración cargada: %s", corners.tolist())
        return corners
    except Exception as e:
        logger.error("[CORNERS] Error cargando calibración: %s", e)
        return None


# -----------------------------------------
# Detección automática de esquinas del tablero
# -----------------------------------------

def order_corners(corners):
    """Ordena 4 esquinas detectadas en orden [TL, TR, BR, BL]."""
    s    = corners.sum(axis=1)            # TL: min(x+y),  BR: max(x+y)
    diff = corners[:, 0] - corners[:, 1]  # TR: max(x-y),  BL: min(x-y)
    ordered = np.zeros((4, 2), dtype=np.float32)
    ordered[0] = corners[np.argmin(s)]
    ordered[1] = corners[np.argmax(diff)]
    ordered[2] = corners[np.argmax(s)]
    ordered[3] = corners[np.argmin(diff)]
    return ordered


def auto_detect_board_corners(frame):
    """
    Detecta automáticamente las 4 esquinas exteriores del tablero de ajedrez.
    Devuelve float32 en orden [TL, TR, BR, BL] compatible con get_matriz().

    POSICIÓN ESTÁNDAR DE GRABACIÓN (obligatoria para el mapeo correcto):
      - Cámara elevada desde el LADO DEL REY (columna h), mirando hacia la columna a.
      - Blancas a la IZQUIERDA de la imagen, negras a la DERECHA.
      - El tablero debe ser visible en su totalidad.
      TL=a1  TR=a8  BR=h8  BL=h1

    Estrategias en orden de prioridad:
      0. Calibración manual guardada (corners_config.json) — siempre tiene prioridad
      1. findChessboardCorners (casillas vacías visibles)
      2. Líneas de Hough (detecta la cuadrícula)
      3. Canny + contorno convexo con CLAHE
      4. Umbral adaptativo + contorno con CLAHE
      5. Fallback: recorte central al 80%
    """
    h, w   = frame.shape[:2]
    gray   = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    kernel = np.ones((5, 5), np.uint8)

    def _is_fullframe_corner(corners_result, max_coverage=0.88):
        """
        Devuelve True si las esquinas cubren más del max_coverage del frame.
        Indica que el algoritmo encontró los bordes del vídeo en vez del tablero.
        Un tablero de ajedrez filmado en encuadre lateral nunca ocupa >85% del frame.
        """
        xs = [float(p[0]) for p in corners_result]
        ys = [float(p[1]) for p in corners_result]
        coverage_x = (max(xs) - min(xs)) / w
        coverage_y = (max(ys) - min(ys)) / h
        return coverage_x > max_coverage or coverage_y > max_coverage

    def _save_corner_debug(corners_result, label):
        """Dibuja las esquinas sobre el frame original y lo guarda en media/debug/."""
        vis = frame.copy()
        pts = corners_result.astype(int)
        labels_pos = ['TL(a1)', 'TR(a8)', 'BR(h8)', 'BL(h1)']
        colors     = [(0,255,0),(0,165,255),(0,0,255),(255,0,0)]
        for pt, lbl, col in zip(pts, labels_pos, colors):
            cv2.circle(vis, tuple(pt), 12, col, -1)
            cv2.putText(vis, lbl, (pt[0]+14, pt[1]-8),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, col, 2)
        # Cuadrilátero
        cv2.polylines(vis, [pts.reshape(-1,1,2)], True, (255,255,0), 3)
        cv2.putText(vis, label, (10,30), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (255,255,0), 2)
        save_debug_image("corners_detected", vis)

    # --- Prioridad 0: Calibración manual guardada ---
    stored = load_corners_config((w, h))
    if stored is not None:
        logger.info("[CORNERS] Usando calibración manual guardada")
        _save_corner_debug(stored, "calibracion manual")
        return stored

    # --- Estrategia 1: findChessboardCorners ---
    # Funciona bien cuando al menos las casillas centrales del tablero son visibles.
    small  = cv2.resize(gray, (640, 480))
    sh, sw = small.shape[:2]
    for pat in [(7, 7), (6, 6), (5, 5)]:
        flags = (cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
                 | cv2.CALIB_CB_FAST_CHECK)
        ret, pts = cv2.findChessboardCorners(small, pat, flags)
        if ret:
            pts = pts.reshape(pat[1], pat[0], 2) * np.float32([w / sw, h / sh])
            nr, nc = pat[1], pat[0]
            dx = (pts[0, -1] - pts[0, 0]) / (nc - 1)
            dy = (pts[-1, 0] - pts[0, 0]) / (nr - 1)
            tl = np.clip(pts[0,  0] - dx - dy, [0, 0], [w - 1, h - 1])
            tr = np.clip(pts[0, -1] + dx - dy, [0, 0], [w - 1, h - 1])
            br = np.clip(pts[-1,-1] + dx + dy, [0, 0], [w - 1, h - 1])
            bl = np.clip(pts[-1, 0] - dx + dy, [0, 0], [w - 1, h - 1])
            result = np.float32([tl, tr, br, bl])
            logger.info("[CORNERS] Detectado con findChessboardCorners %s", pat)
            _save_corner_debug(result, f"findChessboardCorners {pat}")
            return result

    # Aplicar CLAHE para mejorar el contraste antes de las estrategias de borde
    clahe    = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # --- Estrategia 1: Líneas de Hough ---
    # Detecta las líneas horizontales y verticales de la cuadrícula del tablero.
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 0)
    edges   = cv2.Canny(blurred, 20, 80)
    min_votes = int(min(h, w) * 0.25)
    lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=min_votes)
    if lines is not None:
        h_ys, v_xs = [], []
        for line in lines:
            rho, theta = line[0]
            cos_t, sin_t = np.cos(theta), np.sin(theta)
            if abs(sin_t) < 0.25 and abs(cos_t) > 1e-3:     # línea casi vertical
                v_xs.append(rho / cos_t)
            elif abs(cos_t) < 0.25 and abs(sin_t) > 1e-3:   # línea casi horizontal
                h_ys.append(rho / sin_t)
        if len(h_ys) >= 2 and len(v_xs) >= 2:
            top, bottom = min(h_ys), max(h_ys)
            left, right = min(v_xs), max(v_xs)
            if (bottom - top) > h * 0.3 and (right - left) > w * 0.3:
                left   = max(0.0, left);  right  = min(float(w - 1), right)
                top    = max(0.0, top);   bottom = min(float(h - 1), bottom)
                result = np.float32([[left, top], [right, top],
                                     [right, bottom], [left, bottom]])
                if _is_fullframe_corner(result):
                    logger.warning("[CORNERS] Hough detectó el frame completo — descartado")
                else:
                    logger.info("[CORNERS] Detectado con líneas de Hough")
                    _save_corner_debug(result, "Hough lines")
                    return result

    # --- Estrategia 2 y 3: Canny/umbral adaptativo + contorno ---
    min_area = h * w * 0.05

    def find_quad(binary):
        cnts, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in sorted(cnts, key=cv2.contourArea, reverse=True)[:15]:
            if cv2.contourArea(c) < min_area:
                break
            # Intentar approxPolyDP directamente
            peri = cv2.arcLength(c, True)
            for eps in (0.01, 0.02, 0.03, 0.05, 0.08):
                approx = cv2.approxPolyDP(c, eps * peri, True)
                if len(approx) == 4:
                    return np.float32([p[0] for p in approx])
            # Fallback: casco convexo del contorno
            hull = cv2.convexHull(c)
            peri = cv2.arcLength(hull, True)
            for eps in (0.02, 0.05, 0.10):
                approx = cv2.approxPolyDP(hull, eps * peri, True)
                if len(approx) == 4:
                    return np.float32([p[0] for p in approx])
        return None

    # Estrategia 2: Canny + dilatación con CLAHE
    edges2 = cv2.Canny(cv2.GaussianBlur(enhanced, (7, 7), 0), 20, 80)
    edges2 = cv2.dilate(edges2, kernel, iterations=2)
    result = find_quad(edges2)
    if result is not None:
        result = order_corners(result)
        if _is_fullframe_corner(result):
            logger.warning("[CORNERS] Canny detectó el frame completo — descartado")
            result = None
        else:
            logger.info("[CORNERS] Detectado con Canny + contorno")
            _save_corner_debug(result, "Canny contour")
            return result

    # Estrategia 3: Umbral adaptativo con CLAHE
    thresh = cv2.adaptiveThreshold(cv2.GaussianBlur(enhanced, (11, 11), 0), 255,
                                   cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                   cv2.THRESH_BINARY_INV, 11, 2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
    result = find_quad(thresh)
    if result is not None:
        result = order_corners(result)
        if _is_fullframe_corner(result):
            logger.warning("[CORNERS] Umbral adaptativo detectó el frame completo — descartado")
        else:
            logger.info("[CORNERS] Detectado con umbral adaptativo")
            _save_corner_debug(result, "adaptive threshold")
            return result

    # Fallback: recorte central del 80% (margen 10% por lado)
    logger.warning("[CORNERS] Auto-detección falló — CALIBRACIÓN MANUAL NECESARIA.\n"
                   "          Ejecuta de nuevo y responde 's' para marcar las 4 esquinas del tablero.")
    mx, my = w * 0.10, h * 0.10
    result = np.float32([[mx, my], [w - mx, my], [w - mx, h - my], [mx, h - my]])
    _save_corner_debug(result, "FALLBACK 80% crop")
    return result


def get_first_frame(video_path):
    """Lee y devuelve el primer frame del video sin mantenerlo abierto."""
    cap = open_video(video_path)
    if isinstance(cap, dict):
        return None
    ret, frame = cap.read()
    cap.release()
    return frame if ret else None


def refine_warp_with_grid(warped):
    """
    Aplica una corrección secundaria al tablero ya transformado por perspectiva.

    Estrategia:
      - Detecta las líneas de la cuadrícula del tablero en la imagen warpeada
        usando la transformada de Hough.
      - A partir de las líneas horizontales y verticales más dominantes, estima
        la posición real de cada borde de celda.
      - Si la cuadrícula detectada difiere más de 30 px del ideal (celdas iguales),
        aplica una segunda homografía para corregir la distorsión residual.

    Devuelve la imagen corregida (o la original si la detección falla).
    """
    try:
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 30, 90)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=80)
        if lines is None or len(lines) < 6:
            return warped

        h_lines, v_lines = [], []
        for line in lines[:60]:
            rho, theta = line[0]
            if abs(theta) < 0.2 or abs(theta - np.pi) < 0.2:       # casi vertical
                v_lines.append(abs(rho))
            elif abs(theta - np.pi / 2) < 0.2:                      # casi horizontal
                h_lines.append(abs(rho))

        h_lines = sorted(set(round(x / 20) * 20 for x in h_lines))
        v_lines = sorted(set(round(x / 20) * 20 for x in v_lines))

        # Necesitamos al menos las 4 líneas exteriores del tablero en cada eje
        if len(h_lines) < 2 or len(v_lines) < 2:
            return warped

        # Esquinas detectadas del tablero en la imagen warpeada
        x0, x1 = v_lines[0], v_lines[-1]
        y0, y1 = h_lines[0], h_lines[-1]

        # Si la desviación del borde ideal es menor de 30 px, no es necesario corregir
        if (abs(x0) < 30 and abs(x1 - (NORMALIZED_SIZE - 1)) < 30 and
                abs(y0) < 30 and abs(y1 - (NORMALIZED_SIZE - 1)) < 30):
            return warped

        N = float(NORMALIZED_SIZE - 1)
        src = np.float32([[x0, y0], [x1, y0], [x1, y1], [x0, y1]])
        dst = np.float32([[0, 0], [N, 0], [N, N], [0, N]])
        refine_mat = cv2.getPerspectiveTransform(src, dst)
        refined = cv2.warpPerspective(warped, refine_mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        logger.info("[WARP] Corrección secundaria aplicada: bordes detectados x=[%.0f,%.0f] y=[%.0f,%.0f]",
                    x0, x1, y0, y1)
        return refined

    except Exception as e:
        logger.warning("[WARP] refine_warp_with_grid falló: %s", e)
        return warped


def get_warped_frame_preview(video_path, corners_rel):
    """Devuelve el primer frame warpeado con las esquinas relativas dadas (para previsualización)."""
    frame = get_first_frame(video_path)
    if frame is None:
        return None
    h, w = frame.shape[:2]
    corners = np.float32([[rx * w, ry * h] for rx, ry in corners_rel])
    mat = get_matriz(corners)
    return cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))


def get_initial_board_frame(video_path, corners):
    """
    Obtiene el primer frame del video con la transformación de perspectiva aplicada
    (mismo proceso que los frames clave). Guarda el resultado en media/debug/warped_initial.jpg.
    """
    frame = get_first_frame(video_path)
    if frame is None:
        return None
    mat    = get_matriz(corners)
    warped = cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))

    # Debug: dibujar la cuadrícula de las 64 celdas sobre el frame transformado
    grid_vis = warped.copy()
    cs = NORMALIZED_SIZE // 8
    for i in range(9):
        cv2.line(grid_vis, (i * cs, 0), (i * cs, NORMALIZED_SIZE), (0, 255, 0), 1)
        cv2.line(grid_vis, (0, i * cs), (NORMALIZED_SIZE, i * cs), (0, 255, 0), 1)
    # Etiquetar esquinas
    corner_labels = {(0, 0): 'a1', (cs*7, 0): 'a8', (0, cs*7): 'h1', (cs*7, cs*7): 'h8'}
    for (cx, cy), lbl in corner_labels.items():
        cv2.putText(grid_vis, lbl, (cx + 4, cy + 20),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2)
    save_debug_image("warped_initial", grid_vis)

    return warped


# -----------------------------------------
# Comparación de celdas del tablero para detección de movimientos
# -----------------------------------------

def get_board_cells(board_image, roi_top=CELL_ROI_TOP, roi_bottom=CELL_ROI_BOTTOM):
    """
    Divide la imagen del tablero (NORMALIZED_SIZE × NORMALIZED_SIZE) en 64 celdas 8×8.

    Aplica un recorte vertical (roi_top, roi_bottom) dentro de cada celda para
    ignorar la zona donde las cimas de piezas altas sangran desde filas adyacentes
    debido a la perspectiva residual tras el warp. Sólo se analiza la franja
    [roi_top·cs, roi_bottom·cs] de cada celda, que corresponde a la base de la pieza.
    """
    cs  = NORMALIZED_SIZE // 8
    t   = int(cs * roi_top)
    b   = int(cs * roi_bottom)
    return [board_image[r*cs + t : r*cs + b, c*cs:(c+1)*cs] for r in range(8) for c in range(8)]


def get_changed_cells(frame_before, frame_after, threshold=CELL_CHANGE_THRESHOLD):
    """
    Compara las 64 celdas entre dos frames y devuelve los índices de las
    celdas que cambiaron significativamente, ordenados por magnitud (mayor primero).

    Mejoras respecto a la versión anterior:
    - Cada celda se normaliza por su brillo medio antes de comparar (elimina efecto
      de cambios globales de iluminación que afectan a todas las celdas igual).
    - Se resta la mediana de los diffs de todas las celdas (compensación de modo común):
      si la luz cambia uniformemente, el diff de todas las celdas sube en la misma cantidad
      y la mediana lo absorbe; sólo las celdas con movimiento real destacan por encima.
    - Se limita a 6 resultados (en un movimiento normal se tocan 2 celdas; en enroque, 4).
    """
    def to_gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    cells_b = get_board_cells(to_gray(frame_before))
    cells_a = get_board_cells(to_gray(frame_after))

    raw_diffs = []
    for cb, ca in zip(cells_b, cells_a):
        cb_f = cb.astype(np.float32)
        ca_f = ca.astype(np.float32)
        # Normalizar por brillo medio de cada celda (independiente de iluminación global)
        diff = float(np.mean(np.abs(
            (ca_f - np.mean(ca_f)) - (cb_f - np.mean(cb_f))
        )))
        raw_diffs.append(diff)

    # Compensar variación común de iluminación restando la mediana de todas las celdas
    median_diff = float(np.median(raw_diffs))
    changes = []
    for i, d in enumerate(raw_diffs):
        residual = d - median_diff
        if residual > threshold:
            changes.append((i, residual))

    changes.sort(key=lambda x: x[1], reverse=True)
    return [idx for idx, _ in changes[:6]]


def classify_cells_occupation(frame_before, frame_after, changed_indices):
    """
    Para cada índice de celda cambiada, clasifica si la celda ganó (+1) o perdió (-1)
    una pieza, midiendo la densidad de bordes (las piezas 3D generan más bordes que
    una celda vacía de tablero).

    Retorna un dict {cell_index: +1 | -1 | 0}.
    """
    def to_gray(img):
        return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if len(img.shape) == 3 else img

    def edge_density(cell):
        return float(np.mean(cv2.Canny(cell, 30, 100)))

    cells_b = get_board_cells(to_gray(frame_before))
    cells_a = get_board_cells(to_gray(frame_after))

    result = {}
    for idx in changed_indices:
        ed_b = edge_density(cells_b[idx])
        ed_a = edge_density(cells_a[idx])
        delta = ed_a - ed_b
        if delta > 4:       # más bordes → pieza llegó
            result[idx] = +1
        elif delta < -4:    # menos bordes → pieza salió
            result[idx] = -1
        else:
            result[idx] = 0
    return result


def cell_index_to_square(cell_index):
    """
    Convierte índice de celda (0–63, fila a fila desde arriba-izquierda)
    en casilla de python-chess para la orientación LATERAL estándar de grabación:

        Posición de cámara:
          - Cámara elevada desde el lado del rey (columna h), mirando hacia la columna a.
          - Blancas a la IZQUIERDA, negras a la DERECHA en la imagen.
          - Columna h cerca de la cámara → fila inferior de la imagen (fila 7).
          - Columna a lejos de la cámara → fila superior de la imagen (fila 0).

        Mapeo en la imagen normalizada (1000×1000):
          Fila (i//8): 0=columna a, 7=columna h  →  archivo de ajedrez = i//8
          Col  (i%8):  0=rango 1,  7=rango 8     →  rango de ajedrez  = i%8

          cell  0 (fila 0, col 0) = a1  →  chess.A1  ✓
          cell  7 (fila 0, col 7) = a8  →  chess.A8  ✓
          cell 56 (fila 7, col 0) = h1  →  chess.H1  ✓
          cell 63 (fila 7, col 7) = h8  →  chess.H8  ✓
    """
    return chess.square(cell_index // 8, cell_index % 8)


def detect_move_from_squares(board, changed_squares,
                              frame_before=None, frame_after=None, changed_indices=None):
    """
    Dado el estado del tablero y las casillas que cambiaron, devuelve el
    movimiento legal que mejor explica los cambios.

    Estrategia en dos niveles:
      1. Clasificación origen/destino: si se puede identificar qué celda perdió
         una pieza (fuente) y cuál la recibió (destino), se busca directamente
         el movimiento legal from_square→to_square.  Mucho más preciso que sólo
         contar solapamiento.
      2. Máximo solapamiento (fallback): si la clasificación no es concluyente,
         se usa el método original de máxima intersección.
    """
    changed_set = set(changed_squares)
    castling_extras = {
        chess.G1: {chess.H1, chess.F1},
        chess.C1: {chess.A1, chess.D1},
        chess.G8: {chess.H8, chess.F8},
        chess.C8: {chess.A8, chess.D8},
    }

    # ── Nivel 1: clasificación origen / destino ──────────────────────────────
    if frame_before is not None and frame_after is not None and changed_indices is not None:
        classification = classify_cells_occupation(frame_before, frame_after, changed_indices)
        sources = {cell_index_to_square(i) for i, c in classification.items() if c == -1}
        dests   = {cell_index_to_square(i) for i, c in classification.items() if c == +1}

        if sources and dests:
            logger.debug("[FEN]   Clasificación → fuentes=%s destinos=%s",
                         [chess.square_name(s) for s in sources], [chess.square_name(d) for d in dests])
            # Buscar movimiento legal que encaje exactamente
            for move in board.legal_moves:
                if move.from_square in sources and move.to_square in dests:
                    return move
            # Enroque: el rey puede no clasificarse correctamente por la torre
            for move in board.legal_moves:
                if board.is_castling(move):
                    involved = {move.from_square, move.to_square} | castling_extras.get(move.to_square, set())
                    if len(involved & changed_set) >= 3:
                        return move

    # ── Nivel 2: fallback por máximo solapamiento ────────────────────────────
    best_move, best_overlap = None, 0
    for move in board.legal_moves:
        involved = {move.from_square, move.to_square}
        if board.is_castling(move):
            involved |= castling_extras.get(move.to_square, set())
        overlap = len(involved & changed_set)
        if overlap > best_overlap:
            best_overlap, best_move = overlap, move

    return best_move if best_overlap >= 2 else None


# -----------------------------------------
# Generación y persistencia de FENs
# -----------------------------------------

def detect_two_moves(board, changed_squares):
    """
    Cuando se detectan demasiadas celdas cambiadas para ser un único movimiento
    (>4 celdas), intenta encontrar dos movimientos legales consecutivos que juntos
    expliquen los cambios observados.

    Estrategia:
      - Para cada movimiento legal posible como primer movimiento (move1),
        comprueba cuántas de las celdas cambiadas cubre.
      - Aplica move1 temporalmente y busca move2 que cubra el resto.
      - Devuelve (move1, move2) si la cobertura combinada es suficiente, o None.

    Complejidad: O(legal_moves²) ≈ 40×40 = 1600 iteraciones máx. → rápido.
    """
    changed_set = set(changed_squares)
    if len(changed_set) < 3:
        return None

    castling_extras = {
        chess.G1: {chess.H1, chess.F1},
        chess.C1: {chess.A1, chess.D1},
        chess.G8: {chess.H8, chess.F8},
        chess.C8: {chess.A8, chess.D8},
    }

    for move1 in list(board.legal_moves):
        inv1 = {move1.from_square, move1.to_square}
        if board.is_castling(move1):
            inv1 |= castling_extras.get(move1.to_square, set())
        if not (inv1 & changed_set):
            continue                          # move1 no toca ninguna celda cambiada

        board.push(move1)
        for move2 in list(board.legal_moves):
            inv2 = {move2.from_square, move2.to_square}
            if board.is_castling(move2):
                inv2 |= castling_extras.get(move2.to_square, set())
            combined = inv1 | inv2
            # Aceptar si la unión cubre al menos len-1 celdas cambiadas
            if len(combined & changed_set) >= max(3, len(changed_set) - 1):
                board.pop()
                return move1, move2
        board.pop()

    return None


def frames_to_fens(all_frames, initial_fen=None, progress_key=None):
    """
    Convierte una secuencia de frames del tablero en una lista de FENs.
      all_frames[0]  → posición inicial (antes de cualquier movimiento)
      all_frames[i]  → posición después del movimiento i

    La lógica NO necesita reconocer las piezas visualmente: sólo detecta
    qué casillas cambiaron entre frames consecutivos y busca el movimiento
    legal de python-chess que mejor explica ese cambio.

    Retorna lista de FENs con len(all_frames) elementos.
    """
    if initial_fen is None:
        initial_fen = chess.STARTING_FEN

    board          = chess.Board(initial_fen)
    fens           = [initial_fen]
    consecutive_failures = 0          # Fallos consecutivos sin detectar movimiento
    MAX_FAILURES   = 5                # Tras este nº de fallos seguidos se imprime aviso

    # Limpiar imágenes de debug de ejecuciones anteriores
    if os.path.isdir(DEBUG_LOCATION):
        for f in os.listdir(DEBUG_LOCATION):
            if f.startswith("frame_pair_") and f.endswith(".jpg"):
                try:
                    os.remove(os.path.join(DEBUG_LOCATION, f))
                except Exception:
                    pass

    # Sin pares de frames no hay nada que procesar (ej. extracción devolvió
    # 0 keyframes, all_frames = [initial_frame] solo).
    total_steps = len(all_frames) - 1
    if total_steps <= 0:
        logger.warning("[FEN] No hay pares de frames para procesar (all_frames=%d). "
                       "Devolviendo solo el FEN inicial.", len(all_frames))
        return [board.fen()]
    for i in range(total_steps):
        if progress_key:
            set_progress(progress_key, 50 + int(i / total_steps * 50))
        try:
            frame_a = all_frames[i]
            frame_b = all_frames[i + 1]

            changed = get_changed_cells(frame_a, frame_b)
            squares = [cell_index_to_square(idx) for idx in changed]
            logger.info("[FEN] Frame %d→%d: %d celdas cambiadas → casillas %s",
                        i, i+1, len(changed), [chess.square_name(s) for s in squares])

            # Guardar debug de todos los pares para inspección visual
            _save_frame_pair_debug(i, frame_a, frame_b, changed)

            if not changed:
                logger.info("[FEN] Sin cambios detectados, manteniendo FEN anterior")
                fens.append(board.fen())
                consecutive_failures += 1
                continue

            # ── Detección de doble movimiento ────────────────────────────────
            # Si hay >4 celdas cambiadas y no es un enroque, es probable que el frame
            # capturado ya contenga 2 movimientos (jugadas muy rápidas sin pausa intermedia).
            if len(changed) > 4:
                two = detect_two_moves(board, squares)
                if two:
                    m1, m2 = two
                    san1 = board.san(m1)
                    board.push(m1)
                    fens.append(board.fen())            # FEN intermedio (tras mov 1)
                    san2 = board.san(m2)
                    board.push(m2)
                    fens.append(board.fen())            # FEN final (tras mov 2)
                    consecutive_failures = 0
                    logger.info("[FEN] ✓ Doble movimiento detectado: %s + %s", san1, san2)
                    continue

            # ── Detección de movimiento simple ────────────────────────────────
            move = detect_move_from_squares(board, squares,
                                            frame_before=frame_a, frame_after=frame_b,
                                            changed_indices=changed)

            if move:
                san = board.san(move)
                board.push(move)
                fens.append(board.fen())
                consecutive_failures = 0
                logger.info("[FEN] ✓ Movimiento detectado: %s (%s)", san, move.uci())
            else:
                # Reintento con umbral más bajo (posible movimiento sutil)
                changed_r = get_changed_cells(frame_a, frame_b,
                                              threshold=CELL_CHANGE_THRESHOLD // 2)
                squares_r = [cell_index_to_square(idx) for idx in changed_r]
                move2 = detect_move_from_squares(board, squares_r,
                                                 frame_before=frame_a, frame_after=frame_b,
                                                 changed_indices=changed_r)
                if move2:
                    san = board.san(move2)
                    board.push(move2)
                    fens.append(board.fen())
                    consecutive_failures = 0
                    print(f"[FEN] ✓ Movimiento detectado (umbral relajado): {san} ({move2.uci()})")
                else:
                    fens.append(board.fen())
                    consecutive_failures += 1
                    if consecutive_failures >= MAX_FAILURES:
                        print(f"[FEN] ⚠ {consecutive_failures} fallos consecutivos — "
                              f"revisa media/debug/frame_pair_*.jpg")
                    else:
                        print(f"[FEN] No se pudo determinar el movimiento (fallo #{consecutive_failures})")

        except Exception as e:
            print(f"[FEN] Error procesando frame {i}: {e}")
            fens.append(board.fen())
            consecutive_failures += 1

    return fens


def _save_frame_pair_debug(idx, frame_a, frame_b, changed_indices):
    """
    Guarda un collage con los dos frames y resalta las celdas detectadas como cambiadas.
    Útil para depurar los primeros movimientos.
    """
    try:
        cs = NORMALIZED_SIZE // 8
        vis_a = frame_a.copy()
        vis_b = frame_b.copy()
        for ci in changed_indices:
            r, c = ci // 8, ci % 8
            x1, y1 = c * cs, r * cs
            cv2.rectangle(vis_a, (x1, y1), (x1 + cs, y1 + cs), (0, 0, 255), 3)
            cv2.rectangle(vis_b, (x1, y1), (x1 + cs, y1 + cs), (0, 255, 0), 3)
        collage = np.hstack([
            cv2.resize(vis_a, (500, 500)),
            cv2.resize(vis_b, (500, 500)),
        ])
        cv2.putText(collage, f"Frame {idx} (antes)", (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
        cv2.putText(collage, f"Frame {idx+1} (despues)", (510, 25),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
        save_debug_image(f"frame_pair_{idx:03d}", collage)
    except Exception as e:
        print(f"[DEBUG] _save_frame_pair_debug falló: {e}")


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


# -----------------------------------------
# Cache del análisis de motores (engine analysis)
# -----------------------------------------

def save_engine_analysis(analysis_id, results):
    """Guarda los resultados del análisis de motores en ENGINE_ANALYSIS_LOCATION/<analysis_id>.json."""
    os.makedirs(ENGINE_ANALYSIS_LOCATION, exist_ok=True)
    path = os.path.join(ENGINE_ANALYSIS_LOCATION, f"{analysis_id}.json")
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'results': results}, f)
        print(f"[ENGINE] Análisis guardado: {path}")
        return True
    except Exception as e:
        print(f"[ENGINE] Error al guardar análisis: {e}")
        return False


def load_engine_analysis(analysis_id):
    """Carga el análisis de motores guardado. Devuelve la lista de resultados o None."""
    path = os.path.join(ENGINE_ANALYSIS_LOCATION, f"{analysis_id}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data.get('results')
    except Exception as e:
        print(f"[ENGINE] Error al cargar análisis: {e}")
        return None


def delete_engine_analysis(analysis_id):
    """Elimina el análisis de motores asociado. Devuelve True si se borró."""
    path = os.path.join(ENGINE_ANALYSIS_LOCATION, f"{analysis_id}.json")
    if os.path.exists(path):
        try:
            os.remove(path)
            print(f"[DELETE] Engine analysis {analysis_id}.json eliminado.")
            return True
        except Exception as e:
            print(f"[DELETE] Error al eliminar engine analysis: {e}")
    return False


# -----------------------------------------
# Funciones de Análisis de Partida
# -----------------------------------------

def analysis_best_posStockfish(fen):

    """
    Obtiene la mejor jugada para la posición dada en formato FEN utilizando el motor Stockfish.
        Parametros:
        - fen: Cadena FEN que representa la posición actual del tablero.
        
        - Devuelve un diccionario con:
            - movement_uci: Movimiento recomendado en formato UCI (ejemplo: "e2e4").
            - movement_san: Movimiento recomendado en formato SAN (ejemplo: "e4").
            - new_fen: FEN resultante después de aplicar el movimiento recomendado.
            - score: Evaluación de la posición después del movimiento recomendado (en centipawns, positivo para blancas, negativo para negras).
    """

    path_engine = os.path.join(ENGINES_DIR, 'stockfish-windows-x86-64-avx2.exe')

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        pv = info.get("pv") or []
        if not pv:
            raise ValueError(f"Stockfish no encontró jugadas para la posición: {fen}")
        best_move = pv[0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].white().score(mate_score=10000) / 100
        }

def analysis_best_posObsidian(fen):

    """
    Obtiene la mejor jugada para la posición dada en formato FEN utilizando el motor Obsidian.
        Parametros:
        - fen: Cadena FEN que representa la posición actual del tablero.
        
        - Devuelve un diccionario con:
            - movement_uci: Movimiento recomendado en formato UCI (ejemplo: "e2e4").
            - movement_san: Movimiento recomendado en formato SAN (ejemplo: "e4").
            - new_fen: FEN resultante después de aplicar el movimiento recomendado.
            - score: Evaluación de la posición después del movimiento recomendado (en centipawns, positivo para blancas, negativo para negras).
    """

    path_engine = os.path.join(ENGINES_DIR, 'Obsidian160-avx2-pext.exe')

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        pv = info.get("pv") or []
        if not pv:
            raise ValueError(f"Obsidian no encontró jugadas para la posición: {fen}")
        best_move = pv[0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].white().score(mate_score=10000) / 100
        }

def analysis_best_posPlentyChess(fen):

    """
    Obtiene la mejor jugada para la posición dada en formato FEN utilizando el motor PlentyChess.

        Parametros:
        - fen: Cadena FEN que representa la posición actual del tablero.
        
        - Devuelve un diccionario con:
            - movement_uci: Movimiento recomendado en formato UCI (ejemplo: "e2e4").
            - movement_san: Movimiento recomendado en formato SAN (ejemplo: "e4").
            - new_fen: FEN resultante después de aplicar el movimiento recomendado.
            - score: Evaluación de la posición después del movimiento recomendado (en centipawns, positivo para blancas, negativo para negras).
    """
    
    path_engine = os.path.join(ENGINES_DIR, 'PlentyChess-7.0.0-windows-avx2.exe')

    with chess.engine.SimpleEngine.popen_uci(path_engine) as engine:

        board = chess.Board(fen)

        info = engine.analyse(board, chess.engine.Limit(time=0.1))

        pv = info.get("pv") or []
        if not pv:
            raise ValueError(f"PlentyChess no encontró jugadas para la posición: {fen}")
        best_move = pv[0]

        return {
            "movement_uci": best_move.uci(),
            "movement_san": board.san(best_move) if not board.move_stack else chess.Board(fen).san(best_move),
            "new_fen": board.fen(),
            "score": info["score"].white().score(mate_score=10000) / 100
        }

def analysis_engines_parallel(fen: str) -> tuple:
    """
    Ejecuta los 3 motores de ajedrez en paralelo usando ThreadPoolExecutor.

    En lugar de la secuencia:
        stock    → 0.1 s
        obsidian → 0.1 s
        plenty   → 0.1 s   (total: 0.3 s por paso)

    Los tres corren simultáneamente (~0.1 s por paso → 3× más rápido).

    Devuelve: (resultado_stockfish, resultado_obsidian, resultado_plentychess)
    """
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {
            executor.submit(analysis_best_posStockfish,   fen): 'stockfish',
            executor.submit(analysis_best_posObsidian,    fen): 'obsidian',
            executor.submit(analysis_best_posPlentyChess, fen): 'plentychess',
        }
        results = {}
        for future in as_completed(futures):
            name = futures[future]
            results[name] = future.result()  # Re-lanza excepciones si las hay

    return results['stockfish'], results['obsidian'], results['plentychess']


def consensus_analysis(stock, obsidian, plenty, fen):

    """
    Dada una posición en formato FEN y las recomendaciones de movimiento de tres motores de ajedrez (Stockfish, Obsidian y PlentyChess),
    esta función determina el movimiento recomendado por consenso entre los motores. El movimiento de consenso se define como el movimiento 
    que al menos dos de los motores recomiendan. Si no hay consenso, se selecciona el movimiento recomendado por Stockfish como predeterminado.

    Parámetros:
    - stock: Diccionario con la recomendación de movimiento de Stockfish, movimiento en formato UCI, movimiento en formato SAN, FEN resultante y evaluación de la posición.
    - obsidian: Diccionario con la recomendación de movimiento de Obsidian, cono formato similar al de Stockfish.
    - plenty: Diccionario con la recomendación de movimiento de PlentyChess, con formato similar al de Stockfish.
    - fen: Cadena FEN que representa la posición actual del tablero.

    Devuelve un diccionario con:
    - movement_uci: Movimiento recomendado por consenso en formato UCI (ejemplo: "e2e4").
    - movement_san: Movimiento recomendado por consenso en formato SAN (ejemplo: "e4").
    - new_fen: FEN resultante después de aplicar el movimiento recomendado por consenso.
    """

    board = chess.Board(fen)
    moves = [
        stock["movement_uci"],
        obsidian["movement_uci"],
        plenty["movement_uci"]
    ]

    count = Counter(moves)

    most_common_uci = count.most_common(1)[0][0]

    try:
        move = chess.Move.from_uci(most_common_uci)

    except ValueError as e:
        raise ValueError(f"Movimiento invalido: {moves}. Error: {e}")

    if move not in board.legal_moves:
        print(f"\n ERROR: El movimiento {most_common_uci} NO es legal en esta posición")
        print(f"Posición: {board.board_fen()}")
        print(f"\nMovimientos legales disponibles:")
        for legal_move in list(board.legal_moves)[:10]:
            print(f"  - {legal_move.uci()} ({board.san(legal_move)})")

        raise ValueError(
            f"El movimiento {most_common_uci} no es legal en la posición {fen}. "
            f"Los motores probablemente analizaron una posición diferente."
        )

    move_san = board.san(move)
    board.push(move)
    return {
        "movement_uci": most_common_uci,
        "movement_san": move_san,
        "new_fen": board.fen(),
    }


# -----------------------------------------
# Generación de FENs con YOLOv8 (detección de estado absoluto)
# -----------------------------------------

def frames_to_fens_yolo(all_frames, initial_fen=None, progress_key=None, on_fen=None,
                        original_frames=None, M=None,
                        detected_states=None, accepted_moves=None,
                        key_frames_groups=None, key_frames_orig_groups=None):
    """
    Versión YOLOv8 de frames_to_fens.

    Cuando se proporciona `detected_states` (lista de BoardState, una por keyframe),
    los estados pre-calculados por extract_key_frames se reutilizan directamente,
    evitando re-ejecutar YOLO sobre los mismos frames. Solo se ejecuta YOLO una vez
    más para el frame inicial (all_frames[0]).

    Sin `detected_states` (modo legado o fallback absdiff), ejecuta YOLO en cada
    frame como antes (compatible con el comportamiento anterior).

    Si YOLO no está disponible, cae automáticamente en frames_to_fens (deltas).

    Parámetros:
      all_frames[0]    → posición inicial (antes de cualquier movimiento)
      all_frames[i]    → posición después del movimiento i
      detected_states  → [state_kf0, state_kf1, ...] estados de all_frames[1:]
    """
    try:
        from .chess_detector import (
            is_available, detect_board_state, detect_board_state_consensus,
            infer_move_from_states, invalidate_grid_cache, reset_square_beliefs,
        )
    except ImportError:
        from chess_detector import (
            is_available, detect_board_state, detect_board_state_consensus,
            infer_move_from_states, invalidate_grid_cache, reset_square_beliefs,
        )

    if not is_available():
        logger.info("[FEN-YOLO] Modelo YOLO no disponible — usando detección por deltas")
        return frames_to_fens(all_frames, initial_fen, progress_key)

    # ── Inicialización ────────────────────────────────────────────────────────
    # Solo invalidar caché y creencias si vamos a ejecutar YOLO de nuevo
    # (si detected_states cubre todos los keyframes, YOLO solo corre 1 vez)
    invalidate_grid_cache()
    if not detected_states:
        # Modo sin estados pre-calculados: YOLO corre en cada frame → resetear Bayes
        reset_square_beliefs()
    try:
        from . import chess_detector as _cd
    except ImportError:
        import chess_detector as _cd
    _cd._yolo_debug_counter = 0

    # Limpiar imágenes de debug de ejecuciones anteriores
    if os.path.isdir(DEBUG_LOCATION):
        for f in os.listdir(DEBUG_LOCATION):
            if f.startswith("frame_pair_") and f.endswith(".jpg"):
                try:
                    os.remove(os.path.join(DEBUG_LOCATION, f))
                except Exception:
                    pass

    if detected_states:
        logger.info("[FEN-YOLO] Usando %d estados pre-calculados (YOLO ya ejecutado en extracción)",
                    len(detected_states))
    else:
        logger.info("[FEN-YOLO] Ejecutando YOLO en cada frame (modo sin estados pre-calculados)")

    if initial_fen is None:
        initial_fen = chess.STARTING_FEN

    board = chess.Board(initial_fen)
    fens  = [initial_fen]
    consecutive_failures = 0
    MAX_FAILURES = 5

    # Sin pares de frames no hay nada que procesar (ej. extracción devolvió
    # 0 keyframes, all_frames = [initial_frame] solo).
    total_steps = len(all_frames) - 1
    if total_steps <= 0:
        logger.warning("[FEN-YOLO] No hay pares de frames para procesar "
                       "(all_frames=%d). Devolviendo solo el FEN inicial.",
                       len(all_frames))
        return [board.fen()]

    # Estado del frame inicial: calculado una sola vez aquí
    # all_frames[0] = initial_frame, no tiene entrada en detected_states
    _initial_state_cache = None

    def _get_state(idx):
        """
        Devuelve el BoardState para all_frames[idx].

        Si detected_states está disponible:
          idx=0 → frame inicial → YOLO (una sola vez, cacheado)
          idx>0 → detected_states[idx-1] (pre-calculado en extracción)

        Sin detected_states: sigue la lógica legada de grupos/YOLO.
        """
        nonlocal _initial_state_cache

        if detected_states:
            if idx == 0:
                # Frame inicial: ejecutar YOLO una sola vez
                if _initial_state_cache is None:
                    orig_0 = original_frames[0] if original_frames else None
                    _initial_state_cache = detect_board_state(
                        all_frames[0], original_frame=orig_0, M=M
                    )
                return _initial_state_cache
            else:
                ds_idx = idx - 1
                if ds_idx < len(detected_states):
                    return detected_states[ds_idx]
                # Fuera de rango → fallback YOLO
                orig = original_frames[idx] if original_frames else None
                return detect_board_state(all_frames[idx], original_frame=orig, M=M)

        # ── Modo legado: grupos de consenso o YOLO directo ────────────────────
        orig = original_frames[idx] if original_frames else None
        if key_frames_groups and idx > 0 and (idx - 1) < len(key_frames_groups):
            wg = key_frames_groups[idx - 1]
            og = key_frames_orig_groups[idx - 1] if key_frames_orig_groups else None
            return detect_board_state_consensus(wg, og, M)
        return detect_board_state(all_frames[idx], original_frame=orig, M=M)

    for i in range(total_steps):
        if progress_key:
            set_progress(progress_key, 50 + int(i / total_steps * 50))

        frame_a = all_frames[i]
        frame_b = all_frames[i + 1]

        try:
            # ── Camino rápido: usar el move ya validado por Phase 4 ─────────
            # Phase 4 (en extract_key_frames) ya seleccionó el movimiento legal
            # que mejor explica el delta YOLO observado. Si está disponible y
            # sigue siendo legal sobre el board actual, lo aplicamos directamente
            # sin re-inferir. Esto elimina la divergencia entre los dos motores
            # de inferencia y la corrupción del FEN base por inferencias erróneas.
            move = None
            move_source = None
            if accepted_moves and i < len(accepted_moves) and accepted_moves[i] is not None:
                cand = accepted_moves[i]
                if cand in board.legal_moves:
                    move = cand
                    move_source = "phase4"
                else:
                    logger.warning(
                        "[FEN-YOLO] Move pre-validado %s ya no es legal en posición "
                        "actual — fallback a inferencia", cand.uci()
                    )

            # Solo si Phase 4 no nos dio move (o es ilegal) recurrimos a la
            # inferencia clásica como fallback.
            if move is None:
                state_before = _get_state(i)
                state_after  = _get_state(i + 1)

                # NO se enriquece state_before con legal_fill: la asimetría
                # (state_before completo, state_after parcial) genera 13+ piezas
                # "fantasma desaparecidas" que dominan la inferencia y producen
                # moves incorrectos. Comprobado experimentalmente.

                changed_cells = get_changed_cells(frame_a, frame_b)
                flow_sq = {cell_index_to_square(idx) for idx in changed_cells}

                if state_before is None or state_after is None:
                    logger.warning("[FEN-YOLO] Estado None — usando fallback delta")
                    squares_delta = [cell_index_to_square(idx) for idx in changed_cells]
                    move = detect_move_from_squares(
                        board, squares_delta,
                        frame_before=frame_a, frame_after=frame_b,
                        changed_indices=changed_cells,
                    )
                    move_source = "delta"
                else:
                    move = infer_move_from_states(
                        board, state_before, state_after, flow_squares=flow_sq
                    )
                    move_source = "infer_states"
                    if move is None:
                        logger.debug("[FEN-YOLO] YOLO sin resultado → fallback deltas")
                        squares_delta = [cell_index_to_square(idx) for idx in changed_cells]
                        move = detect_move_from_squares(
                            board, squares_delta,
                            frame_before=frame_a, frame_after=frame_b,
                            changed_indices=changed_cells,
                        )
                        move_source = "delta"

            if move:
                san = board.san(move)
                board.push(move)
                fens.append(board.fen())
                if on_fen:
                    on_fen(board.fen(), len(fens) - 1)
                consecutive_failures = 0
                logger.info("[FEN-YOLO] ✓ %s (%s) [src=%s]", san, move.uci(), move_source)
            else:
                fens.append(board.fen())
                consecutive_failures += 1
                if consecutive_failures >= MAX_FAILURES:
                    logger.warning(
                        "[FEN-YOLO] %d fallos consecutivos", consecutive_failures
                    )
                else:
                    logger.debug("[FEN-YOLO] Sin movimiento (fallo #%d)", consecutive_failures)
                _save_frame_pair_debug(i, frame_a, frame_b, [])

        except Exception as exc:
            logger.error("[FEN-YOLO] Error procesando frame %d: %s", i, exc)
            fens.append(board.fen())
            consecutive_failures += 1

    return fens
