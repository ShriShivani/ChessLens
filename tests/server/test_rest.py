import io

import chess.pgn
from fastapi.testclient import TestClient

from server.config import Settings
from server.main import create_app
from tests.server.conftest import AUTH, TOKEN


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_create_requires_token(client):
    assert client.post("/api/games", json={}).status_code == 401
    assert client.post("/api/games", json={}, headers={"X-Ingest-Token": "nope"}).status_code == 401


def test_create_list_and_detail(client):
    created = client.post(
        "/api/games", json={"white": "Ann", "black": "Bo", "event": "Club night"}, headers=AUTH
    )
    assert created.status_code == 201
    body = created.json()
    assert body["ply"] == 0 and body["result"] == "*" and body["moves"] == []
    listing = client.get("/api/games").json()
    assert [g["id"] for g in listing] == [body["id"]]
    detail = client.get(f"/api/games/{body['id']}").json()
    assert detail["white"] == "Ann" and detail["event"] == "Club night"


def test_unknown_game_is_404(client):
    assert client.get("/api/games/missing").status_code == 404
    assert client.get("/api/games/missing/pgn").status_code == 404


def test_validation_rejects_bad_fen(client):
    r = client.post("/api/games", json={"start_fen": "not a fen"}, headers=AUTH)
    assert r.status_code == 422


def test_pgn_download(client, game_id):
    with client.websocket_connect(f"/ws/ingest/{game_id}?token={TOKEN}") as ws:
        ws.receive_json()
        for ply, uci in enumerate(["e2e4", "e7e5", "g1f3"], start=1):
            ws.send_json({"type": "move", "ply": ply, "uci": uci})
            assert ws.receive_json() == {"type": "ack", "ply": ply}
    r = client.get(f"/api/games/{game_id}/pgn")
    assert r.status_code == 200
    assert "attachment" in r.headers["content-disposition"]
    game = chess.pgn.read_game(io.StringIO(r.text))
    assert [m.uci() for m in game.mainline_moves()] == ["e2e4", "e7e5", "g1f3"]
    assert game.headers["White"] == "Ann"


def test_rate_limit():
    settings = Settings(database_url="sqlite://", ingest_token=TOKEN, rate_limit_per_min=3)
    with TestClient(create_app(settings)) as c:
        codes = [c.get("/api/games").status_code for _ in range(5)]
        assert codes == [200, 200, 200, 429, 429]
        assert c.get("/health").status_code == 200  # only /api is limited
