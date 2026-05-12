"""Module 2: stable frame selection from a video.

Reads a video, samples it at a controlled rate, and yields one warped board
view per detected calm period (= one per move). Motion is measured on the
warped board region only, so movements outside the board are ignored.

Algorithm:
    1. Sample the source video at ``sample_fps``.
    2. For each sampled frame, compute motion = mean absolute pixel difference
       (grayscale, 0..255 scale) against the previous sampled warp.
    3. For each sample, also compute the *change count* against the last
       yielded stable warp: how many of the 64 chess squares show a per-square
       mean diff significantly above the adaptive noise floor. This single
       metric drives a three-way classification of the new sample:

         * ``n_changed <= dedupe_max_changed`` -> same position as last yielded
         * ``dedupe_max_changed < n_changed < anomaly_min_changed`` ->
           a candidate stable position consistent with a chess move
         * ``n_changed >= anomaly_min_changed`` -> *anomalous* (typically a
           hand spanning many squares, or a large lighting/setup disturbance)

       Anomalous samples are not calm, so the state machine cannot emit while
       one is in view. This is equivalent to a hand detector but does not
       depend on skin colour and therefore works for wooden sets, plastic
       pieces, gloves, etc.

    4. Small two-state machine:
         WAITING -> (calm streak >= min_calm) -> EMITTED   yields a StableFrame
         EMITTED -> (motion streak >= min_motion) -> WAITING  arms the next emit
       Both transitions require sustained, not single-sample, evidence.
       Single motion blips (e.g. hand passing near the camera, brief
       shadows, sub-pixel vibration) no longer reset the EMITTED state, so
       a stable position emits exactly once between real moves.
    5. The initial calm period is optionally emitted (default: yes) — useful
       for capturing the starting position before any move is played. The
       anomaly check is silent before the first yield (no baseline).
    6. At emit time, the cached change count is reused: if it is
       ``<= dedupe_max_changed`` the candidate is dropped as a duplicate of
       the previous yielded position.
    7. Stale-reference safeguard: if the change count stays anomalous (>= 6)
       while motion has been continuously below ``motion_threshold`` for at
       least ``anomaly_stale_seconds``, the reference baseline is refreshed
       to the current sample. This is necessary because a single missed
       emit (e.g. when a calm period is shorter than ``min_stable_seconds``)
       leaves the baseline pointing at an old position; subsequent moves
       accumulate change count beyond the anomaly threshold and are
       wrongly blocked. The refresh breaks the cascade. The threshold is
       deliberately longer than any plausible hand pause on the board.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

import cv2
import numpy as np

from .board_detector import BoardCalibration, warp_board


@dataclass
class StableFrame:
    """A frame captured during a stable (post-move) period.

    Attributes:
        frame_index: index in the source video (0-based).
        timestamp: seconds from the start of the video.
        frame: original BGR frame, full resolution.
        warped: warped board view (warp_size x warp_size, BGR), ready for
            classification.
        motion_score: mean absolute pixel difference (0..255 scale) between
            this sample and the previous sample. Always low at emit time.
        change_count: number of chess squares that differ from the
            previously yielded warp beyond the adaptive noise floor. 0-1
            for the very first emit (no baseline) or for re-emits of the
            same position; 2-5 for typical chess moves; never above
            ``anomaly_min_changed`` because anomalies don't reach emit.
    """

    frame_index: int
    timestamp: float
    frame: np.ndarray
    warped: np.ndarray
    motion_score: float
    change_count: int = 0


def iter_stable_frames(
    video_path: str | Path,
    calibration: BoardCalibration,
    sample_fps: float = 5.0,
    motion_threshold: float = 2.0,
    min_stable_seconds: float = 0.4,
    min_motion_seconds: float = 0.6,
    emit_initial: bool = True,
    motion_log: list[tuple[int, float, float]] | None = None,
    dedupe_max_changed: int | None = 1,
    dedupe_square_threshold: float = 3.0,
    anomaly_min_changed: int | None = None,
    anomaly_stale_seconds: float = 3.0,
    anomaly_log: list[tuple[int, float, int]] | None = None,
) -> Iterator[StableFrame]:
    """Yield one ``StableFrame`` per detected calm period in the video.

    Args:
        video_path: input video file path.
        calibration: ``BoardCalibration`` from module 1.
        sample_fps: frames per second to analyse from the source video.
            5-10 is plenty for chess. Higher values cost CPU; lower values
            risk missing brief calm periods between fast moves.
        motion_threshold: mean absolute grayscale pixel difference (0..255)
            below which a sample is "calm" with respect to *motion*.
        min_stable_seconds: required duration of a calm streak before a
            stable event is emitted.
        min_motion_seconds: required duration of *sustained* non-calm
            samples to transition the state machine back from EMITTED to
            WAITING. Single-sample blips do not re-arm the next emit.
        emit_initial: emit the very first calm period (typically the
            initial chess position).
        motion_log: optional list to populate with ``(frame_index, timestamp,
            motion)`` for every sampled frame. Use for tuning thresholds.
        dedupe_max_changed: at emit time, if the change count is at most
            this many, drop the event (same position as the last yielded
            warp). Use ``None`` to disable dedupe.
        dedupe_square_threshold: minimum absolute signal above the noise
            floor for a square to be "changed". The noise floor is estimated
            adaptively per pair as ``median + k*MAD`` of the 64 per-square
            diffs (k = 4 internally), so the effective threshold scales with
            the video's actual noise level.
        anomaly_min_changed: optional gate. A sample whose change count
            against the last yielded warp is at least this many is treated
            as anomalous (typically hand on board) and is not calm.
            Default ``None`` (gate off) prioritises recall — module 5 will
            filter false positives during inference via no-move detection.
            Set to e.g. 8 when using this module to extract training data
            for the classifier (module 3), where you want a cleaner stream
            even at the cost of missing some real positions.
        anomaly_stale_seconds: if motion stays below ``motion_threshold``
            continuously for this many seconds AND the change count vs the
            last yielded warp is still anomalous, the reference is assumed
            to be stale (we missed earlier emits, e.g. due to short calm
            periods between fast moves) and is refreshed to the current
            sample. This breaks the cascading-cycle where a single missed
            emit grows the change count past the anomaly threshold and
            blocks every subsequent emit. 3.0 seconds is much longer than
            a typical hand pause on the board, so it does not cause
            phantom emits.
        anomaly_log: optional list to populate with ``(frame_index,
            timestamp, change_count)`` for every sampled frame after the
            first emit. Use for tuning ``anomaly_min_changed``.

    Yields:
        ``StableFrame`` in chronological order.
    """
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")
    try:
        video_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        step = max(1, int(round(video_fps / sample_fps)))
        min_calm = max(1, int(round(sample_fps * min_stable_seconds)))
        min_motion = max(1, int(round(sample_fps * min_motion_seconds)))
        stale_samples = max(1, int(round(sample_fps * anomaly_stale_seconds)))

        state = "waiting"
        calm_streak = 0
        motion_streak = 0
        motion_low_streak = 0
        emitted_count = 0
        prev_gray: np.ndarray | None = None
        last_yielded_gray: np.ndarray | None = None
        frame_idx = -1

        while True:
            ok, frame = cap.read()
            if not ok:
                break
            frame_idx += 1
            if frame_idx % step != 0:
                continue

            warped = warp_board(frame, calibration)
            gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
            if prev_gray is None:
                motion = 0.0
            else:
                motion = float(cv2.absdiff(gray, prev_gray).mean())
            prev_gray = gray
            timestamp = frame_idx / video_fps
            if motion_log is not None:
                motion_log.append((frame_idx, timestamp, motion))

            motion_low = motion < motion_threshold
            if motion_low:
                motion_low_streak += 1
            else:
                motion_low_streak = 0

            if last_yielded_gray is not None:
                n_changed = _count_changed_squares(
                    last_yielded_gray, gray,
                    calibration.square_size,
                    dedupe_square_threshold,
                )
            else:
                n_changed = 0

            if (anomaly_min_changed is not None
                    and last_yielded_gray is not None
                    and n_changed >= anomaly_min_changed
                    and motion_low_streak >= stale_samples):
                last_yielded_gray = gray
                n_changed = 0
                motion_low_streak = 0

            if anomaly_log is not None and last_yielded_gray is not None:
                anomaly_log.append((frame_idx, timestamp, n_changed))

            anomalous = (
                anomaly_min_changed is not None
                and last_yielded_gray is not None
                and n_changed >= anomaly_min_changed
            )
            is_calm = motion_low and (not anomalous)

            if is_calm:
                motion_streak = 0
                calm_streak += 1
                if state == "waiting" and calm_streak >= min_calm:
                    state = "emitted"
                    skip = (emitted_count == 0 and not emit_initial)
                    if (not skip
                            and last_yielded_gray is not None
                            and dedupe_max_changed is not None
                            and n_changed <= dedupe_max_changed):
                        skip = True
                    if not skip:
                        yield StableFrame(
                            frame_index=frame_idx,
                            timestamp=timestamp,
                            frame=frame,
                            warped=warped,
                            motion_score=motion,
                            change_count=n_changed,
                        )
                        emitted_count += 1
                    last_yielded_gray = gray
            else:
                calm_streak = 0
                motion_streak += 1
                if state == "emitted" and motion_streak >= min_motion:
                    state = "waiting"
    finally:
        cap.release()


def select_stable_frames(
    video_path: str | Path,
    calibration: BoardCalibration,
    **kwargs,
) -> list[StableFrame]:
    """Eager wrapper around :func:`iter_stable_frames`."""
    return list(iter_stable_frames(video_path, calibration, **kwargs))


_DEDUPE_MAD_MULTIPLIER = 4.0


def _count_changed_squares(
    gray1: np.ndarray,
    gray2: np.ndarray,
    square_size: int,
    min_signal_above_noise: float,
) -> int:
    """Count chess squares whose mean abs diff is significantly above the
    per-pair noise floor.

    The noise floor is estimated robustly as ``median + k*MAD`` over the 64
    per-square mean diffs, where MAD is the median absolute deviation and
    ``k = _DEDUPE_MAD_MULTIPLIER``. ``min_signal_above_noise`` is an absolute
    floor that prevents k*MAD from collapsing to zero on extremely uniform
    diff distributions.

    Inputs must be ``(8*square_size, 8*square_size)`` grayscale images.
    """
    diff = cv2.absdiff(gray1, gray2).astype(np.float32)
    s = square_size
    means = diff.reshape(8, s, 8, s).mean(axis=(1, 3)).ravel()
    median = float(np.median(means))
    mad = float(np.median(np.abs(means - median)))
    threshold = median + max(_DEDUPE_MAD_MULTIPLIER * mad, min_signal_above_noise)
    return int((means > threshold).sum())
