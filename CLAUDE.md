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

## Commands (filled in as phases land)
- Python lint: `ruff check . ; ruff format --check .`
- Python tests: `pytest`
- Web: `cd web ; npm ci ; npm run lint ; npm test ; npm run build`
- Full stack: `docker compose up --build`
