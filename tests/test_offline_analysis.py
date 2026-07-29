from __future__ import annotations

from pathlib import Path

from sori_with.models.schemas import SessionCreate, SessionMode
from sori_with.pipeline.offline_analysis import (
    report_to_dashboard_payload,
    run_offline_ensemble_analysis,
)
from sori_with.storage.memory import store
from sori_with.tools.synthetic import build_synthetic_session


def test_offline_analysis_synthetic(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path, tempo_bpm=120.0, bars=16)
    session = store.create_session(
        SessionCreate(mode=SessionMode.OFFLINE_ANALYSIS, song_id="synth_001")
    )
    report = run_offline_ensemble_analysis(
        session_id=session.session_id,
        song_id="synth_001",
        midi_path=paths["midi"],
        part_wavs={
            "vocal": paths["vocal"],
            "guitar": paths["guitar"],
            "bass": paths["bass"],
            "drums": paths["drums"],
        },
        tempo_bpm=120.0,
    )
    assert report.duration_sec > 0
    assert set(report.parts) == {"vocal", "guitar", "bass", "drums"}
    assert report.ensemble_clock_summary["n_clock_samples"] > 0
    assert len(report.state_timeline) > 0
    assert "bass" in report.part_timing_deviation_ms
    # Bass was delayed in second half — expect higher deviation than drums
    assert report.part_timing_deviation_ms["bass"] >= report.part_timing_deviation_ms["drums"]
    payload = report_to_dashboard_payload(report)
    assert payload["sessionId"] == session.session_id
    assert "stateHistogram" in payload


def test_relations_not_empty(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path, tempo_bpm=100.0, bars=12)
    report = run_offline_ensemble_analysis(
        session_id="sess_test",
        song_id="synth_002",
        midi_path=paths["midi"],
        part_wavs={
            "bass": paths["bass"],
            "drums": paths["drums"],
        },
        tempo_bpm=100.0,
    )
    assert len(report.relations) >= 1
