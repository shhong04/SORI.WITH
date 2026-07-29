from __future__ import annotations

import numpy as np

from sori_with.config import get_thresholds
from sori_with.engines.part_understanding import PartAnalysis
from sori_with.models.schemas import EnsembleClock


def estimate_ensemble_clock(
    parts: list[PartAnalysis],
    grid_sec: float = 0.25,
) -> list[EnsembleClock]:
    """Build a shared ensemble clock timeline from part onsets."""
    cfg = get_thresholds()
    if not parts:
        return []

    duration = max(p.audio_duration for p in parts)
    times = np.arange(0.0, duration + grid_sec, grid_sec)
    clocks: list[EnsembleClock] = []

    for t in times:
        weighted_tempos: list[tuple[float, float]] = []
        local_onsets: list[tuple[str, float, float]] = []  # part, onset, weight

        for p in parts:
            prior = cfg.role_prior.get(p.instrument, 1.0)
            # nearest onset within window
            if len(p.onset_times) == 0:
                continue
            idx = int(np.argmin(np.abs(p.onset_times - t)))
            onset = float(p.onset_times[idx])
            if abs(onset - t) > grid_sec * 2:
                continue
            tempo = float(p.tempo_curve[idx]) if idx < len(p.tempo_curve) else p.tempo_bpm
            weighted_tempos.append((tempo, prior))
            local_onsets.append((p.part_id, onset, prior))

        if not weighted_tempos:
            tempo = cfg.default_tempo_bpm
            ref_part = None
            ref_type = "majority_consensus"
            stability = 0.2
            trend = "stable"
        else:
            wsum = sum(w for _, w in weighted_tempos)
            tempo = sum(v * w for v, w in weighted_tempos) / wsum
            # reference = highest prior among recently active
            ref_part = max(local_onsets, key=lambda x: x[2])[0]
            ref_inst = next(p.instrument for p in parts if p.part_id == ref_part)
            ref_type = ref_inst if ref_inst in cfg.role_prior else "majority_consensus"
            lags = [abs(o - t) * 1000 for _, o, _ in local_onsets]
            spread = float(np.std(lags)) if len(lags) > 1 else 0.0
            stability = float(np.clip(1.0 - spread / 120.0, 0.0, 1.0))
            trend = "stable"

        beat_dur = 60.0 / max(tempo, 1e-3)
        total_beats = t / beat_dur
        bar = int(total_beats // 4) + 1
        beat = (total_beats % 4) + 1.0
        phase = (total_beats % 1.0)

        clocks.append(
            EnsembleClock(
                timestamp=float(t),
                tempo=float(tempo),
                phase=float(phase),
                bar=bar,
                beat=float(beat),
                reference_type=ref_type,
                reference_part_id=ref_part,
                stability=stability,
                tempo_trend=trend,  # type: ignore[arg-type]
            )
        )

    # tempo trend smoothing pass
    for i in range(1, len(clocks)):
        d = clocks[i].tempo - clocks[i - 1].tempo
        if d > 0.8:
            clocks[i].tempo_trend = "accelerating"
        elif d < -0.8:
            clocks[i].tempo_trend = "decelerating"
        else:
            clocks[i].tempo_trend = "stable"
    return clocks
