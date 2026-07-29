from __future__ import annotations

from pathlib import Path

from sori_with.engines.sessionist import (
    LiveSessionistController,
    build_transport_map,
    extract_role_content,
    plan_sessionist_schedule,
    schedule_lookahead,
)
from sori_with.midi.score import synthesize_click_midi
from sori_with.models.schemas import SessionistMode


def test_transport_faster_user_compresses_timeline(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=8, tempo_bpm=120)
    curve_fast = [(t, 150.0) for t in [0.0, 2.0, 4.0, 8.0, 16.0]]
    sched_score = plan_sessionist_schedule(score, role="bass", mode=SessionistMode.FOLLOW)
    sched_fast = plan_sessionist_schedule(
        score,
        role="bass",
        mode=SessionistMode.FOLLOW,
        user_tempo_curve=curve_fast,
    )
    assert sched_fast[-1].timestamp < sched_score[-1].timestamp


def test_content_marks_pattern_source_for_bass_on_click_score(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=4, tempo_bpm=120)
    notes = extract_role_content(score, "bass")
    assert notes
    assert all(n.source == "pattern" for n in notes)


def test_lookahead_returns_near_future_notes(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=4, tempo_bpm=120)
    schedule = plan_sessionist_schedule(score, role="drums", mode=SessionistMode.FOLLOW)
    near = schedule_lookahead(schedule, timestamp=0.0, horizon_sec=1.0)
    assert len(near) >= 1
    assert all(a.timestamp <= 1.0 for a in near)


def test_live_controller_reenter_after_low_confidence(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=4, tempo_bpm=120)
    ctrl = LiveSessionistController(
        role="bass",
        mode=SessionistMode.FOLLOW,
        score=score,
        confidence_floor=0.45,
    )
    ctrl.ensure_content()
    # establish a prior play
    a0 = ctrl.tick(bar=1, beat=1.0, tempo=120, confidence=0.9, timestamp=0.0)
    assert a0.action in {"play", "fill", "reenter"}
    # dip
    for i in range(3):
        h = ctrl.tick(bar=1, beat=2.0 + i * 0.1, tempo=120, confidence=0.2, timestamp=1.0 + i)
        assert h.action in {"hold", "repeat"}
    # still mid-bar → wait
    wait = ctrl.tick(bar=2, beat=2.0, tempo=120, confidence=0.9, timestamp=4.0)
    assert wait.action == "hold"
    # downbeat recovery
    reenter = ctrl.tick(bar=2, beat=1.0, tempo=120, confidence=0.9, timestamp=4.5)
    assert reenter.action == "reenter"


def test_transport_map_monotonic(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=4, tempo_bpm=100)
    transport = build_transport_map(
        score,
        [(0.0, 100.0), (5.0, 110.0), (10.0, 90.0)],
        SessionistMode.FOLLOW,
    )
    times = [0.0, 1.0, 2.0, 4.0, 6.0]
    perf = [transport.performance_time(t) for t in times]
    assert all(perf[i] <= perf[i + 1] for i in range(len(perf) - 1))
