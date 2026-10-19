import json
import socket
import threading
import time
import urllib.request

import pytest
import uvicorn

from edge.uploader import GameState, Uploader, apply_to, plan_sync, ws_base
from server.config import Settings
from server.main import create_app

TOKEN = "e2e-token"


def gs(moves, start=None):
    return GameState(start, tuple(moves))


class TestPlanSync:
    def test_nothing_to_do_when_equal(self):
        assert plan_sync(gs(["e2e4"]), gs(["e2e4"])) == []

    def test_sends_missing_moves_with_plies(self):
        plan = plan_sync(gs(["e2e4"]), gs(["e2e4", "e7e5", "g1f3"]))
        assert plan == [
            {"type": "move", "ply": 2, "uci": "e7e5"},
            {"type": "move", "ply": 3, "uci": "g1f3"},
        ]

    def test_undoes_then_replays_on_divergence(self):
        plan = plan_sync(gs(["e2e4", "e7e5", "g1f3"]), gs(["e2e4", "c7c5"]))
        assert [m["type"] for m in plan] == ["undo", "undo", "move"]
        assert plan[-1] == {"type": "move", "ply": 2, "uci": "c7c5"}

    def test_server_ahead_is_undone(self):
        assert plan_sync(gs(["e2e4", "e7e5"]), gs(["e2e4"])) == [{"type": "undo"}]

    def test_start_position_change_resets_then_replays(self):
        fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
        assert plan_sync(gs(["e2e4"]), gs([], fen)) == [{"type": "set_fen", "fen": fen}]
        plan = plan_sync(gs([], fen), gs(["e2e4"]))
        assert plan == [{"type": "reset"}, {"type": "move", "ply": 1, "uci": "e2e4"}]

    def test_applying_the_plan_reaches_the_local_state(self):
        remote, local = gs(["e2e4", "e7e5", "g1f3"]), gs(["e2e4", "c7c5", "g1f3", "d7d6"])
        for msg in plan_sync(remote, local):
            remote = apply_to(remote, msg)
        assert remote == local


def test_ws_base():
    assert ws_base("http://h:1/") == "ws://h:1"
    assert ws_base("https://h") == "wss://h"


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class LiveServer:
    """Real uvicorn server in a thread so websockets and HTTP behave as in production."""

    def __init__(self, port: int, db_url: str) -> None:
        settings = Settings(
            database_url=db_url, ingest_token=TOKEN, rate_limit_per_min=0, log_level="ERROR"
        )
        config = uvicorn.Config(
            create_app(settings), host="127.0.0.1", port=port, log_level="error"
        )
        self.server = uvicorn.Server(config)
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self):
        self.thread.start()
        deadline = time.time() + 10
        while not self.server.started and time.time() < deadline:
            time.sleep(0.05)
        assert self.server.started
        return self

    def stop(self):
        self.server.should_exit = True
        self.thread.join(timeout=10)


def get(port: int, path: str):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.load(r)


def post_game(port: int) -> str:
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/games",
        data=b"{}",
        headers={"X-Ingest-Token": TOKEN, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)["id"]


def wait_for(predicate, timeout=10.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


@pytest.fixture
def live(tmp_path):
    port = free_port()
    db = f"sqlite:///{(tmp_path / 'e2e.db').as_posix()}"
    server = LiveServer(port, db).start()
    yield port, db, server
    server.stop()


def test_moves_reach_server_and_follow_undo_and_new_game(live):
    port, _, _ = live
    game_id = post_game(port)
    up = Uploader(f"http://127.0.0.1:{port}", TOKEN, game_id, retry_seconds=(0.1, 0.5))
    up.start()
    try:
        up.publish(None, ["e2e4", "e7e5"])
        assert up.wait_synced(10)
        assert [m["uci"] for m in get(port, f"/api/games/{game_id}")["moves"]] == ["e2e4", "e7e5"]
        up.publish(None, ["e2e4", "c7c5", "g1f3"])  # operator undid e5 and played c5
        assert up.wait_synced(10)
        assert [m["san"] for m in get(port, f"/api/games/{game_id}")["moves"]] == [
            "e4",
            "c5",
            "Nf3",
        ]
        up.publish(None, [])
        assert up.wait_synced(10)
        assert get(port, f"/api/games/{game_id}")["ply"] == 0
    finally:
        up.close()


def test_moves_made_while_server_is_down_arrive_after_it_returns(tmp_path):
    port = free_port()
    db = f"sqlite:///{(tmp_path / 'outage.db').as_posix()}"
    first = LiveServer(port, db).start()
    game_id = post_game(port)
    first.stop()

    up = Uploader(f"http://127.0.0.1:{port}", TOKEN, game_id, retry_seconds=(0.1, 0.3))
    up.start()
    try:
        up.publish(None, ["d2d4", "d7d5", "c2c4"])  # played during the outage
        assert not up.wait_synced(1.0)
        second = LiveServer(port, db).start()  # same database, same port
        try:
            assert up.wait_synced(15)
            moves = get(port, f"/api/games/{game_id}")["moves"]
            assert [m["uci"] for m in moves] == ["d2d4", "d7d5", "c2c4"]
        finally:
            second.stop()
    finally:
        up.close(flush_seconds=0.1)


def test_set_fen_position_is_mirrored(live):
    port, _, _ = live
    game_id = post_game(port)
    fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    up = Uploader(f"http://127.0.0.1:{port}", TOKEN, game_id, retry_seconds=(0.1, 0.5))
    up.start()
    try:
        up.publish(fen, ["e2e4"])
        assert up.wait_synced(10)
        game = get(port, f"/api/games/{game_id}")
        assert game["start_fen"] == fen and game["ply"] == 1
    finally:
        up.close()
