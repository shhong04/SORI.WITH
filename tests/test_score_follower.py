from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from sori_with.engines.score_follower import follow_score_offline
from sori_with.midi.score import load_midi_score, synthesize_click_midi
from sori_with.pipeline.offline_analysis import run_offline_ensemble_analysis
from sori_with.tools.synthetic import _click_track, build_synthetic_session


def test_score_follower_known_late_lag(tmp_path: Path) -> None:
    """All onsets late by ~80ms → mean signed error should be near +80."""
    tempo = 120.0
    lag = 0.08
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=8, tempo_bpm=tempo)
    duration = score.duration_sec + 0.25
    sr = 48000
    audio = _click_track(duration, sr, tempo, lag_sec=lag, amp=0.5)
    wav = tmp_path / "late.wav"
    sf.write(str(wav), audio, sr)

    # Use ground-truth onset times (avoid detector jitter for unit check)
    beat_dur = 60.0 / tempo
    onsets = np.arange(lag, duration - 0.05, beat_dur)
    result = follow_score_offline(onsets, load_midi_score(midi, default_tempo_bpm=tempo))
    assert len(result.matches) >= 8
    assert 50 <= result.mean_signed_error_ms <= 110
    assert result.alignment_confidence > 0.4


def test_score_follower_on_time(tmp_path: Path) -> None:
    tempo = 100.0
    midi = tmp_path / "score.mid"
    score = synthesize_click_midi(midi, bars=6, tempo_bpm=tempo)
    beat_dur = 60.0 / tempo
    onsets = np.arange(0.0, score.duration_sec - 0.01, beat_dur)
    result = follow_score_offline(onsets, score)
    assert abs(result.mean_signed_error_ms) < 20
    assert result.mean_abs_error_ms < 25


def test_offline_report_exposes_signed_deviation(tmp_path: Path) -> None:
    paths = build_synthetic_session(tmp_path, tempo_bpm=120.0, bars=12)
    report = run_offline_ensemble_analysis(
        session_id="align_sess",
        song_id="align",
        midi_path=paths["midi"],
        part_wavs={"drums": paths["drums"], "bass": paths["bass"]},
        tempo_bpm=120.0,
    )
    assert report.part_signed_timing_deviation_ms
    assert "bass" in report.part_alignment_confidence
    assert report.part_alignment_confidence["drums"] > 0.2
    # bass is late in second half → overall signed mean should be >= drums
    assert (
        report.part_signed_timing_deviation_ms["bass"]
        >= report.part_signed_timing_deviation_ms["drums"] - 5
    )
    assert report.timing_windows
    assert len(report.state_timeline) > 0
