import chess
import numpy as np
import pytest

from edge.pipeline import Pipeline
from edge.verify import (
    consistency_errors,
    decode_position,
    make_prior,
    move_agreement,
    occupancy_mismatches,
    occupancy_probs,
)
from ml.common import board_labels, class_of
from tests.ml.helpers import probs_for
from tests.synth import SynthConfig, play


def test_occupancy_probs_sum_to_one():
    occ = occupancy_probs(probs_for(chess.Board()))
    np.testing.assert_allclose(occ.sum(1), 1.0, rtol=1e-5)


def test_no_mismatch_when_classifier_agrees_and_flags_a_missing_piece():
    board = chess.Board()
    assert occupancy_mismatches(board, probs_for(board)) == []
    wrong = board.copy()
    for sq in (chess.A2, chess.B2, chess.C2):
        wrong.remove_piece_at(sq)
    assert sorted(occupancy_mismatches(board, probs_for(wrong))) == [chess.A2, chess.B2, chess.C2]


def test_unsure_classifier_is_not_trusted():
    board = chess.Board()
    wrong = board.copy()
    wrong.remove_piece_at(chess.A2)
    assert occupancy_mismatches(board, probs_for(wrong, confidence=0.3)) == []


def test_prior_prefers_the_move_the_classifier_sees():
    board = chess.Board()
    after = board.copy()
    played = chess.Move.from_uci("g1f3")
    after.push(played)
    probs = probs_for(after)
    occ = occupancy_probs(probs)
    assert move_agreement(board, played, occ) > move_agreement(
        board, chess.Move.from_uci("b1c3"), occ
    )
    prior = make_prior(board, list(board.legal_moves), probs, weight=0.5)
    assert prior(played) == pytest.approx(0.0)
    assert prior(chess.Move.from_uci("b1c3")) < -0.3
    assert all(prior(m) <= 1e-9 for m in board.legal_moves)  # never raises a score


class TestConsistency:
    def test_start_position_is_fine(self):
        assert consistency_errors(chess.Board().piece_map()) == []

    def test_reports_each_kind_of_violation(self):
        pieces = chess.Board().piece_map()
        pieces.pop(chess.E1)
        assert any("0 kings" in e for e in consistency_errors(pieces))
        pieces = chess.Board().piece_map()
        pieces[chess.E4] = chess.Piece(chess.KING, chess.WHITE)
        assert any("2 kings" in e for e in consistency_errors(pieces))
        pieces = chess.Board().piece_map()
        pieces[chess.A8] = chess.Piece(chess.PAWN, chess.WHITE)
        assert any("first or last rank" in e for e in consistency_errors(pieces))
        pieces = chess.Board().piece_map()
        for sq in (chess.A3, chess.B3):
            pieces[sq] = chess.Piece(chess.PAWN, chess.WHITE)
        assert any("9 pawns" in e or "10 pawns" in e for e in consistency_errors(pieces))
        pieces = chess.Board().piece_map()
        pieces[chess.A3] = chess.Piece(chess.QUEEN, chess.WHITE)
        assert any("promoted" in e for e in consistency_errors(pieces))


class TestDecode:
    def test_clean_probabilities_decode_to_the_same_position(self):
        board = chess.Board("r3k2r/pp3ppp/2n1bn2/3pp3/3P4/2N1BN2/PPP1QPPP/R3K2R w KQkq - 0 1")
        decoded, errors = decode_position(probs_for(board), board.turn)
        assert errors == []
        assert decoded.board_fen() == board.board_fen()

    def test_two_kings_are_repaired_keeping_the_more_confident_one(self):
        board = chess.Board()
        probs = probs_for(board)
        wk = class_of(chess.Piece(chess.KING, chess.WHITE))
        probs[chess.D1] = 0.01
        probs[chess.D1, wk] = 0.6  # queen square now looks like a second king
        probs[chess.D1, class_of(chess.Piece(chess.QUEEN, chess.WHITE))] = 0.39
        decoded, errors = decode_position(probs)
        assert errors == []
        assert decoded.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
        assert decoded.piece_at(chess.D1) == chess.Piece(chess.QUEEN, chess.WHITE)

    def test_missing_king_is_restored_from_the_most_king_like_piece(self):
        board = chess.Board()
        probs = probs_for(board)
        wk = class_of(chess.Piece(chess.KING, chess.WHITE))
        wq = class_of(chess.Piece(chess.QUEEN, chess.WHITE))
        probs[chess.E1] = 0.01
        probs[chess.E1, wq] = 0.7  # the king looks like a queen
        probs[chess.E1, wk] = 0.29
        decoded, errors = decode_position(probs)
        assert decoded.piece_at(chess.E1) == chess.Piece(chess.KING, chess.WHITE)
        assert errors == []

    def test_pawn_on_back_rank_is_replaced(self):
        board = chess.Board()
        probs = probs_for(board)
        wp = class_of(chess.Piece(chess.PAWN, chess.WHITE))
        wn = class_of(chess.Piece(chess.KNIGHT, chess.WHITE))
        probs[chess.B1] = 0.01
        probs[chess.B1, wp] = 0.6
        probs[chess.B1, wn] = 0.39
        decoded, errors = decode_position(probs)
        assert decoded.piece_at(chess.B1) == chess.Piece(chess.KNIGHT, chess.WHITE)
        assert errors == []

    def test_bad_shape_is_rejected(self):
        with pytest.raises(ValueError):
            decode_position(np.zeros((64, 5)))


class FakeClassifier:
    """Returns probabilities for a scripted sequence of positions, one per stable frame."""

    def __init__(self, boards):
        self.boards = iter(boards)

    def predict(self, warped):
        return probs_for(next(self.boards))


def positions_after(moves):
    board, out = chess.Board(), []
    for m in moves:
        board.push(m)
        out.append(board.copy())
    return out


MOVES = [chess.Move.from_uci(u) for u in ("e2e4", "e7e5", "g1f3")]


def run(pipe, game):
    events = []
    for frame, t, _ in game.frames:
        events += pipe.process_frame(frame, t)
    return events


def test_pipeline_with_agreeing_classifier_tracks_without_desync():
    game = play(MOVES, SynthConfig(seed=13))
    pipe = Pipeline(game.calibration, classifier=FakeClassifier(positions_after(MOVES)))
    events = run(pipe, game)
    assert [e.san for e in events if e.kind == "move"] == ["e4", "e5", "Nf3"]
    assert not [e for e in events if e.kind == "desync"]


def test_pipeline_flags_desync_and_accepts_a_proposed_position():
    game = play(MOVES[:1], SynthConfig(seed=14))
    truth = positions_after(MOVES[:1])[0]
    skewed = truth.copy()
    for sq in (chess.A7, chess.B7, chess.C7):  # classifier sees three black pawns missing
        skewed.remove_piece_at(sq)
    pipe = Pipeline(game.calibration, classifier=FakeClassifier([skewed]))
    events = run(pipe, game)
    desync = [e for e in events if e.kind == "desync"]
    assert len(desync) == 1
    assert set(desync[0].candidates) == {"a7", "b7", "c7"}
    assert pipe.proposed_fen is not None
    event = pipe.accept_proposal()
    assert event is not None and event.kind == "set_fen"
    assert pipe.board.board_fen() == skewed.board_fen()
    assert pipe.accept_proposal() is None  # one-shot


def test_labels_helper_matches_classifier_layout():
    board = chess.Board()
    assert probs_for(board).argmax(1).tolist() == board_labels(board).tolist()
