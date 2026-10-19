import chess
import cv2
import pytest

from edge.calibration import Calibration
from tests.eval_real import find_clips, main, run_clip, summarize
from tests.synth import FRAME_H, FRAME_W, SynthConfig, play

MOVES = [chess.Move.from_uci(u) for u in ("e2e4", "e7e5", "g1f3")]


def write_clip(folder, name, moves):
    game = play(moves, SynthConfig(seed=4))
    path = folder / f"{name}.mp4"
    out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 10.0, (FRAME_W, FRAME_H))
    if not out.isOpened():
        pytest.skip("this OpenCV build cannot write mp4")
    for frame, _, _ in game.frames:
        out.write(frame)
    out.release()
    game.calibration.save(folder / f"{name}.calibration.json")
    board = chess.Board()
    san = []
    for m in moves:
        san.append(board.san(m))
        board.push(m)
    (folder / f"{name}.pgn").write_text('[Result "*"]\n\n' + " ".join(san) + " *\n")
    return path


def test_scores_a_clip_against_its_truth(tmp_path):
    video = write_clip(tmp_path, "clip", MOVES)
    result = run_clip(video, MOVES, Calibration.load(video.with_suffix(".calibration.json")))
    assert (result.truth_moves, result.correct_prefix, result.accepted) == (3, 3, 3)
    assert result.fully_correct


def test_wrong_truth_stops_the_correct_prefix(tmp_path):
    video = write_clip(tmp_path, "clip", MOVES)
    wrong = [MOVES[0], chess.Move.from_uci("c7c5"), MOVES[2]]
    result = run_clip(video, wrong, Calibration.load(video.with_suffix(".calibration.json")))
    assert result.correct_prefix == 1
    assert not result.fully_correct


def test_find_clips_needs_all_three_files(tmp_path):
    (tmp_path / "a.mp4").write_bytes(b"x")
    (tmp_path / "a.pgn").write_text("*")
    assert find_clips(tmp_path) == []
    (tmp_path / "a.calibration.json").write_text("{}")
    assert [p.name for p in find_clips(tmp_path)] == ["a.mp4"]


def test_main_reports_when_there_are_no_clips(tmp_path, capsys):
    assert main(["--dir", str(tmp_path)]) == 2
    assert "No complete clips" in capsys.readouterr().out


def test_summarize_empty():
    assert summarize([])["prefix_accuracy"] == 0.0
