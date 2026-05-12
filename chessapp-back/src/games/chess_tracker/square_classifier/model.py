"""Module 3: per-square classifier model.

EfficientNet-B0 backbone (pretrained on ImageNet by default) with a 13-class
classification head. Designed for ``96 x 96`` RGB inputs (the default in
``dataset.default_*_transform``), but accepts any spatial size thanks to
EfficientNet's adaptive global pooling.

Why EfficientNet-B0:
    - Small (~4.0M params, ~5MB FP32 checkpoint) so training is fast on CPU
      or a small GPU and inference is cheap (we run it 64 times per stable
      frame in module 6).
    - Pretrained features transfer well to small datasets like ours
      (~3.6k per-square examples).
    - Resilient to non-standard input sizes via adaptive pooling.
"""
from __future__ import annotations

from pathlib import Path

import torch
import torch.nn as nn
from torchvision.models import EfficientNet_B0_Weights, efficientnet_b0

from ..position_to_fen import NUM_CLASSES


class SquareClassifier(nn.Module):
    """13-class classifier built on EfficientNet-B0.

    Args:
        num_classes: output classes (default 13: empty + 6 white + 6 black).
        pretrained: load ImageNet weights for the backbone.
        dropout: dropout probability before the final linear layer.
    """

    def __init__(
        self,
        num_classes: int = NUM_CLASSES,
        pretrained: bool = True,
        dropout: float = 0.2,
    ) -> None:
        super().__init__()
        weights = EfficientNet_B0_Weights.IMAGENET1K_V1 if pretrained else None
        backbone = efficientnet_b0(weights=weights)
        in_features = backbone.classifier[1].in_features
        backbone.classifier = nn.Sequential(
            nn.Dropout(p=dropout, inplace=True),
            nn.Linear(in_features, num_classes),
        )
        self.backbone = backbone
        self.num_classes = num_classes

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.backbone(x)

    @torch.no_grad()
    def predict_proba(self, x: torch.Tensor) -> torch.Tensor:
        """Softmax probabilities for ``x``. Sets eval mode internally."""
        was_training = self.training
        self.eval()
        try:
            logits = self.forward(x)
            return torch.softmax(logits, dim=-1)
        finally:
            if was_training:
                self.train()


def save_checkpoint(
    model: SquareClassifier,
    path: Path | str,
    *,
    extra: dict | None = None,
) -> None:
    """Save weights plus the metadata needed to reconstruct the model."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "state_dict": model.state_dict(),
        "num_classes": model.num_classes,
    }
    if extra:
        payload["extra"] = extra
    torch.save(payload, path)


def load_checkpoint(
    path: Path | str,
    map_location: str | torch.device = "cpu",
) -> tuple[SquareClassifier, dict]:
    """Load a checkpoint saved by :func:`save_checkpoint`.

    Returns the model (in eval mode) and the ``extra`` metadata dict, or
    an empty dict if none was saved.
    """
    payload = torch.load(path, map_location=map_location, weights_only=False)
    model = SquareClassifier(
        num_classes=payload.get("num_classes", NUM_CLASSES),
        pretrained=False,
    )
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, payload.get("extra", {})


# --- Self-test --------------------------------------------------------------


if __name__ == "__main__":
    model = SquareClassifier(pretrained=False)
    n_params = sum(p.numel() for p in model.parameters())
    print(f"SquareClassifier built. Parameters: {n_params:,}")

    x = torch.randn(4, 3, 96, 96)
    logits = model(x)
    print(f"Forward 96x96: input {tuple(x.shape)} -> logits {tuple(logits.shape)}")
    assert logits.shape == (4, NUM_CLASSES)

    x_big = torch.randn(2, 3, 224, 224)
    logits = model(x_big)
    print(f"Forward 224x224: input {tuple(x_big.shape)} -> "
          f"logits {tuple(logits.shape)}")
    assert logits.shape == (2, NUM_CLASSES)

    probs = model.predict_proba(x)
    print(f"predict_proba sum check: row 0 sums to {probs[0].sum().item():.4f}")
    assert torch.allclose(probs.sum(dim=-1), torch.ones(4), atol=1e-5)

    print("Self-test passed.")
