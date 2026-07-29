from __future__ import annotations

import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from sori_with.config import get_settings, get_thresholds
from sori_with.tools.synthetic import build_synthetic_session


def test_path_analyze_disabled_in_production(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SORI_WITH_ENVIRONMENT", "production")
    get_settings.cache_clear()
    get_thresholds.cache_clear()

    from sori_with.api.main import app

    build_synthetic_session(tmp_path / "demo")
    settings = get_settings()
    target = settings.data_dir / "test_prod_block"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(tmp_path / "demo", target)

    try:
        client = TestClient(app)
        r = client.post(
            "/api/v1/sessions/analyze/path",
            json={
                "song_id": "blocked",
                "midi_path": str(target / "score.mid"),
                "parts": {
                    "guitar": str(target / "guitar.wav"),
                    "bass": str(target / "bass.wav"),
                },
                "tempo_bpm": 120,
            },
        )
        assert r.status_code == 403
        assert r.json()["detail"]["code"] == "PATH_ENDPOINT_DISABLED"
    finally:
        shutil.rmtree(target, ignore_errors=True)
        monkeypatch.delenv("SORI_WITH_ENVIRONMENT", raising=False)
        get_settings.cache_clear()
        get_thresholds.cache_clear()


def test_path_outside_roots_rejected(tmp_path: Path, monkeypatch):
    # Force production-like roots (no tempdir allowlist) while keeping path API on
    monkeypatch.setenv("SORI_WITH_ENVIRONMENT", "development")
    monkeypatch.setenv("SORI_WITH_ALLOW_PATH_ANALYZE", "true")
    get_settings.cache_clear()
    get_thresholds.cache_clear()

    from sori_with.api.uploads import resolve_allowed_path
    from fastapi import HTTPException

    # Create a file outside data_dir/ROOT/temp by using a nested path that we
    # temporarily treat as forbidden: monkeypatch allowed roots to data_dir only.
    outside = tmp_path / "secret.mid"
    outside.write_bytes(b"MThd" + b"\x00" * 20)

    monkeypatch.setattr(
        "sori_with.api.uploads.allowed_path_roots",
        lambda settings=None: [get_settings().data_dir.resolve()],
    )

    try:
        resolve_allowed_path(str(outside))
        assert False, "expected HTTPException"
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail["code"] == "PATH_NOT_ALLOWED"
    finally:
        get_settings.cache_clear()
        get_thresholds.cache_clear()
