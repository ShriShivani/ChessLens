"""Train SquareNet.

Run:  python -m ml.train --config ml/configs/synthetic_tiny.yaml

Splits are by game/session (ml/splits.py). Every run writes model.pt, config.json, split.json
and metrics.json (with seed and git commit) into ml/runs/<name>/.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import yaml
from torch.utils.data import DataLoader, Dataset

from ml.augment import augment
from ml.common import split_label
from ml.data import CropSet, class_weights, discover, load_games, read_meta
from ml.model import SquareNet
from ml.splits import assert_no_leakage, split_groups


@dataclass
class Config:
    name: str = "run"
    data_dirs: list[str] = field(default_factory=lambda: ["ml/data/synthetic"])
    backbone: str = "tiny"  # "tiny" or any timm model name, e.g. mobilenetv3_small_100
    pretrained: bool = False
    init_from: str | None = None  # checkpoint to fine-tune from (e.g. a synthetic-pretrained run)
    epochs: int = 30
    batch_size: int = 128
    lr_head: float = 1e-3
    lr_backbone: float = 3e-4
    weight_decay: float = 1e-4
    label_smoothing: float = 0.05
    patience: int = 6
    augment: bool = True
    seed: int = 0
    workers: int = 0
    max_train_crops: int | None = None  # cap for quick experiments
    out_dir: str = "ml/runs"

    @classmethod
    def load(cls, path: str | Path) -> Config:
        return cls(**yaml.safe_load(Path(path).read_text(encoding="utf-8")))


class CropDataset(Dataset):
    def __init__(self, crops: np.ndarray, labels: np.ndarray, train: bool, seed: int = 0) -> None:
        self.crops, self.labels, self.train = crops, labels, train
        self.rng = np.random.default_rng(seed)
        self.occ, self.typ = split_label(labels)

    def __len__(self) -> int:
        return len(self.labels)

    def __getitem__(self, i: int):
        img = self.crops[i]
        if self.train:
            img = augment(img, self.rng)
        x = torch.from_numpy(np.ascontiguousarray(img)).permute(2, 0, 1).float() / 255.0
        return x, int(self.occ[i]), int(self.typ[i])


def git_commit() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def subset(data: CropSet, games: set[str]) -> CropSet:
    keep_ids = [i for i, g in enumerate(data.games) if g in games]
    mask = np.isin(data.game, keep_ids)
    return CropSet(data.crops[mask], data.labels[mask], data.game[mask], data.games)


def make_splits(cfg: Config) -> tuple[dict[str, str], dict[str, str], dict[str, Path]]:
    paths: dict[str, Path] = {}
    sessions: dict[str, str] = {}
    for d in cfg.data_dirs:
        for p in discover(d):
            game, session = read_meta(p)
            paths[game], sessions[game] = p, session
    if not paths:
        raise SystemExit(f"no .npz crop files found in {cfg.data_dirs}")
    assignment = split_groups(list(paths), sessions, seed=cfg.seed)
    assert_no_leakage(assignment, sessions)
    return assignment, sessions, paths


def load_split(paths: dict[str, Path], assignment: dict[str, str], split: str) -> CropSet | None:
    chosen = [paths[g] for g in sorted(paths) if assignment[g] == split]
    return load_games(chosen) if chosen else None


@torch.no_grad()
def predict_logits(model: SquareNet, crops: np.ndarray, batch: int = 256):
    model.eval()
    occ, typ = [], []
    for i in range(0, len(crops), batch):
        x = torch.from_numpy(crops[i : i + batch]).permute(0, 3, 1, 2).float() / 255.0
        o, t = model(x)
        occ.append(o)
        typ.append(t)
    return torch.cat(occ), torch.cat(typ)


def run_epoch_metrics(model: SquareNet, data: CropSet, loss_fns) -> dict[str, float]:
    occ_l, typ_l = predict_logits(model, data.crops)
    occ_y, typ_y = split_label(data.labels)
    occ_y_t, typ_y_t = torch.from_numpy(occ_y), torch.from_numpy(typ_y)
    occupied = typ_y_t >= 0
    loss = loss_fns[0](occ_l, occ_y_t).item()
    if occupied.any():
        loss += loss_fns[1](typ_l, typ_y_t).item()
    type_acc = (
        (typ_l[occupied].argmax(1) == typ_y_t[occupied]).float().mean().item()
        if occupied.any()
        else 0.0
    )
    return {
        "loss": loss,
        "occ_acc": (occ_l.argmax(1) == occ_y_t).float().mean().item(),
        "type_acc": type_acc,
    }


def train(cfg: Config) -> Path:
    torch.manual_seed(cfg.seed)
    np.random.seed(cfg.seed)
    assignment, sessions, paths = make_splits(cfg)
    train_set = load_split(paths, assignment, "train")
    val_set = load_split(paths, assignment, "val")
    if train_set is None:
        raise SystemExit("the split left no training games; add more games or sessions")
    if cfg.max_train_crops and len(train_set) > cfg.max_train_crops:
        keep = np.random.default_rng(cfg.seed).choice(len(train_set), cfg.max_train_crops, False)
        train_set = CropSet(
            train_set.crops[keep], train_set.labels[keep], train_set.game[keep], train_set.games
        )

    model = SquareNet(cfg.backbone, cfg.pretrained)
    if cfg.init_from:
        model.load_state_dict(torch.load(cfg.init_from, map_location="cpu"))
    w_occ, w_typ = class_weights(train_set.labels)
    loss_occ = nn.CrossEntropyLoss(torch.from_numpy(w_occ), label_smoothing=cfg.label_smoothing)
    # The type loss ignores empty squares (label -1).
    loss_typ = nn.CrossEntropyLoss(
        torch.from_numpy(w_typ), ignore_index=-1, label_smoothing=cfg.label_smoothing
    )
    opt = torch.optim.AdamW(
        [
            {"params": model.backbone.parameters(), "lr": cfg.lr_backbone},
            {"params": model.head_parameters(), "lr": cfg.lr_head},
        ],
        weight_decay=cfg.weight_decay,
    )
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=cfg.epochs)
    loader = DataLoader(
        CropDataset(train_set.crops, train_set.labels, cfg.augment, cfg.seed),
        batch_size=cfg.batch_size,
        shuffle=True,
        num_workers=cfg.workers,
        drop_last=False,
    )

    out = Path(cfg.out_dir) / cfg.name
    out.mkdir(parents=True, exist_ok=True)
    history, best, bad = [], float("inf"), 0
    monitor = val_set if val_set is not None else train_set
    for epoch in range(1, cfg.epochs + 1):
        model.train()
        t0, total = time.time(), 0.0
        for x, occ_y, typ_y in loader:
            opt.zero_grad()
            o, t = model(x)
            loss = loss_occ(o, occ_y)
            if (typ_y >= 0).any():  # a batch of only empty squares has no type target
                loss = loss + loss_typ(t, typ_y)
            loss.backward()
            opt.step()
            total += loss.item() * len(occ_y)
        sched.step()
        metrics = run_epoch_metrics(model, monitor, (loss_occ, loss_typ))
        row = {
            "epoch": epoch,
            "train_loss": total / len(train_set),
            **metrics,
            "seconds": round(time.time() - t0, 1),
        }
        history.append(row)
        print(json.dumps(row), flush=True)
        if metrics["loss"] < best - 1e-4:
            best, bad = metrics["loss"], 0
            torch.save(model.state_dict(), out / "model.pt")
        else:
            bad += 1
            if bad >= cfg.patience:
                print("early stopping")
                break

    (out / "config.json").write_text(json.dumps(asdict(cfg), indent=2), encoding="utf-8")
    (out / "split.json").write_text(
        json.dumps({"assignment": assignment, "sessions": sessions}, indent=2), encoding="utf-8"
    )
    (out / "metrics.json").write_text(
        json.dumps(
            {
                "seed": cfg.seed,
                "git_commit": git_commit(),
                "monitored_split": "val" if val_set is not None else "train (no val games)",
                "train_crops": len(train_set),
                "history": history,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, required=True)
    args = ap.parse_args(argv)
    print(f"saved to {train(Config.load(args.config))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
