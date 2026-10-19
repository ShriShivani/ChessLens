"""In-memory publish/subscribe for viewer WebSockets (single server instance)."""

from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from fastapi import WebSocket

log = logging.getLogger("chesslens.hub")


class Hub:
    def __init__(self, max_per_game: int = 500) -> None:
        self.max_per_game = max_per_game
        self._viewers: dict[str, set[WebSocket]] = defaultdict(set)

    def count(self, game_id: str) -> int:
        return len(self._viewers.get(game_id, ()))

    def has_room(self, game_id: str) -> bool:
        return self.count(game_id) < self.max_per_game

    def add(self, game_id: str, ws: WebSocket) -> None:
        self._viewers[game_id].add(ws)

    def remove(self, game_id: str, ws: WebSocket) -> None:
        viewers = self._viewers.get(game_id)
        if viewers is None:
            return
        viewers.discard(ws)
        if not viewers:
            del self._viewers[game_id]

    async def publish(self, game_id: str, message: dict[str, Any]) -> None:
        """Send to every viewer; a viewer that fails is dropped, never blocking the rest."""
        for ws in list(self._viewers.get(game_id, ())):
            try:
                await ws.send_json(message)
            except Exception:  # noqa: BLE001 - a dead socket must not break the broadcast
                log.info("dropping dead viewer", extra={"game_id": game_id})
                self.remove(game_id, ws)
