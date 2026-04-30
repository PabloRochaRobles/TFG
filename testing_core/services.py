import json
import logging
import os
import sys
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
        import mediapipe.python.solutions.hands as _mp_hands    # fallback Windows
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
PUNTOS_ORIGEN = []
MAX_PUNTOS = 4
VENTANA_NOMBRE = 'Selecciona las 4 Esquinas del Tablero'
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
# Parámetros de captura de frames clave (defaults)
# Todos pueden sobreescribirse en media/frames_config.json sin tocar código.
# -----------------------------------------
#
# THRESHOLD_PIXEL_BINARY (int, 1–50, default 15)
#   Umbral de binarización sobre la diferencia absoluta entre frames consecutivos.
#   Más bajo → detecta movimientos más sutiles (más ruido).
#   Más alto → sólo detecta movimientos grandes (menos ruido, puede perder piezas pequeñas).
#
# THRESHOLD_START (int, default 1200)
#   Nº de píxeles "distintos" (tras binarización) para declarar inicio de movimiento.
#   Más bajo → empieza a detectar antes (más sensible, puede activarse con sombras).
#   Más alto → sólo activa con movimientos claros (puede perderse el inicio de un gesto rápido).
#
# THRESHOLD_END (int, default 600)
#   Nº de píxeles distintos por debajo del cual el frame se considera "estable".
#   Más bajo → exige más calma antes de declarar estabilidad (frame más limpio, más tarde).
#   Más alto → acepta estabilidad antes (captura más rápido, pero la mano puede seguir en cuadro).
#
# STABILITY_FRAMES (int, default 6)
#   Frames consecutivos estables requeridos para capturar el frame clave.
#   Más alto → espera más tiempo a que el tablero repose (imagen más limpia).
#   Más bajo → captura antes (riesgo de coger la pieza a medio posicionar o la mano aún visible).
#
# MIN_CHANGE_FROM_REF (int, default 1500)
#   Diferencia mínima contra la última posición estable de referencia para confirmar
#   que hubo un movimiento real (filtra falsas alarmas por iluminación o vibración).
#   Más alto → más estricto (puede ignorar movimientos sutiles).
#   Más bajo → acepta más cambios como movimiento real (más falsos positivos).
#
# REF_PIXEL_BINARY (int, 1–50, default 25)
#   Umbral de binarización para la comparación contra la referencia (min_change_from_ref).
#   Más bajo → la comparación de referencia es más sensible.
#   Más alto → más resistente a cambios globales de iluminación en la confirmación.
#
# LOG_INTERVAL (int, default 300)
#   Cada cuántos frames se imprime una línea de estadísticas en la consola.
#   Bajar a 30–60 para diagnóstico fino; subir a 600 para producción.
#
# COOLDOWN_FRAMES (int, default 20)
#   Frames a ignorar tras capturar un frame clave antes de reanudar la detección.
#   Evita que una misma jugada (p.ej. soltar la pieza lentamente) se capture dos veces.
#   Más alto → mayor separación mínima entre capturas (menos duplicados, puede perder jugadas rápidas).
#   Más bajo → permite capturas más seguidas (más sensible, mayor riesgo de duplicados).

# =============================================================================
# ESTRATEGIA EXPERIMENTAL DE SCORING — cambiar SCORING_STRATEGY para elegir
# =============================================================================
# "default":     Comportamiento actual (señales sueltas YOLO + pixel-diff).
#                Mejor resultado conocido: ~18 keyframes, primeros 4 correctos.
# "full_state":  Opción C — Comparar el ESTADO COMPLETO YOLO (32 casillas) con
#                el estado canónico esperado tras cada movimiento legal. El
#                ganador es el que más casillas coinciden globalmente (no por
#                señales puntuales). Robusto frente a ruido en señales sueltas.
# "best_frame":  Opción A — En lugar de procesar el primer frame estable tras
#                la mano, recolectar BEST_FRAME_WINDOW_SIZE frames estables
#                consecutivos, ejecutar Phase 4 sobre cada uno, y quedarse con
#                el de MAYOR score y MAYOR margen. El primer frame "limpio"
#                rara vez es el óptimo (el jugador puede no haberse retirado
#                completamente todavía).
#
# Combinaciones recomendadas para experimentar:
# - SCORING_STRATEGY = "default"     → línea base
# - SCORING_STRATEGY = "full_state"  → C sola
# - SCORING_STRATEGY = "best_frame"  → A sola
# - SCORING_STRATEGY = "full_state+best_frame"  → ambas combinadas (paranoia)
# =============================================================================
SCORING_STRATEGY = "full_state+best_frame"

# Tamaño de la ventana de frames estables a evaluar cuando best_frame está activo.
# Más alto → más tolerancia, mayor latencia y costo computacional.
BEST_FRAME_WINDOW_SIZE = 3

_FRAMES_DEFAULTS: dict = {
    "THRESHOLD_PIXEL_BINARY": 15,
    "THRESHOLD_START":        1200,
    "THRESHOLD_END":          600,
    "STABILITY_FRAMES":       6,
    "MIN_CHANGE_FROM_REF":    1500,
    "REF_PIXEL_BINARY":       25,
    "LOG_INTERVAL":           300,
    "COOLDOWN_FRAMES":        20,
    "NOISE_MULT_START":       20.0,
    "NOISE_MULT_END":         10.0,
    "NOISE_MULT_REF":         40.0,
}

def load_frames_config() -> dict:
    """
    Carga media/frames_config.json y lo mezcla con los defaults.
    Las claves ausentes usan el valor por defecto.
    Llamar en cada análisis para que los cambios al JSON surtan efecto sin reiniciar.
    """
    cfg = dict(_FRAMES_DEFAULTS)
    try:
        if os.path.exists(FRAMES_CONFIG_PATH):
            with open(FRAMES_CONFIG_PATH, 'r') as f:
                overrides = json.load(f)
            for k, v in overrides.items():
                if k in cfg:
                    cfg[k] = v
                    logger.info("[CONFIG] frames_config: %s = %s", k, v)
                else:
                    logger.warning("[CONFIG] frames_config: clave desconocida ignorada → '%s'", k)
    except Exception as e:
        logger.warning("[CONFIG] No se pudo cargar frames_config.json: %s — usando defaults", e)
    return cfg

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
    """Devuelve True si MediaPipe detecta una mano en el frame (BGR). Fallback: False."""
    global _mp_hands_instance, _hand_in_frame_logged
    if not _MEDIAPIPE_AVAILABLE:
        if not _hand_in_frame_logged:
            logger.warning("[HANDS] MediaPipe NO DISPONIBLE — filtro de manos desactivado.")
            logger.warning("[HANDS] Python: %s | sys.platform: %s",
                           sys.version.replace('\n', ' '), sys.platform)
            if _MEDIAPIPE_IMPORT_ERROR:
                logger.warning("[HANDS] Causa del fallo de import (capturada al cargar services):\n%s",
                               _MEDIAPIPE_IMPORT_ERROR)
            else:
                logger.warning("[HANDS] No se capturó error de import. Probablemente "
                               "mediapipe no está instalado en este entorno. "
                               "Comprueba con: python -c \"import mediapipe; print(mediapipe.__version__)\"")
            _hand_in_frame_logged = True
        return False
    try:
        if _mp_hands_instance is None:
            logger.info("[HANDS] Inicializando MediaPipe Hands (versión=%s)…", _MEDIAPIPE_VERSION)
            _mp_hands_instance = _mp_hands.Hands(
                static_image_mode=True,
                max_num_hands=1,
                min_detection_confidence=0.6,
            )
            logger.info("[HANDS] MediaPipe Hands inicializado correctamente")
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = _mp_hands_instance.process(rgb)
        detected = bool(result.multi_hand_landmarks)
        if detected:
            logger.info("[HANDS] Mano detectada — esperando retirada")
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

