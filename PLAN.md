# ChessLens: Phase 0 Plan

Status: **draft, awaiting approval.** No code has been written yet.

## 1. Decisions (from the project brief)

| Item | Decision |
|---|---|
| OS | Windows 11; PowerShell-first scripts, Docker Desktop with WSL2 |
| Camera | Phone as webcam (DroidCam or IP Webcam). Supports OpenCV device index, RTSP/HTTP URL, and video files |
| AWS | No account yet. Nothing touches AWS until the user confirms an account exists (Phase 7). Everything runs locally until then |
| Frontend hosting | Undecided. Web app is built as static files so it works on Cloudflare Pages, Vercel, or S3 |
| Repo | Public GitHub repo, no secrets committed |
| Footage | Real physical board available |
| Scope | MVP only: MUST items (days 1-7), SHOULD items (days 8-11), COULD items only if time remains |

## 2. Assumptions (stated, not silently guessed)

1. **Move detection is tracking, not piece recognition.** The edge client holds a `python-chess` board and scores each legal move against measured per-square change. Ambiguous moves are flagged, never guessed.
2. **Only move events leave the venue laptop.** Vision never runs in the cloud.
3. **Synthetic and real accuracy are reported separately** and only from `tests/eval.py` output.
4. **Python 3.11+, Node 20 LTS**, as in the setup guide.
5. **Ingest auth = one shared token** from `.env`. No user accounts (out of scope).
6. **Single-instance in-memory pub/sub** for WebSockets. No Redis.
7. **SQLite** by default, via SQLAlchemy, so Postgres is a config change.
8. **Chessground or react-chessboard** for the board. Default to react-chessboard unless chessground is needed for the eval bar.
9. **Promotion** defaults to queen; the operator can override.
10. **Stockfish** is COULD-only. Not part of Phase 1 to 6.
11. **AWS facts** (Free Plan limits, eligible instance types, 6-month clock) are verified against official AWS docs in Phase 7, not assumed here.

## 3. Open questions (blocking only)

These need your answer before Phase 1:

1. **License:** MIT, Apache-2.0, or no license yet? (Brief says "ask me".)
2. **Frontend host for the SHOULD CD step:** S3 (+CloudFront only if free-plan allowed), Cloudflare Pages, or Vercel? (Can wait until Phase 7.)
3. **Camera app:** DroidCam or IP Webcam? (Both are supported; this only decides which one we test first.)

Everything else is answered in the brief.

## 4. Repository layout

```
ChessLens/
  edge/                 Python client: camera -> moves
  server/               FastAPI backend
  web/                  React + TypeScript + Vite spectator app
  infra/                Terraform (AWS), written but not applied until Phase 7
  tests/
    fixtures/           generated synthetic videos (git-ignored if large)
    real/README.md      how to record and label real clips
    eval.py             accuracy report
  docs/                 ACCURACY.md, ROADMAP.md, RUNBOOK.md, COSTS.md
  .github/workflows/    ci.yml, cd.yml
  CLAUDE.md             conventions and commands
  .env.example
  docker-compose.yml
  README.md
  PLAN.md               this file
```

## 5. Phase plan (MVP order)

| Days | Phase | Done when |
|---|---|---|
| 1 | Scaffold: repo files, CLAUDE.md, .env.example, README skeleton, pre-commit | `git init` done, first conventional commit |
| 2-4 | Synthetic generator + edge core (calibration, stability gate, tracking move detection, uncertainty flag, operator controls, offline PGN) + `tests/eval.py` | Eval runs and prints per-category accuracy |
| 5-6 | Server (FastAPI, SQLite, REST, ingest and viewer WebSockets) + web app (live board, move list, PGN download, reconnect) + `docker compose up` | Full stack runs locally; a fixture game appears live in the browser |
| 6-7 | CI: ruff, pytest, ESLint, Vitest, accuracy regression, Docker build | `ci.yml` green on a PR |
| 7 | Record real clips (you), label ground truth PGN | Clips in `tests/real/` (git-ignored) |
| 8-9 | Real-footage eval, fixes, `docs/ACCURACY.md` with synthetic and real kept apart | Numbers traceable to a script run |
| 10-11 | Terraform + CD, billing alarm, teardown runbook. **Stops for you before any `terraform apply`** | Deploy approved by you, or dropped and logged in ROADMAP |
| 12+ | README, demo, resume bullets | Resume uses only measured numbers |

**If time runs short:** drop the AWS deployment first, then the COULD items. Record cuts in `docs/ROADMAP.md`.

## 6. Test and evaluation plan

- **Synthetic generator:** render boards from known PGNs with Pillow, then apply perspective warp, lighting jitter, noise, and simulated hand occlusion. Output video fixtures with ground-truth moves.
- **`tests/eval.py`:** per-game and overall move accuracy, plus failure buckets: castling, en passant, promotion, ambiguity, occlusion. Exits non-zero below a threshold in `config`.
- **Honesty rules:** no metric appears in docs or resume unless `eval.py` produced it. Synthetic and real numbers never share a table cell.

## 7. Cost estimate

| Item | Estimate |
|---|---|
| Local development | $0 |
| GitHub Actions (public repo) | $0 |
| GHCR images | $0 (within free limits; verify current GitHub limits) |
| AWS EC2 + S3 + CloudWatch alarm | Free-plan eligibility **to be verified** in Phase 7 against official AWS docs. Target $0; budget alarm set on day one of account creation |

No infrastructure change is made without a cost estimate shown first.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Real accuracy far below synthetic | Test real footage on day 7; report both; operator controls |
| Scope exceeds 1-2 weeks | MVP priority order; drop AWS before core features |
| AWS charges or account closure | Free plan, budget alarm, teardown runbook, everything in Git |
| Desync after a misread move | Uncertainty flag, undo, set-FEN, optional CNN recovery (COULD) |
| Lighting and glare | Matte board, diffuse light, calibration contrast check |
| Over-reliance on generated code | You review every PR; code kept small and tested |

## 9. What I need from you

1. Answer the three blocking questions in section 3.
2. Approve this plan, or request changes.
3. Confirm that writing code starts with Phase 1 after approval.

Nothing else is blocking. Phases 1 to 6 need no action from you.
