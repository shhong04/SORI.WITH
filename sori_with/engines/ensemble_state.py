from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from sori_with.config import get_thresholds
from sori_with.engines.ensemble_clock import estimate_ensemble_clock
from sori_with.engines.ensemble_relationship import (
    local_deviating_parts,
    timing_deviation_ms,
)
from sori_with.engines.part_understanding import PartAnalysis
from sori_with.models.schemas import (
    EnsembleEvent,
    EnsembleState,
    EnsembleStateLabel,
)


def _score_matched_spread_ms(
    parts: list[PartAnalysis],
    t: float,
    window: float = 0.6,
) -> tuple[float, float, list[str]]:
    """
    Spread of score-matched signed errors near t (beat-phase sync),
    plus tempo variance and active part ids.
    """
    errors: list[float] = []
    tempos: list[float] = []
    active: list[str] = []
    for p in parts:
        near = [m for m in p.matches if abs(m.onset_time - t) <= window]
        if near:
            active.append(p.part_id)
            errors.extend(m.signed_error_ms for m in near)
            tempos.append(p.tempo_bpm)
            continue
        # fallback: raw onsets (less reliable)
        if len(p.onset_times) == 0:
            continue
        mask = np.abs(p.onset_times - t) <= window
        if not np.any(mask):
            continue
        active.append(p.part_id)
        med = float(np.median(p.onset_times[mask]))
        errors.append((med - t) * 1000.0)
        idx = int(np.argmin(np.abs(p.onset_times - t)))
        tempos.append(float(p.tempo_curve[idx]) if idx < len(p.tempo_curve) else p.tempo_bpm)

    if len(errors) < 2:
        return 0.0, 0.0, active
    # Relative sync: std of signed errors across parts
    spread = float(np.std(errors))
    tvar = float(np.var(tempos)) if len(tempos) > 1 else 0.0
    return spread, tvar, active


def _apply_hysteresis(
    raw_labels: list[EnsembleStateLabel],
    spreads: list[float],
    *,
    min_hold: int = 2,
) -> list[EnsembleStateLabel]:
    """Require min_hold consecutive raw labels before switching (except recovery)."""
    if not raw_labels:
        return []
    out: list[EnsembleStateLabel] = [raw_labels[0]]
    pending = raw_labels[0]
    hold = 1
    for i in range(1, len(raw_labels)):
        lab = raw_labels[i]
        if lab == out[-1]:
            pending = lab
            hold = 1
            out.append(lab)
            continue
        if lab == pending:
            hold += 1
        else:
            pending = lab
            hold = 1
        if hold >= min_hold or lab == EnsembleStateLabel.RECOVERY:
            out.append(lab)
            hold = 1
        else:
            out.append(out[-1])
    # Recovery: improving spread after drift/breakdown
    cfg = get_thresholds()
    for i in range(1, len(out)):
        if (
            out[i - 1] in {EnsembleStateLabel.BREAKDOWN, EnsembleStateLabel.DRIFT}
            and spreads[i] < spreads[i - 1] * 0.7
            and spreads[i] < cfg.drift_timing_spread_ms
            and out[i] != EnsembleStateLabel.BREAKDOWN
        ):
            # need one more improving sample if possible
            if i + 1 < len(spreads) and spreads[i + 1] <= spreads[i] * 1.05:
                out[i] = EnsembleStateLabel.RECOVERY
            elif i + 1 >= len(spreads):
                out[i] = EnsembleStateLabel.RECOVERY
    return out


def build_state_timeline(
    parts: list[PartAnalysis],
    clocks: list | None = None,
) -> list[EnsembleState]:
    cfg = get_thresholds()
    clocks = clocks or estimate_ensemble_clock(parts)
    timeline: list[EnsembleState] = []
    raw_labels: list[EnsembleStateLabel] = []
    spreads: list[float] = []
    drafts: list[dict[str, Any]] = []

    for clock in clocks:
        spread, tvar, active = _score_matched_spread_ms(parts, clock.timestamp)
        spreads.append(spread)
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
        raw_labels.append(label)

        leaders = [clock.reference_part_id] if clock.reference_part_id else []
        followers = [p for p in active if p not in leaders]
        # score-position spread: disagreement of matched score times near now
        score_pos_spread = 0.0
        score_times = []
        for p in parts:
            near = [m for m in p.matches if abs(m.onset_time - clock.timestamp) <= 0.6]
            if near:
                score_times.append(min(near, key=lambda m: abs(m.onset_time - clock.timestamp)).score_time)
        if len(score_times) >= 2:
            score_pos_spread = float(np.std(score_times) / max(60.0 / clock.tempo, 1e-3))

        drafts.append(
            {
                "spread": spread,
                "tvar": tvar,
                "active": active,
                "leaders": [x for x in leaders if x],
                "followers": followers,
                "risk": risk,
                "recovery_p": recovery_p,
                "score_pos_spread": score_pos_spread,
                "clock": clock,
            }
        )

    labels = _apply_hysteresis(raw_labels, spreads, min_hold=max(2, int(cfg.min_state_duration_beats)))

    for lab, draft in zip(labels, drafts, strict=True):
        clock = draft["clock"]
        timeline.append(
            EnsembleState(
                timestamp=clock.timestamp,
                state=lab,
                ensemble_clock=clock,
                leader_part_ids=draft["leaders"],
                follower_part_ids=draft["followers"],
                deviating_part_ids=local_deviating_parts(parts, clock.timestamp),
                timing_spread_ms=draft["spread"],
                tempo_variance=draft["tvar"],
                score_position_spread=draft["score_pos_spread"],
                breakdown_risk=draft["risk"],
                natural_recovery_probability=draft["recovery_p"],
                confidence=clock.stability,
            )
        )
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

    if deviations:
        source = max(deviations.items(), key=lambda kv: kv[1])
        if source[1] >= cfg.deviation_significance_ms:
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
                                "alignment": {
                                    p.part_id: {
                                        "mean_signed_ms": p.mean_signed_error_ms,
                                        "confidence": p.alignment_confidence,
                                    }
                                    for p in parts
                                },
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
