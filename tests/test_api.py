from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from sori_with.api.main import app
from sori_with.tools.synthetic import build_synthetic_session

client = TestClient(app)


def test_health() -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_analyze_path_endpoint(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path)
    body = {
        "song_id": "api_synth",
        "midi_path": str(paths["midi"]),
        "parts": {
            "vocal": str(paths["vocal"]),
            "guitar": str(paths["guitar"]),
            "bass": str(paths["bass"]),
            "drums": str(paths["drums"]),
        },
        "tempo_bpm": 120.0,
    }
    r = client.post("/api/v1/sessions/analyze/path", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["song_id"] == "api_synth"
    assert len(data["parts"]) == 4
    sid = data["session_id"]
    r2 = client.get(f"/api/v1/sessions/{sid}/report")
    assert r2.status_code == 200
    r3 = client.get(f"/api/v1/sessions/{sid}/dashboard")
    assert r3.status_code == 200
    r4 = client.get(f"/api/v1/sessions/{sid}/state")
    assert r4.status_code == 200
    assert r4.json()["type"] == "ensemble_state"
