import pytest
from starlette.websockets import WebSocketDisconnect

from tests.server.conftest import TOKEN


def ingest(client, game_id):
    ws = client.websocket_connect(f"/ws/ingest/{game_id}?token={TOKEN}")
    return ws


def send_move(ws, ply, uci):
    ws.send_json({"type": "move", "ply": ply, "uci": uci})
    return ws.receive_json()


def test_ingest_requires_valid_token(client, game_id):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws/ingest/{game_id}?token=wrong"):
            pass
    assert exc.value.code == 4401
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/ingest/{game_id}"):
            pass


def test_ingest_accepts_bearer_header(client, game_id):
    headers = {"Authorization": f"Bearer {TOKEN}"}
    with client.websocket_connect(f"/ws/ingest/{game_id}", headers=headers) as ws:
        assert ws.receive_json()["type"] == "hello"


def test_unknown_game_closes_with_404_code(client):
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws/games/nope"):
            pass
    assert exc.value.code == 4404


def test_hello_reports_current_state_for_resync(client, game_id):
    with ingest(client, game_id) as ws:
        assert ws.receive_json()["ply"] == 0
        send_move(ws, 1, "e2e4")
    with ingest(client, game_id) as ws:
        hello = ws.receive_json()
        assert hello["ply"] == 1 and " b " in hello["fen"]


def test_viewer_gets_snapshot_then_live_moves(client, game_id):
    with client.websocket_connect(f"/ws/games/{game_id}") as viewer:
        snap = viewer.receive_json()
        assert snap["type"] == "snapshot" and snap["game"]["moves"] == []
        with ingest(client, game_id) as edge:
            edge.receive_json()
            assert send_move(edge, 1, "e2e4") == {"type": "ack", "ply": 1}
            event = viewer.receive_json()
            assert event["type"] == "move" and event["san"] == "e4" and event["ply"] == 1
            send_move(edge, 2, "c7c5")
            assert viewer.receive_json()["san"] == "c5"


def test_late_viewer_sees_existing_moves(client, game_id):
    with ingest(client, game_id) as edge:
        edge.receive_json()
        send_move(edge, 1, "d2d4")
        send_move(edge, 2, "d7d5")
    with client.websocket_connect(f"/ws/games/{game_id}") as viewer:
        moves = viewer.receive_json()["game"]["moves"]
        assert [m["san"] for m in moves] == ["d4", "d5"]


def test_duplicate_move_is_acked_but_not_rebroadcast(client, game_id):
    with (
        client.websocket_connect(f"/ws/games/{game_id}") as viewer,
        ingest(client, game_id) as edge,
    ):
        viewer.receive_json()
        edge.receive_json()
        send_move(edge, 1, "e2e4")
        assert viewer.receive_json()["type"] == "move"
        assert send_move(edge, 1, "e2e4") == {"type": "ack", "ply": 1}  # retry after reconnect
        send_move(edge, 2, "e7e5")
        assert viewer.receive_json()["ply"] == 2  # next event is ply 2, no repeat of ply 1


@pytest.mark.parametrize(
    "ply,uci,fragment",
    [(1, "e2e5", "illegal"), (3, "e2e4", "expected ply 1"), (1, "zzzz", "String should match")],
)
def test_bad_moves_are_rejected_without_closing(client, game_id, ply, uci, fragment):
    with ingest(client, game_id) as edge:
        edge.receive_json()
        reply = send_move(edge, ply, uci)
        assert reply["type"] == "error" and fragment in reply["detail"]
        assert send_move(edge, 1, "e2e4") == {"type": "ack", "ply": 1}  # still usable


def test_conflicting_move_for_existing_ply_is_rejected(client, game_id):
    with ingest(client, game_id) as edge:
        edge.receive_json()
        send_move(edge, 1, "e2e4")
        reply = send_move(edge, 1, "d2d4")
        assert reply["type"] == "error" and "already holds" in reply["detail"]


def test_garbage_messages_do_not_kill_the_connection(client, game_id):
    with ingest(client, game_id) as edge:
        edge.receive_json()
        edge.send_text("{not json")
        assert edge.receive_json()["type"] == "error"
        edge.send_json({"type": "launch_missiles"})
        assert edge.receive_json()["type"] == "error"
        assert send_move(edge, 1, "e2e4")["type"] == "ack"


def test_undo_reset_set_fen_and_result_broadcast_snapshots(client, game_id):
    fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    with (
        client.websocket_connect(f"/ws/games/{game_id}") as viewer,
        ingest(client, game_id) as edge,
    ):
        viewer.receive_json()
        edge.receive_json()
        send_move(edge, 1, "e2e4")
        viewer.receive_json()

        edge.send_json({"type": "undo"})
        edge.receive_json()
        assert viewer.receive_json()["game"]["ply"] == 0

        edge.send_json({"type": "set_fen", "fen": fen})
        edge.receive_json()
        assert viewer.receive_json()["game"]["start_fen"] == fen

        send_move(edge, 1, "e2e4")
        viewer.receive_json()
        edge.send_json({"type": "result", "result": "1/2-1/2"})
        edge.receive_json()
        assert viewer.receive_json()["game"]["result"] == "1/2-1/2"

        edge.send_json({"type": "reset"})
        edge.receive_json()
        snap = viewer.receive_json()["game"]
        assert snap["ply"] == 0 and snap["start_fen"] is None and snap["result"] == "*"


def test_checkmate_sets_result_automatically(client, game_id):
    with ingest(client, game_id) as edge:
        edge.receive_json()
        for ply, uci in enumerate(["f2f3", "e7e5", "g2g4", "d8h4"], start=1):
            send_move(edge, ply, uci)
    assert client.get(f"/api/games/{game_id}").json()["result"] == "0-1"


def test_viewer_cap(game_id):
    from fastapi.testclient import TestClient

    from server.config import Settings
    from server.main import create_app

    settings = Settings(
        database_url="sqlite://", ingest_token=TOKEN, max_viewers_per_game=1, rate_limit_per_min=0
    )
    with TestClient(create_app(settings)) as c:
        gid = c.post("/api/games", json={}, headers={"X-Ingest-Token": TOKEN}).json()["id"]
        with c.websocket_connect(f"/ws/games/{gid}") as first:
            first.receive_json()
            with pytest.raises(WebSocketDisconnect) as exc:
                with c.websocket_connect(f"/ws/games/{gid}"):
                    pass
            assert exc.value.code == 4429
