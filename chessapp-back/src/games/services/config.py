"""
Constantes y rutas de configuración del paquete `services`.

Este módulo no contiene lógica: sólo umbrales, rutas y banderas que el resto
del paquete consume. No depende de ningún otro submódulo de `services` ni de
`chess_detector` — sólo de `os.path` y de `django.conf.settings`.

Las constantes específicas de la fase WHICH (CASCADE_*, K_HYPOTHESES, LEADER_*)
viven dentro de `identify_moves_from_keyframes` porque son parámetros locales
de su maquinaria multi-hipótesis, no configuración global.
"""

import os
from django.conf import settings

# -----------------------------------------------------------------------------
# Rutas en MEDIA_ROOT y BASE_DIR
# -----------------------------------------------------------------------------
TEMP_VIDEOS_LOCATION     = os.path.join(settings.MEDIA_ROOT, 'temp_videos')
TEMP_FRAMES_LOCATION     = os.path.join(settings.MEDIA_ROOT, 'temp_frames')
ENGINES_DIR              = os.path.join(settings.BASE_DIR, 'misc', 'engines')
DEBUG_LOCATION           = os.path.join(settings.MEDIA_ROOT, 'debug')
FENS_LOCATION            = os.path.join(settings.MEDIA_ROOT, 'fens')
ENGINE_ANALYSIS_LOCATION = os.path.join(settings.MEDIA_ROOT, 'engine_analysis')

# -----------------------------------------------------------------------------
# Tablero warpeado
# -----------------------------------------------------------------------------
NORMALIZED_SIZE = 1000

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


__all__ = [
    # Rutas
    'TEMP_VIDEOS_LOCATION', 'TEMP_FRAMES_LOCATION', 'ENGINES_DIR',
    'DEBUG_LOCATION', 'FENS_LOCATION', 'ENGINE_ANALYSIS_LOCATION',
    # Tablero warpeado
    'NORMALIZED_SIZE', 'CELL_ROI_TOP', 'CELL_ROI_BOTTOM',
    # Trigger absdiff
    'ABSDIFF_BIN_THRESHOLD', 'MOTION_PIXEL_RATIO', 'STABLE_FRAMES_REQUIRED',
    'COOLDOWN_AFTER_CAPTURE', 'LONG_MOTION_THRESHOLD', 'LONG_MOTION_EXTRA_STABLE',
    # Scorer ocupación / Jaccard
    'STABLE_WINDOW_SIZE', 'OCC_VARIANCE_TOP_K', 'OCC_VARIANCE_MIN_THR',
    'JACCARD_ACCEPT_THR', 'JACCARD_MARGIN_REQ',
    'RECOVERY_REJECT_THR', 'RECOVERY_MATCH_THR', 'RECOVERY_DEPTH',
    # Modos
    'WHEN_ONLY_MODE',
    # Filtro refractario
    'REFRACTORY_WINDOW', 'REFRACTORY_MIN_VAR_RATIO',
    # Fusión de keyframes
    'FUSE_DUPLICATES', 'FUSE_WEAK_TOP_VAR', 'FUSE_MODERATE_TOP_VAR',
    'FUSE_CONCENTRATION_RATIO', 'FUSE_TEMPORAL_FRAMES',
    # Iluminación
    'LIGHTING_REJECT_TOP_VAR', 'LIGHTING_REJECT_RATIO',
    # Multi-move
    'MULTI_MIN_EXTRA_VAR', 'MULTI_MARGIN_OVER_SINGLE',
    'MULTI_MIN_FALLBACK_SCORE_BONUS',
]
