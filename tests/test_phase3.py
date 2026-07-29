from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sori_with.api.main import app
from sori_with.audio.render import render_schedule_to_audio, render_sessionist_bundle
from sori_with.engines.sessionist import plan_sessionist_schedule
from sori_with.midi.score import synthesize_click_midi
from sori_with.models.schemas import SessionistMode
from sori_with.tools.synthetic import build_synthetic_session

client = TestClient(app)


def test_render_sessionist_audio(tmp_path: Path) -> None:
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=4, tempo_bpm=120)
    schedule = plan_sessionist_schedule(score, role="bass", mode=SessionistMode.FOLLOW)
    audio = render_schedule_to_audio(schedule, sr=22050)
    assert audio.ndim == 1
    assert len(audio) > 1000
    assert float(abs(audio).max()) > 0.01
    stems = render_sessionist_bundle(schedule, tmp_path / "out", tempo_bpm=120)
    assert stems["mix_wav"].exists()
    assert stems["mix_midi"].exists()
    assert stems["bass_wav"].exists()


def test_practice_renders_audio(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path, bars=8)
    body = {
        "song_id": "render_prac",
        "midi_path": str(paths["midi"]),
        "user_part": "guitar",
        "user_wav_path": str(paths["guitar"]),
        "sessionist_parts": ["bass", "drums"],
        "sessionist_mode": "accompany",
        "tempo_bpm": 120,
        "render_audio": True,
    }
    r = client.post("/api/v1/practice/analyze", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "mix_wav" in data["render_paths"]
    assert Path(data["render_paths"]["mix_wav"]).exists()


def test_ensemble_room_flow(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path, bars=8)

    r = client.post(
        "/api/v1/rooms",
        json={
            "song_id": "band_1",
            "room_name": "Campus Band",
            "network_mode": "hybrid",
            "tempo_bpm": 120,
        },
    )
    assert r.status_code == 200, r.text
    room = r.json()
    room_id = room["room_id"]

    with client.websocket_connect(f"/api/v1/ws/rooms/{room_id}") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "subscribed"

        r = client.post(
            f"/api/v1/rooms/{room_id}/join",
            json={"user_id": "u1", "part_id": "guitar", "display_name": "Alex"},
        )
        assert r.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "member_joined"

        r = client.post(
            f"/api/v1/rooms/{room_id}/join",
            json={"user_id": "u2", "part_id": "drums", "display_name": "Kim"},
        )
        assert r.status_code == 200
        _ = ws.receive_json()

        # duplicate part should fail
        r = client.post(
            f"/api/v1/rooms/{room_id}/join",
            json={"user_id": "u3", "part_id": "guitar"},
        )
        assert r.status_code == 400

        r = client.post(
            f"/api/v1/rooms/{room_id}/score/path",
            data={"midi_path": str(paths["midi"])},
        )
        assert r.status_code == 200

        r = client.post(
            f"/api/v1/rooms/{room_id}/parts/u1/audio/path",
            data={"audio_path": str(paths["guitar"])},
        )
        assert r.status_code == 200
        r = client.post(
            f"/api/v1/rooms/{room_id}/parts/u2/audio/path",
            data={"audio_path": str(paths["drums"])},
        )
        assert r.status_code == 200

        r = client.post(f"/api/v1/rooms/{room_id}/start")
        assert r.status_code == 200
        msg = ws.receive_json()
        assert msg["type"] == "rehearsal_started"

        r = client.post(f"/api/v1/rooms/{room_id}/analyze?fill_missing_with_ai=true")
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["room"]["status"] == "ready"
        assert "bass" in data["report"]["parts"] or "vocal" in data["aiSessionistParts"] or len(
            data["report"]["parts"]
        ) >= 2
        msg = ws.receive_json()
        assert msg["type"] == "room_analyzed"

    r = client.get(f"/api/v1/rooms/{room_id}/dashboard")
    assert r.status_code == 200
    assert "parts" in r.json()
