# ChessLens

Real-time digitization and live broadcast of physical chess games using computer vision. No sensor board required: a phone camera is enough.

> Status: scaffold only. Nothing is implemented yet.

## How it works
The edge client keeps a `python-chess` board and works out which legal move caused the change between two stable camera frames. Only move events are sent to the server, which broadcasts them to a web spectator page.

## Repository layout
See [CLAUDE.md](CLAUDE.md) and [PLAN.md](PLAN.md).

## Setup
_To be written as components land._

## Accuracy
_No numbers yet. Results will be published only from `tests/eval.py`, synthetic and real reported separately._

## Limitations
_To be written._

## License
MIT. See [LICENSE](LICENSE).
