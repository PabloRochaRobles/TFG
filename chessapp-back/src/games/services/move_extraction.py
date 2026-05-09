"""
move_extraction.py — Fase WHEN del pipeline de detección.

Recorre el vídeo frame a frame, dispara absdiff para detectar momentos de
movimiento y de estabilidad, acumula ventanas estables y emite la lista de
keyframes en los que se produjo una jugada. No identifica QUÉ jugada fue
(eso lo hace la fase WHICH en `move_identification.py`); sólo decide CUÁNDO.

Funciones públicas:
  - extract_key_frames(video_path, coords, progress_key) — wrapper que delega
    en `_extract_key_frames_occupancy`. Retorna 8-tupla:
      (key_frames, key_frames_orig, detected_states, mat, accepted_moves,
       key_frame_indices, bootstrap_warped, bootstrap_orig)
"""

import logging
import os

import cv2
import chess
import numpy as np

from .config import *  # noqa: F401,F403  (constantes WHEN/visión)
from .progress import set_progress
from .video_io import open_video, get_matriz, process_image, save_debug_image
from .matchers import (
    _cell_variance_map,
    _changed_squares_occ,
    _fuse_consecutive_duplicate_keyframes,
    _match_move_by_jaccard,
    _move_changed_squares,
    _try_multi_move_jaccard,
    _try_state_recovery,
    _variance_diff_all,
)

logger = logging.getLogger(__name__)


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
        from ..chess_detector import invalidate_grid_cache
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
    # Sin esto, WHICH usaba el frame 0 crudo, que difiere del bootstrap en
    # jitter de cámara/iluminación y produce diffs contaminados que penalizan
    # los movimientos correctos en la primera comparación → cascada de errores.
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
                        if last_motion_duration > LONG_MOTION_THRESHOLD
                        else 0)

        if stable_run < STABLE_FRAMES_REQUIRED + extra_stable or not seen_motion_since_capture:
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
                "rej_refractory=%d",
                accepted, initial_count, fused_count,
                rejected_occ, rejected_jaccard, rejected_repeat,
                rejected_diffuse, rejected_refractory)

    return (key_frames, key_frames_orig, detected_states, mat, accepted_moves,
            key_frame_indices, bootstrap_warped, bootstrap_orig)




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


