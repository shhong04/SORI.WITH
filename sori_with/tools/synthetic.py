"""Generate synthetic multi-part ensemble WAVs + MIDI for tests."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from sori_with.midi.score import synthesize_click_midi


def _click_track(
    duration: float,
    sr: int,
    tempo_bpm: float,
    lag_sec: float = 0.0,
    drop_from: float | None = None,
    drop_to: float | None = None,
    amp: float = 0.4,
) -> np.ndarray:
    n = int(duration * sr)
    audio = np.zeros(n, dtype=np.float64)
    beat_dur = 60.0 / tempo_bpm
    t = lag_sec
    while t < duration:
        if drop_from is not None and drop_to is not None and drop_from <= t <= drop_to:
            t += beat_dur
            continue
        i = int(t * sr)
        if 0 <= i < n - 50:
            # short decaying click
            click = amp * np.exp(-np.linspace(0, 8, 50)) * np.sin(
                2 * np.pi * 1000 * np.arange(50) / sr
            )
            audio[i : i + 50] += click
        t += beat_dur
    peak = np.max(np.abs(audio)) + 1e-9
    return audio / peak * 0.9


def build_synthetic_session(
    out_dir: Path | str,
    tempo_bpm: float = 120.0,
    bars: int = 16,
    sr: int = 48000,
) -> dict[str, Path]:
    """
    Create score.mid + 4 part wavs.
    Bass is intentionally late after bar 8 to induce drift/breakdown.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    midi_path = out_dir / "score.mid"
    score = synthesize_click_midi(midi_path, bars=bars, tempo_bpm=tempo_bpm)
    duration = score.duration_sec + 0.5

    parts = {
        "drums": _click_track(duration, sr, tempo_bpm, lag_sec=0.0, amp=0.5),
        "guitar": _click_track(duration, sr, tempo_bpm, lag_sec=0.01, amp=0.35),
        "vocal": _click_track(duration, sr, tempo_bpm, lag_sec=0.005, amp=0.3),
        # bass drifts late in second half
        "bass": _click_track(duration, sr, tempo_bpm, lag_sec=0.0, amp=0.4),
    }
    # inject late bass after midpoint
    mid = duration * 0.5
    beat_dur = 60.0 / tempo_bpm
    late = _click_track(duration, sr, tempo_bpm, lag_sec=0.12, amp=0.45)
    n_mid = int(mid * sr)
    parts["bass"][n_mid:] = late[n_mid:]

    paths: dict[str, Path] = {"midi": midi_path}
    for name, audio in parts.items():
        p = out_dir / f"{name}.wav"
        sf.write(str(p), audio, sr)
        paths[name] = p
    return paths
