# Resume bullets

Rule: only numbers produced by an evaluation script, labelled synthetic or real. Delete any
technology you did not actually use or run.

## Current state (draft, fully traceable)

**ChessLens: Real-Time Chess Digitization and Live Broadcast** (Oct. 2026 to Present)
*Python, OpenCV, python-chess, FastAPI, WebSockets, SQLite, React, TypeScript, Docker, GitHub Actions*

- Built a computer-vision pipeline that converts camera video of a physical chessboard into
  moves and PGN without a sensor board, using perspective calibration, a stability gate and
  legal-move tracking that flags uncertain moves instead of guessing.
- Evaluated it on generated footage (simulated perspective, lighting drift, noise and hands):
  236 of 237 moves correct (99.6%), none silently wrong, across 9 games; evaluation gates the
  CI pipeline (synthetic data only; real-board evaluation is a separate pending step).
- Streamed games to a React/TypeScript spectator page through a FastAPI WebSocket backend with
  an edge uploader that reconciles state after network outages; 67 Python and 22 web tests.

## Add only after you have actually done it

- Real footage: "achieving X% correct-prefix move accuracy over N real games" from
  `python -m tests.eval_real` (record the date and clip count).
- Cloud: "deployed on AWS (EC2) with Terraform and GitHub OIDC" only after a successful
  `terraform apply` and CD run. Until then drop AWS and Terraform from the technology list.
- CI: "automated CI with GitHub Actions" only after the workflow has run green on GitHub.
