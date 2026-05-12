"""Module 1: board calibration via 4 manual corner clicks.

The user clicks the 4 corners in the fixed order ``a1, a8, h8, h1``.
The resulting :class:`BoardCalibration` is the single source of truth for
mapping the input video to a top-down 800x800 view in which every chess
square is a fixed 100x100 region.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


CORNER_ORDER = ("a1", "a8", "h8", "h1")


@dataclass
class BoardCalibration:
    """Manual 4-corner calibration. Corners are in source-image pixel coords."""

    a1: tuple[float, float]
    a8: tuple[float, float]
    h8: tuple[float, float]
    h1: tuple[float, float]
    warp_size: int = 800
    square_size: int = 100

    def __post_init__(self) -> None:
        if self.warp_size != 8 * self.square_size:
            raise ValueError(
                f"warp_size ({self.warp_size}) must equal 8 * square_size "
                f"({self.square_size})"
            )

    @property
    def src_points(self) -> np.ndarray:
        return np.array([self.a1, self.a8, self.h8, self.h1], dtype=np.float32)

    @property
    def dst_points(self) -> np.ndarray:
        # White at bottom: a1 bottom-left, a8 top-left, h8 top-right, h1 bottom-right.
        s = self.warp_size
        return np.array([[0, s], [0, 0], [s, 0], [s, s]], dtype=np.float32)

    @property
    def homography(self) -> np.ndarray:
        return cv2.getPerspectiveTransform(self.src_points, self.dst_points)


def warp_board(frame: np.ndarray, calib: BoardCalibration) -> np.ndarray:
    """Apply the homography and return the top-down board view."""
    return cv2.warpPerspective(
        frame, calib.homography, (calib.warp_size, calib.warp_size)
    )


def square_to_pixels(
    file: str, rank: int, square_size: int = 100
) -> tuple[int, int, int, int]:
    """Return ``(x, y, w, h)`` of a chess square in the warped image."""
    if file not in "abcdefgh":
        raise ValueError(f"Invalid file: {file!r}")
    if not 1 <= rank <= 8:
        raise ValueError(f"Invalid rank: {rank}")
    col = ord(file) - ord("a")
    row = 8 - rank
    return col * square_size, row * square_size, square_size, square_size


def get_square_crop(
    warped: np.ndarray, file: str, rank: int, square_size: int = 100
) -> np.ndarray:
    """Return a copy of the square's crop from the warped image."""
    x, y, w, h = square_to_pixels(file, rank, square_size)
    return warped[y : y + h, x : x + w].copy()


def calibrate_interactive(
    frame: np.ndarray,
    window_name: str = "Calibrate board (click a1, a8, h8, h1)",
    warp_size: int = 800,
    square_size: int = 100,
) -> BoardCalibration:
    """Open an OpenCV window and capture 4 clicks in order ``a1, a8, h8, h1``.

    Controls:
        Left click    place next corner
        z / Backspace undo last click
        r             reset all clicks
        Enter         confirm (only with 4 corners placed)
        Esc / q       cancel (raises ``RuntimeError``)
    """
    points: list[tuple[float, float]] = []

    def on_mouse(event, x, y, flags, _):
        if event == cv2.EVENT_LBUTTONDOWN and len(points) < 4:
            points.append((float(x), float(y)))

    cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(window_name, on_mouse)
    try:
        while True:
            display = frame.copy()
            _draw_calibration_overlay(display, points)
            cv2.imshow(window_name, display)
            key = cv2.waitKey(20) & 0xFF
            if key in (ord("q"), 27):
                raise RuntimeError("Calibration cancelled by user")
            if key in (ord("z"), 8):
                if points:
                    points.pop()
            elif key == ord("r"):
                points.clear()
            elif key in (13, 10) and len(points) == 4:
                break
    finally:
        cv2.destroyWindow(window_name)

    return BoardCalibration(
        a1=points[0],
        a8=points[1],
        h8=points[2],
        h1=points[3],
        warp_size=warp_size,
        square_size=square_size,
    )


def _draw_calibration_overlay(
    img: np.ndarray, points: list[tuple[float, float]]
) -> None:
    h, w = img.shape[:2]
    next_idx = len(points)
    instr = (
        f"Click corner {next_idx + 1}/4: {CORNER_ORDER[next_idx]}"
        if next_idx < 4
        else "Press Enter to confirm | r=reset | z=undo"
    )
    cv2.rectangle(img, (0, 0), (w, 30), (0, 0, 0), -1)
    cv2.putText(
        img, instr, (8, 22), cv2.FONT_HERSHEY_SIMPLEX,
        0.6, (255, 255, 255), 1, cv2.LINE_AA,
    )
    for i, (x, y) in enumerate(points):
        ix, iy = int(x), int(y)
        cv2.circle(img, (ix, iy), 6, (0, 255, 0), -1)
        cv2.putText(
            img, CORNER_ORDER[i], (ix + 8, iy - 8),
            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2, cv2.LINE_AA,
        )
    for i in range(len(points) - 1):
        cv2.line(
            img,
            tuple(map(int, points[i])),
            tuple(map(int, points[i + 1])),
            (0, 255, 0), 1, cv2.LINE_AA,
        )
    if len(points) == 4:
        cv2.line(
            img,
            tuple(map(int, points[3])),
            tuple(map(int, points[0])),
            (0, 255, 0), 1, cv2.LINE_AA,
        )


def draw_grid(
    warped: np.ndarray,
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 1,
    square_size: int = 100,
) -> np.ndarray:
    """Overlay an 8x8 grid plus file/rank labels for visual verification."""
    out = warped.copy()
    s = square_size
    h, w = out.shape[:2]
    for i in range(9):
        cv2.line(out, (i * s, 0), (i * s, h), color, thickness)
        cv2.line(out, (0, i * s), (w, i * s), color, thickness)
    for i, f in enumerate("abcdefgh"):
        cv2.putText(
            out, f, (i * s + s // 2 - 5, h - 6),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    for rank in range(1, 9):
        y = (8 - rank) * s + s // 2 + 5
        cv2.putText(
            out, str(rank), (4, y),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1, cv2.LINE_AA,
        )
    return out


def save_calibration(calib: BoardCalibration, path: str | Path) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "corners": {
            "a1": list(calib.a1),
            "a8": list(calib.a8),
            "h8": list(calib.h8),
            "h1": list(calib.h1),
        },
        "warp_size": calib.warp_size,
        "square_size": calib.square_size,
    }
    path.write_text(json.dumps(data, indent=2))


def load_calibration(path: str | Path) -> BoardCalibration:
    data = json.loads(Path(path).read_text())
    c = data["corners"]
    return BoardCalibration(
        a1=tuple(c["a1"]),
        a8=tuple(c["a8"]),
        h8=tuple(c["h8"]),
        h1=tuple(c["h1"]),
        warp_size=data.get("warp_size", 800),
        square_size=data.get("square_size", 100),
    )
