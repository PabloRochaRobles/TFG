"""Module 5: legal-move inference from a noisy per-square observation.

Given the current ``chess.Board`` state and an ``(8, 8, 13)`` probability tensor
from the per-square classifier, evaluate every legal move (and optionally the
"no move" and "two missed plies" hypotheses) and pick the move sequence whose
*resulting position* best explains the observation.

This is the core of the system: the chess-rules constraint converts a noisy
per-square classifier into a near-perfect game tracker, because the search
space of legal moves at each ply is tiny (~30) compared to the space of
arbitrary 8x8 grids (13 ** 64).

This module can be exercised end-to-end *without a trained classifier* by
feeding it perfect probabilities synthesised from a known PGN — that is what
the self-test below does, and it is also how the rest of the pipeline can be
debugged before module 3 produces real predictions.
"""
from __future__ import annotations

from dataclasses import dataclass

import chess
import numpy as np

from .position_to_fen import NUM_CLASSES, PIECE_TO_INDEX, indices_to_grid


# --- python-chess <-> grid bridge -------------------------------------------


def board_to_indices(board: chess.Board) -> np.ndarray:
    """Return an ``(8, 8) int64`` piece-index grid (row 0 = rank 8, col 0 = a)."""
    grid = np.zeros((8, 8), dtype=np.int64)
    for sq in chess.SQUARES:
        piece = board.piece_at(sq)
        if piece is None:
            continue
        row = 7 - chess.square_rank(sq)
        col = chess.square_file(sq)
        grid[row, col] = PIECE_TO_INDEX[piece.symbol()]
    return grid


def board_to_grid(board: chess.Board) -> np.ndarray:
    """Return an ``(8, 8) U1`` piece-symbol grid (e.g. 'P', '.', 'k')."""
    return indices_to_grid(board_to_indices(board))


def hard_labels_to_probs(
    grid_indices: np.ndarray, off_class: float = 1e-3
) -> np.ndarray:
    """Build an ``(8, 8, NUM_CLASSES)`` probability tensor from argmax labels.

    Each ``(r, c)`` gets ``1 - off_class * (NUM_CLASSES - 1)`` on the predicted
    class and ``off_class`` on every other class. Useful for unit tests and as
    a fallback when only hard labels are available.
    """
    if grid_indices.shape != (8, 8):
        raise ValueError(f"expected (8,8), got {grid_indices.shape}")
    probs = np.full((8, 8, NUM_CLASSES), off_class, dtype=np.float64)
    rows, cols = np.indices((8, 8))
    probs[rows, cols, grid_indices] = 1.0 - off_class * (NUM_CLASSES - 1)
    return probs


# --- Inference --------------------------------------------------------------


@dataclass
class InferenceResult:
    """Result of evaluating an observation against the legal moves.

    Attributes:
        moves: 0 = no move detected, 1 = a single move, 2+ = multiple plies
            recovered at once (the upstream stable-frame detector missed some).
        score: mean log-probability of the observation under the chosen
            hypothesis. Closer to 0 is better; very negative means poor fit.
        margin: ``score - second_best_score``. Larger = more decisive.
        no_move_score: score if we assumed nothing changed since ``board``.
            The caller can compare against ``score`` to detect "the player
            hasn't moved yet" or "a piece was knocked sideways".
    """

    moves: tuple[chess.Move, ...]
    score: float
    margin: float
    no_move_score: float

    @property
    def legal(self) -> bool:
        return len(self.moves) > 0

    @property
    def primary(self) -> chess.Move | None:
        """The latest move applied, or None if no-move was the best hypothesis."""
        return self.moves[-1] if self.moves else None


def infer_move(
    board: chess.Board,
    probs: np.ndarray,
    max_extra_plies: int = 1,
) -> InferenceResult:
    """Find the best legal move sequence consistent with ``probs``.

    Args:
        board: state BEFORE the move whose effect is being observed. Not
            mutated (a copy is used internally).
        probs: ``(8, 8, NUM_CLASSES)`` classifier probabilities.
        max_extra_plies: extend the search by up to this many extra plies,
            allowing recovery if the upstream stable-frame detector missed
            one or more moves. Default 1 -> search depth in {1, 2}.

    Returns:
        InferenceResult. ``result.legal`` is False if the observation is best
        explained by "no move occurred". Always inspect ``margin`` and
        ``score`` before accepting.
    """
    if probs.shape != (8, 8, NUM_CLASSES):
        raise ValueError(f"probs must be (8,8,{NUM_CLASSES}), got {probs.shape}")
    if max_extra_plies < 0:
        raise ValueError(f"max_extra_plies must be >= 0, got {max_extra_plies}")

    log_probs = np.log(np.clip(probs, 1e-9, None))

    work = board.copy()
    no_move_score = _score(log_probs, board_to_indices(work))

    candidates: list[tuple[tuple[chess.Move, ...], float]] = [((), no_move_score)]
    _expand(work, log_probs, candidates, prefix=(), depth_left=1 + max_extra_plies)

    candidates.sort(key=lambda x: x[1], reverse=True)
    best_moves, best_score = candidates[0]
    second_score = candidates[1][1] if len(candidates) > 1 else float("-inf")

    return InferenceResult(
        moves=best_moves,
        score=best_score,
        margin=best_score - second_score,
        no_move_score=no_move_score,
    )


