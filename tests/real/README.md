# Real footage: how to record and label clips

Real clips measure what synthetic data cannot: glare, shadows, real hands, sloppy
placement and phone-camera quirks. Video files here are git-ignored (only this README is
committed). Real numbers are always reported separately from synthetic ones.

## What to record (10 to 20 clips)

Aim for short clips (a full game of 20 to 60 moves, or a 5 to 15 move excerpt), shot in
different conditions. Cover at least:

| Clip type | Why |
|---|---|
| Normal opening, quiet moves | Baseline |
| Captures, including a recapture | Capture squares change colour |
| Kingside and queenside castling | Four squares change |
| An en passant capture | Three squares change |
| A promotion (queen) | Default promotion piece |
| Fast play (blitz speed, one hand moves, one hand presses the clock) | Stability gate timing |
| Sloppy placement (pieces slightly off centre) | Robustness |
| Different lighting (daylight, lamp, evening) | Exposure matching |
| White at the bottom and, if you can, White on the other side | Orientation |

Underpromotion is not supported (the piece type is not visible); avoid it in clips.

## Camera setup

1. Fixed camera, overhead or a steep angle. A tripod or a stack of books works.
2. The whole board and a little margin in frame; the camera must not move during a clip.
3. Even light, no glare on the board. A matte board helps a lot.
4. Phone as webcam: DroidCam or IP Webcam. Record with the phone's own camera app
   (or OBS) to an `.mp4`; do not rely on the live stream for ground-truth clips.
5. Start each clip with the starting position set up and the board still for a second.
   If the clip starts from another position, say so in the PGN (a `[FEN "..."]` header
   and `[SetUp "1"]`).

## Label each clip (ground truth)

For every `NAME.mp4` create two more files in this folder:

1. `NAME.pgn`: the full list of moves actually played, written by you from the scoresheet
   or from watching the clip. Standard PGN, for example:

   ```
   [Event "Club game 1"]
   [Result "*"]

   1. e4 e5 2. Nf3 Nc6 3. Bb5 a6 *
   ```

   Check it opens in any chess program; an illegal move makes the file unusable.
2. `NAME.calibration.json`: click the four board corners once, using the first frame of
   the clip:

   ```powershell
   python -m edge calibrate --source tests/real/NAME.mp4 --out tests/real/NAME.calibration.json --white-side bottom
   ```

   Click clockwise starting at the board corner nearest the image's top-left, then press
   Enter. Use `--white-side left|right|top` if White is not at the bottom of the image.

## Run the evaluation

```powershell
python -m tests.eval_real --json tests/real/results.json
```

It reports, per clip and overall, how many moves were right before the first mistake,
how many moves were accepted, and how often the pipeline flagged a move as uncertain.
There is no operator resync, so this is stricter than the synthetic evaluation.

Copy the printed numbers into `docs/ACCURACY.md` under "Real footage" with the date and
the number of clips. Do not edit the numbers by hand.
