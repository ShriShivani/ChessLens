"""Evaluate a trained run on a split and write metrics, a confusion matrix and an error gallery.

Run:  python -m ml.evaluate --run ml/runs/synthetic_tiny --split test
      (add --data DIR to evaluate on a different crop folder, e.g. REAL crops)

Always say which data was used when quoting a number: synthetic and real are reported apart.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch

from ml.common import CLASS_NAMES, NUM_CLASSES, join_probs, split_label
from ml.data import CropSet, discover, load_games, read_meta
from ml.model import SquareNet
from ml.train import load_split, predict_logits


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = logits / temperature
    z = z - z.max(1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(1, keepdims=True)


def fit_temperature(logits: np.ndarray, y: np.ndarray) -> float:
    """Single temperature minimising negative log-likelihood (run on validation data)."""
    keep = y >= 0
    if not keep.any():
        return 1.0
    lg, yy = torch.from_numpy(logits[keep]).float(), torch.from_numpy(y[keep])
    log_t = torch.zeros(1, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

    def closure():
        opt.zero_grad()
        loss = torch.nn.functional.cross_entropy(lg / log_t.exp(), yy)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp().item())


def expected_calibration_error(probs: np.ndarray, y: np.ndarray, bins: int = 10) -> float:
    keep = y >= 0
    if not keep.any():
        return 0.0
    p, yy = probs[keep], y[keep]
    conf, pred = p.max(1), p.argmax(1)
    ece = 0.0
    for lo in np.linspace(0, 1, bins, endpoint=False):
        m = (conf > lo) & (conf <= lo + 1 / bins)
        if m.any():
            ece += m.mean() * abs((pred[m] == yy[m]).mean() - conf[m].mean())
    return float(ece)


def confusion(y: np.ndarray, pred: np.ndarray, n: int = NUM_CLASSES) -> np.ndarray:
    m = np.zeros((n, n), dtype=np.int64)
    np.add.at(m, (y, pred), 1)
    return m


def per_class(cm: np.ndarray, names: list[str]) -> dict[str, dict[str, float]]:
    out = {}
    for i, name in enumerate(names):
        tp, support, predicted = cm[i, i], cm[i].sum(), cm[:, i].sum()
        out[name] = {
            "precision": float(tp / predicted) if predicted else 0.0,
            "recall": float(tp / support) if support else 0.0,
            "support": int(support),
        }
    return out


def evaluate_arrays(
    occ_logits: np.ndarray,
    typ_logits: np.ndarray,
    labels: np.ndarray,
    t_occ: float = 1.0,
    t_typ: float = 1.0,
) -> dict:
    occ_y, typ_y = split_label(labels)
    occ_p, typ_p = softmax(occ_logits, t_occ), softmax(typ_logits, t_typ)
    pred = join_probs(occ_p, typ_p).argmax(1)
    occupied = typ_y >= 0
    correct = pred == labels
    boards = correct.reshape(-1, 64)
    square = np.arange(len(labels)) % 64
    file, rank = square % 8, square // 8
    border = (file == 0) | (file == 7) | (rank == 0) | (rank == 7)
    cm = confusion(labels, pred)
    return {
        "crops": int(len(labels)),
        "boards": int(len(labels) // 64),
        "occupancy_accuracy": float((occ_p.argmax(1) == occ_y).mean()),
        "type_accuracy_on_occupied": float(
            (typ_p[occupied].argmax(1) == typ_y[occupied]).mean() if occupied.any() else 0.0
        ),
        "class_accuracy": float(correct.mean()),
        "full_board_exact_match": float(boards.all(1).mean()) if len(boards) else 0.0,
        "border_square_accuracy": float(correct[border].mean()),
        "interior_square_accuracy": float(correct[~border].mean()),
        "occupancy_ece": expected_calibration_error(occ_p, occ_y),
        "per_class": per_class(cm, CLASS_NAMES),
        "confusion_matrix": cm.tolist(),
    }


def error_gallery(
    crops: np.ndarray, labels: np.ndarray, probs: np.ndarray, path: Path, count: int = 50
) -> None:
    """The most confidently wrong crops, with true and predicted class written on each tile."""
    pred = probs.argmax(1)
    wrong = np.flatnonzero(pred != labels)
    if not len(wrong):
        return
    worst = wrong[np.argsort(-probs[wrong, pred[wrong]])][:count]
    tile, cols = crops.shape[1], 10
    rows = -(-len(worst) // cols)
    sheet = np.full((rows * (tile + 26), cols * tile, 3), 255, dtype=np.uint8)
    for k, i in enumerate(worst):
        r, c = divmod(k, cols)
        y, x = r * (tile + 26), c * tile
        sheet[y + 26 : y + 26 + tile, x : x + tile] = crops[i]
        cv2.putText(sheet, f"T:{CLASS_NAMES[labels[i]]}", (x + 2, y + 10), 0, 0.35, (0, 120, 0), 1)
        cv2.putText(sheet, f"P:{CLASS_NAMES[pred[i]]}", (x + 2, y + 22), 0, 0.35, (0, 0, 200), 1)
    cv2.imwrite(str(path), cv2.cvtColor(sheet, cv2.COLOR_RGB2BGR))


def load_model(run: Path) -> SquareNet:
    cfg = json.loads((run / "config.json").read_text(encoding="utf-8"))
    model = SquareNet(cfg["backbone"], pretrained=False)
    model.load_state_dict(torch.load(run / "model.pt", map_location="cpu"))
    return model.eval()


def evaluate_run(run: Path, split: str, data_dir: Path | None) -> dict:
    model = load_model(run)
    meta = json.loads((run / "split.json").read_text(encoding="utf-8"))
    cfg = json.loads((run / "config.json").read_text(encoding="utf-8"))
    if data_dir:
        data: CropSet | None = load_games(discover(data_dir))
        source = str(data_dir)
    else:
        paths = {}
        for d in cfg["data_dirs"]:
            for p in discover(d):
                paths[read_meta(p)[0]] = p
        data = load_split(paths, meta["assignment"], split)
        source = f"{split} split of {cfg['data_dirs']}"
    if data is None:
        raise SystemExit(f"no games in the {split} split")

    # Temperature is fitted on validation crops (never on the data being evaluated).
    t_occ = t_typ = 1.0
    paths_all = {read_meta(p)[0]: p for d in cfg["data_dirs"] for p in discover(d)}
    val = load_split(paths_all, meta["assignment"], "val")
    if val is not None:
        vo, vt = predict_logits(model, val.crops)
        v_occ_y, v_typ_y = split_label(val.labels)
        t_occ = fit_temperature(vo.numpy(), v_occ_y)
        t_typ = fit_temperature(vt.numpy(), v_typ_y)

    occ_l, typ_l = (x.numpy() for x in predict_logits(model, data.crops))
    result = evaluate_arrays(occ_l, typ_l, data.labels, t_occ, t_typ)
    result["uncalibrated_occupancy_ece"] = expected_calibration_error(
        softmax(occ_l), split_label(data.labels)[0]
    )
    result.update({"data": source, "temperature_occ": t_occ, "temperature_typ": t_typ})
    probs = join_probs(softmax(occ_l, t_occ), softmax(typ_l, t_typ))
    error_gallery(data.crops, data.labels, probs, run / f"errors_{split}.png")
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--split", choices=["train", "val", "test"], default="test")
    ap.add_argument("--data", type=Path, help="evaluate on this crop folder instead of a split")
    args = ap.parse_args(argv)
    res = evaluate_run(args.run, args.split, args.data)
    out = args.run / f"eval_{args.split if not args.data else args.data.name}.json"
    out.write_text(json.dumps(res, indent=2), encoding="utf-8")
    print(f"data: {res['data']}")
    for key in (
        "boards",
        "occupancy_accuracy",
        "type_accuracy_on_occupied",
        "class_accuracy",
        "full_board_exact_match",
        "border_square_accuracy",
        "interior_square_accuracy",
        "occupancy_ece",
        "uncalibrated_occupancy_ece",
        "temperature_occ",
        "temperature_typ",
    ):
        v = res[key]
        print(f"{key:<28} {v:.4f}" if isinstance(v, float) else f"{key:<28} {v}")
    weak = sorted(res["per_class"].items(), key=lambda kv: kv[1]["recall"])[:4]
    print("weakest classes by recall:", ", ".join(f"{k} {v['recall']:.2f}" for k, v in weak))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
