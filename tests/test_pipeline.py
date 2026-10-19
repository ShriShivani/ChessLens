import chess
import pytest

from edge.pipeline import Pipeline
from tests.synth import SynthConfig, categorize, load_pgn_moves, play, random_game

MOVES = [chess.Move.from_uci(u) for u in ("e2e4", "e7e5", "g1f3", "b8c6")]


def run(pipe, game):
    events = []
    for frame, t, _ in game.frames:
        events += pipe.process_frame(frame, t)
    return events


@pytest.fixture(scope="module")
def played(tmp_path_factory):
    game = play(MOVES, SynthConfig(seed=5))
    pgn_file = tmp_path_factory.mktemp("pgn") / "game.pgn"
    pipe = Pipeline(game.calibration, pgn_path=pgn_file)
    events = run(pipe, game)
    return pipe, events, pgn_file


def test_tracks_a_short_game(played):
    pipe, events, _ = played
    assert [e.san for e in events if e.kind == "move"] == ["e4", "e5", "Nf3", "Nc6"]
    assert pipe.board.move_stack == MOVES


def test_pgn_is_written_offline(played):
    _, _, pgn_file = played
    text = pgn_file.read_text(encoding="utf-8")
    assert "1. e4 e5 2. Nf3 Nc6" in text
    assert '[Event "ChessLens"]' in text


def test_undo_set_fen_force_and_new_game():
    game = play(MOVES[:2], SynthConfig(seed=6))
    pipe = Pipeline(game.calibration)
    run(pipe, game)
    assert len(pipe.board.move_stack) == 2
    assert pipe.undo().kind == "undo"
    assert pipe.board.move_stack == MOVES[:1]
    assert pipe.force_move("e5").san == "e5"
    with pytest.raises(ValueError):
        pipe.force_move("e5")  # no longer legal for the side to move
    fen = "4k3/8/8/8/8/8/4P3/4K3 w - - 0 1"
    assert pipe.set_fen(fen).fen == chess.Board(fen).fen()
    assert "[FEN " in pipe.pgn()
    assert pipe.new_game().kind == "reset"
    assert pipe.board.fen() == chess.STARTING_FEN
    assert pipe.undo() is None


def test_pause_ignores_frames():
    game = play(MOVES[:1], SynthConfig(seed=7))
    pipe = Pipeline(game.calibration)
    pipe.pause()
    assert run(pipe, game) == []
    assert pipe.board.move_stack == []
    pipe.resume()
    assert not pipe.paused


def test_flip_changes_orientation():
    game = play(MOVES[:1], SynthConfig(seed=8))
    pipe = Pipeline(game.calibration)
    pipe.flip()
    assert pipe.calibration.white_side == "top"


def test_unexplained_change_is_flagged_and_can_be_confirmed():
    game = play([chess.Move.from_uci("e2e4")], SynthConfig(seed=9))
    pipe = Pipeline(game.calibration)
    # Camera sees e2e4, but the pipeline believes e2 is empty, so no legal move fits well.
    pipe.set_fen("rnbqkbnr/pppppppp/8/8/8/8/PPPP1PPP/RNBQKBNR w KQkq - 0 1")
    events = run(pipe, game)
    assert not [e for e in events if e.kind == "move"]
    assert [e for e in events if e.kind == "uncertain"]


def test_synthetic_helpers():
    moves = random_game(1, 20)
    assert 0 < len(moves) <= 20
    board = chess.Board()
    for m in moves:
        assert m in board.legal_moves
        board.push(m)
    assert categorize(chess.Board(), chess.Move.from_uci("e2e4")) == "quiet"
    assert len(load_pgn_moves("tests/games/promotion.pgn")) == 10
