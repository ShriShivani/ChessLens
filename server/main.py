"""FastAPI app: REST for games, WebSockets for edge ingest and live viewers."""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from collections.abc import Iterator

from fastapi import Depends, FastAPI, Header, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from server import service
from server.config import DEFAULT_TOKEN, Settings
from server.db import Game, make_engine, make_sessionmaker
from server.hub import Hub
from server.logging_config import configure_logging
from server.ratelimit import RateLimitMiddleware
from server.schemas import (
    GameCreate,
    GameDetail,
    GameOut,
    IngestMessage,
    MoveMsg,
    ResetMsg,
    ResultMsg,
    SetFenMsg,
    UndoMsg,
)

log = logging.getLogger("chesslens.api")
_ingest_adapter: TypeAdapter = TypeAdapter(IngestMessage)

WS_UNAUTHORIZED = 4401
WS_NOT_FOUND = 4404
WS_FULL = 4429


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level)
    if settings.ingest_token == DEFAULT_TOKEN:
        log.warning("INGEST_TOKEN is the default value; set a real secret before deploying")

    app = FastAPI(title="ChessLens API", version="0.1.0")
    app.state.settings = settings
    app.state.engine = make_engine(settings.database_url)
    app.state.sessions = make_sessionmaker(app.state.engine)
    app.state.hub = Hub(settings.max_viewers_per_game)

    app.add_middleware(RateLimitMiddleware, limit_per_min=settings.rate_limit_per_min)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    def get_db() -> Iterator[Session]:
        with app.state.sessions() as db:
            yield db

    def require_token(x_ingest_token: str | None = Header(None)) -> None:
        if not x_ingest_token or not secrets.compare_digest(x_ingest_token, settings.ingest_token):
            raise HTTPException(status_code=401, detail="invalid ingest token")

    def find_game(db: Session, game_id: str) -> Game:
        game = db.get(Game, game_id)
        if game is None:
            raise HTTPException(status_code=404, detail="game not found")
        return game

    # ---- REST ---------------------------------------------------------------
    @app.get("/health")
    def health(db: Session = Depends(get_db)) -> dict[str, str]:
        db.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.post("/api/games", response_model=GameDetail, status_code=201)
    def create_game(
        body: GameCreate, db: Session = Depends(get_db), _: None = Depends(require_token)
    ) -> GameDetail:
        game = Game(
            id=uuid.uuid4().hex[:10],
            event=body.event,
            white=body.white,
            black=body.black,
            start_fen=body.start_fen,
        )
        db.add(game)
        db.commit()
        log.info("game created", extra={"game_id": game.id})
        return service.game_detail(game)

    @app.get("/api/games", response_model=list[GameOut])
    def list_games(
        limit: int = Query(50, ge=1, le=200), db: Session = Depends(get_db)
    ) -> list[GameOut]:
        rows = db.scalars(select(Game).order_by(Game.created_at.desc()).limit(limit))
        return [service.game_out(g) for g in rows]

    @app.get("/api/games/{game_id}", response_model=GameDetail)
    def get_game(game_id: str, db: Session = Depends(get_db)) -> GameDetail:
        return service.game_detail(find_game(db, game_id))

    @app.get("/api/games/{game_id}/pgn", response_class=PlainTextResponse)
    def get_pgn(game_id: str, db: Session = Depends(get_db)) -> PlainTextResponse:
        game = find_game(db, game_id)
        return PlainTextResponse(
            service.to_pgn(game),
            media_type="application/x-chess-pgn",
            headers={"Content-Disposition": f'attachment; filename="chesslens-{game.id}.pgn"'},
        )

    # ---- WebSockets -----------------------------------------------------------
    async def handle_ingest(ws: WebSocket, game_id: str, raw: object) -> None:
        try:
            msg = _ingest_adapter.validate_python(raw)
        except ValidationError as exc:
            await ws.send_json({"type": "error", "detail": exc.errors(include_url=False)[0]["msg"]})
            return
        hub: Hub = app.state.hub
        with app.state.sessions() as db:
            game = db.get(Game, game_id)
            if game is None:
                await ws.send_json({"type": "error", "detail": "game not found"})
                return
            if isinstance(msg, MoveMsg):
                try:
                    row = service.apply_move(db, game, msg.ply, msg.uci)
                except service.MoveRejected as exc:
                    await ws.send_json({"type": "error", "ply": msg.ply, "detail": str(exc)})
                    return
                await ws.send_json({"type": "ack", "ply": msg.ply})
                if row is not None:
                    log.info("move accepted", extra={"game_id": game_id, "ply": row.ply})
                    await hub.publish(
                        game_id,
                        {
                            "type": "move",
                            "ply": row.ply,
                            "san": row.san,
                            "uci": row.uci,
                            "fen": row.fen,
                            "result": game.result,
                        },
                    )
                return
            if isinstance(msg, UndoMsg):
                service.undo_last(db, game)
            elif isinstance(msg, ResetMsg):
                service.reset_game(db, game)
            elif isinstance(msg, SetFenMsg):
                service.reset_game(db, game, msg.fen)
            elif isinstance(msg, ResultMsg):
                service.set_result(db, game, msg.result)
            await ws.send_json({"type": "ack", "ply": len(game.moves)})
            await hub.publish(
                game_id,
                {"type": "snapshot", "game": service.game_detail(game).model_dump(mode="json")},
            )

    @app.websocket("/ws/ingest/{game_id}")
    async def ws_ingest(ws: WebSocket, game_id: str, token: str | None = Query(None)) -> None:
        supplied = token
        auth = ws.headers.get("authorization", "")
        if auth.lower().startswith("bearer "):
            supplied = auth[7:]
        if not supplied or not secrets.compare_digest(supplied, settings.ingest_token):
            await ws.close(code=WS_UNAUTHORIZED)
            return
        with app.state.sessions() as db:
            game = db.get(Game, game_id)
            if game is None:
                await ws.close(code=WS_NOT_FOUND)
                return
            hello = {
                "type": "hello",
                "ply": len(game.moves),
                "fen": service.board_for(game).fen(),
                "start_fen": game.start_fen,
                "moves": [m.uci for m in game.moves],
            }
        await ws.accept()
        await ws.send_json(hello)
        log.info("edge connected", extra={"game_id": game_id})
        try:
            while True:
                try:
                    raw = json.loads(await ws.receive_text())
                except json.JSONDecodeError:
                    await ws.send_json({"type": "error", "detail": "message is not valid JSON"})
                    continue
                await handle_ingest(ws, game_id, raw)
        except WebSocketDisconnect:
            log.info("edge disconnected", extra={"game_id": game_id})

    @app.websocket("/ws/games/{game_id}")
    async def ws_viewer(ws: WebSocket, game_id: str) -> None:
        hub: Hub = app.state.hub
        with app.state.sessions() as db:
            game = db.get(Game, game_id)
            if game is None:
                await ws.close(code=WS_NOT_FOUND)
                return
            if not hub.has_room(game_id):
                await ws.close(code=WS_FULL)
                return
            snapshot = {
                "type": "snapshot",
                "game": service.game_detail(game).model_dump(mode="json"),
            }
        await ws.accept()
        hub.add(game_id, ws)
        try:
            await ws.send_json(snapshot)
            while True:
                await ws.receive_text()  # viewers send nothing; this detects disconnects
        except WebSocketDisconnect:
            pass
        finally:
            hub.remove(game_id, ws)

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn server.main:app_factory --factory`."""
    return create_app()
