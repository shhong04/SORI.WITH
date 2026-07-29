from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field

from sori_with.config import get_thresholds
from sori_with.models.schemas import (
    CoachingEvent,
    EnsembleEvent,
    EnsembleState,
    EnsembleStateLabel,
)


@dataclass
class CoachingPolicyState:
    last_feedback_at: float = -1e9
    cooldown_sec: float = 4.0
    history: list[CoachingEvent] = field(default_factory=list)


def decide_coaching(
    *,
    ensemble_state: EnsembleState,
    events: list[EnsembleEvent] | None = None,
    policy: CoachingPolicyState | None = None,
    now: float | None = None,
) -> CoachingEvent | None:
    """
    Rule-based coaching:
    - only when drift/breakdown and natural recovery is unlikely
    - cooldown between messages
    - actionable [state] + [reference] + [when]
    """
    cfg = get_thresholds()
    policy = policy or CoachingPolicyState()
    now = now if now is not None else time.time()

    if now - policy.last_feedback_at < policy.cooldown_sec:
        return None

    state = ensemble_state.state
    if state == EnsembleStateLabel.STABLE:
        return None
    if ensemble_state.confidence < 0.4:
        return None
    if (
        state == EnsembleStateLabel.DRIFT
        and ensemble_state.natural_recovery_probability > 0.7
        and ensemble_state.timing_spread_ms < cfg.drift_timing_spread_ms * 1.2
    ):
        return None

    reference = (
        ensemble_state.leader_part_ids[0]
        if ensemble_state.leader_part_ids
        else ensemble_state.ensemble_clock.reference_part_id
        or "drums"
    )
    targets = ensemble_state.deviating_part_ids or [
        p for p in ensemble_state.follower_part_ids if p != reference
    ]
    if not targets:
        targets = ["team"]

    if state == EnsembleStateLabel.BREAKDOWN:
        priority = 0
        message = (
            f"합주 위치가 갈라지고 있습니다. "
            f"다음 마디 첫 박에서 {reference}를 기준으로 맞춰주세요."
        )
        timing = "next_bar"
    elif state == EnsembleStateLabel.RECOVERY:
        priority = 2
        message = f"회복 중입니다. {reference}의 강박을 기준으로 유지해주세요."
        timing = "next_beat"
    else:  # DRIFT
        priority = 1
        who = ", ".join(targets[:2])
        message = (
            f"{who}와 리듬 섹션 간격이 커지고 있습니다. "
            f"다음 마디 첫 박에서 {reference}를 기준으로 맞춰주세요."
        )
        timing = "next_bar"

    source_id = events[-1].event_id if events else None
    event = CoachingEvent(
        coaching_event_id=f"coach_{uuid.uuid4().hex[:8]}",
        source_ensemble_event_id=source_id,
        target_part_ids=targets[:3],
        delivery_target="team",
        delivery_timing=timing,  # type: ignore[arg-type]
        message=message,
        priority=priority,
        confidence=float(ensemble_state.confidence),
        evidence={
            "state": state.value,
            "timing_spread_ms": ensemble_state.timing_spread_ms,
            "breakdown_risk": ensemble_state.breakdown_risk,
            "reference_part": reference,
            "bar": ensemble_state.ensemble_clock.bar,
            "beat": ensemble_state.ensemble_clock.beat,
        },
        delivered_at=now,
    )
    policy.last_feedback_at = now
    policy.history.append(event)
    return event
