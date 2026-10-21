"""Frame-by-frame pipeline: warp -> stability gate -> move detection -> game state."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import chess
import chess.pgn
import numpy as np

from edge.calibration import Calibration
from edge.detector import Candidate, DetectorConfig, detect_move
from edge.stability import StabilityGate
from edge.verify import (
    Classifier,
    decode_position,
    make_prior,
    occupancy_mismatches,
)


@dataclass(frozen=True)
class Event:
    """Something the operator or server cares about."""

    kind: str  # "move" | "uncertain" | "undo" | "reset" | "set_fen"
    ply: int = 0
    san: str = ""
    uci: str = ""
    fen: str = ""
    confidence: float = 0.0
    candidates: tuple[str, ...] = ()  # SAN of top candidates when uncertain


class Pipeline:
    def __init__(
        self,
        calibration: Calibration,
        cfg: DetectorConfig | None = None,
        still_seconds: float = 0.7,
        pgn_path: str | Path | None = None,
        classifier: Classifier | None = None,
        classifier_weight: float = 0.5,
        desync_squares: int = 3,
    ) -> None:
        self.calibration = calibration
        self.cfg = cfg or DetectorConfig()
        self.gate = StabilityGate(still_seconds)
        self.pgn_path = Path(pgn_path) if pgn_path else None
        self.classifier = classifier
        self.classifier_weight = classifier_weight
        self.desync_squares = desync_squares
        self.proposed_fen: str | None = None
        self._last_desync: tuple[str, ...] = ()
        self.paused = False
        self.white = "?"
        self.black = "?"
        self.board = chess.Board()
        self.start_fen: str | None = None
        self.last_warped: np.ndarray | None = None
        self.last_stable: np.ndarray | None = None  # last frame the stability gate released
        self._reference: np.ndarray | None = None
        self._ref_history: list[np.ndarray] = []
        self._pending: tuple[Candidate, ...] = ()
        self._last_uncertain: tuple[str, ...] = ()

    # ---- frame processing -------------------------------------------------
    def process_frame(self, frame: np.ndarray, t: float) -> list[Event]:
        warped = self.calibration.warp(frame)
        self.last_warped = warped
        if self.paused:
            self.gate.reset()
            return []
        if not self.gate.update(warped, t):
            return []
        self.last_stable = warped
        if self._reference is None:
            self._reference = warped
            return []
        probs = self.classifier.predict(warped) if self.classifier else None
        prior = None
        if probs is not None:
            moves = list(self.board.legal_moves)
            prior = make_prior(self.board, moves, probs, self.classifier_weight)
        result = detect_move(self.board, self._reference, warped, self.cfg, prior)
        if result.status == "move" and result.move is not None:
            events = [self._push(result.move, warped, result.confidence)]
            return events + self._verify(probs)
        if result.status == "uncertain":
            self._pending = result.candidates
            sans = tuple(self.board.san(c.move) for c in result.candidates)
            if sans != self._last_uncertain:
                self._last_uncertain = sans
                return [
                    Event(
                        "uncertain",
                        len(self.board.move_stack),
                        confidence=result.confidence,
                        candidates=sans,
                    )
                ]
        return self._verify(probs) if result.status == "nochange" else []

    def _verify(self, probs: np.ndarray | None) -> list[Event]:
        """Flag a possible desync when the classifier disagrees with the tracked board."""
        if probs is None:
            return []
        bad = occupancy_mismatches(self.board, probs)
        if len(bad) < self.desync_squares:
            self._last_desync = ()
            return []
        names = tuple(chess.square_name(sq) for sq in bad)
        if names == self._last_desync:
            return []
        self._last_desync = names
        proposed, errors = decode_position(probs, self.board.turn)
        self.proposed_fen = None if errors else proposed.fen()
        return [
            Event(
                "desync",
                len(self.board.move_stack),
                fen=self.proposed_fen or "",
                candidates=names,
            )
        ]

    def accept_proposal(self) -> Event | None:
        """Adopt the classifier-proposed position after the operator has checked it."""
        if not self.proposed_fen:
            return None
        fen, self.proposed_fen = self.proposed_fen, None
        return self.set_fen(fen)

    def _push(self, move: chess.Move, warped: np.ndarray, confidence: float = 1.0) -> Event:
        san = self.board.san(move)
        self._ref_history.append(self._reference if self._reference is not None else warped)
        self.board.push(move)
        self._reference = warped
        self._pending = ()
        self._last_uncertain = ()
        self._write_pgn()
        return Event(
            "move", len(self.board.move_stack), san, move.uci(), self.board.fen(), confidence
        )

    # ---- operator controls ------------------------------------------------
    def _baseline(self) -> np.ndarray | None:
        """Best known clean picture of the board (avoids frames with a hand in them)."""
        return self.last_stable if self.last_stable is not None else self.last_warped

    def confirm_uncertain(self, index: int = 0) -> Event | None:
        """Accept one of the candidates offered by the last 'uncertain' event."""
        frame = self._baseline()
        if not self._pending or frame is None or index >= len(self._pending):
            return None
        return self._push(self._pending[index].move, frame)

    def force_move(self, text: str) -> Event:
        """Play a move given as SAN or UCI, regardless of what the camera saw."""
        try:
            move = self.board.parse_san(text)
        except ValueError:
            move = self.board.parse_uci(text)
        if move not in self.board.legal_moves:
            raise ValueError(f"illegal move: {text}")
        frame = self._baseline()
        if frame is None:
            raise RuntimeError("no frame seen yet")
        return self._push(move, frame)

    def undo(self) -> Event | None:
        if not self.board.move_stack:
            return None
        self.board.pop()
        if self._ref_history:
            self._reference = self._ref_history.pop()
        self._pending = ()
        self._last_uncertain = ()
        self.gate.reset()
        self._write_pgn()
        return Event("undo", len(self.board.move_stack), fen=self.board.fen())

    def set_fen(self, fen: str) -> Event:
        board = chess.Board(fen)
        self.board = board
        self.start_fen = None if fen == chess.STARTING_FEN else board.fen()
        self._ref_history.clear()
        self._reference = self._baseline()
        self._pending = ()
        self._last_uncertain = ()
        self.gate.reset()
        self._write_pgn()
        return Event("set_fen", 0, fen=board.fen())

    def new_game(self) -> Event:
        self.board = chess.Board()
        self.start_fen = None
        self._ref_history.clear()
        self._reference = self._baseline()
        self._pending = ()
        self._last_uncertain = ()
        self.gate.reset()
        self._write_pgn()
        return Event("reset", 0, fen=self.board.fen())

    def pause(self) -> None:
        self.paused = True

    def resume(self) -> None:
        self.paused = False
        self.gate.reset()
        # The board may have been rearranged while paused; re-baseline on the next stable frame.
        self._reference = None

    def flip(self) -> None:
        self.calibration = self.calibration.flipped()
        self.gate.reset()
        self._reference = None
        self._ref_history.clear()

    # ---- output -------------------------------------------------------------
    def pgn(
        self, white: str | None = None, black: str | None = None, result: str | None = None
    ) -> str:
        game = chess.pgn.Game.from_board(self.board)
        game.headers["Event"] = "ChessLens"
        game.headers["Date"] = date.today().strftime("%Y.%m.%d")
        game.headers["White"] = white or self.white
        game.headers["Black"] = black or self.black
        game.headers["Result"] = result or self.board.result(claim_draw=False)
        return str(game)

    def _write_pgn(self) -> None:
        if self.pgn_path:
            self.pgn_path.write_text(self.pgn() + "\n", encoding="utf-8")
