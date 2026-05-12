"""Module 4: 8x8 grid <-> FEN conversion (pure string/array manipulation).

The canonical grid is a ``(8, 8)`` numpy array of single-character piece codes:

    Row 0 = rank 8 (top of warped image)
    Row 7 = rank 1 (bottom)
    Col 0 = file a (left)
    Col 7 = file h (right)

    grid[row, col] is one of:
        '.'                          empty
        'P','N','B','R','Q','K'      white pieces
        'p','n','b','r','q','k'      black pieces

This orientation matches both the warped image produced by ``board_detector``
and the row order used by FEN (FEN lists ranks 8 -> 1, files a -> h).

The FEN metadata fields (turn, castling, en passant, halfmove, fullmove) are
not derivable from a single position; they are tracked by python-chess in
module 5. Use ``grid_to_fen_board`` for the board portion alone, or
``grid_to_fen`` with explicit metadata.
"""
from __future__ import annotations

import numpy as np


EMPTY = "."

# Index 0 = empty; 1..6 = white pieces; 7..12 = black pieces.
PIECES: tuple[str, ...] = (
    EMPTY,
    "P", "N", "B", "R", "Q", "K",
    "p", "n", "b", "r", "q", "k",
)
PIECE_TO_INDEX: dict[str, int] = {p: i for i, p in enumerate(PIECES)}
INDEX_TO_PIECE: tuple[str, ...] = PIECES
NUM_CLASSES: int = len(PIECES)  # 13

INITIAL_FEN: str = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1"


# --- Conversions ------------------------------------------------------------


def grid_to_fen_board(grid: np.ndarray) -> str:
    """Return only the board portion of a FEN (8 ranks separated by '/')."""
    arr = _validate_grid(grid)
    rows: list[str] = []
    for row in arr:
        run = 0
        out: list[str] = []
        for ch in row:
            if ch == EMPTY:
                run += 1
            else:
                if run:
                    out.append(str(run))
                    run = 0
                out.append(str(ch))
        if run:
            out.append(str(run))
        rows.append("".join(out))
    return "/".join(rows)


def grid_to_fen(
    grid: np.ndarray,
    turn: str = "w",
    castling: str = "KQkq",
    en_passant: str = "-",
    halfmove: int = 0,
    fullmove: int = 1,
) -> str:
    """Return a full FEN string. Defaults assume start-of-game metadata."""
    if turn not in ("w", "b"):
        raise ValueError(f"turn must be 'w' or 'b', got {turn!r}")
    return (
        f"{grid_to_fen_board(grid)} {turn} {castling or '-'} "
        f"{en_passant} {halfmove} {fullmove}"
    )


def fen_to_grid(fen: str) -> np.ndarray:
    """Parse a FEN (board portion or full) and return the 8x8 grid."""
    if not isinstance(fen, str) or not fen.strip():
        raise ValueError(f"fen must be a non-empty string, got {fen!r}")
    board_part = fen.split(" ", 1)[0]
    rows = board_part.split("/")
    if len(rows) != 8:
        raise ValueError(f"FEN must have 8 rows, got {len(rows)}: {fen!r}")
    grid = np.full((8, 8), EMPTY, dtype="<U1")
    for r, row in enumerate(rows):
        col = 0
        for ch in row:
            if ch.isdigit():
                col += int(ch)
            elif ch in PIECE_TO_INDEX and ch != EMPTY:
                if col >= 8:
                    raise ValueError(f"Row {r} overflows 8 squares: {row!r}")
                grid[r, col] = ch
                col += 1
            else:
                raise ValueError(f"Invalid FEN character {ch!r} in row {row!r}")
        if col != 8:
            raise ValueError(f"Row {r} has {col} squares, expected 8: {row!r}")
    return grid


# --- Index <-> grid (for the classifier in module 3) ------------------------


def grid_to_indices(grid: np.ndarray) -> np.ndarray:
    """Map an 8x8 grid of piece chars to ``(8, 8) int64`` class indices."""
    arr = _validate_grid(grid)
    out = np.zeros((8, 8), dtype=np.int64)
    for r in range(8):
        for c in range(8):
            out[r, c] = PIECE_TO_INDEX[str(arr[r, c])]
    return out


