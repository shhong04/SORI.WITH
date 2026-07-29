from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from sori_with.config import ThresholdConfig, get_thresholds


def load_mono(path: Path | str, target_sr: int | None = None) -> tuple[np.ndarray, int]:
    cfg = get_thresholds()
    sr = target_sr or cfg.sample_rate
    audio, file_sr = sf.read(str(path), always_2d=False)
    if audio.ndim > 1:
        audio = np.mean(audio, axis=1)
    audio = audio.astype(np.float64)
    if file_sr != sr:
        audio = _resample_linear(audio, file_sr, sr)
    peak = np.max(np.abs(audio)) + 1e-12
    audio = audio / peak
    return audio, sr


def _resample_linear(audio: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
    if orig_sr == target_sr:
        return audio
    duration = len(audio) / orig_sr
    n_target = int(round(duration * target_sr))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n_target, endpoint=False)
    return np.interp(x_new, x_old, audio)


def frame_signal(
    audio: np.ndarray,
    hop_length: int | None = None,
    frame_length: int | None = None,
) -> np.ndarray:
    cfg = get_thresholds()
    hop = hop_length or cfg.hop_length
    fl = frame_length or hop * 2
    if len(audio) < fl:
        audio = np.pad(audio, (0, fl - len(audio)))
    n_frames = 1 + (len(audio) - fl) // hop
    frames = np.lib.stride_tricks.as_strided(
        audio,
        shape=(n_frames, fl),
        strides=(audio.strides[0] * hop, audio.strides[0]),
        writeable=False,
    )
    return np.copy(frames)


def detect_onsets(
    audio: np.ndarray,
    sr: int,
    cfg: ThresholdConfig | None = None,
) -> np.ndarray:
    """Energy-flux onset detection. Returns onset times in seconds."""
    cfg = cfg or get_thresholds()
    frames = frame_signal(audio, hop_length=cfg.hop_length)
    window = np.hanning(frames.shape[1])
    energy = np.sqrt(np.mean((frames * window) ** 2, axis=1) + 1e-12)
    flux = np.diff(energy, prepend=energy[0])
    flux = np.maximum(flux, 0.0)
    if flux.max() < 1e-12:
        return np.array([], dtype=np.float64)
    thresh = np.percentile(flux, cfg.onset_energy_percentile)
    candidates = np.where(flux >= thresh)[0]
    times: list[float] = []
    min_gap = cfg.min_onset_gap_sec
    for idx in candidates:
        t = idx * cfg.hop_length / sr
        if not times or (t - times[-1]) >= min_gap:
            times.append(float(t))
    return np.asarray(times, dtype=np.float64)


def estimate_tempo_curve(
    onset_times: np.ndarray,
    cfg: ThresholdConfig | None = None,
) -> tuple[float, np.ndarray]:
    """Return (median tempo bpm, per-onset local tempo array)."""
    cfg = cfg or get_thresholds()
    if len(onset_times) < 2:
        tempo = cfg.default_tempo_bpm
        return tempo, np.array([tempo], dtype=np.float64)

    ioi = np.diff(onset_times)
    ioi = ioi[ioi > 1e-3]
    if len(ioi) == 0:
        return cfg.default_tempo_bpm, np.full(len(onset_times), cfg.default_tempo_bpm)

    # Assume dominant IOI is quarter-note-ish; clamp to configured range.
    local_bpm = 60.0 / ioi
    local_bpm = np.clip(local_bpm, cfg.tempo_min_bpm / 2, cfg.tempo_max_bpm * 2)
    # Fold double/half tempo into range.
    folded = []
    for bpm in local_bpm:
        while bpm < cfg.tempo_min_bpm:
            bpm *= 2
        while bpm > cfg.tempo_max_bpm:
            bpm /= 2
        folded.append(bpm)
    local_bpm = np.asarray(folded, dtype=np.float64)
    win = max(1, cfg.tempo_smoothing_window)
    smoothed = np.convolve(local_bpm, np.ones(win) / win, mode="same")
    # Align length with onsets (prepend first)
    tempo_per_onset = np.concatenate([[smoothed[0]], smoothed])
    if len(tempo_per_onset) > len(onset_times):
        tempo_per_onset = tempo_per_onset[: len(onset_times)]
    elif len(tempo_per_onset) < len(onset_times):
        tempo_per_onset = np.pad(
            tempo_per_onset,
            (0, len(onset_times) - len(tempo_per_onset)),
            constant_values=float(np.median(smoothed)),
        )
    return float(np.median(smoothed)), tempo_per_onset
