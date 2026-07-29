from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sori_with.config import get_thresholds
from sori_with.engines.part_understanding import PartAnalysis
from sori_with.models.schemas import EnsembleRelation, RelationType


@dataclass
class PartDeviationWindow:
    part_id: str
    window_start: float
    window_end: float
    mean_abs_ms: float
    mean_signed_ms: float
    slope_ms_per_beat: float
    direction: str
    n_matches: int


def estimate_relations(
    parts: list[PartAnalysis],
    *,
    window_sec: float = 8.0,
) -> list[EnsembleRelation]:
    """
    Windowed probable influence from score-matched signed errors.

    Emits at most one directed relation per unordered pair per window
    (avoids contradictory A↔B LEADS pairs).
    """
    cfg = get_thresholds()
    relations: list[EnsembleRelation] = []
    if len(parts) < 2:
        return relations

    duration = max((p.audio_duration for p in parts), default=0.0)
    if duration <= 0:
        return relations

    starts = np.arange(0.0, duration, window_sec)
    for w0 in starts:
        w1 = w0 + window_sec
        # pairwise compare mean signed error vs score in window
        window_stats: dict[str, tuple[float, int]] = {}
        for p in parts:
            errs = [
                m.signed_error_ms
                for m in p.matches
                if w0 <= m.onset_time < w1
            ]
            if len(errs) >= 2:
                window_stats[p.part_id] = (float(np.mean(errs)), len(errs))

        ids = list(window_stats.keys())
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                a_id, b_id = ids[i], ids[j]
                a_mean, a_n = window_stats[a_id]
                b_mean, b_n = window_stats[b_id]
                # relative lag: how much later B is than A vs score
                lag_ms = b_mean - a_mean
                evidence = min(a_n, b_n)
                strength = float(np.clip(1.0 - abs(abs(lag_ms) - 40) / 120.0, 0.0, 1.0))
                conf = float(np.clip(evidence / 6.0, 0.2, 1.0))

                if abs(lag_ms) < cfg.deviation_significance_ms * 0.5:
                    # near-synchronous — report maintains_reference from higher-prior role
                    source, target = a_id, b_id
                    rel = RelationType.MAINTAINS_REFERENCE
                    lag_out = lag_ms
                elif lag_ms > 0:
                    # B later than A → A leads
                    source, target = a_id, b_id
                    rel = RelationType.LEADS
                    lag_out = lag_ms
                else:
                    source, target = b_id, a_id
                    rel = RelationType.LEADS
                    lag_out = -lag_ms

                relations.append(
                    EnsembleRelation(
                        source_part_id=source,
                        target_part_id=target,
                        relation_type=rel,
                        start_timestamp=float(w0),
                        end_timestamp=float(min(w1, duration)),
                        lag_ms=float(lag_out),
                        strength=strength,
                        confidence=conf,
                        evidence_count=evidence,
                    )
                )
    return relations


def timing_deviation_ms(
    parts: list[PartAnalysis],
    reference_part_id: str | None,
) -> dict[str, float]:
    """Mean absolute score-matched timing error per part (ms)."""
    out: dict[str, float] = {}
    for p in parts:
        if p.matches:
            out[p.part_id] = float(np.mean([abs(m.signed_error_ms) for m in p.matches]))
        else:
            out[p.part_id] = float(p.mean_abs_error_ms)
    return out


def signed_timing_deviation_ms(parts: list[PartAnalysis]) -> dict[str, float]:
    """Mean signed score-matched error (positive = late vs score)."""
    return {
        p.part_id: float(p.mean_signed_error_ms)
        if p.matches
        else 0.0
        for p in parts
    }


def alignment_confidence_map(parts: list[PartAnalysis]) -> dict[str, float]:
    return {p.part_id: float(p.alignment_confidence) for p in parts}


def windowed_timing_deviation(
    parts: list[PartAnalysis],
    *,
    window_sec: float = 4.0,
) -> list[PartDeviationWindow]:
    duration = max((p.audio_duration for p in parts), default=0.0)
    windows: list[PartDeviationWindow] = []
    if duration <= 0:
        return windows

    for p in parts:
        for w0 in np.arange(0.0, duration, window_sec):
            w1 = w0 + window_sec
            ms = [m for m in p.matches if w0 <= m.onset_time < w1]
            if len(ms) < 2:
                continue
            signed = np.asarray([m.signed_error_ms for m in ms], dtype=np.float64)
            times = np.asarray([m.onset_time for m in ms], dtype=np.float64)
            # simple slope vs time → approx per-beat using score tempo 120 fallback
            if len(signed) >= 3:
                slope_per_sec = float(np.polyfit(times, signed, 1)[0])
                beat_dur = 0.5
                if p.states:
                    beat_dur = 60.0 / max(p.tempo_bpm, 1e-3)
                slope = slope_per_sec * beat_dur
            else:
                slope = 0.0
            mean_s = float(np.mean(signed))
            direction = "on_time" if abs(mean_s) < 25 else ("late" if mean_s > 0 else "early")
            windows.append(
                PartDeviationWindow(
                    part_id=p.part_id,
                    window_start=float(w0),
                    window_end=float(min(w1, duration)),
                    mean_abs_ms=float(np.mean(np.abs(signed))),
                    mean_signed_ms=mean_s,
                    slope_ms_per_beat=float(slope),
                    direction=direction,
                    n_matches=len(ms),
                )
            )
    return windows


def local_deviating_parts(
    parts: list[PartAnalysis],
    t: float,
    *,
    window_sec: float = 2.0,
    top_k: int = 2,
) -> list[str]:
    cfg = get_thresholds()
    scores: list[tuple[str, float]] = []
    for p in parts:
        errs = [
            abs(m.signed_error_ms)
            for m in p.matches
            if abs(m.onset_time - t) <= window_sec
        ]
        if not errs:
            continue
        mean_abs = float(np.mean(errs))
        if mean_abs >= cfg.deviation_significance_ms:
            scores.append((p.part_id, mean_abs))
    scores.sort(key=lambda x: x[1], reverse=True)
    return [pid for pid, _ in scores[:top_k]]
