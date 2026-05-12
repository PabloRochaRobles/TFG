"""Module 3: inference API for the square classifier (ONNX Runtime).

Wraps a trained ONNX export of the EfficientNet-B0 per-square classifier
behind the same `SquareClassifierInference` API that the rest of the pipeline
expects, but using `onnxruntime` instead of PyTorch in production.

Motivación de la migración a ONNX:
    PyTorch tiene una huella base de ~250 MB de RAM (intérprete + libs);
    `onnxruntime` se sitúa en torno a ~50-80 MB. En Render Free Tier
    (512 MB) eso es la diferencia entre OOM y servicio estable.

Orientation matches :mod:`position_to_fen`: ``probs[0, 0, k]`` is the
probability that the square at rank 8 / file a (top-left of the warped
image) is class ``k``.
"""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

from ..position_to_fen import NUM_CLASSES


# Estadísticas de normalización ImageNet (idénticas a las del entrenamiento).
_IMAGENET_MEAN = np.array([0.485, 0.456, 0.406], dtype=np.float32)
_IMAGENET_STD  = np.array([0.229, 0.224, 0.225], dtype=np.float32)


def _preprocess_crop(bgr_crop: np.ndarray, input_size: int) -> np.ndarray:
    """BGR uint8 → CHW float32 normalized (RGB, ImageNet stats).

    Reproduce exactamente la pipeline de `albumentations` usada en
    entrenamiento (Resize bilinear + Normalize + ToTensorV2 reorder a CHW),
    pero implementada con OpenCV + NumPy para no arrastrar `torch` ni
    `albumentations` en producción.
    """
    rgb = cv2.cvtColor(bgr_crop, cv2.COLOR_BGR2RGB)
    resized = cv2.resize(rgb, (input_size, input_size), interpolation=cv2.INTER_LINEAR)
    arr = resized.astype(np.float32) / 255.0
    arr = (arr - _IMAGENET_MEAN) / _IMAGENET_STD
    return arr.transpose(2, 0, 1)  # HWC → CHW


def _softmax(logits: np.ndarray) -> np.ndarray:
    """Softmax numéricamente estable a lo largo del último eje."""
    shifted = logits - logits.max(axis=-1, keepdims=True)
    e = np.exp(shifted)
    return e / e.sum(axis=-1, keepdims=True)


class SquareClassifierInference:
    """Thin wrapper que turna un warped board en per-square probabilities."""

    def __init__(
        self,
        session: ort.InferenceSession,
        square_size: int = 100,
        input_size: int = 96,
    ) -> None:
        self.session = session
        self.square_size = square_size
        self.input_size = input_size
        self._input_name = session.get_inputs()[0].name

    @classmethod
    def load(
        cls,
        checkpoint_path: Path | str,
        device: str = 'cpu',  # parámetro legacy; onnxruntime usa providers
        square_size: int = 100,
        input_size: int = 96,
    ) -> 'SquareClassifierInference':
        """Carga un modelo ONNX desde disco.

        Limita explícitamente el número de threads (intra y inter) a 1 para
        reducir la presión de memoria — relevante en Render Free Tier.
        El parámetro ``device`` se conserva por compatibilidad con código
        que lo pasaba; aquí no tiene efecto: si se hubiera querido GPU,
        habría que añadir ``'CUDAExecutionProvider'`` a la lista.
        """
        sess_options = ort.SessionOptions()
        sess_options.intra_op_num_threads = 1
        sess_options.inter_op_num_threads = 1
        # Reducción adicional de memoria; desactiva la pre-asignación de
        # arenas grandes que onnxruntime hace por defecto.
        sess_options.enable_mem_pattern = False
        sess_options.enable_cpu_mem_arena = False

        session = ort.InferenceSession(
            str(checkpoint_path),
            sess_options=sess_options,
            providers=['CPUExecutionProvider'],
        )
        return cls(session, square_size=square_size, input_size=input_size)

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

        # Construir el batch de 64 crops normalizados.
        batch = np.empty((64, 3, self.input_size, self.input_size), dtype=np.float32)
        idx = 0
        for r in range(8):
            for c in range(8):
                crop = warped[r * s : (r + 1) * s, c * s : (c + 1) * s]
                batch[idx] = _preprocess_crop(crop, self.input_size)
                idx += 1

        # Inferencia ONNX.
        logits = self.session.run(None, {self._input_name: batch})[0]
        probs = _softmax(logits).astype(np.float32)
        return probs.reshape(8, 8, NUM_CLASSES)


# --- Self-test --------------------------------------------------------------


if __name__ == '__main__':
    """Smoke test: requiere un checkpoint .onnx existente.

    Para probar sin checkpoint real, primero hay que convertir uno con el
    script `_convert_to_onnx.py` de la raíz del backend.
    """
    import os
    import sys

    ckpt = sys.argv[1] if len(sys.argv) > 1 else os.path.join('media', 'models', 'chess_effnet.onnx')
    if not os.path.exists(ckpt):
        print(f"Checkpoint no encontrado: {ckpt}")
        sys.exit(1)

    inf = SquareClassifierInference.load(ckpt)
    fake = (np.random.rand(800, 800, 3) * 255).astype(np.uint8)
    probs = inf.classify_position(fake)
    print(f"probs shape: {probs.shape}  dtype: {probs.dtype}")
    assert probs.shape == (8, 8, NUM_CLASSES)
    sums = probs.sum(axis=-1)
    print(f"row-sum range: [{sums.min():.4f}, {sums.max():.4f}]")
    assert np.allclose(sums, 1.0, atol=1e-4)
    print("Self-test passed.")
