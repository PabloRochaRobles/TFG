"""
matchers.py — Helpers compartidos por las fases WHEN y WHICH de detección.

Funciones puras (frame → score / dict / set) que computan:
  • Cambios pixel-a-pixel sobre la cuadrícula real (Hough) del tablero.
  • Mapas de varianza por casilla y comparaciones contra una referencia.
  • Estados YOLO (símbolos por casilla) y métricas de acuerdo entre estados.
  • Matching de un cambio observado contra la lista de movimientos legales
    (Jaccard, multi-move, score por varianza, desempates).
  • Recuperación: BFS sobre posiciones alcanzables cuando hay desincronización.
  • Fusión post-extracción de keyframes duplicados.

Sin estado global. Sólo dependen de:
  - opencv (`cv2`), numpy, python-chess.
  - Constantes de `services.config`.
  - Lazy import puntual de `.chess_detector._grid_for_frame` dentro de
    `_pixel_changed_squares` para usar la grid Hough real.
"""

import logging
import math
from collections import deque

import cv2
import chess
import numpy as np

from .config import *  # noqa: F401,F403  (constantes compartidas)

logger = logging.getLogger(__name__)


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
        from ..chess_detector import _grid_for_frame
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

