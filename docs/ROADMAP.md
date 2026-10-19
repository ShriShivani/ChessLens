# Roadmap

Items cut from the MVP are recorded here.

## Out of scope for MVP
- User accounts, multi-board tournaments, payments, native mobile apps, cloud-side video processing.

## COULD (only if time remains)
- Stockfish evaluation bar
- Trivy / tfsec scans in CI
- CloudFront for the frontend
- Per-square CNN for automatic desync recovery

## Known gaps (edge vision)
- Underpromotion: piece type is not visible, so promotions default to queen; the operator overrides via force move.
- A hand resting on or beside the board for longer than the stability time is only handled by the "too many squares changed" check.
- Synthetic hands are flat 2D blobs drawn in board space; real hands cast shadows and occlude in 3D.
- Very noisy video (synthetic sigma 12) stops the stability gate from firing; the threshold is absolute, not adaptive.
- Lighting drift of 10% per move produced uncertain flags in a spot check.
