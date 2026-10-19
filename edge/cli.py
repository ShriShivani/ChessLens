"""Command line entry point: `python -m edge calibrate|run`."""

from __future__ import annotations

import argparse
import logging
import os
import time
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

from edge.calibration import Calibration
from edge.pipeline import Event, Pipeline
from edge.uploader import Uploader, create_game

WINDOW = "ChessLens"
HELP = "u undo | f set FEN | m force move | 1-3 confirm | p pause | x flip | n new game | q quit"


def open_source(source: str) -> tuple[cv2.VideoCapture, bool]:
    """Open a camera index, an http/rtsp URL or a video file. Returns (capture, is_live)."""
    if source.isdigit():
        return cv2.VideoCapture(int(source)), True
    is_live = source.lower().startswith(("http://", "https://", "rtsp://"))
    return cv2.VideoCapture(source), is_live


def frames(cap: cv2.VideoCapture, live: bool) -> Iterator[tuple[np.ndarray, float]]:
    """Yield (frame, seconds). Files use their own clock so playback speed does not matter."""
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    start, n = time.monotonic(), 0
    while True:
        ok, frame = cap.read()
        if not ok:
            return
        yield frame, (time.monotonic() - start) if live else n / fps
        n += 1


def calibrate(args: argparse.Namespace) -> int:
    cap, _ = open_source(args.source)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        print(f"cannot read from {args.source}")
        return 1
    clicks: list[tuple[float, float]] = []

    def on_mouse(event: int, x: int, y: int, *_: object) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and len(clicks) < 4:
            clicks.append((float(x), float(y)))

    cv2.namedWindow(WINDOW)
    cv2.setMouseCallback(WINDOW, on_mouse)
    while True:
        view = frame.copy()
        for i, (x, y) in enumerate(clicks):
            cv2.circle(view, (int(x), int(y)), 6, (0, 0, 255), -1)
            cv2.putText(view, str(i + 1), (int(x) + 8, int(y)), 0, 0.8, (0, 0, 255), 2)
        msg = "Click the 4 board corners clockwise from top-left; Enter=save r=reset q=quit"
        cv2.putText(view, msg, (10, 25), 0, 0.6, (0, 255, 0), 2)
        cv2.imshow(WINDOW, view)
        key = cv2.waitKey(30) & 0xFF
        if key == ord("r"):
            clicks.clear()
        elif key == ord("q"):
            return 1
        elif key == 13 and len(clicks) == 4:
            Calibration(tuple(clicks), args.white_side).save(args.out)
            print(f"saved {args.out}")
            return 0


def describe(event: Event) -> str:
    if event.kind == "move":
        return f"ply {event.ply}: {event.san}  (confidence {event.confidence:.2f})"
    if event.kind == "uncertain":
        return f"UNCERTAIN, press 1-{len(event.candidates)}: " + ", ".join(event.candidates)
    return event.kind


def handle_key(pipe: Pipeline, key: int) -> tuple[list[Event], bool]:
    """Apply an operator key press. Returns (events, quit_requested)."""
    events: list[Event | None] = []
    if key == ord("q"):
        return [], True
    if key == ord("u"):
        events.append(pipe.undo())
    elif key == ord("p"):
        pipe.resume() if pipe.paused else pipe.pause()
    elif key == ord("x"):
        pipe.flip()
    elif key == ord("n"):
        events.append(pipe.new_game())
    elif key in (ord("1"), ord("2"), ord("3")):
        events.append(pipe.confirm_uncertain(key - ord("1")))
    elif key == ord("f"):
        try:
            events.append(pipe.set_fen(input("FEN: ").strip()))
        except ValueError as exc:
            print(f"bad FEN: {exc}")
    elif key == ord("m"):
        try:
            events.append(pipe.force_move(input("Move (SAN or UCI): ").strip()))
        except (ValueError, RuntimeError) as exc:
            print(f"cannot play that: {exc}")
    return [e for e in events if e is not None], False


def sync(uploader: Uploader | None, pipe: Pipeline) -> None:
    if uploader:
        uploader.publish(pipe.start_fen, [m.uci() for m in pipe.board.move_stack])


def start_uploader(args: argparse.Namespace) -> Uploader | None:
    """Create/attach to a game on the server, or return None for offline mode."""
    if not args.server:
        return None
    token = args.token or os.environ.get("INGEST_TOKEN", "")
    if not token:
        raise SystemExit("--token (or INGEST_TOKEN) is required with --server")
    game_id = args.game_id or create_game(args.server, token, args.white, args.black, args.event)
    base = args.public_url or args.server
    print(f"broadcasting game {game_id}: {base.rstrip('/')}/#/game/{game_id}", flush=True)
    uploader = Uploader(args.server, token, game_id)
    uploader.start()
    return uploader


def run(args: argparse.Namespace) -> int:
    cap, live = open_source(args.source)
    if not cap.isOpened():
        print(f"cannot open {args.source}")
        return 1
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    pipe = Pipeline(
        Calibration.load(args.calibration), still_seconds=args.still, pgn_path=args.pgn_out
    )
    pipe.white, pipe.black = args.white, args.black
    uploader = start_uploader(args)
    sync(uploader, pipe)
    for frame, t in frames(cap, live):
        events = pipe.process_frame(frame, t)
        for event in events:
            print(describe(event), flush=True)
        if events:
            sync(uploader, pipe)
        if args.headless:
            continue
        view = pipe.last_warped if pipe.last_warped is not None else frame
        view = cv2.resize(view, (640, 640))
        status = "PAUSED  " if pipe.paused else ""
        cv2.putText(view, status + HELP, (5, 630), 0, 0.45, (0, 255, 0), 1)
        cv2.imshow(WINDOW, view)
        key = cv2.waitKey(1) & 0xFF
        if key != 255:
            events, stop = handle_key(pipe, key)
            for event in events:
                print(describe(event), flush=True)
            sync(uploader, pipe)
            if stop:
                break
    cap.release()
    if uploader:
        uploader.close()
    print(pipe.pgn())
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m edge", description="ChessLens edge client")
    sub = ap.add_subparsers(dest="command", required=True)

    cal = sub.add_parser("calibrate", help="click the 4 board corners and save them")
    cal.add_argument("--source", default="0", help="camera index, http/rtsp URL or video file")
    cal.add_argument("--out", type=Path, default=Path("calibration.json"))
    cal.add_argument("--white-side", choices=["bottom", "left", "top", "right"], default="bottom")
    cal.set_defaults(func=calibrate)

    rn = sub.add_parser("run", help="track a game from a camera or video file")
    rn.add_argument("--source", default="0", help="camera index, http/rtsp URL or video file")
    rn.add_argument("--calibration", type=Path, default=Path("calibration.json"))
    rn.add_argument("--pgn-out", type=Path, default=Path("game.pgn"))
    rn.add_argument("--still", type=float, default=0.7, help="seconds the board must be still")
    rn.add_argument("--headless", action="store_true", help="no window, print events only")
    rn.add_argument("--server", help="server base URL, e.g. http://localhost:8000 (omit = offline)")
    rn.add_argument("--token", help="ingest token (default: INGEST_TOKEN env var)")
    rn.add_argument("--game-id", help="attach to an existing game instead of creating one")
    rn.add_argument("--white", default="?", help="White player name for a new game")
    rn.add_argument("--black", default="?", help="Black player name for a new game")
    rn.add_argument("--event", default="ChessLens", help="event name for a new game")
    rn.add_argument("--public-url", help="viewer URL to print (default: --server)")
    rn.set_defaults(func=run)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
