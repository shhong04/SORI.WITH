from pathlib import Path

from sori_with.tools.synthetic import build_synthetic_session


def test_demo_stage_select_sample_analyze(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SORI_WITH_UPLOAD_DIR", str(tmp_path / "uploads"))
    from sori_with.config import get_settings

    get_settings.cache_clear()

    r = client.post("/api/v1/demo/stage/reset")
    assert r.status_code == 200

    g = client.post(
        "/api/v1/demo/stage/select",
        data={"part_id": "guitar", "display_name": "G"},
    )
    assert g.status_code == 200
    gid = g.json()["you"]["userId"]
    assert "guitar" in g.json()["highlightedParts"]

    b = client.post(
        "/api/v1/demo/stage/select",
        data={"part_id": "bass", "display_name": "B"},
    )
    bid = b.json()["you"]["userId"]

    assert client.post("/api/v1/demo/stage/sample", data={"user_id": gid}).status_code == 200
    assert client.post("/api/v1/demo/stage/sample", data={"user_id": bid}).status_code == 200

    an = client.post("/api/v1/demo/stage/analyze")
    assert an.status_code == 200, an.text
    body = an.json()
    assert body["status"] == "ready"
    assert body["dashboard"] is not None
    assert "guitar" in body["dashboard"]["partAlignmentConfidence"]
    assert "bass" in body["dashboard"]["partTimingDeviationMs"]


def test_demo_stage_audio_upload(client, tmp_path, monkeypatch):
    monkeypatch.setenv("SORI_WITH_UPLOAD_DIR", str(tmp_path / "uploads2"))
    from sori_with.config import get_settings

    get_settings.cache_clear()

    client.post("/api/v1/demo/stage/reset")
    syn = build_synthetic_session(tmp_path / "syn")
    sel = client.post(
        "/api/v1/demo/stage/select",
        data={"part_id": "drums", "display_name": "D"},
    )
    uid = sel.json()["you"]["userId"]
    wav = Path(syn["drums"]).read_bytes()
    up = client.post(
        "/api/v1/demo/stage/audio",
        data={"user_id": uid},
        files={"audio": ("drums.wav", wav, "audio/wav")},
    )
    assert up.status_code == 200
    assert "drums" in up.json()["partsWithAudio"]
