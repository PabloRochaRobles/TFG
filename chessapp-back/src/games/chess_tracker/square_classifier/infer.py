"""Module 3: inference API for the square classifier.

Wraps a trained :class:`SquareClassifier` checkpoint into a single call that
turns a warped board image into the ``(8, 8, 13)`` probability tensor that
:func:`chess_tracker.move_inferencer.infer_move` expects.

Orientation matches :mod:`position_to_fen`: ``probs[0, 0, k]`` is the
probability that the square at rank 8 / file a (top-left of the warped
image) is class ``k``.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import torch

from ..position_to_fen import NUM_CLASSES
from .model import SquareClassifier, load_checkpoint


def default_eval_transform(output_size: int = 96):
    """Resize + ImageNet normalize. Idéntico al usado en entrenamiento.

    Inline aquí para que la inferencia en producción no dependa de
    `dataset.py`, que arrastra utilidades de entrenamiento innecesarias en
    el backend.
    """
    import albumentations as A
    from albumentations.pytorch import ToTensorV2

    return A.Compose([
        A.Resize(output_size, output_size),
        A.Normalize(mean=(0.485, 0.456, 0.406), std=(0.229, 0.224, 0.225)),
        ToTensorV2(),
    ])


class SquareClassifierInference:
    """Thin wrapper that turns a warped board into per-square probabilities."""

    def __init__(
        self,
        model: SquareClassifier,
        device: str | torch.device = "cpu",
        square_size: int = 100,
        input_size: int = 96,
    ) -> None:
        self.device = torch.device(device)
        self.square_size = square_size
        self.input_size = input_size
        self.model = model.to(self.device).eval()
        self.transform = default_eval_transform(input_size)

    @classmethod
    def load(
        cls,
        checkpoint_path: Path | str,
        device: str | torch.device = "cpu",
        square_size: int = 100,
        input_size: int = 96,
    ) -> "SquareClassifierInference":
        model, _extra = load_checkpoint(checkpoint_path, map_location=device)
        return cls(
            model=model, device=device,
            square_size=square_size, input_size=input_size,
        )

    @torch.no_grad()
    def classify_position(self, warped: np.ndarray) -> np.ndarray:
        """Return ``(8, 8, 13)`` float32 softmax probabilities.

        ``warped`` must be the BGR warped board image at exactly
        ``8 * square_size`` per side, as produced by
        :func:`chess_tracker.board_detector.warp_board`.
        """
        s = self.square_size
        expected = 8 * s
        if warped.ndim != 3 or warped.shape[0] != expected or warped.shape[1] != expected:
            raise ValueError(
                f"warped must be ({expected}, {expected}, 3); "
                f"got shape {warped.shape}"
            )
        crops: list[torch.Tensor] = []
        for r in range(8):
            for c in range(8):
                crop = warped[r * s : (r + 1) * s, c * s : (c + 1) * s]
                crop = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
                crops.append(self.transform(image=crop)["image"])
        batch = torch.stack(crops).to(self.device)
        logits = self.model(batch)
        probs = torch.softmax(logits, dim=-1).cpu().numpy().astype(np.float32)
        return probs.reshape(8, 8, NUM_CLASSES)


# --- Self-test --------------------------------------------------------------


if __name__ == "__main__":
    """Smoke test: build a fresh (untrained) model, run inference on a fake
    warped image, and check the output shape and that probabilities sum to 1.
    """
    model = SquareClassifier(pretrained=False)
    inf = SquareClassifierInference(model)

    fake = (np.random.rand(800, 800, 3) * 255).astype(np.uint8)
    probs = inf.classify_position(fake)
    print(f"probs shape: {probs.shape}  dtype: {probs.dtype}")
    assert probs.shape == (8, 8, NUM_CLASSES)
    sums = probs.sum(axis=-1)
    print(f"row-sum range: [{sums.min():.4f}, {sums.max():.4f}]")
    assert np.allclose(sums, 1.0, atol=1e-4)
    print("Self-test passed.")
