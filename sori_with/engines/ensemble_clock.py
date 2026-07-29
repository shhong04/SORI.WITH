from __future__ import annotations

import numpy as np

from sori_with.config import get_thresholds
from sori_with.engines.part_understanding import PartAnalysis
from sori_with.models.schemas import EnsembleClock


def estimate_ensemble_clock(
    parts: list[PartAnalysis],
    grid_sec: float = 0.25,
    time_signature: tuple[int, int] = (4, 4),
) -> list[EnsembleClock]:
    """
    Shared ensemble clock from score-matched beat phases when available.

    Falls back to onset-weighted tempo + role prior if matches are sparse.
    """
    cfg = get_thresholds()
    if not parts:
        return []

    duration = max(p.audio_duration for p in parts)
    beats_per_bar = time_signature[0]
    times = np.arange(0.0, duration + grid_sec, grid_sec)
    clocks: list[EnsembleClock] = []

    for t in times:
        weighted_tempos: list[tuple[float, float]] = []
        phase_samples: list[tuple[float, float]] = []  # phase, weight
        local_parts: list[tuple[str, float, float, float]] = []
        # part_id, prior, signed_err_ms, confidence

        for p in parts:
            prior = cfg.role_prior.get(p.instrument, 1.0)
            near_matches = [
                m for m in p.matches if abs(m.onset_time - t) <= grid_sec * 2.5
            ]
            if near_matches:
                m = min(near_matches, key=lambda x: abs(x.onset_time - t))
                tempo = float(p.tempo_bpm)
                weighted_tempos.append((tempo, prior * max(m.confidence, 0.2)))
                # beat phase from fractional beat
                phase = float(m.beat % 1.0)
                phase_samples.append((phase, prior * m.confidence))
                local_parts.append(
                    (p.part_id, prior * m.confidence, m.signed_error_ms, m.confidence)
                )
                continue

            if len(p.onset_times) == 0:
                continue
            idx = int(np.argmin(np.abs(p.onset_times - t)))
            onset = float(p.onset_times[idx])
            if abs(onset - t) > grid_sec * 2:
                continue
            tempo = float(p.tempo_curve[idx]) if idx < len(p.tempo_curve) else p.tempo_bpm
            weighted_tempos.append((tempo, prior * 0.5))
            local_parts.append((p.part_id, prior * 0.5, 0.0, 0.3))

        if not weighted_tempos:
            tempo = cfg.default_tempo_bpm
            ref_part = None
            ref_type = "majority_consensus"
            stability = 0.2
        else:
            wsum = sum(w for _, w in weighted_tempos)
            tempo = sum(v * w for v, w in weighted_tempos) / wsum
            # reference: highest weight among active, but prefer low |error|
            ref_part = max(local_parts, key=lambda x: x[1] - 0.002 * abs(x[2]))[0]
            ref_inst = next(p.instrument for p in parts if p.part_id == ref_part)
            ref_type = ref_inst if ref_inst in cfg.role_prior else "majority_consensus"
            if len(local_parts) > 1:
                errs = [e for _, _, e, _ in local_parts]
                spread = float(np.std(errs))
                stability = float(np.clip(1.0 - spread / 120.0, 0.0, 1.0))
            else:
                stability = 0.5

        beat_dur = 60.0 / max(tempo, 1e-3)
        # Prefer score-matched bar/beat from strongest local match
        bar = None
        beat = None
        for p in parts:
            near = [m for m in p.matches if abs(m.onset_time - t) <= grid_sec * 2.5]
            if near:
                m = min(near, key=lambda x: abs(x.onset_time - t))
                bar, beat = m.bar, m.beat
                break
        if bar is None:
            total_beats = t / beat_dur
            bar = int(total_beats // beats_per_bar) + 1
            beat = (total_beats % beats_per_bar) + 1.0

        if phase_samples:
            # circular mean of phase
            ang = np.asarray([ph * 2 * np.pi for ph, _ in phase_samples])
            w = np.asarray([wt for _, wt in phase_samples])
            c = np.sum(np.cos(ang) * w)
            s = np.sum(np.sin(ang) * w)
            phase = float((np.arctan2(s, c) / (2 * np.pi)) % 1.0)
        else:
            phase = float((beat - 1.0) % 1.0)

        clocks.append(
            EnsembleClock(
                timestamp=float(t),
                tempo=float(tempo),
                phase=phase,
                bar=int(bar),
                beat=float(beat),
                reference_type=ref_type,
                reference_part_id=ref_part,
                stability=stability,
                tempo_trend="stable",
            )
        )

    for i in range(1, len(clocks)):
        d = clocks[i].tempo - clocks[i - 1].tempo
        if d > 0.8:
            clocks[i].tempo_trend = "accelerating"
        elif d < -0.8:
            clocks[i].tempo_trend = "decelerating"
        else:
            clocks[i].tempo_trend = "stable"
    return clocks