def _expand(
    board: chess.Board,
    log_probs: np.ndarray,
    out: list[tuple[tuple[chess.Move, ...], float]],
    prefix: tuple[chess.Move, ...],
    depth_left: int,
) -> None:
    if depth_left == 0:
        return
    # Materialise legal moves so push/pop within the loop cannot disturb iteration.
    for move in list(board.legal_moves):
        board.push(move)
        seq = prefix + (move,)
        score = _score(log_probs, board_to_indices(board))
        out.append((seq, score))
        _expand(board, log_probs, out, prefix=seq, depth_left=depth_left - 1)
        board.pop()


def _score(log_probs: np.ndarray, expected_idx: np.ndarray) -> float:
    """Mean log-probability of the observation given the expected position."""
    rows, cols = np.indices((8, 8))
    return float(log_probs[rows, cols, expected_idx].mean())


# --- Self-test --------------------------------------------------------------


if __name__ == "__main__":
    from .position_to_fen import initial_grid

    # 1) board_to_grid on the start position equals the canonical initial grid.
    assert (board_to_grid(chess.Board()) == initial_grid()).all()

    # 2) Perfect observation -> exact recovery of 1.e4.
    after = chess.Board()
    after.push_san("e4")
    probs = hard_labels_to_probs(board_to_indices(after))

    res = infer_move(chess.Board(), probs)
    assert res.legal and res.primary == chess.Move.from_uci("e2e4")
    assert res.margin > 0
    print(f"  1.e4              ok  score={res.score:+.4f}  margin={res.margin:+.4f}")

    # 3) Two-ply recovery: we missed e4 and only see the position after 1.e4 c5.
    after = chess.Board()
    after.push_san("e4")
    after.push_san("c5")
    probs = hard_labels_to_probs(board_to_indices(after))
    res = infer_move(chess.Board(), probs, max_extra_plies=1)
    assert len(res.moves) == 2, res.moves
    assert res.moves[0] == chess.Move.from_uci("e2e4")
    assert res.moves[1] == chess.Move.from_uci("c7c5")
    print(f"  1.e4 c5 (2-ply)   ok  recovered {[m.uci() for m in res.moves]}")

    # 4) No-move detection: observation matches the *current* board.
    cur = chess.Board()
    cur.push_san("e4")
    probs = hard_labels_to_probs(board_to_indices(cur))
    res = infer_move(cur, probs)
    assert not res.legal, f"expected no-move, got {res.moves}"
    print(f"  no-move           ok  no_move_score={res.no_move_score:+.4f}")

    # 5) Castling (king + rook move in one ply).
    pre = chess.Board("r3k2r/pppppppp/8/8/8/8/PPPPPPPP/R3K2R w KQkq - 0 1")
    after = pre.copy(); after.push_san("O-O")
    probs = hard_labels_to_probs(board_to_indices(after))
    res = infer_move(pre, probs)
    assert res.legal and res.primary == chess.Move.from_uci("e1g1")
    print(f"  O-O (castling)    ok  -> {res.primary.uci()}")

    # 6) Promotion to queen.
    pre = chess.Board("8/4P3/8/8/8/8/8/4k2K w - - 0 1")
    after = pre.copy(); after.push_san("e8=Q")
    probs = hard_labels_to_probs(board_to_indices(after))
    res = infer_move(pre, probs)
    assert res.legal and res.primary == chess.Move.from_uci("e7e8q")
    print(f"  e8=Q (promotion)  ok  -> {res.primary.uci()}")

    # 7) En passant.
    pre = chess.Board("rnbqkbnr/ppp1p1pp/8/3pPp2/8/8/PPPP1PPP/RNBQKBNR w KQkq f6 0 3")
    after = pre.copy(); after.push_san("exf6")  # en passant capture
    probs = hard_labels_to_probs(board_to_indices(after))
    res = infer_move(pre, probs)
    assert res.legal and res.primary == chess.Move.from_uci("e5f6")
    print(f"  exf6 (en passant) ok  -> {res.primary.uci()}")

    # 8) Full short game: every move is recovered from a perfect observation.
    moves_san = ["e4", "c5", "Nf3", "d6", "d4", "cxd4", "Nxd4", "Nf6",
                 "Nc3", "a6", "Be2", "e5", "Nb3", "Be7", "O-O", "O-O"]
    tracker = chess.Board()      # what infer_move builds up
    truth = chess.Board()        # ground truth from the SAN list
    inferred_uci: list[str] = []
    for san in moves_san:
        truth.push_san(san)
        probs = hard_labels_to_probs(board_to_indices(truth))
        res = infer_move(tracker, probs)
        assert res.legal, f"failed at move '{san}'"
        tracker.push(res.primary)
        inferred_uci.append(res.primary.uci())
    assert tracker.fen() == truth.fen(), (tracker.fen(), truth.fen())
    print(f"  16-move game      ok  final FEN matches truth")

    print("\nmove_inferencer self-tests passed.")
