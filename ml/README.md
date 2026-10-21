# ml/: per-square piece classifier

Implements [docs/ML_PLAN.md](../docs/ML_PLAN.md). Each of the 64 squares of the warped board is
cropped and classified into 13 classes (empty plus 12 coloured pieces) by a two-head model:
occupancy/colour (3 classes) and piece type (6 classes, occupied squares only).

**Role:** a verifier and recovery aid next to the move tracker, not a replacement. The tracker
knows piece identity from the rules of chess; the classifier checks it.

**Status:** the code path works end to end on SYNTHETIC data. **Nothing has been trained on
real footage**, so nothing here says how well it works on a real board. See "What the synthetic
numbers mean" below.

## Install

```powershell
.\.venv\Scripts\pip install -r requirements-ml.txt    # torch (CPU), timm, onnx, onnxruntime
```

The edge client only needs `onnxruntime` (and the ONNX file) to use a trained model.

## Workflow

```powershell
# 0. Day-1 feasibility test on a few hundred real crops (needs real data, see step 1)
python -m ml.scripts.feasibility ml/data/real --crops 500

# 1. Real data: video + ground-truth PGN + calibration -> labelled crops (auto-labelled
#    from the tracker, only while it agrees with the PGN) and a 5% spot-check sheet
python -m ml.scripts.extract_crops tests/real/clip1.mp4 --out ml/data/real --session home-lamp

# 2. Synthetic data for pretraining (invented top-down pieces; labelled as synthetic)
python -m ml.scripts.render_synthetic --out ml/data/synthetic --games 12 --positions 8

# 3. Train (config files in ml/configs; run folder ml/runs/<name> is git-ignored)
python -m ml.train --config ml/configs/synthetic_tiny.yaml
python -m ml.train --config ml/configs/real_finetune_mobilenet.yaml   # uses downloaded weights

# 4. Evaluate on the held-out split, or on any crop folder (real vs synthetic stay separate)
python -m ml.evaluate --run ml/runs/synthetic_tiny --split test
python -m ml.evaluate --run ml/runs/real_mobilenet --data ml/data/real

# 5. Export for the edge client and use it
python -m ml.export_onnx --run ml/runs/real_mobilenet --out ml/models/squarenet.onnx
python -m edge run --source 0 --classifier ml/models/squarenet.onnx --server ...
```

Splits are by **session, then game** (`ml/splits.py`): crops from one game or one lighting/board
setup never appear in two splits, because consecutive frames are nearly identical. Give each
lighting or board setup its own `--session` name when extracting crops so the test split is a
setup the model has not seen.

## How the edge client uses the model (`edge/verify.py`)

1. **Verification:** after each stable frame, squares where the classifier confidently disagrees
   with the tracked board are counted; three or more raise a `desync` event.
2. **Move choice:** each legal move's score gets a penalty (never a bonus) proportional to how
   much less the classifier likes the position it would produce than its favourite move.
3. **Recovery:** the full board is decoded and repaired with chess rules (one king per side, at
   most 8 pawns, no pawns on the first or last rank, promotion counts). If a consistent position
   results it is proposed in the `desync` event; pressing `r` adopts it after the operator has
   looked at it. Castling rights and en passant are not guessed.

## Files

| Path | Purpose |
|---|---|
| `common.py` | The one crop function (128 px padded, resized to 96), class layout, labels |
| `splits.py` | Split by game/session and a leakage check |
| `data.py` | `.npz` crop files, class weights |
| `augment.py` | Geometry, light, blur, noise, erasing; never inverts colour |
| `synthetic.py` | Invented top-down piece renderer (not real pieces) |
| `model.py` | `SquareNet`: tiny CNN or any timm backbone, normalisation inside the model |
| `train.py` | Training loop; saves config, split, seed and git commit with every run |
| `evaluate.py` | Per-class precision/recall, confusion matrix, board exact match, calibration, error gallery |
| `export_onnx.py`, `infer.py` | ONNX export with parity check; onnxruntime inference |
| `scripts/` | `extract_crops`, `render_synthetic`, `feasibility` |
| `models/` | Exported `.onnx` (git-ignored) and the model card |

## What the synthetic numbers mean

The synthetic renderer draws discs with small per-type marks (a knight "head" blob, a bishop slit,
a rook with corner notches, a queen ring of dots, a king cross). That look is invented here. Real
top-down pieces differ, so a model that scores well on it has shown only that the pipeline works
and that colour/occupancy are easy. Its weak spots (see the model card) point at the same
difficulty the plan predicts for real boards: knights and bishops are hard to tell apart from above.

## Known gaps

- No real data, so no real numbers. The first real step is the feasibility test.
- No pretrained-backbone run was done here; `real_finetune_mobilenet.yaml` needs a download of
  timm weights and real crops.
- CPU latency of the tiny model was about 62 ms per board on the development laptop (12 ms
  cropping, 49 ms model), above the plan's 50 ms target. It runs once per stable frame, not per
  video frame. A smaller input size or a lighter backbone are the first things to try.
- The move-choice prior can only lower scores, so it widens margins but cannot rescue a move
  whose frame-difference confidence is below the threshold.
