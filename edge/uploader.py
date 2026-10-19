"""Background uploader: keeps the server's copy of the game equal to the edge's.

Instead of replaying a queue of events (undo is not idempotent), the uploader reconciles
state. On every (re)connect the server's `hello` lists its start position and moves; the
uploader diffs that against the local game and sends only what is missing. Moves played
while offline are therefore never lost, and a lost acknowledgement cannot cause a double undo.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.request
from dataclasses import dataclass

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect

log = logging.getLogger("chesslens.edge.uploader")


@dataclass(frozen=True)
class GameState:
    start_fen: str | None
    moves: tuple[str, ...]  # UCI


def plan_sync(remote: GameState, local: GameState) -> list[dict]:
    """Messages that turn the server's game (`remote`) into the local one."""
    if remote.start_fen != local.start_fen:
        head: list[dict] = (
            [{"type": "set_fen", "fen": local.start_fen}]
            if local.start_fen
            else [{"type": "reset"}]
        )
        return head + [
            {"type": "move", "ply": i, "uci": uci} for i, uci in enumerate(local.moves, 1)
        ]
    common = 0
    for a, b in zip(remote.moves, local.moves, strict=False):
        if a != b:
            break
        common += 1
    plan: list[dict] = [{"type": "undo"}] * (len(remote.moves) - common)
    plan += [
        {"type": "move", "ply": i, "uci": local.moves[i - 1]}
        for i in range(common + 1, len(local.moves) + 1)
    ]
    return plan


def apply_to(state: GameState, msg: dict) -> GameState:
    """Predict the server state after it accepts `msg`."""
    kind = msg["type"]
    if kind == "move":
        return GameState(state.start_fen, (*state.moves, msg["uci"]))
    if kind == "undo":
        return GameState(state.start_fen, state.moves[:-1])
    if kind == "set_fen":
        return GameState(msg["fen"], ())
    if kind == "reset":
        return GameState(None, ())
    return state


def create_game(server: str, token: str, white: str, black: str, event: str) -> str:
    """POST /api/games and return the new game id."""
    body = json.dumps({"white": white, "black": black, "event": event}).encode()
    req = urllib.request.Request(
        f"{server.rstrip('/')}/api/games",
        data=body,
        headers={"Content-Type": "application/json", "X-Ingest-Token": token},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        return str(json.load(resp)["id"])


def ws_base(server: str) -> str:
    return server.rstrip("/").replace("https://", "wss://").replace("http://", "ws://")


class Uploader:
    def __init__(
        self,
        server: str,
        token: str,
        game_id: str,
        retry_seconds: tuple[float, float] = (1.0, 10.0),
    ) -> None:
        self.url = f"{ws_base(server)}/ws/ingest/{game_id}"
        self._headers = {"Authorization": f"Bearer {token}"}
        self._retry_min, self._retry_max = retry_seconds
        self._local = GameState(None, ())
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._synced = threading.Event()
        self._thread = threading.Thread(target=self._run, name="uploader", daemon=True)

    def start(self) -> None:
        self._thread.start()

    def close(self, flush_seconds: float = 3.0) -> None:
        """Give pending moves a moment to go out, then stop."""
        self.wait_synced(flush_seconds)
        self._stop.set()
        self._wake.set()
        self._thread.join(timeout=5)

    def publish(self, start_fen: str | None, moves: list[str]) -> None:
        """Record the current local game; the thread syncs it whenever a connection exists."""
        with self._lock:
            self._local = GameState(start_fen, tuple(moves))
            self._synced.clear()
        self._wake.set()

    def wait_synced(self, timeout: float) -> bool:
        return self._synced.wait(timeout)

    def _snapshot(self) -> GameState:
        with self._lock:
            return self._local

    def _run(self) -> None:
        delay = self._retry_min
        while not self._stop.is_set():
            try:
                with connect(self.url, additional_headers=self._headers, open_timeout=10) as ws:
                    hello = json.loads(ws.recv(timeout=10))
                    remote = GameState(hello.get("start_fen"), tuple(hello.get("moves", ())))
                    log.info("connected to %s (server has %d moves)", self.url, len(remote.moves))
                    delay = self._retry_min
                    self._pump(ws, remote)
            except (OSError, WebSocketException, TimeoutError, ValueError) as exc:
                log.warning("server unreachable (%s); retrying in %.0fs", exc, delay)
            if self._stop.wait(delay):
                return
            delay = min(delay * 2, self._retry_max)

    def _pump(self, ws, remote: GameState) -> None:  # noqa: ANN001 - websockets ClientConnection
        while not self._stop.is_set():
            local = self._snapshot()
            plan = plan_sync(remote, local)
            if not plan:
                if local == self._snapshot():
                    self._synced.set()
                self._wake.wait(timeout=5)
                self._wake.clear()
                continue
            for msg in plan:
                ws.send(json.dumps(msg))
                reply = json.loads(ws.recv(timeout=10))
                if reply.get("type") != "ack":
                    log.warning("server rejected %s: %s", msg, reply.get("detail"))
                    return  # reconnect for a fresh hello and re-diff
                remote = apply_to(remote, msg)
