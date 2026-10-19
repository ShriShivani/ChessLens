# ChessLens: conventions for Claude Code

Turns camera video of a physical chessboard into moves, PGN and a live web broadcast. Vision runs on the edge laptop; only move events go to the server. See PLAN.md for scope.

## Layout
- `edge/` Python client (camera -> moves). OpenCV, python-chess.
- `server/` FastAPI + SQLAlchemy (SQLite default). WebSockets `/ws/ingest/{id}` (token) and `/ws/games/{id}` (public).
- `web/` React + TypeScript (strict) + Vite. Static build.
- `infra/` Terraform. Never run `terraform apply` or create cloud resources without explicit user confirmation.
- `tests/` fixtures, synthetic generator, `eval.py`.

## Rules
- Windows 11 / PowerShell first. Scripts must work on Windows (provide bash too if needed).
- Never fabricate metrics. Accuracy numbers come only from `tests/eval.py`, synthetic and real kept separate.
- Never commit secrets. Config goes through `.env` (see `.env.example`). AWS auth via GitHub OIDC only.
- No AWS until the user says an account exists. Free tier only; no NAT gateway, load balancer, RDS or Fargate.
- Type hints, small functions, simple readable code. Conventional commits.
- Anything cut from scope goes in `docs/ROADMAP.md`.

## Commands (PowerShell; venv at `.venv`)
- Setup: `python -m venv .venv ; .\.venv\Scripts\pip install -r requirements-dev.txt`
- Lint: `.\.venv\Scriptsuff check . ; .\.venv\Scriptsuff format --check .`
- Tests: `.\.venv\Scripts\python -m pytest -q`
- Synthetic accuracy eval (fails below `tests/eval_thresholds.json`): `.\.venv\Scripts\python -m tests.eval`
- Make a test video: `python -m tests.make_video tests/games/italian_castling.pgn tests/fixtures/italian`
- Edge: `python -m edge calibrate --source 0` then `python -m edge run --source 0` (source = index, URL or file)
- Web / full stack (later phases): `cd web ; npm ci ; npm run lint ; npm test` and `docker compose up --build`

## Edge design notes
- `edge/detector.py` scores each legal move by change on its expected squares minus a leak penalty; flags "uncertain" instead of guessing.
- Exposure is matched with a robust gain+offset fit before differencing (global lighting shifts must not look like moves).
- Operator controls act on `Pipeline.last_stable` (never a frame with a hand in it).