# Función que extrae los frames posteriores a un movimiento realizado y devuelve el conjunto de todas las imágenes.
CONSENSUS_WINDOW = 3  # Nº de frames estables a conservar para el consenso YOLO por captura

# ── Parámetros del trigger híbrido absdiff + YOLO (4 fases) ──────────────────
# FASE 1: detector de ventanas pixel-estables vía absdiff (determinista, barato).
# FASE 2: votación YOLO de N sondeos consecutivos dentro de la ventana estable.
# FASE 3: filtros de plausibilidad física (rango de diff de un movimiento legal).
# FASE 4: validación de legalidad con python-chess sobre tablero oficial.
#
# Por qué híbrido: YOLO sobre PyTorch+CUDA no es determinista. Si se usa como
# trigger temporal, su ruido (subset de piezas detectadas varía entre runs) se
# convierte en falsos keyframes. absdiff sobre frames consecutivos es totalmente
# determinista y aísla los instantes en que el tablero está físicamente quieto;
# allí YOLO opera en su régimen más estable y la votación 2/3 elimina las
# piezas marginales que son el origen del ruido entre runs.

# FASE 1 — trigger absdiff (sobre el WARPED 1000×1000 con blur)
# Sin zona neutra: ratio < MOTION ⇒ estable (incrementa stable_run);
# ratio ≥ MOTION ⇒ movimiento (resetea stable_run).
ABSDIFF_BIN_THRESHOLD   = 15      # umbral de binarización por pixel
MOTION_PIXEL_RATIO      = 0.003   # > 0.3% píxeles cambiados → movimiento real
STABLE_FRAMES_REQUIRED  = 3       # Antes 5. Reducido para no perder jugadas muy rápidas.
COOLDOWN_AFTER_CAPTURE  = 3       # Antes 15. Reducido para no comerse la jugada del oponente.

# FASE 2 — votación multi-shot YOLO
YOLO_VOTING_SHOTS       = 3       # inferencias YOLO por candidato
YOLO_VOTE_MIN_AGREE     = 2       # votos mínimos por casilla para aceptar pieza

# FASE 3 — sanity check mínimo (solo excluye d==0)
# YOLO detecta ~50% de piezas con subconjunto variable entre scans; cualquier
# umbral máximo aquí genera falsos rechazos. El filtro real es Phase 4.
REAL_MOVE_DIFF_MIN      = 1
REAL_MOVE_DIFF_MAX      = 999   # sin límite superior efectivo

# FASE 4 — validación legal
USE_LEGAL_MOVE_VALIDATION = True
LEGAL_MOVE_TOLERANCE      = 2     # errores tolerados sobre el DELTA de casillas
                                  # cambiadas (no sobre el tablero completo).
                                  # Un movimiento simple cambia 2 casillas →
                                  # toleramos hasta 2 de ellas mal clasificadas.
MIN_PIECES_TRUST          = 8     # estados con menos piezas → mano u oclusión

# -----------------------------------------
# Parámetros de auto-calibración del ruido base del vídeo (usados solo en fallback absdiff)
# -----------------------------------------
# La fase de calibración muestrea los primeros segundos del vídeo (sin movimiento
# de piezas) para medir el diff base de la cámara y ajustar los umbrales
# proporcionalmente al ruido real del clip.
#
# CALIB_SKIP_SECONDS: segundos iniciales a saltar (evita el arranque con mano/piezas)
# CALIB_SAMPLE_SECONDS: cuántos segundos muestrear para calcular el ruido base
# NOISE_MULT_START: threshold_start   = p25_ruido × NOISE_MULT_START  (cap: 30× config)
# NOISE_MULT_END:   threshold_end     = p25_ruido × NOISE_MULT_END    (cap: 30× config)
# NOISE_MULT_REF:   min_change_from_ref = p25_ruido × NOISE_MULT_REF  (cap: 30× config)
CALIB_SKIP_SECONDS   = 3
CALIB_SAMPLE_SECONDS = 10
NOISE_MULT_START     = 20.0
NOISE_MULT_END       = 10.0
NOISE_MULT_REF       = 40.0


