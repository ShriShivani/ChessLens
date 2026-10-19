"""Command line entry point: `python -m edge calibrate|run`."""

from __future__ import annotations

import argparse
import time
from collections.abc import Iterator
from pathlib import Path

import cv2
import numpy as np

from edge.calibration import Calibration
from edge.pipeline import Event, Pipeline

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


def run(args: argparse.Namespace) -> int:
    cap, live = open_source(args.source)
    if not cap.isOpened():
        print(f"cannot open {args.source}")
        return 1
    pipe = Pipeline(
        Calibration.load(args.calibration), still_seconds=args.still, pgn_path=args.pgn_out
    )
    for frame, t in frames(cap, live):
        for event in pipe.process_frame(frame, t):
            print(describe(event), flush=True)
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
            if stop:
                break
    cap.release()
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
    rn.set_defaults(func=run)

    args = ap.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
