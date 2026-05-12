"""Module 6: end-to-end orchestrator.

Reads a video and a calibration, drives modules 1-5, and produces the
reconstructed game (board state, FEN sequence, move list).

Decision logic per stable frame from module 2:
    * If the classifier produces a very poor observation (mean log-prob below
      ``score_floor``) we skip the frame as garbage. This catches hand-on-board
      shots and severe lighting glitches that module 2 didn't filter.
    * If module 5 picks "no move" as the best hypothesis (``not result.legal``)
      we skip — duplicate frames of the previous position, or pauses where the
      player hasn't acted yet.
    * If the chosen move sequence has a margin below ``margin_threshold``
      (default off) we treat the frame as ambiguous and skip — wait for the
      next stable frame.
    * Otherwise we accept the move(s) and advance the board. ``max_extra_plies``
      enables 2-ply recovery for moves missed by module 2.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

import chess
import chess.pgn

from .board_detector import BoardCalibration, load_calibration
from .frame_selector import StableFrame, iter_stable_frames
from .move_inferencer import infer_move
from .square_classifier.infer import SquareClassifierInference


@dataclass
class FrameDecision:
    """What the orchestrator did with one stable frame."""

    frame_index: int
    timestamp: float
    decision: str
    """One of: 'move', 'no-move', 'low-margin', 'garbage'."""
    moves: tuple[chess.Move, ...]
    """Moves applied (length 1 normally; 2 with 2-ply recovery; 0 otherwise)."""
    score: float
    margin: float
    no_move_score: float


@dataclass
class GameResult:
    board: chess.Board
    fens: list[str]
    moves: list[chess.Move]
    decisions: list[FrameDecision] = field(default_factory=list)

    def to_pgn_game(self) -> chess.pgn.Game:
        game = chess.pgn.Game()
        node: chess.pgn.GameNode = game
        for m in self.moves:
            node = node.add_variation(m)
        return game

    def to_pgn(self) -> str:
        return str(self.to_pgn_game())

    def stats(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.decisions:
            out[d.decision] = out.get(d.decision, 0) + 1
        return out


ProgressCallback = Callable[[FrameDecision, StableFrame], None]


def process_video(
    video_path: Path | str,
    calibration: BoardCalibration | Path | str,
    classifier: SquareClassifierInference | Path | str,
    *,
    score_floor: float = -3.0,
    margin_threshold: float = 0.10,
    max_extra_plies: int = 1,
    progress: ProgressCallback | None = None,
    stable_frame_kwargs: dict | None = None,
) -> GameResult:
    """Reconstruct the game played in ``video_path``.

    Args:
        video_path: input video file.
        calibration: ``BoardCalibration`` or path to a calibration JSON.
        classifier: ``SquareClassifierInference`` or path to a checkpoint.
        score_floor: minimum acceptable mean log-prob. Frames whose best
            hypothesis scores below this are dropped as garbage.
        margin_threshold: minimum required margin between best and second-best
            hypothesis. Default 0 disables the check.
        max_extra_plies: forwarded to :func:`infer_move`. Default 1 enables
            2-ply recovery if module 2 missed a move.
        progress: optional callback invoked after each stable frame.
        stable_frame_kwargs: extra kwargs forwarded to ``iter_stable_frames``.
    """
    if isinstance(calibration, (str, Path)):
        calibration = load_calibration(calibration)
    if isinstance(classifier, (str, Path)):
        classifier = SquareClassifierInference.load(classifier)

    sf_kwargs = dict(stable_frame_kwargs or {})

    board = chess.Board()
    fens = [board.fen()]
    moves: list[chess.Move] = []
    decisions: list[FrameDecision] = []

    for stable in iter_stable_frames(video_path, calibration, **sf_kwargs):
        probs = classifier.classify_position(stable.warped)
        result = infer_move(board, probs, max_extra_plies=max_extra_plies)

        applied: tuple[chess.Move, ...] = ()
        if result.score < score_floor:
            decision_type = "garbage"
        elif not result.legal:
            decision_type = "no-move"
        elif result.margin < margin_threshold:
            decision_type = "low-margin"
        else:
            decision_type = "move"
            applied = result.moves
            for m in applied:
                board.push(m)
                moves.append(m)
                fens.append(board.fen())

        dec = FrameDecision(
            frame_index=stable.frame_index,
            timestamp=stable.timestamp,
            decision=decision_type,
            moves=applied,
            score=result.score,
            margin=result.margin,
            no_move_score=result.no_move_score,
        )
        decisions.append(dec)
        if progress is not None:
            progress(dec, stable)

        if board.is_game_over():
            break

    return GameResult(board=board, fens=fens, moves=moves, decisions=decisions)


def compare_with_ground_truth(
    reconstructed: list[chess.Move], truth_pgn_path: Path | str,
) -> dict:
    """Compare a reconstructed move list with the mainline of a PGN.

    Returns a dict with keys: ``truth_plies``, ``reconstructed_plies``,
    ``match_until``, ``correct``, ``first_mismatch`` (None if match).
    """
    with Path(truth_pgn_path).open() as f:
        game = chess.pgn.read_game(f)
    if game is None:
        raise ValueError(f"Could not parse PGN: {truth_pgn_path}")
    truth = list(game.mainline_moves())
    n = min(len(truth), len(reconstructed))
    correct = 0
    first_mismatch: int | None = None
    for i in range(n):
        if truth[i] == reconstructed[i]:
            correct += 1
        elif first_mismatch is None:
            first_mismatch = i
    return {
        "truth_plies": len(truth),
        "reconstructed_plies": len(reconstructed),
        "match_until": n,
        "correct": correct,
        "first_mismatch": first_mismatch,
        "truth_moves": truth,
        "reconstructed_moves": list(reconstructed),
    }