def indices_to_grid(indices: np.ndarray) -> np.ndarray:
    """Map ``(8, 8)`` integer class indices back to a grid of piece chars."""
    arr = np.asarray(indices)
    if arr.shape != (8, 8):
        raise ValueError(f"indices must be 8x8, got shape {arr.shape}")
    if arr.min() < 0 or arr.max() >= NUM_CLASSES:
        raise ValueError(
            f"indices out of range [0, {NUM_CLASSES - 1}]: "
            f"min={arr.min()}, max={arr.max()}"
        )
    out = np.empty((8, 8), dtype="<U1")
    for r in range(8):
        for c in range(8):
            out[r, c] = INDEX_TO_PIECE[int(arr[r, c])]
    return out


# --- Convenience constructors and accessors --------------------------------


def empty_grid() -> np.ndarray:
    return np.full((8, 8), EMPTY, dtype="<U1")


def initial_grid() -> np.ndarray:
    return fen_to_grid(INITIAL_FEN)


def piece_at(grid: np.ndarray, file: str, rank: int) -> str:
    r, c = _coords_to_indices(file, rank)
    return str(grid[r, c])


def set_piece(grid: np.ndarray, file: str, rank: int, piece: str) -> None:
    if piece not in PIECE_TO_INDEX:
        raise ValueError(f"Invalid piece: {piece!r}")
    r, c = _coords_to_indices(file, rank)
    grid[r, c] = piece


# --- Internal ---------------------------------------------------------------


def _coords_to_indices(file: str, rank: int) -> tuple[int, int]:
    if file not in "abcdefgh":
        raise ValueError(f"Invalid file: {file!r}")
    if not 1 <= rank <= 8:
        raise ValueError(f"Invalid rank: {rank}")
    return 8 - rank, ord(file) - ord("a")


def _validate_grid(grid: np.ndarray) -> np.ndarray:
    """Coerce input to ndarray and check shape and contents."""
    arr = np.asarray(grid)
    if arr.shape != (8, 8):
        raise ValueError(f"grid must be 8x8, got shape {arr.shape}")
    invalid = sorted({str(cell) for cell in arr.ravel().tolist()
                      if str(cell) not in PIECE_TO_INDEX})
    if invalid:
        raise ValueError(f"Invalid piece symbols in grid: {invalid}")
    return arr.astype("<U1")


# --- Self-test --------------------------------------------------------------


if __name__ == "__main__":
    # Round-trip the starting position.
    g = fen_to_grid(INITIAL_FEN)
    assert grid_to_fen(g) == INITIAL_FEN
    assert grid_to_fen_board(g) == INITIAL_FEN.split(" ")[0]

    # Coordinate accessors.
    assert piece_at(g, "a", 1) == "R"
    assert piece_at(g, "e", 1) == "K"
    assert piece_at(g, "e", 8) == "k"
    assert piece_at(g, "d", 4) == EMPTY
    assert piece_at(g, "h", 8) == "r"

    # Empty grid -> "8/8/8/8/8/8/8/8".
    assert grid_to_fen_board(empty_grid()) == "8/8/8/8/8/8/8/8"

    # Mid-game position with mixed runs and en passant metadata.
    sicilian = "rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq c6 0 2"
    sg = fen_to_grid(sicilian)
    assert piece_at(sg, "c", 5) == "p"
    assert piece_at(sg, "e", 4) == "P"
    assert grid_to_fen_board(sg) == sicilian.split(" ")[0]

    # Index round-trip.
    idx = grid_to_indices(g)
    assert idx.shape == (8, 8) and idx.dtype == np.int64
    assert (indices_to_grid(idx) == g).all()
    assert idx[0, 0] == PIECE_TO_INDEX["r"]   # a8 black rook
    assert idx[7, 4] == PIECE_TO_INDEX["K"]   # e1 white king

    # set_piece mutates in place.
    eg = empty_grid()
    set_piece(eg, "e", 4, "P")
    assert piece_at(eg, "e", 4) == "P"
    assert grid_to_fen_board(eg) == "8/8/8/8/4P3/8/8/8"

    # Validation errors.
    try:
        fen_to_grid("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBN")  # 7 squares row
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for malformed FEN")

    try:
        bad = empty_grid()
        bad[0, 0] = "X"
        grid_to_fen_board(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for invalid piece")

    print("position_to_fen self-tests passed.")
