"""Export a trained run to ONNX and check it against PyTorch.

Run:  python -m ml.export_onnx --run ml/runs/synthetic_tiny --out ml/models/squarenet.onnx

Writes the model plus `<out>.json` (input size, class names, calibration temperatures, source
run, git commit). Inference applies the temperatures; the graph itself outputs raw logits.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import onnxruntime as ort
import torch

from ml.common import CLASS_NAMES, DEFAULT_INPUT
from ml.evaluate import load_model
from ml.train import git_commit


def export(
    model: torch.nn.Module, out: Path, size: int, temperatures: tuple[float, float]
) -> float:
    """Export, reload with onnxruntime and return the max absolute logit difference."""
    model.eval()
    dummy = torch.rand(4, 3, size, size)
    torch.onnx.export(
        model,
        dummy,
        str(out),
        input_names=["x"],
        output_names=["occ", "typ"],
        dynamic_axes={"x": {0: "batch"}, "occ": {0: "batch"}, "typ": {0: "batch"}},
        opset_version=17,
        dynamo=False,
    )
    session = ort.InferenceSession(str(out), providers=["CPUExecutionProvider"])
    occ, typ = session.run(None, {"x": dummy.numpy()})
    with torch.no_grad():
        ref_occ, ref_typ = model(dummy)
    diff = max(
        float(np.abs(occ - ref_occ.numpy()).max()), float(np.abs(typ - ref_typ.numpy()).max())
    )
    sidecar = {
        "input_size": size,
        "classes": CLASS_NAMES,
        "temperature_occ": temperatures[0],
        "temperature_typ": temperatures[1],
        "max_abs_logit_diff_vs_torch": diff,
    }
    out.with_suffix(".json").write_text(json.dumps(sidecar, indent=2), encoding="utf-8")
    return diff


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("ml/models/squarenet.onnx"))
    ap.add_argument("--size", type=int, default=DEFAULT_INPUT)
    args = ap.parse_args(argv)

    temps = (1.0, 1.0)
    for eval_file in sorted(args.run.glob("eval_*.json")):
        res = json.loads(eval_file.read_text(encoding="utf-8"))
        temps = (res.get("temperature_occ", 1.0), res.get("temperature_typ", 1.0))
        break
    args.out.parent.mkdir(parents=True, exist_ok=True)
    diff = export(load_model(args.run), args.out, args.size, temps)
    meta = json.loads(args.out.with_suffix(".json").read_text(encoding="utf-8"))
    meta.update({"source_run": str(args.run), "git_commit": git_commit()})
    args.out.with_suffix(".json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    print(f"wrote {args.out} (max logit difference vs torch: {diff:.2e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
