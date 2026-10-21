# Plan: Training a Top-Down Chess Piece Detector

Status: implemented as scaffolding under `ml/` (see `ml/README.md`). Nothing has been trained on
real footage yet; every result so far is synthetic only.

## 0. Decide the approach first

**Classify each square instead of detecting objects.** The pipeline already warps the board to a flat 800×800 image, so every square is a known 100×100 region. Cropping 64 squares and classifying each one is simpler, faster and easier to train than a general object detector, and it needs only simple labels (one class per square).

**Be honest about top-down limits.** From directly overhead, pieces look like circles of different sizes. Telling empty from white from black is easy. Telling **knight, bishop, rook, queen and king** apart is much harder, because the height cues are gone. So:

- Split the problem into two heads: **occupancy/color** (empty, white, black) and **piece type** (6 classes).
- Run a **quick feasibility test** (Section 3) before investing in the full pipeline.
- Use the model as a **verifier and recovery tool** alongside the move tracker, not as a replacement. The tracker already knows piece identity from the rules of the game.

If the camera can be tilted slightly (say 15 to 30 degrees off vertical), piece-type accuracy improves a lot. Test both.

## 1. Targets and metrics

| Metric | Why it matters | Starting goal (not a guarantee) |
|---|---|---|
| Occupancy/color accuracy per square | Core signal for verification | 99%+ on held-out real games |
| Piece-type accuracy per occupied square | Hardest part from above | 90%+ |
| Full-board exact match | The strictest metric | Report it; expect it to be much lower |
| Per-class precision/recall and confusion matrix | Shows which pieces get confused | Review every run |
| CPU latency for 64 crops | Must run on a laptop | Under 50 ms per board |

Report synthetic and real results separately, as in the rest of the project.

## 2. Data

### 2.1 Auto-labeling from your own games (best source)

The move tracker already knows the exact position after each move. For games you record where you also know the PGN:

1. Run the pipeline on the video and, at each stable frame, save the 64 warped square crops.
2. Label each crop from the tracker's board state (for example "white knight" or "empty").
3. Manually spot-check about 5% of the crops, because a tracker error becomes a wrong label.

This gives labeled data almost for free, and it matches the real camera, board and lighting exactly.

### 2.2 Synthetic data

- Render positions from Lichess PGNs using piece images or 3D models (Blender is optional). Check the license on any piece models or sprites used.
- Randomize: board colors, piece styles, lighting, shadows, camera noise, blur, small perspective errors, slightly off-center pieces and random rotation.
- Use synthetic data to pretrain, then fine-tune on real crops.

### 2.3 Public datasets (optional pretraining)

ChessReD (10,800 smartphone photos) and Roboflow chess datasets can help pretrain, but they use other boards and angles. Check each license before commercial use. Fine-tune on your own crops in any case.

### 2.4 Collection protocol

- Record at least **20 to 30 games** with 2 or more lighting setups, and ideally 2 board and piece sets.
- Include sloppy placement, pieces near square edges, shadows from hands and fast play.
- Capture promotions with real extra queens, and positions with few pieces (endgames), since empties dominate otherwise.

### 2.5 Splits (important)

Split by **game and session**, never randomly by crop. Consecutive frames are nearly identical, so a random split leaks test data into training and gives fake accuracy.

| Split | Content |
|---|---|
| Train | About 70% of games |
| Validation | About 15%, different games |
| Test | About 15%, ideally a different lighting setup or board |

### 2.6 Class balance

Empty squares are around 60% of all crops. Use class weights or oversample rare classes (kings, queens). Make sure every class has enough crops, since kings and queens appear only once per side per game.

## 3. Feasibility test (day 1)

Before training anything heavy:

1. Crop about 500 squares from real footage.
2. Train a tiny CNN or logistic regression on color-versus-empty and look at the accuracy.
3. Look at crops of king versus queen and bishop versus knight by eye. If you can't tell them apart, the model won't either, and you should tilt the camera or rely more on tracking.

## 4. Preprocessing

- Take the warped board and crop each square with **padding** (for example 100 px plus 14 px on each side, giving 128×128) so overhanging pieces and neighbor context are included.
- Resize to **96×96 or 112×112** (try both) and normalize with ImageNet statistics if using a pretrained backbone.
- Keep the same crop function for training and inference, in one shared module, because a mismatch there is a common silent bug.

## 5. Model

| Option | When to use |
|---|---|
| **Tiny CNN from scratch** (4 conv blocks) | Baseline; fast, easy to explain |
| **MobileNetV3-Small or EfficientNet-B0** (pretrained, via PyTorch / timm) | Recommended main model; good accuracy on CPU |
| **ResNet18** | Solid fallback |
| **YOLO-style detector** on the warped board | Only if a detection approach is wanted; check the license of the library, as some popular ones use AGPL, which matters if this is sold |

**Two heads** on the shared backbone:

- Head A: 3 classes (empty, white, black)
- Head B: 6 classes (pawn, knight, bishop, rook, queen, king), trained only on occupied squares