def _calibrate_noise_floor(video, mat, pixel_binary: int) -> dict:
    """
    Muestrea los primeros CALIB_SAMPLE_SECONDS del vídeo (tras saltar
    CALIB_SKIP_SECONDS) para calcular el ruido base de la cámara.

    Devuelve un dict con estadísticas del diff estable: mean, p50, p75, p95.
    El cursor del vídeo queda reposicionado en el frame 0 al finalizar.
    Devuelve {} si el vídeo es demasiado corto o si falla la lectura.
    """
    fps   = video.get(cv2.CAP_PROP_FPS) or 30.0
    total = int(video.get(cv2.CAP_PROP_FRAME_COUNT))

    skip = min(int(CALIB_SKIP_SECONDS  * fps), total // 5)
    samp = min(int(CALIB_SAMPLE_SECONDS * fps), total // 5)

    if samp < 5:   # Vídeo demasiado corto para calibrar
        video.set(cv2.CAP_PROP_POS_FRAMES, 0)
        return {}

    for _ in range(skip):
        video.read()

    diffs: list[float] = []
    prev_blur = None
    for _ in range(samp):
        ret, frame = video.read()
        if not ret:
            break
        warped = cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        blur   = process_image(warped)
        if prev_blur is not None:
            d = cv2.absdiff(prev_blur, blur)
            _, t = cv2.threshold(d, pixel_binary, 255, cv2.THRESH_BINARY)
            diffs.append(float(np.sum(t > 0)))
        prev_blur = blur

    video.set(cv2.CAP_PROP_POS_FRAMES, 0)

    if not diffs:
        return {}

    arr = np.array(diffs)
    # p25 en vez de p75: en vídeos con juego activo desde el inicio, p75 incluye
    # frames de movimiento real y sobreestima el ruido base. p25 captura la
    # parte tranquila de la distribución (tablero quieto entre jugadas).
    return {
        'mean': float(arr.mean()),
        'p25':  float(np.percentile(arr, 25)),
        'p75':  float(np.percentile(arr, 75)),
        'p95':  float(np.percentile(arr, 95)),
    }


def _extract_key_frames_absdiff(video_path, coords, progress_key=None):
    """
    Trigger clásico por diferencia de píxeles (absdiff). Se usa como fallback
    cuando YOLO no está disponible. No llamar directamente — usar extract_key_frames.
    Retorna la 5-tupla original: (key_frames, key_frames_orig, groups, orig_groups, mat).
    """
    # Variables de la función
    key_frames = []                 # Lista de los frames claves (warpeados)
    key_frames_orig = []            # Lista de los frames claves (originales sin warpear)
    key_frames_groups = []          # Lista de grupos de frames estables (warpeados) para consenso
    key_frames_orig_groups = []     # Lista de grupos de frames estables (originales) para consenso
    frames_since_motion = 0         # Frames consecutivos de estabilidad desde el último movimiento
    motion_detected = False         # Indica si actualmente se está detectando un movimiento
    stable_win_warped = deque(maxlen=CONSENSUS_WINDOW)   # Ventana deslizante de frames estables
    stable_win_orig   = deque(maxlen=CONSENSUS_WINDOW)
    last_yolo_piece_count = None    # Nº de piezas detectadas en el último keyframe validado

    # ── Umbrales (cargados desde media/frames_config.json o defaults) ──────────
    cfg                 = load_frames_config()
    pixel_binary        = cfg["THRESHOLD_PIXEL_BINARY"]
    threshold_start     = cfg["THRESHOLD_START"]
    threshold_end       = cfg["THRESHOLD_END"]
    stability_frames    = cfg["STABILITY_FRAMES"]
    min_change_from_ref = cfg["MIN_CHANGE_FROM_REF"]
    ref_pixel_binary    = cfg["REF_PIXEL_BINARY"]
    log_interval        = cfg["LOG_INTERVAL"]
    cooldown_frames     = cfg["COOLDOWN_FRAMES"]
    noise_mult_start    = float(cfg.get("NOISE_MULT_START", NOISE_MULT_START))
    noise_mult_end      = float(cfg.get("NOISE_MULT_END",   NOISE_MULT_END))
    noise_mult_ref      = float(cfg.get("NOISE_MULT_REF",   NOISE_MULT_REF))
    frame_count         = 0         # Contador de frames procesados
    cooldown_remaining  = 0         # Frames restantes de cooldown tras la última captura

    mat   = get_matriz(coords)
    video = open_video(video_path)
    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT)) or 1           # Total de frames para el progreso

    # ── Auto-calibración: ajustar umbrales al ruido real del clip ────────────
    # Se usa p25 (no p75) porque p75 se contamina con frames de movimiento real
    # cuando el juego está en marcha durante los primeros segundos del clip.
    # p25 captura la parte tranquila de la distribución (tablero quieto).
    # Safety cap: nunca superar 30× el valor de config para evitar sobreajuste.
    noise = _calibrate_noise_floor(video, mat, pixel_binary)
    if noise and noise['p25'] > 0:
        p25 = noise['p25']
        cap_start = threshold_start     * 30
        cap_end   = threshold_end       * 30
        cap_ref   = min_change_from_ref * 30
        adaptive_start = min(p25 * noise_mult_start, cap_start)
        adaptive_end   = min(p25 * noise_mult_end,   cap_end)
        adaptive_ref   = min(p25 * noise_mult_ref,   cap_ref)
        threshold_start     = max(threshold_start,     adaptive_start)
        threshold_end       = max(threshold_end,       adaptive_end)
        min_change_from_ref = max(min_change_from_ref, adaptive_ref)
        logger.info("[AUTO-CALIB] Ruido base del clip: mean=%.0f p25=%.0f p75=%.0f p95=%.0f",
                    noise['mean'], noise['p25'], noise['p75'], noise['p95'])
        logger.info("[AUTO-CALIB] Umbrales adaptativos → start=%.0f end=%.0f ref=%.0f",
                    threshold_start, threshold_end, min_change_from_ref)
    else:
        logger.info("[AUTO-CALIB] Calibración omitida (vídeo muy corto o lectura fallida)")

    logger.info("[CONFIG] Parámetros de captura: pixel_binary=%s start=%s end=%s "
                "stability=%s min_ref=%s ref_binary=%s cooldown=%s",
                pixel_binary, threshold_start, threshold_end,
                stability_frames, min_change_from_ref, ref_pixel_binary, cooldown_frames)
    ret, frame_ref = video.read()                                           # Obtención del primer frame

    if not ret:
        return {"error": "Video vacío."}

    frame_ref_warped = cv2.warpPerspective(frame_ref, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))  # Transformación de perspectiva
    blur_ref  = process_image(frame_ref_warped)                                                 # Última posición estable conocida del tablero
    blur_prev = blur_ref.copy()                                                                 # Frame anterior para diff consecutiva

    while video.isOpened():
        ret, frame_curr = video.read()
        if not ret:
            break

        frame_count += 1
        if progress_key:
            set_progress(progress_key, int(frame_count / total_frames * 50))
        frame_curr_warped = cv2.warpPerspective(frame_curr, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        blur_curr = process_image(frame_curr_warped)

        # Cooldown: ignorar detección durante N frames tras una captura para evitar duplicados
        if cooldown_remaining > 0:
            cooldown_remaining -= 1
            blur_prev = blur_curr
            continue

        # Diferencia entre frames consecutivos: detecta movimiento activo entre fotogramas adyacentes
        consec_diff  = cv2.absdiff(blur_prev, blur_curr)
        _, consec_thresh = cv2.threshold(consec_diff, pixel_binary, 255, cv2.THRESH_BINARY)
        consec_area  = int(np.sum(consec_thresh > 0))

        # Log periódico para calibrar umbrales: imprime el diff en reposo cada log_interval frames
        if frame_count % log_interval == 0:
            logger.debug("[FRAMES] frame=%d consec_area=%d motion=%s key_frames=%d",
                         frame_count, consec_area, motion_detected, len(key_frames))

        if not motion_detected:
            if consec_area > threshold_start:                               # Inicio de movimiento detectado
                motion_detected     = True
                frames_since_motion = 0
                stable_win_warped.clear()
                stable_win_orig.clear()
                logger.info("[FRAMES] Movimiento iniciado en frame %d (consec_area=%d)", frame_count, consec_area)
            else:
                # Actualización gradual del frame de referencia para compensar cambios de iluminación
                blur_ref = cv2.addWeighted(blur_ref, 0.99, blur_curr, 0.01, 0)

        else:                                                               # Durante el movimiento
            if consec_area < threshold_end:
                frames_since_motion += 1                                    # Frame estable: incrementar contador
                stable_win_warped.append(frame_curr_warped.copy())
                stable_win_orig.append(frame_curr.copy())
            else:
                frames_since_motion = 0                                     # Movimiento aún activo: reiniciar
                stable_win_warped.clear()
                stable_win_orig.clear()

            if frames_since_motion >= stability_frames:                     # Tablero estabilizado tras el movimiento
                # Confirmar movimiento real comparando contra la última posición estable de referencia
                ref_diff = cv2.absdiff(blur_ref, blur_curr)
                _, ref_thresh = cv2.threshold(ref_diff, ref_pixel_binary, 255, cv2.THRESH_BINARY)
                ref_area = int(np.sum(ref_thresh > 0))

                if ref_area > min_change_from_ref:
                    if _hand_in_frame(frame_curr):
                        frames_since_motion = 0
                        stable_win_warped.clear()
                        stable_win_orig.clear()
                        logger.info("[FRAMES] Mano detectada en frame %d, esperando retirada", frame_count)
                    else:
                        # ── Validación YOLO: rechaza falsos positivos obvios ──────
                        # Un cambio real mueve exactamente 1 pieza (delta en piezas ∈ {0, 1}).
                        # Si YOLO ve 2+ piezas más que en el último keyframe válido,
                        # el tablero no cambió realmente (duplicado o falsa alarma tardía).
                        _accept_frame = True
                        try:
                            try:
                                from .chess_detector import detect_board_state as _ds_val, is_available as _ia_val
                            except ImportError:
                                from chess_detector import detect_board_state as _ds_val, is_available as _ia_val
                            if _ia_val():
                                quick_state = _ds_val(frame_curr_warped)
                                if quick_state is not None:
                                    curr_count = len(quick_state)
                                    if last_yolo_piece_count is not None:
                                        delta = last_yolo_piece_count - curr_count
                                        if delta < -2:
                                            # YOLO ve 3+ piezas más → casi seguro es un duplicado
                                            _accept_frame = False
                                            logger.info("[FRAMES] Candidato rechazado por YOLO "
                                                        "(ref_area=%d, δpiezas=%+d, antes=%d ahora=%d)",
                                                        ref_area, delta, last_yolo_piece_count, curr_count)
                                        else:
                                            last_yolo_piece_count = curr_count
                                    else:
                                        last_yolo_piece_count = curr_count
                        except Exception as _e_val:
                            logger.debug("[FRAMES] Validación YOLO fallida: %s", _e_val)

                        if _accept_frame:
                            warp_group = list(stable_win_warped) or [frame_curr_warped.copy()]
                            orig_group = list(stable_win_orig)   or [frame_curr.copy()]
                            key_frames.append(warp_group[-1])
                            key_frames_orig.append(orig_group[-1])
                            key_frames_groups.append(warp_group)
                            key_frames_orig_groups.append(orig_group)
                            blur_ref = blur_curr.copy()
                            cooldown_remaining = cooldown_frames
                            motion_detected = False
                            frames_since_motion = 0
                            stable_win_warped.clear()
                            stable_win_orig.clear()
                            logger.info("[FRAMES] Frame clave #%d guardado (ref_area=%d, consensus_frames=%d) "
                                        "→ cooldown %d frames",
                                        len(key_frames), ref_area, len(warp_group), cooldown_frames)
                        else:
                            frames_since_motion = 0
                            stable_win_warped.clear()
                            stable_win_orig.clear()
                else:
                    logger.info("[FRAMES] Movimiento ignorado como falsa alarma (ref_area=%d)", ref_area)
                    motion_detected     = False
                    frames_since_motion = 0
                    stable_win_warped.clear()
                    stable_win_orig.clear()

        blur_prev = blur_curr

    video.release()
    return key_frames, key_frames_orig, key_frames_groups, key_frames_orig_groups, mat


def _diff_states(canonical, yolo):
    """
    Diff ASIMÉTRICO: solo contradicciones de YOLO contra el estado canónico.

    No penaliza omisiones (casillas donde el canónico tiene pieza pero YOLO no
    la ve), porque YOLO típicamente detecta solo ~50% de las piezas en cada
    inferencia y eso inflaría el diff con falsa señal.

    Cuenta únicamente casillas donde YOLO afirma una pieza que contradice al
    estado canónico (pieza distinta o pieza donde el canónico dice vacía).
    """
    if canonical is None or yolo is None:
        return 99
    return sum(
        1 for sq, sym in yolo.items()
        if canonical.get(sq, '') != sym
    )


def _vote_per_square(states, min_votes):
    """
    Agrega N estados YOLO en uno robusto vía votación por casilla.
    Para cada casilla, devuelve la pieza con >= min_votes coincidencias.
    Las casillas sin consenso quedan vacías → ruido marginal filtrado.
    """
    valid = [s for s in states if s]
    if not valid:
        return {}
    all_squares = set()
    for s in valid:
        all_squares.update(s.keys())
    out = {}
    for sq in all_squares:
        votes = Counter(s.get(sq) for s in valid)
        sym, n = votes.most_common(1)[0]
        if sym is not None and n >= min_votes:
            out[sq] = sym
    return out


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


def _match_state_change_to_legal_move_full_state(
    legal_board, prev_warped, curr_warped, robust_state, prev_robust=None,
):
    """
    OPCIÓN C — Scoring por COMPARACIÓN DE ESTADO COMPLETO con pesos calibrados.

    Para cada movimiento legal:
      1. Aplicarlo al legal_board → genera estado canónico esperado.
      2. Calcular `_fen_agreement_score(expected, robust_state)` — la misma
         función que el resto del proyecto usa para comparar consensus YOLO
         con candidatos canónicos. Pesos asimétricos calibrados:
            +1.0  ambos coinciden (incluyendo casilla vacía)
            -0.50 ambos ven pieza pero discrepan en tipo/color
            -0.30 YOLO ve pieza, candidato vacío  (FP YOLO — frecuente)
            -0.15 candidato ve pieza, YOLO no la detecta (FN YOLO — frecuente)
      3. El movimiento ganador es el que produce el estado más coherente con
         lo que YOLO realmente está viendo, NO el que tiene "más señales
         puntuales".

    Por qué ESTOS pesos y no -1.0/-1.0:
      - YOLO en este pipeline detecta ~19 de 32 piezas y produce algunos
        falsos positivos por sombras/brazo. Penalizar fuerte cada FP/FN
        hace que TODO movimiento dé score muy negativo (la versión inicial
        de full_state daba scores típicos de -10 a -15 incluso para el
        movimiento real).
      - Los pesos asimétricos reconocen que FP/FN son ruido inevitable y
        priorizan las coincidencias positivas sobre las contradicciones.

    Pixel-diff sigue como tiebreaker leve.

    Devuelve (best_move, expected_state, err, top_alts) o None si rechazado.
    """
    try:
        from .chess_detector import _board_to_state, _fen_agreement_score
    except ImportError:
        from chess_detector import _board_to_state, _fen_agreement_score

    # Los scores reales del agreement están típicamente entre +2 y +8 cuando
    # el match es bueno con la lógica delta-aware (solo las casillas que cambiaron
    # contribuyen activamente). ACCEPT_THRESHOLD bajado de 3.0 → 1.2 para
    # no descartar movimientos con YOLO parcial (~50% recall).
    # MARGIN_REQUIRED bajado de 0.4 → 0.3 ya que el espacio de scores es más estrecho.
    ACCEPT_THRESHOLD = 1.2       # Score absoluto mínimo para aceptar
    MARGIN_REQUIRED  = 0.3       # Diferencia mínima vs segundo mejor
    ABSOLUTE_MIN_MARGIN = 0.15   # Inviolable

    if prev_robust is None:
        return None

    prev_expected = _board_to_state(legal_board)

    # Pixel-diff como tiebreaker secundario
    pixel_changed_dict = {}
    if prev_warped is not None and curr_warped is not None:
        pixel_changed_dict = _pixel_changed_squares(
            prev_warped, curr_warped, top_k=6, threshold=8
        )
    pixel_changed = set(pixel_changed_dict.keys())

    candidates = []   # list[(neg_score, move, expected_state)]
    for move in legal_board.legal_moves:
        legal_board.push(move)
        expected = _board_to_state(legal_board)   # estado canónico tras el move
        legal_board.pop()

        # === Señal PRIMARIA: Coherencia global delta-aware con casillas de movimiento protegidas ===
        match_score = 0.0
        all_squares = set(expected.keys()) | set(robust_state.keys())
        # Las casillas físicamente implicadas en este movimiento (incluyendo
        # casillas de torre en enroque y captura al paso) nunca se perdonan.
        move_squares = _move_changed_squares(legal_board, move)
        for sq in all_squares:
            c_sym = expected.get(sq, '')
            y_sym = robust_state.get(sq, '')
            
            if c_sym == y_sym:
                match_score += 1.0
            else:
                # Mismatch. ¿Era un error sistemático que ya existía en el frame anterior?
                prev_c_sym = prev_expected.get(sq, '')
                prev_y_sym = prev_robust.get(sq, '')
                
                # Las casillas implicadas en el movimiento candidato NUNCA se perdonan:
                # son exactamente las que queremos evaluar para discriminar movimientos.
                # Para el resto: si el error es el mismo (YOLO sigue tropezando con la
                # misma oclusión), lo perdonamos para no penalizar el candidato correcto
                # por ruido sistemático ajeno al movimiento.
                if sq not in move_squares and c_sym == prev_c_sym and y_sym == prev_y_sym:
                    continue
                    
                if c_sym and y_sym: match_score -= 0.50
                elif y_sym:         match_score -= 0.30
                else:               match_score -= 0.15

        # === Tiebreaker secundario: pixel-diff sobre origen/destino del move ===
        expected_sqs = _move_changed_squares(legal_board, move)
        if pixel_changed:
            pixel_overlap = len(pixel_changed & expected_sqs)
            match_score += 0.4 * pixel_overlap

            # Tiebreaker continuo
            diff_sum = sum(pixel_changed_dict.get(sq, 0.0) for sq in expected_sqs)
            match_score += 0.001 * diff_sum

        # Tiebreaker leve para capturas
        if legal_board.is_capture(move):
            match_score += 0.1

        candidates.append((-match_score, move, expected))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    best_neg, best_move, best_state = candidates[0]
    best_score = -best_neg
    second_score = -candidates[1][0] if len(candidates) > 1 else float('-inf')
    margin = best_score - second_score

    # Top-3 SANs para diagnóstico
    top_alts = []
    for neg, mv, _ in candidates[:3]:
        try:
            san = legal_board.san(mv)
        except Exception:
            san = mv.uci()
        top_alts.append((san, -neg))

    dynamic_margin = MARGIN_REQUIRED
    
    # Con scores delta-aware el rango es más estrecho; si el mejor score es
    # alto (≥ 4.0) permitir margen más pequeño (el pixel-diff ya discrimina).
    if best_score >= 4.0:
        dynamic_margin = ABSOLUTE_MIN_MARGIN
    elif best_score >= 2.0 and len(pixel_changed) <= 4:
        dynamic_margin = 0.3

    if best_score < ACCEPT_THRESHOLD:
        alts_str = ", ".join(f"{san}({s:.2f})" for san, s in top_alts)
        logger.info("[FASE 4 FullState] Rechazado por score bajo: best=%.2f < %s. Top: %s",
                    best_score, ACCEPT_THRESHOLD, alts_str)
        return None
    if margin < dynamic_margin:
        alts_str = ", ".join(f"{san}({s:.2f})" for san, s in top_alts)
        logger.info("[FASE 4 FullState] Rechazado por margen bajo: margin=%.2f < %.2f. Top: %s",
                    margin, dynamic_margin, alts_str)
        return None

    expected_sqs_best = _move_changed_squares(legal_board, best_move)
    err = max(0, len(expected_sqs_best) - len(pixel_changed & expected_sqs_best))

    return (best_move, best_state, err, top_alts)


def _match_state_change_to_legal_move(
    legal_board, prev_warped, curr_warped, robust_state, prev_robust=None,
):
    """
    Phase 4: identifica el movimiento legal usando el DELTA DEL ESTADO YOLO
    como señal primaria, no el pixel-diff.

    Por qué YOLO state delta y no pixel-diff:
      - YOLO opera sobre el frame ORIGINAL lateral, detecta el bbox de cada
        pieza, toma su BASE POINT y lo proyecta vía M al warped. La base
        está en el plano del tablero por lo que la proyección es exacta:
        YOLO mapea correctamente cada pieza a su casilla.
      - Pixel-diff sobre el warped es INHERENTEMENTE ERRÓNEO en vista lateral:
        la homografía solo es exacta para el plano del tablero, pero el
        cuerpo de las piezas (sobre el plano) se estira hacia las casillas
        adyacentes en el warp. Resultado: pixel-diff identifica casillas
        equivocadas off-by-one.
      - Por tanto, el delta del state YOLO (qué piezas aparecen/desaparecen
        entre scans) es la fuente fiable de "qué casillas cambiaron".
      - El pixel-diff se mantiene como confirmación SECUNDARIA de bajo peso.

    Score por movimiento (signals YOLO con peso ALTO):
        +2.0  pieza movida desapareció del origen  (prev='P', now='')
        +2.0  pieza esperada apareció en destino   (prev='', now='P')
        -1.5  pieza movida sigue en origen          (move no ocurrió)
        -1.5  pieza distinta en destino              (move incompatible)
        +0.3  pixel-diff confirma cada casilla esperada (peso bajo)
        +0.1  captura (tiebreaker)

    Aceptación: best >= ACCEPT_THRESHOLD (1.5) y margin >= MARGIN (0.5).
    """
    try:
        from .chess_detector import _board_to_state
    except ImportError:
        from chess_detector import _board_to_state

    ACCEPT_THRESHOLD = 1.5     # Subido de 1.2: señales YOLO valen 2.0 c/u
    MARGIN_REQUIRED  = 0.4

    if prev_robust is None:
        return None

    # Pixel-diff sobre Hough grid (señal secundaria).
    # top_k=6 elimina las casillas vecinas "salpicadas" por la perspectiva del
    # peón que se movió. threshold=8 evita que ruido tenue arrastre casillas
    # legítimas fuera del top_k cuando una jugada real es sutil (peón que
    # avanza una casilla en zonas con poco contraste).
    pixel_changed_dict = {}
    if prev_warped is not None and curr_warped is not None:
        pixel_changed_dict = _pixel_changed_squares(
            prev_warped, curr_warped, top_k=6, threshold=8
        )
    pixel_changed = set(pixel_changed_dict.keys())

    candidates = []   # list[(neg_score, move, expected_state)]
    for move in legal_board.legal_moves:
        legal_board.push(move)
        expected = _board_to_state(legal_board)
        legal_board.pop()

        # Pieza que se mueve y posible captura (estado ANTES del move)
        moving_piece   = legal_board.piece_at(move.from_square)
        moving_sym     = moving_piece.symbol() if moving_piece else ''
        captured_piece = legal_board.piece_at(move.to_square)
        captured_sym   = captured_piece.symbol() if captured_piece else ''

        # Lo que YOLO veía/ve en origen y destino
        prev_orig = prev_robust.get(move.from_square, '')
        now_orig  = robust_state.get(move.from_square, '')
        prev_dest = prev_robust.get(move.to_square, '')
        now_dest  = robust_state.get(move.to_square, '')
        expected_dest = expected.get(move.to_square, '')

        score = 0.0

        # === Señal YOLO 1: ¿desapareció la pieza del origen? ===
        # Peso aumentado (1.5 → 2.0): señal YOLO explícita es más fiable que
        # pixel-diff cuando las piezas tienen altura (perspectiva lateral).
        if prev_orig == moving_sym and moving_sym and not now_orig:
            score += 2.0    # YOLO confirma desaparición
        elif prev_orig == moving_sym and now_orig == moving_sym:
            score -= 1.5    # CONTRADICCIÓN: la pieza sigue en origen

        # === Señal YOLO 2: ¿apareció la pieza esperada en destino? ===
        if not prev_dest and now_dest and now_dest == expected_dest:
            score += 2.0    # YOLO confirma aparición
        elif prev_dest == captured_sym and captured_sym and now_dest == expected_dest:
            score += 2.0    # YOLO confirma captura
        elif now_dest and now_dest != expected_dest:
            score -= 1.5

        # === Señal PRIMARIA (pixel-diff): Diferencia Física ===
        # Peso reducido (1.5 → 0.8) para que la señal YOLO domine.
        # El pixel-diff es menos fiable en vista lateral porque las piezas
        # altas proyectan sombras en casillas adyacentes (off-by-one).
        # Sigue siendo útil como tiebreaker entre candidatos con igual score YOLO.
        expected_sqs = _move_changed_squares(legal_board, move)
        if pixel_changed:
            pixel_overlap = len(pixel_changed & expected_sqs)
            score += 0.8 * pixel_overlap

            missing_changes = len(expected_sqs - pixel_changed)
            score -= 0.05 * missing_changes

            # Tiebreaker continuo: desempata sumando magnitud real de diferencia
            diff_sum = sum(pixel_changed_dict.get(sq, 0.0) for sq in expected_sqs)
            score += 0.0005 * diff_sum

        # Tiebreaker leve para capturas
        if legal_board.is_capture(move):
            score += 0.1

        candidates.append((-score, move, expected))

    if not candidates:
        return None

    candidates.sort(key=lambda c: c[0])
    best_neg, best_move, best_state = candidates[0]
    best_score = -best_neg
    second_score = -candidates[1][0] if len(candidates) > 1 else float('-inf')
    margin = best_score - second_score

    # Top-3 SANs para diagnóstico
    top_alts = []
    for neg, mv, _ in candidates[:3]:
        try:
            san = legal_board.san(mv)
        except Exception:
            san = mv.uci()
        top_alts.append((san, -neg))

    ABSOLUTE_MIN_MARGIN = 0.2

    dynamic_margin = MARGIN_REQUIRED

    # Con los nuevos pesos (YOLO=2.0), un score ≥ 2.0 indica al menos
    # una señal YOLO confirmada → podemos relajar el margen exigido.
    if best_score >= 2.0:
        dynamic_margin = ABSOLUTE_MIN_MARGIN
    elif best_score >= 1.5 and len(pixel_changed) <= 4:
        dynamic_margin = ABSOLUTE_MIN_MARGIN

    if best_score < ACCEPT_THRESHOLD:
        alts_str = ", ".join(f"{san}({s:.2f})" for san, s in top_alts)
        logger.info("[FASE 4] Rechazado por score bajo: best=%.2f < %s. Top: %s", best_score, ACCEPT_THRESHOLD, alts_str)
        return None
    if margin < dynamic_margin:
        alts_str = ", ".join(f"{san}({s:.2f})" for san, s in top_alts)
        logger.info("[FASE 4] Rechazado por margen bajo: margin=%.2f < %.2f. Top: %s",
                    margin, dynamic_margin, alts_str)
        return None

    expected_sqs_best = _move_changed_squares(legal_board, best_move)
    err = max(0, len(expected_sqs_best) - len(pixel_changed & expected_sqs_best))

    return (best_move, best_state, err, top_alts)


def _evaluate_best_frame_in_window(
    video, mat, legal_board,
    last_accepted_warped, current_warped, current_frame,
    current_robust, prev_robust, current_idx,
    scorer, window_size=5,
):
    """
    OPCIÓN A — Evalúa varios frames consecutivos y elige el mejor candidato.

    En vez de procesar el primer frame estable tras la mano (que muchas veces
    captura al jugador retirando el brazo), recolectamos hasta `window_size`
    frames adicionales y ejecutamos `scorer` sobre cada uno. Nos quedamos con
    el frame que produzca:
      - Un match válido (no None)
      - Mayor `best_score` (estabilidad de la decisión)
      - Mayor `margin` sobre el segundo candidato (confianza relativa)

    Si el frame inicial ya da match limpio (margen > 3) lo aceptamos sin gastar
    más frames — atajo para no degradar la latencia.

    Devuelve (match, warped_elegido, frame_orig_elegido, robust_elegido, idx_elegido).
    Si ninguno produce match, devuelve (None, ..., ...) con valores del actual.
    """
    try:
        from .chess_detector import detect_board_state
    except ImportError:
        from chess_detector import detect_board_state

    # Evaluar el frame actual primero
    current_match = scorer(
        legal_board,
        prev_warped=last_accepted_warped,
        curr_warped=current_warped,
        robust_state=current_robust,
        prev_robust=prev_robust,
    )

    # Atajo: si el frame actual ya tiene un margen amplio, no perdemos tiempo
    if current_match is not None:
        _, _, _, top_alts = current_match
        if len(top_alts) >= 2:
            best_score   = top_alts[0][1]
            second_score = top_alts[1][1]
            if (best_score - second_score) >= 3.0:
                return (current_match, current_warped, current_frame,
                        current_robust, current_idx)

    # Coleccionar candidatos: el actual + los próximos `window_size` frames
    # estables que podamos leer.
    candidates = []   # list[(margin, best_score, match, warped, frame_orig, robust, idx)]
    if current_match is not None:
        ts = current_match[3]   # top_alts
        bs = ts[0][1]
        sc = ts[1][1] if len(ts) >= 2 else float('-inf')
        candidates.append((bs - sc, bs, current_match,
                           current_warped, current_frame, current_robust, current_idx))

    extra_idx = current_idx
    extras_collected = 0
    while extras_collected < window_size:
        ret, frame = video.read()
        if not ret:
            break
        extra_idx += 1
        # Filtrar: descartar frames con mano para no contaminar la votación
        if _hand_in_frame(frame):
            continue
        warped = cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        # Detectar estado YOLO sobre el frame original (lateral)
        try:
            state_now = detect_board_state(warped, original_frame=frame, M=mat)
        except Exception:
            continue
        if not state_now or len(state_now) < MIN_PIECES_TRUST:
            continue
        match = scorer(
            legal_board,
            prev_warped=last_accepted_warped,
            curr_warped=warped,
            robust_state=state_now,
            prev_robust=prev_robust,
        )
        extras_collected += 1
        if match is None:
            continue
        ts = match[3]
        bs = ts[0][1]
        sc = ts[1][1] if len(ts) >= 2 else float('-inf')
        candidates.append((bs - sc, bs, match, warped, frame, state_now, extra_idx))

    if not candidates:
        return (None, current_warped, current_frame, current_robust, current_idx)

    # Elegir el de MAYOR margen; en empate, mayor best_score
    candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
    margin, bs, match, warped, fr, robust, idx = candidates[0]
    logger.info("[BEST-FRAME] Elegido frame %d sobre %d candidatos "
                "(margin=%.2f, best=%.2f)", idx, len(candidates), margin, bs)
    return (match, warped, fr, robust, idx)


def extract_key_frames(video_path, coords, progress_key=None):
    """
    Extrae frames clave usando un pipeline híbrido en 4 fases:

      FASE 1 — Trigger temporal por absdiff: detecta ventanas pixel-estables.
                Determinista, barato, inmune al no-determinismo de YOLO.
      FASE 2 — Lectura semántica con votación multi-shot: YOLO se invoca
                YOLO_VOTING_SHOTS veces dentro de la ventana estable y se
                vota por casilla (>=YOLO_VOTE_MIN_AGREE coincidencias).
      FASE 3 — Plausibilidad física: solo se aceptan diffs en el rango
                físico de un movimiento legal (REAL_MOVE_DIFF_MIN..MAX).
      FASE 4 — Validación legal con python-chess: el cambio observado debe
                corresponder a un movimiento legal sobre el tablero oficial.
                La referencia (last_stable_state) se actualiza al estado
                CANÓNICO post-jugada, NO a la salida YOLO → la referencia
                nunca se contamina con ruido del detector.

    Retorna (key_frames, key_frames_orig, detected_states, mat, accepted_moves).
    Si YOLO no está disponible, delega en _extract_key_frames_absdiff.
    """
    try:
        from .chess_detector import (
            detect_board_state, is_available, _board_to_state,
            invalidate_grid_cache, reset_square_beliefs,
            calibrate_yolo_offset, reset_yolo_offset,
        )
    except ImportError:
        from chess_detector import (
            detect_board_state, is_available, _board_to_state,
            invalidate_grid_cache, reset_square_beliefs,
            calibrate_yolo_offset, reset_yolo_offset,
        )

    mat   = get_matriz(coords)
    video = open_video(video_path)

    if isinstance(video, dict):
        return video

    if not is_available():
        logger.info("[TRIGGER] YOLO no disponible — fallback a detección por absdiff")
        video.release()
        result = _extract_key_frames_absdiff(video_path, coords, progress_key)
        if isinstance(result, dict):
            return result
        kf, kf_orig, *_, m = result
        return kf, kf_orig, [], m, []

    # ── Inicialización ────────────────────────────────────────────────────────
    invalidate_grid_cache()
    reset_square_beliefs()
    reset_yolo_offset()

    total_frames = int(video.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    fps          = video.get(cv2.CAP_PROP_FPS) or 30.0

    key_frames      = []
    key_frames_orig = []
    detected_states = []
    accepted_moves: list[chess.Move] = []   # moves elegidos por Phase 4 (motor A)

    # Tablero oficial: solo para validación legal (Phase 4), NUNCA comparado
    # directamente con YOLO (YOLO detecta ~50% piezas, mismatch ≥ 9 vs canónico).
    legal_board = chess.Board()

    # Referencia YOLO: estado robusto del último keyframe aceptado.
    # None → todavía no hay referencia; el primer ventana estable lo inicializa
    # sin añadir keyframe (bootstrap de la posición inicial vista por YOLO).
    last_robust_state = None     # dict | None
    last_accepted_warped = None  # imagen warpeada del último keyframe aceptado
                                 # (referencia para Phase 4 pixel-diff)

    # FASE 1: estado del detector absdiff
    gray_prev   = None
    stable_run  = 0
    cooldown    = 0
    seen_motion_since_capture = True   # bootstrap: aceptar la 1ª jugada

    # FASE 2: buffer de candidatos durante la ventana estable
    voting_buffer = []  # list[(warped, frame_orig)]

    frame_idx = 0
    accepted  = 0
    rejected_range  = 0
    rejected_legal  = 0
    rejected_pieces = 0

    logger.info("[TRIGGER] Pipeline híbrido — absdiff(stable≥%df) + YOLO×%d-vote + diff∈[%d,%d] "
                "+ legalidad=%s (fps=%.1f)",
                STABLE_FRAMES_REQUIRED, YOLO_VOTING_SHOTS, REAL_MOVE_DIFF_MIN, REAL_MOVE_DIFF_MAX,
                USE_LEGAL_MOVE_VALIDATION, fps)
    logger.info("[TRIGGER] SCORING_STRATEGY='%s' (best_frame_window=%d)",
                SCORING_STRATEGY, BEST_FRAME_WINDOW_SIZE)

    while video.isOpened():
        ret, frame = video.read()
        if not ret:
            break

        frame_idx += 1
        if progress_key:
            set_progress(progress_key, int(frame_idx / total_frames * 50))

        # Warpeo + blur sobre el dominio del tablero — ignora el fondo ruidoso
        warped     = cv2.warpPerspective(frame, mat, (NORMALIZED_SIZE, NORMALIZED_SIZE))
        gray_board = process_image(warped)

        if gray_prev is None:
            gray_prev = gray_board
            continue

        # ── FASE 1: clasificación pixel del frame (sobre warped) ─────────────
        diff_pixels = cv2.absdiff(gray_board, gray_prev)
        _, mask     = cv2.threshold(diff_pixels, ABSDIFF_BIN_THRESHOLD, 255, cv2.THRESH_BINARY)
        ratio       = float(np.count_nonzero(mask)) / mask.size
        gray_prev   = gray_board

        # Log periódico de diagnóstico
        if frame_idx % 60 == 0:
            logger.debug("[FASE1] frame=%d ratio=%.5f stable_run=%d cooldown=%d buf=%d kf=%d",
                         frame_idx, ratio, stable_run, cooldown, len(voting_buffer), len(key_frames))

        # Cooldown post-captura: solo registramos si hubo movimiento
        if cooldown > 0:
            cooldown -= 1
            if ratio > MOTION_PIXEL_RATIO:
                seen_motion_since_capture = True
            continue

        # Movimiento real → resetea cualquier ventana estable en curso
        if ratio > MOTION_PIXEL_RATIO:
            stable_run = 0
            seen_motion_since_capture = True
            voting_buffer.clear()
            continue

        # Frame pixel-estable (ratio ≤ MOTION_PIXEL_RATIO)
        stable_run += 1

        if stable_run < STABLE_FRAMES_REQUIRED or not seen_motion_since_capture:
            continue

        # ── FASE 2: ventana estable alcanzada — recolectar shots y votar ─────
        # Filtrar frames con mano ANTES de añadir al buffer: si la mano sigue
        # visible en un frame estable (jugador lento en retirar la mano), el
        # detector YOLO podría incluir el brazo como pieza. Con votación 2/3,
        # si 2 frames tienen mano, los artefactos se consolidan como "piezas".
        if _hand_in_frame(frame):
            # No añadir al buffer; tampoco resetear stable_run para no retrasar
            # innecesariamente la captura cuando la mano se retira rápido.
            # Sí limpiar el buffer ya acumulado para descartar frames previos
            # que también pueden estar contaminados.
            if voting_buffer:
                voting_buffer.clear()
            continue

        voting_buffer.append((warped, frame.copy()))

        if len(voting_buffer) < YOLO_VOTING_SHOTS:
            continue

        # YOLO sobre el frame ORIGINAL (no warpeado): el modelo fue entrenado
        # en perspectiva natural; el cenital deforma piezas altas y dispara
        # falsas contradicciones. M proyecta el punto base al espacio 1000×1000.
        states = [detect_board_state(w, original_frame=o, M=mat)
                  for w, o in voting_buffer]
        robust = _vote_per_square(states, YOLO_VOTE_MIN_AGREE)
        warped_chosen, frame_chosen = voting_buffer[-1]
        voting_buffer.clear()

        # ── Filtrado canónico post-votación ──────────────────────────────────
        # Si conocemos el estado canónico actual (ya pasamos el bootstrap),
        # eliminamos detecciones YOLO que contradicen casillas que el tablero
        # canónico dice que no deberían haber cambiado con respecto al
        # último keyframe aceptado.
        # No eliminamos las casillas que podrían corresponder a un movimiento
        # real (las comparamos en Phase 4). Solo eliminamos detecciones en
        # casillas que el canónico y YOLO previo ya marcaban como vacías y
        # que YOLO ahora dice estar ocupadas (falsos positivos puros del Bayes).
        if last_robust_state is not None:
            robust_filtered = {}
            for sq, sym in robust.items():
                canon_piece = legal_board.piece_at(sq)
                # Mantener la detección si:
                # (a) El canónico también tiene pieza en esta casilla (coincidencia)
                # (b) El canónico tiene pieza diferente (posible movimiento real)
                # (c) El canónico dice vacío Y el YOLO previo también decía vacío
                #     → es un FP puro del Bayes, eliminar.
                # Criterio: eliminar SOLO si canonico=vacío Y yolo_prev=vacío Y yolo_ahora=pieza
                if canon_piece is None and last_robust_state.get(sq) is None:
                    # Falso positivo nuevo que no estaba antes → descartar
                    logger.debug("[TRIGGER] FP canónico descartado: %s=%s (canónico vacío, YOLO previo vacío)",
                                 chess.square_name(sq), sym)
                else:
                    robust_filtered[sq] = sym
            if len(robust_filtered) >= MIN_PIECES_TRUST:
                robust = robust_filtered
            else:
                # Si el filtro elimina demasiadas piezas, usar el estado sin filtrar
                logger.debug("[TRIGGER] Filtrado canónico descartado (demasiado agresivo): %d→%d piezas",
                             len(robust), len(robust_filtered))

        if len(robust) < MIN_PIECES_TRUST:
            rejected_pieces += 1
            logger.info("[TRIGGER] Estado robusto pobre (%d piezas) frame %d — descartado",
                        len(robust), frame_idx)
            stable_run = 0
            continue

        # ── Bootstrap: primera ventana estable = posición inicial vista por YOLO ──
        if last_robust_state is None:
            # Auto-calibrar el offset YOLO usando la posición inicial estándar.
            # Compensa el sesgo sistemático del bbox (la base se reporta
            # más arriba de donde la pieza realmente toca el tablero).
            calibrate_yolo_offset(warped_chosen, frame_chosen, mat)

            # Re-ejecutar YOLO UNA sola vez con el offset ya aplicado.
            # El modelo es determinista → repetir el mismo frame no añade información.
            # Usamos el frame elegido del voting_buffer (mejor calidad visual).
            state_recalibrated = detect_board_state(warped_chosen, original_frame=frame_chosen, M=mat)
            if state_recalibrated and len(state_recalibrated) >= MIN_PIECES_TRUST:
                robust = state_recalibrated

            last_robust_state = robust
            last_accepted_warped = warped_chosen.copy()
            logger.info("[TRIGGER] Estado inicial YOLO capturado (%d piezas) frame %d — sin keyframe",
                        len(robust), frame_idx)
            stable_run = 0
            seen_motion_since_capture = False
            continue

        # ── FASE 3: sanity check (siempre actualizar referencia) ──────────────
        # Guardamos el estado anterior ANTES de actualizar la referencia para
        # medir la delta real entre scans consecutivos.
        # La referencia se actualiza en CADA votación (tanto si se acepta como
        # si se rechaza): así el diff siempre mide la última ventana, no el
        # acumulado de toda la partida desde el bootstrap.
        prev_robust       = last_robust_state
        last_robust_state = robust            # actualizar SIEMPRE aquí

        d = _diff_states(prev_robust, robust)

        if d == 0:
            # Misma detección que el scan anterior → sin movimiento, ignorar
            stable_run = 0
            continue

        # Sanity check: límites muy amplios, el filtro real es Phase 4
        if not (REAL_MOVE_DIFF_MIN <= d <= REAL_MOVE_DIFF_MAX):
            rejected_range += 1
            logger.info("[TRIGGER] Diff fuera de rango (%d) frame %d — descartado [piezas_yolo=%d]",
                        d, frame_idx, len(robust))
            stable_run = 0
            continue

        if _hand_in_frame(frame_chosen):
            # Revertir la actualización de last_robust_state: el estado detectado
            # durante la ventana con mano está contaminado (oclusiones, sombras).
            # Si no revertimos, prev_robust en la próxima iteración será el estado
            # de la mano y el delta resultante será artificialmente grande → falsos positivos.
            last_robust_state = prev_robust
            logger.info("[TRIGGER] Mano visible frame %d — estado revertido, esperando retirada", frame_idx)
            stable_run = 0
            voting_buffer.clear()
            continue

        # ── FASE 4: validación legal por PIXEL-DIFF + python-chess ────────────
        # Selección del scorer según SCORING_STRATEGY (configurado al inicio
        # del módulo). "full_state" usa la opción C (comparación de estado
        # completo); cualquier otro valor usa el scorer por señales sueltas.
        if "full_state" in SCORING_STRATEGY:
            _phase4_scorer = _match_state_change_to_legal_move_full_state
        else:
            _phase4_scorer = _match_state_change_to_legal_move

        move = None
        if USE_LEGAL_MOVE_VALIDATION:
            # Si "best_frame" está activo, recolectamos varios candidatos y nos
            # quedamos con el mejor por score y margen. Si no, evaluamos solo
            # el frame actual (comportamiento original).
            if "best_frame" in SCORING_STRATEGY:
                match, chosen_warped, chosen_orig, chosen_robust, chosen_idx = (
                    _evaluate_best_frame_in_window(
                        video, mat, legal_board,
                        last_accepted_warped, warped_chosen, frame_chosen,
                        robust, prev_robust, frame_idx,
                        scorer=_phase4_scorer,
                        window_size=BEST_FRAME_WINDOW_SIZE,
                    )
                )
                # Reemplazar el frame elegido (puede haber avanzado en la ventana)
                if match is not None:
                    warped_chosen     = chosen_warped
                    frame_chosen      = chosen_orig
                    robust            = chosen_robust
                    last_robust_state = robust
                    frame_idx         = chosen_idx
            else:
                match = _phase4_scorer(
                    legal_board,
                    prev_warped=last_accepted_warped,
                    curr_warped=warped_chosen,
                    robust_state=robust,
                    prev_robust=prev_robust,
                )
            if match is None:
                rejected_legal += 1
                logger.info("[TRIGGER] Sin movimiento legal compatible (d_yolo=%d) "
                            "frame %d — descartado [piezas_yolo=%d]", d, frame_idx, len(robust))
                stable_run = 0
                continue
            move, expected_state, err, top_alts = match
            try:
                move_san = legal_board.san(move)
            except Exception:
                move_san = move.uci()
            best_score = top_alts[0][1]
            alts_str = ", ".join(f"{san}({s:.2f})" for san, s in top_alts[1:])
            legal_board.push(move)
            accepted += 1
            logger.info("[TRIGGER] ✓ Keyframe #%d confirmado (frame %d, move=%s [%s], "
                        "score=%.2f, err=%d, piezas_yolo=%d, alts=[%s])",
                        len(key_frames)+1, frame_idx, move_san, move.uci(),
                        best_score, err, len(robust), alts_str)
        else:
            accepted += 1
            logger.info("[TRIGGER] ✓ Keyframe #%d confirmado (frame %d, d=%d, piezas=%d) [sin val. legal]",
                        len(key_frames)+1, frame_idx, d, len(robust))

        # Deduplicación: descartar si el delta YOLO vs el último keyframe aceptado
        # es 0 (mismo estado visual → duplicado capturado antes del cooldown).
        if key_frames and _diff_states(detected_states[-1], last_robust_state) == 0:
            rejected_range += 1
            # Si ya hicimos push del move, hay que deshacerlo para no corromper
            # el legal_board: el keyframe se descarta pero el move ya estaba
            # registrado por _match_state_change_to_legal_move.
            if move is not None and legal_board.move_stack and legal_board.move_stack[-1] == move:
                legal_board.pop()
            logger.info("[TRIGGER] Duplicado descartado frame %d (mismo estado que keyframe #%d)",
                        frame_idx, len(key_frames))
            stable_run = 0
            continue

        # Confirmar keyframe (incluyendo el move escogido por Phase 4)
        key_frames.append(warped_chosen)
        key_frames_orig.append(frame_chosen)
        detected_states.append(last_robust_state)
        accepted_moves.append(move)   # None si USE_LEGAL_MOVE_VALIDATION=False

        # Actualizar referencia pixel-diff para Phase 4 del próximo keyframe
        last_accepted_warped = warped_chosen.copy()

        cooldown   = COOLDOWN_AFTER_CAPTURE
        stable_run = 0
        seen_motion_since_capture = False

    video.release()
    logger.info("[TRIGGER] Extracción completada: %d keyframes — "
                "aceptados=%d, rechazados[rango=%d, legal=%d, piezas=%d], frames totales=%d",
                len(key_frames), accepted, rejected_range, rejected_legal, rejected_pieces, frame_idx)
    return key_frames, key_frames_orig, detected_states, mat, accepted_moves


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
        logger.info("[CORNERS] Detectado con umbral adaptativo")
        _save_corner_debug(result, "adaptive threshold")
        return result

    # Fallback: recorte central del 80% (margen 10% por lado)
    logger.warning("[CORNERS] Auto-detección falló, usando recorte central (80%)")
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
