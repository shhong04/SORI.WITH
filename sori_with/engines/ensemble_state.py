from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from sori_with.config import get_thresholds
from sori_with.engines.ensemble_clock import estimate_ensemble_clock
from sori_with.engines.ensemble_relationship import estimate_relations, timing_deviation_ms
from sori_with.engines.part_understanding import PartAnalysis
from sori_with.models.schemas import (
    EnsembleEvent,
    EnsembleState,
    EnsembleStateLabel,
)


def _spread_at(
    parts: list[PartAnalysis],
    t: float,
    window: float = 0.35,
) -> tuple[float, float, list[str]]:
    """Return timing_spread_ms, tempo_variance, active part ids near t."""
    onsets_near: list[float] = []
    tempos: list[float] = []
    active: list[str] = []
    for p in parts:
        if len(p.onset_times) == 0:
            continue
        mask = np.abs(p.onset_times - t) <= window
        if not np.any(mask):
            continue
        active.append(p.part_id)
        local = p.onset_times[mask]
        onsets_near.extend(local.tolist())
        idx = int(np.argmin(np.abs(p.onset_times - t)))
        tempos.append(float(p.tempo_curve[idx]) if idx < len(p.tempo_curve) else p.tempo_bpm)
    if len(onsets_near) < 2:
        return 0.0, 0.0, active
    # relative to median onset in window
    med = float(np.median(onsets_near))
    spread = float(np.std([(o - med) * 1000.0 for o in onsets_near]))
    tvar = float(np.var(tempos)) if len(tempos) > 1 else 0.0
    return spread, tvar, active


def build_state_timeline(
    parts: list[PartAnalysis],
    clocks: list | None = None,
) -> list[EnsembleState]:
    cfg = get_thresholds()
    clocks = clocks or estimate_ensemble_clock(parts)
    timeline: list[EnsembleState] = []
    deviations = timing_deviation_ms(parts, None)
    ranked = sorted(deviations.items(), key=lambda kv: kv[1], reverse=True)

    for clock in clocks:
        spread, tvar, active = _spread_at(parts, clock.timestamp)
        if spread >= cfg.breakdown_timing_spread_ms:
            label = EnsembleStateLabel.BREAKDOWN
            risk = 0.9
            recovery_p = 0.2
        elif spread >= cfg.drift_timing_spread_ms:
            label = EnsembleStateLabel.DRIFT
            risk = 0.55
            recovery_p = 0.45
        elif spread >= cfg.stable_timing_spread_ms:
            label = EnsembleStateLabel.DRIFT
            risk = 0.35
            recovery_p = 0.6
        else:
            label = EnsembleStateLabel.STABLE
            risk = 0.1
            recovery_p = 0.85

        leaders = [clock.reference_part_id] if clock.reference_part_id else []
        followers = [p for p in active if p not in leaders]
        deviating = [pid for pid, d in ranked if d >= cfg.deviation_significance_ms][:2]

        timeline.append(
            EnsembleState(
                timestamp=clock.timestamp,
                state=label,
                ensemble_clock=clock,
                leader_part_ids=[x for x in leaders if x],
                follower_part_ids=followers,
                deviating_part_ids=deviating,
                timing_spread_ms=spread,
                tempo_variance=tvar,
                score_position_spread=spread / 50.0,
                breakdown_risk=risk,
                natural_recovery_probability=recovery_p,
                confidence=clock.stability,
            )
        )

    # Mark recovery segments: breakdown/drift -> improving spread
    for i in range(1, len(timeline)):
        prev, cur = timeline[i - 1], timeline[i]
        if (
            prev.state in {EnsembleStateLabel.BREAKDOWN, EnsembleStateLabel.DRIFT}
            and cur.timing_spread_ms < prev.timing_spread_ms * 0.7
            and cur.timing_spread_ms < cfg.drift_timing_spread_ms
        ):
            cur.state = EnsembleStateLabel.RECOVERY
    return timeline


def detect_breakdown_recovery(
    timeline: list[EnsembleState],
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    breakdown = None
    recovery = None
    for st in timeline:
        if breakdown is None and st.state == EnsembleStateLabel.BREAKDOWN:
            breakdown = {
                "bar": st.ensemble_clock.bar,
                "beat": st.ensemble_clock.beat,
                "timestamp": st.timestamp,
                "timing_spread_ms": st.timing_spread_ms,
                "deviating_part_ids": st.deviating_part_ids,
            }
        if breakdown is not None and recovery is None and st.state == EnsembleStateLabel.RECOVERY:
            recovery = {
                "bar": st.ensemble_clock.bar,
                "beat": st.ensemble_clock.beat,
                "timestamp": st.timestamp,
                "reference_part": (
                    st.leader_part_ids[0] if st.leader_part_ids else st.ensemble_clock.reference_part_id
                ),
            }
            break
    return breakdown, recovery


def build_events(
    session_id: str,
    parts: list[PartAnalysis],
    timeline: list[EnsembleState],
    relations: list,
) -> list[EnsembleEvent]:
    events: list[EnsembleEvent] = []
    cfg = get_thresholds()
    deviations = timing_deviation_ms(parts, None)

    # First significant deviation event
    if deviations:
        source = max(deviations.items(), key=lambda kv: kv[1])
        if source[1] >= cfg.deviation_significance_ms:
            # find first drift/breakdown state
            st = next(
                (s for s in timeline if s.state in {EnsembleStateLabel.DRIFT, EnsembleStateLabel.BREAKDOWN}),
                timeline[0] if timeline else None,
            )
            if st:
                events.append(
                    EnsembleEvent(
                        event_id=f"event_{uuid.uuid4().hex[:8]}",
                        session_id=session_id,
                        type="tempo_drift" if st.state == EnsembleStateLabel.DRIFT else "breakdown",
                        start_time=st.timestamp,
                        end_time=None,
                        start_bar=st.ensemble_clock.bar,
                        start_beat=st.ensemble_clock.beat,
                        involved_part_ids=st.deviating_part_ids or [source[0]],
                        probable_source_part_id=source[0],
                        reference_part_id=st.ensemble_clock.reference_part_id,
                        severity=min(1.0, source[1] / 200.0),
                        confidence=0.7,
                        evidence=[
                            {
                                "part_timing_deviation_ms": deviations,
                                "timing_spread_ms": st.timing_spread_ms,
                            }
                        ],
                    )
                )

    bd, rc = detect_breakdown_recovery(timeline)
    if bd:
        events.append(
            EnsembleEvent(
                event_id=f"event_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                type="breakdown",
                start_time=bd["timestamp"],
                start_bar=bd["bar"],
                start_beat=bd["beat"],
                involved_part_ids=bd.get("deviating_part_ids") or [],
                probable_source_part_id=(bd.get("deviating_part_ids") or [None])[0],
                severity=0.85,
                confidence=0.75,
                evidence=[bd],
            )
        )
    if rc:
        events.append(
            EnsembleEvent(
                event_id=f"event_{uuid.uuid4().hex[:8]}",
                session_id=session_id,
                type="recovery",
                start_time=rc["timestamp"],
                start_bar=rc["bar"],
                start_beat=rc["beat"],
                involved_part_ids=[rc["reference_part"]] if rc.get("reference_part") else [],
                reference_part_id=rc.get("reference_part"),
                severity=0.2,
                confidence=0.7,
                evidence=[rc],
            )
        )
    return events
