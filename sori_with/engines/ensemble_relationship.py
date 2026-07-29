from __future__ import annotations

import itertools

import numpy as np

from sori_with.config import get_thresholds
from sori_with.engines.part_understanding import PartAnalysis
from sori_with.models.schemas import EnsembleRelation, RelationType


def estimate_relations(parts: list[PartAnalysis]) -> list[EnsembleRelation]:
    """Estimate probable lead/follow relations from onset lag correlations."""
    cfg = get_thresholds()
    relations: list[EnsembleRelation] = []
    if len(parts) < 2:
        return relations

    for a, b in itertools.permutations(parts, 2):
        if len(a.onset_times) < 3 or len(b.onset_times) < 3:
            continue
        lags: list[float] = []
        for t in a.onset_times:
            j = int(np.argmin(np.abs(b.onset_times - t)))
            lag_ms = (float(b.onset_times[j]) - float(t)) * 1000.0
            if abs(lag_ms) <= cfg.propagation_lag_window_ms:
                lags.append(lag_ms)
        if len(lags) < 3:
            continue
        mean_lag = float(np.mean(lags))
        strength = float(np.clip(1.0 - np.std(lags) / 100.0, 0.0, 1.0))
        conf = float(np.clip(len(lags) / max(len(a.onset_times), 1), 0.0, 1.0))

        if abs(mean_lag) < cfg.deviation_significance_ms * 0.5:
            rel = RelationType.MAINTAINS_REFERENCE
        elif mean_lag > 0:
            # b is later than a -> a leads, b follows
            rel = RelationType.LEADS
        else:
            rel = RelationType.FOLLOWS

        relations.append(
            EnsembleRelation(
                source_part_id=a.part_id,
                target_part_id=b.part_id,
                relation_type=rel,
                start_timestamp=float(min(a.onset_times[0], b.onset_times[0])),
                end_timestamp=float(max(a.onset_times[-1], b.onset_times[-1])),
                lag_ms=mean_lag,
                strength=strength,
                confidence=conf,
            )
        )
    return relations


def timing_deviation_ms(
    parts: list[PartAnalysis],
    reference_part_id: str | None,
) -> dict[str, float]:
    if not parts:
        return {}
    ref = None
    if reference_part_id:
        ref = next((p for p in parts if p.part_id == reference_part_id), None)
    if ref is None:
        # prefer drums/bass
        for name in ("drums", "bass"):
            ref = next((p for p in parts if p.instrument == name), None)
            if ref is not None:
                break
    if ref is None:
        ref = parts[0]

    out: dict[str, float] = {}
    for p in parts:
        if p.part_id == ref.part_id or len(p.onset_times) == 0 or len(ref.onset_times) == 0:
            out[p.part_id] = 0.0
            continue
        lags = []
        for t in p.onset_times:
            j = int(np.argmin(np.abs(ref.onset_times - t)))
            lags.append((float(t) - float(ref.onset_times[j])) * 1000.0)
        out[p.part_id] = float(np.mean(np.abs(lags))) if lags else 0.0
    return out
