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
- Extremely degraded synthetic video (noise sigma 12, 8 px corner error, 10% lighting drift) gave 4/147 moves correct, mostly missed. Cause not diagnosed; suspect the stability gate's absolute motion threshold (not adaptive to noise).
- Lighting drift of 10% per move produced uncertain flags in a spot check.

## Server gaps
- Stockfish evaluation: the `STOCKFISH_*` variables in `.env.example` are placeholders; not implemented (COULD item).
- Rate limiting and viewer fan-out are per-process in memory (single instance only).
- No auth beyond the shared ingest token; anyone can read games.
- Blocking SQLite calls run inside async handlers; fine at this scale, revisit for many concurrent edges.

## Deployment and verification gaps (honest status)
- Docker images, `docker compose up`, the GitHub Actions workflows and the Terraform code have not been executed. Docker Desktop's engine did not respond on the development machine, `terraform` is not installed there, and nothing has been pushed to GitHub. CI is their first real test.
- `infra/.terraform.lock.hcl` has not been generated; run `terraform init` once and commit it.
- Trivy fails the build on HIGH/CRITICAL findings with fixes available; base-image CVEs may need a pin bump.
- No TLS: the deployed site is plain HTTP. Options: a TLS proxy (Cloudflare) or Caddy with a domain.
- The VM deploy uses `docker run` through an SSM script, not the compose file.
- Real-board accuracy has not been measured; see `docs/ACCURACY.md` and `tests/real/README.md`.

## ML classifier (see docs/ML_PLAN.md and ml/README.md)
- Not done: any training on real crops, the day-1 feasibility test, a pretrained MobileNetV3 run, synthetic-pretrain vs real-only comparison, per-lighting breakdown, TensorBoard/W&B logging.
- Synthetic knights are almost never recognised (small mark); the renderer or a tilted real camera are the next things to look at.
- CPU latency above the 50 ms target (about 62 ms for the tiny model); try a smaller input or lighter backbone.
- The classifier prior can only lower move scores; it cannot rescue a move whose frame-difference confidence is below threshold. One synthetic seed (11) shows such a first-move miss even without a classifier.
- Recovery proposals do not set castling rights or en passant; the operator must check the FEN.
