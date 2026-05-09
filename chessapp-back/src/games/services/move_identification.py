"""
move_identification.py — Fase WHICH del pipeline de detección.

Recibe la lista de keyframes producida por la fase WHEN y devuelve la secuencia
de movimientos jugados, en orden de juego. Es un orquestador modal que combina:

  • Modo LINEAL (default): UNA hipótesis del estado del tablero. En cada
    keyframe se aplican 7+ capas de matching (`_run_kf_matchers`):
    YOLO-DIFF → STATE → CONSENSUS → YOLO+VAR → YOLO-DOUBLE → PURE-VAR →
    PHANTOM → JACCARD → MULTI → RECOVERY → FORCED → SKIP.
  • Modo MULTI (bajo demanda): tras N kfs consecutivos con score bajo se
    asume desincronización del tablero canónico y se ramifica en K hipótesis
    paralelas. Las hipótesis viven hasta que una domina o se alcanza un
    timeout (kfs o segundos).
  • Selección final: hipótesis ganadora por MÁXIMA PRECISIÓN
    (high_quality_count, avg_score, n_movs).

Función pública:
  - identify_moves_from_keyframes(...) → (moves, skipped_indices, stats)

Sus constantes específicas (CASCADE_*, K_HYPOTHESES, LEADER_*, HQ_THR, etc.)
viven como locales dentro de la función — son tunables del algoritmo, no
configuración global del paquete.
"""

import logging
import time
from collections import deque

import cv2
import chess
import numpy as np

from .matchers import (
    _board_to_state_symbols,
    _break_tie_by_variance,
    _intelligent_tiebreak,
    _match_move_by_jaccard,
    _move_changed_squares,
    _pure_variance_match,
    _try_multi_move_jaccard,
    _try_state_recovery,
    _variance_diff_all,
    _variance_score_for_move,
    _yolo_change_centroid_tiebreak,
    _yolo_diff_squares,
    _yolo_match_double_move,
    _yolo_match_single_move,
    _yolo_match_single_move_diff,
    _yolo_score_state,
)

logger = logging.getLogger(__name__)


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
    progress_callback=None,
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
            from ..chess_detector import (
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

    n_kfs_total = max(1, len(key_frames) - 1)
    for i in range(1, len(key_frames)):
        # Reporte de progreso para que la barra del frontend avance durante
        # la fase WHICH (antes se quedaba parada al 50% varios minutos).
        if progress_callback is not None:
            try:
                progress_callback(i / n_kfs_total)
            except Exception:
                pass  # nunca abortar el análisis por un fallo en el callback

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