Combined output: 13 classes (empty plus 12 colored pieces).

```python
import torch.nn as nn, timm

class SquareNet(nn.Module):
    def __init__(self):
        super().__init__()
        self.backbone = timm.create_model("mobilenetv3_small_100",
                                          pretrained=True, num_classes=0)
        d = self.backbone.num_features
        self.occ = nn.Linear(d, 3)    # empty / white / black
        self.typ = nn.Linear(d, 6)    # P N B R Q K

    def forward(self, x):
        f = self.backbone(x)
        return self.occ(f), self.typ(f)
```

## 6. Training

- **Framework:** PyTorch, run on Google Colab or Kaggle free GPUs, or CPU for the small model.
- **Loss:** cross-entropy with label smoothing (about 0.05); type loss masked to occupied squares; class weights for imbalance.
- **Optimizer:** AdamW, cosine learning-rate schedule, learning rate about 1e-3 for the heads and 3e-4 for the backbone, weight decay 1e-4.
- **Schedule:** 30 to 50 epochs, batch size 128, mixed precision, early stopping on validation loss.
- **Augmentation:** color and brightness jitter, gaussian blur and noise, small shifts and scaling (about ±8%), small rotations, perspective jitter, random shadows, random erasing. Horizontal flips are fine for piece classes, but don't alter color-related channels in ways that could flip white and black.
- **Stages:** (1) pretrain on synthetic, (2) fine-tune on real, (3) compare against real-only training so you know whether synthetic data helps.
- **Tracking:** TensorBoard or Weights & Biases (free tier), and save the config, seed and git commit with every run.

## 7. Evaluation

1. Per-class precision, recall and a confusion matrix (expect knight and bishop, and king and queen, to be the weakest).
2. Per-square and full-board exact-match accuracy on the test games.
3. Break results down by lighting, board and square position (edges and corners are often worse).
4. Calibrate confidence (temperature scaling), because probabilities are used in decoding.
5. Review the 50 worst errors by eye each iteration and fix data problems first, model problems second.

## 8. Integrating with the move tracker (where it pays off)

Don't use the classifier alone. Use it in three ways:

1. **Verification:** after each detected move, compare the classifier's occupancy with the tracker's board. If they disagree on several squares, flag a possible desync.
2. **Better move choice:** score each legal move by how well the resulting board matches the classifier's probabilities, and combine that with the frame-differencing score. This resolves ambiguous moves.
3. **Recovery:** after a desync, predict the full position, then apply consistency rules (exactly one king per side, at most 8 pawns, no pawns on the first or last rank, plausible piece counts) and ask the operator to confirm a corrected FEN.

## 9. Deployment

- Export to **ONNX** and run with **onnxruntime** on CPU.
- Batch all 64 crops in one call; target under 50 ms.
- Keep the model file versioned (GitHub release or GHCR), with a short model card (data used, metrics, known weaknesses).
- Keep inference in the edge client, not the cloud.

```python
import torch
model.eval()
torch.onnx.export(model, torch.randn(1, 3, 96, 96), "squarenet.onnx",
                  input_names=["x"], output_names=["occ", "typ"],
                  dynamic_axes={"x": {0: "batch"}})
```

## 10. Repository layout for the ML part

```
ml/
  data/           raw clips, crops (git-ignored), labels.csv
  scripts/
    extract_crops.py    video + PGN -> labeled square crops
    render_synthetic.py PGN -> synthetic boards -> crops
    split.py            split by game/session
  train.py              training loop and config
  evaluate.py           metrics, confusion matrix, error gallery
  export_onnx.py
  configs/              yaml per experiment
  models/               exported .onnx + model card
```

CI should include a tiny fixture test: load the ONNX model, run it on a few sample crops and check the output shape and a minimum accuracy.

## 11. Timeline (about 8 to 10 days, after the MVP works)

| Day | Work |
|---|---|
| 1 | Feasibility test on real crops; decide camera tilt |
| 2 to 3 | Auto-label extraction, record more games, spot-check labels |
| 3 to 4 | Synthetic generator and first baseline model |
| 5 to 6 | Pretrained backbone, augmentation, two-head training, ablations |
| 7 | Evaluation, error analysis, fix data issues |
| 8 | ONNX export, integrate as verifier and move scorer |
| 9 to 10 | Tests, model card, README results, buffer |

If time is short, do only the **occupancy/color** head. It gives most of the verification value and is the easiest to get right.

## 12. Risks

| Risk | Mitigation |
|---|---|
| Piece types indistinguishable from above | Feasibility test; tilt the camera; lean on the tracker for identity |
| Label noise from tracker errors | Spot-check; drop low-confidence frames from training |
| Data leakage inflating accuracy | Split by game and session |
| Overfitting to one board and lighting | Multiple setups, strong augmentation, a held-out board |
| Class imbalance | Weights, oversampling, per-class metrics |
| Dataset or model license limits | Check licenses before commercial use |
| Scope creep | Do the occupancy head first; treat piece type as a stretch |
