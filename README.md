# ChessLens

Real-time digitization and live broadcast of physical chess games using computer vision. No sensor board required: a phone camera is enough.

> Status: edge vision core, synthetic generator and evaluation are implemented. Server and web app are not yet.

## How it works
The edge client keeps a `python-chess` board and works out which legal move caused the change between two stable camera frames. Only move events are sent to the server, which broadcasts them to a web spectator page.

## Repository layout
See [CLAUDE.md](CLAUDE.md) and [PLAN.md](PLAN.md).

## Setup
```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\python -m pytest -q
.\.venv\Scripts\python -m tests.eval
python -m edge calibrate --source 0     # click the 4 board corners
python -m edge run --source 0           # source: camera index, http/rtsp URL, or video file
```

## Accuracy
Synthetic only (no real footage yet), from `python -m tests.eval` on 2026-10-17: 236 of 237 moves correct (99.6%) over 9 games with simulated hands, 0 silently wrong, 1 flagged uncertain. Synthetic data is easier than a real board; real numbers will be reported separately.

## Limitations
_To be written._

## License
MIT. See [LICENSE](LICENSE).
