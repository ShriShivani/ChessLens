# Accuracy

Every number on this page was printed by an evaluation script. Synthetic and real results
are kept apart and must never be mixed or averaged together.

## Synthetic footage

Produced by `python -m tests.eval` on 2026-10-19 (default settings: 3 hand-written games
plus 6 seeded random games of 30 plies, every game filmed through a simulated perspective
camera with lighting drift, sensor noise, corner-click error and a simulated hand moving over
the board for each move; White on all four sides of the image across games).

| | Result |
|---|---|
| Games / moves | 9 / 237 |
| Moves auto-accepted and correct | 236 (99.6%) |
| Flagged uncertain (nothing guessed) | 1 |
| Silently wrong | 0 |
| Missed | 0 |
| Games with every move correct | 8 / 9 |

| Move type | Correct / total |
|---|---|
| Quiet | 203 / 204 |
| Capture | 27 / 27 |
| Castling | 4 / 4 |
| En passant | 1 / 1 |
| Promotion (to queen) | 1 / 1 |

Scoring: after each move is judged the pipeline is resynced to the truth, as an operator
would with undo or force-move, so one miss does not corrupt every later move.

CI fails if accuracy drops below 95% or the silent-wrong rate rises above 1%
(`tests/eval_thresholds.json`).

### Stress runs (single factor, 4 games, `--no-threshold`)

These were spot checks while developing, not part of CI.

| Change from default | Result |
|---|---|
| Sensor noise sigma 6 (default 3) | 87 / 87 correct |
| Corner-click error 6 px (default 2) | 87 / 87 correct |
| Lighting drift 10% per move (default 4%) | 80 / 87 correct, 7 flagged uncertain, none wrong |
| Noise sigma 12 + corner error 8 px + drift 10% together (6 games) | 4 / 147 correct, 133 missed (no move reported), 10 flagged uncertain. Cause not diagnosed; the stability gate's absolute motion threshold is the main suspect |

### What these numbers do not tell you

- Synthetic pieces are flat discs with a letter on them over a plain two-colour board. Real
  pieces, real boards, shadows, glare and 3D hands are harder. Expect lower numbers.
- Synthetic hands are flat shapes drawn onto the board plane.
- Only queen promotions are generated; underpromotion cannot be detected at all.
- Nothing here says anything about accuracy on a real board.

## Piece classifier (`ml/`), synthetic only

From `python -m ml.evaluate --run ml/runs/synthetic_tiny --split test` on 2026-10-21: a tiny CNN
trained on 6 synthetic games and tested on 3 synthetic games from a lighting/colour session it
never saw (24 boards, 1,536 crops). The synthetic pieces are an invented look, so none of this
says anything about real boards.

| Metric | Result |
|---|---|
| Occupancy/colour accuracy | 100.0% |
| Piece-type accuracy on occupied squares | 83.7% |
| 13-class square accuracy | 92.6% |
| Full-board exact match | 0 / 24 boards |
| Weakest classes by recall | black knight 2%, white knight 6%, white queen 62%, white bishop 67% |

Latency (CPU, onnxruntime, this development laptop, tiny model): about 62 ms per board
(12 ms cropping + 49 ms model), above the 50 ms target in the plan. Details and caveats:
[ml/models/MODEL_CARD.md](../ml/models/MODEL_CARD.md). There is no real-footage classifier result yet.

## Real footage

**No real clips have been evaluated yet.** To produce numbers, record clips and labels as
described in [tests/real/README.md](../tests/real/README.md), then run:

```powershell
python -m tests.eval_real --json tests/real/results.json
```

Paste the printed output here, with the date and clip count. That evaluation is stricter than
the synthetic one: it has no operator resync and reports the number of moves correct before
the first mistake.

| Date | Clips | Truth moves | Correct-prefix accuracy | Fully correct clips | Uncertain events |
|---|---|---|---|---|---|
| _not run yet_ | | | | | |
