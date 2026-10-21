"""SquareNet: a shared backbone with an occupancy/colour head and a piece-type head.

The model takes float32 RGB in [0, 1], NCHW, and normalises internally, so the exported ONNX
graph needs no separate preprocessing beyond `ml.common.square_crops`.
"""

from __future__ import annotations

import torch
import torch.nn as nn

MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def _block(cin: int, cout: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Conv2d(cin, cout, 3, padding=1, bias=False),
        nn.BatchNorm2d(cout),
        nn.ReLU(inplace=True),
        nn.MaxPool2d(2),
    )


class TinyBackbone(nn.Module):
    """Four conv blocks from scratch: the fast, easy-to-explain baseline."""

    num_features = 128

    def __init__(self) -> None:
        super().__init__()
        self.net = nn.Sequential(_block(3, 24), _block(24, 48), _block(48, 96), _block(96, 128))
        self.pool = nn.AdaptiveAvgPool2d(1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.pool(self.net(x)).flatten(1)


class SquareNet(nn.Module):
    def __init__(self, backbone: str = "tiny", pretrained: bool = False) -> None:
        super().__init__()
        if backbone == "tiny":
            self.backbone: nn.Module = TinyBackbone()
        else:
            import timm  # imported lazily so the tiny model has no timm dependency

            self.backbone = timm.create_model(backbone, pretrained=pretrained, num_classes=0)
        d = int(self.backbone.num_features)  # type: ignore[arg-type]
        self.occ = nn.Linear(d, 3)  # empty / white / black
        self.typ = nn.Linear(d, 6)  # P N B R Q K
        self.register_buffer("mean", torch.tensor(MEAN).view(1, 3, 1, 1))
        self.register_buffer("std", torch.tensor(STD).view(1, 3, 1, 1))

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        f = self.backbone((x - self.mean) / self.std)
        return self.occ(f), self.typ(f)

    def head_parameters(self) -> list[nn.Parameter]:
        return [*self.occ.parameters(), *self.typ.parameters()]
