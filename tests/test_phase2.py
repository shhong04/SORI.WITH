from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sori_with.api.main import app
from sori_with.engines.coaching import CoachingPolicyState, decide_coaching
from sori_with.engines.sessionist import control_from_live_tick, plan_sessionist_schedule
from sori_with.midi.score import synthesize_click_midi
from sori_with.models.schemas import (
    EnsembleClock,
    EnsembleState,
    EnsembleStateLabel,
    SessionistMode,
)
from sori_with.pipeline.practice import run_personal_practice
from sori_with.tools.synthetic import build_synthetic_session

client = TestClient(app)


def test_sessionist_schedule(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=8, tempo_bpm=120)
    schedule = plan_sessionist_schedule(score, role="bass", mode=SessionistMode.FOLLOW)
    assert len(schedule) > 0
    assert schedule[0].role == "bass"
    assert schedule[0].action in {"play", "hold", "fill"}


def test_sessionist_hold_on_low_confidence() -> None:
    action = control_from_live_tick(
        role="drums",
        mode=SessionistMode.FOLLOW,
        bar=2,
        beat=1.0,
        tempo=110,
        confidence=0.2,
        timestamp=1.0,
    )
    assert action.action == "hold"


def test_coaching_emits_on_breakdown() -> None:
    clock = EnsembleClock(
        timestamp=1.0,
        tempo=120,
        phase=0.0,
        bar=4,
        beat=1.0,
        reference_type="drums",
        reference_part_id="drums",
        stability=0.8,
    )
    state = EnsembleState(
        timestamp=1.0,
        state=EnsembleStateLabel.BREAKDOWN,
        ensemble_clock=clock,
        leader_part_ids=["drums"],
        follower_part_ids=["bass"],
        deviating_part_ids=["bass"],
        timing_spread_ms=200,
        tempo_variance=1.0,
        score_position_spread=4.0,
        breakdown_risk=0.9,
        natural_recovery_probability=0.2,
        confidence=0.9,
    )
    ev = decide_coaching(ensemble_state=state, policy=CoachingPolicyState(cooldown_sec=0))
    assert ev is not None
    assert "drums" in ev.message


def test_practice_pipeline(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path, tempo_bpm=120, bars=12)
    report = run_personal_practice(
        session_id="prac_1",
        song_id="p",
        midi_path=paths["midi"],
        user_part="guitar",
        user_wav_path=paths["guitar"],
        sessionist_parts=["bass", "drums"],
        sessionist_mode=SessionistMode.ACCOMPANY,
        tempo_bpm=120,
    )
    assert report.user_part == "guitar"
    assert len(report.sessionist_schedule) > 0
    assert "timing" in report.accuracy


def test_practice_api(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path)
    body = {
        "song_id": "api_practice",
        "midi_path": str(paths["midi"]),
        "user_part": "guitar",
        "user_wav_path": str(paths["guitar"]),
        "sessionist_parts": ["bass", "drums"],
        "sessionist_mode": "follow",
        "tempo_bpm": 120,
    }
    r = client.post("/api/v1/practice/analyze", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["song_id"] == "api_practice"
    sid = data["session_id"]
    r2 = client.get(f"/api/v1/practice/{sid}/report")
    assert r2.status_code == 200


def test_live_tick_and_ws() -> None:
    tick = {
        "session_id": "live_demo",
        "timestamp": 3.0,
        "bar": 8,
        "beat": 1.0,
        "tempo": 118.0,
        "confidence": 0.92,
        "user_part": "guitar",
        "sessionist_role": "bass",
        "sessionist_mode": "follow",
        "timing_spread_ms": 180.0,
        "state": "breakdown",
        "deviating_parts": ["bass"],
        "reference_part": "drums",
    }
    with client.websocket_connect("/api/v1/ws/sessions/live_demo") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "subscribed"
        r = client.post("/api/v1/live/tick", json=tick)
        assert r.status_code == 200, r.text
        payload = r.json()
        assert payload["sessionistAction"]["role"] == "bass"
        # coaching may or may not appear depending on policy; breakdown should usually emit
        msg = ws.receive_json()
        assert msg["type"] == "live_tick"
        assert msg["sessionId"] == "live_demo"
