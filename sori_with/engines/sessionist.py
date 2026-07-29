from __future__ import annotations

from sori_with.midi.score import ScoreGraph
from sori_with.models.schemas import SessionistAction, SessionistMode


# Simple role patterns relative to bar grid (MIDI pitch templates)
_ROLE_PATTERN: dict[str, list[tuple[float, int, float]]] = {
    # (beat_in_bar 1-indexed, pitch, duration_beats)
    "drums": [
        (1.0, 36, 0.25),  # kick
        (2.0, 42, 0.25),  # hat
        (3.0, 38, 0.25),  # snare
        (4.0, 42, 0.25),
    ],
    "bass": [
        (1.0, 36, 1.0),
        (3.0, 43, 1.0),
    ],
    "keyboard": [
        (1.0, 60, 2.0),
        (3.0, 67, 2.0),
    ],
    "guitar": [
        (1.0, 52, 1.0),
        (2.0, 52, 1.0),
        (3.0, 59, 1.0),
        (4.0, 59, 1.0),
    ],
    "vocal": [
        (1.0, 64, 2.0),
    ],
}


def _tempo_smooth(prev: float | None, measured: float, mode: SessionistMode) -> float:
    if prev is None:
        return measured
    if mode == SessionistMode.FOLLOW:
        alpha = 0.65
    elif mode == SessionistMode.ACCOMPANY:
        alpha = 0.45
    elif mode == SessionistMode.LEAD:
        alpha = 0.15
    else:
        alpha = 0.5
    return prev * (1 - alpha) + measured * alpha


def plan_sessionist_schedule(
    score: ScoreGraph,
    role: str,
    mode: SessionistMode = SessionistMode.FOLLOW,
    user_tempo_curve: list[tuple[float, float]] | None = None,
    confidence_floor: float = 0.45,
) -> list[SessionistAction]:
    """
    Build a MIDI-like action schedule for one AI Sessionist role.

    user_tempo_curve: optional list of (time_sec, tempo_bpm) from the human player.
    If confidence would be low / no user tempo, hold score tempo (safe fallback).
    """
    role = role if role in _ROLE_PATTERN else "bass"
    pattern = _ROLE_PATTERN[role]
    beats_per_bar = score.time_signature[0]
    beat_dur_score = 60.0 / score.tempo_bpm
    n_bars = max(1, int(score.duration_sec / (beat_dur_score * beats_per_bar)) + 1)

    tempo_fn = _make_tempo_lookup(user_tempo_curve, score.tempo_bpm)
    actions: list[SessionistAction] = []
    prev_tempo: float | None = None

    for bar in range(1, n_bars + 1):
        section = "chorus" if bar > n_bars // 2 else "verse"
        for beat_pos, pitch, dur in pattern:
            # nominal time from score grid
            t_score = ((bar - 1) * beats_per_bar + (beat_pos - 1)) * beat_dur_score
            measured = tempo_fn(t_score)
            target_tempo = _tempo_smooth(prev_tempo, measured, mode)
            prev_tempo = target_tempo

            # Adaptive timing: stretch schedule by local tempo vs score tempo
            stretch = score.tempo_bpm / max(target_tempo, 1e-3)
            t = t_score * stretch

            conf = 0.95
            action = "play"
            fill_type = None
            if mode == SessionistMode.ACCOMPANY and beat_pos == beats_per_bar and bar % 4 == 0:
                action = "fill"
                fill_type = "end_of_phrase"
                conf = 0.9
            if conf < confidence_floor:
                action = "hold"

            actions.append(
                SessionistAction(
                    timestamp=float(t),
                    role=role,  # type: ignore[arg-type]
                    mode=mode,
                    target_bar=bar,
                    target_beat=float(beat_pos),
                    target_tempo=float(target_tempo),
                    action=action,  # type: ignore[arg-type]
                    pitch=pitch,
                    velocity=100 if beat_pos == 1.0 else 80,
                    duration_beats=dur,
                    dynamics=0.75 if section == "chorus" else 0.6,
                    fill_type=fill_type,
                    confidence=conf,
                )
            )
    return actions


def next_action_at(
    schedule: list[SessionistAction],
    timestamp: float,
) -> SessionistAction | None:
    upcoming = [a for a in schedule if a.timestamp >= timestamp - 1e-6]
    return upcoming[0] if upcoming else None


def control_from_live_tick(
    *,
    role: str,
    mode: SessionistMode,
    bar: int,
    beat: float,
    tempo: float,
    confidence: float,
    timestamp: float,
) -> SessionistAction:
    """Realtime single-step controller used by /live/tick and WebSocket."""
    if confidence < 0.45:
        return SessionistAction(
            timestamp=timestamp,
            role=role,  # type: ignore[arg-type]
            mode=mode,
            target_bar=bar,
            target_beat=beat,
            target_tempo=tempo,
            action="hold",
            confidence=confidence,
        )

    pattern = _ROLE_PATTERN.get(role, _ROLE_PATTERN["bass"])
    # pick nearest pattern beat
    nearest = min(pattern, key=lambda x: abs(x[0] - beat))
    action = "play"
    fill_type = None
    if mode == SessionistMode.ACCOMPANY and abs(nearest[0] - 4.0) < 1e-6:
        action = "fill"
        fill_type = "bar_end"

    return SessionistAction(
        timestamp=timestamp,
        role=role,  # type: ignore[arg-type]
        mode=mode,
        target_bar=bar,
        target_beat=beat,
        target_tempo=tempo,
        action=action,  # type: ignore[arg-type]
        pitch=nearest[1],
        velocity=95,
        duration_beats=nearest[2],
        fill_type=fill_type,
        confidence=confidence,
    )


def _make_tempo_lookup(
    curve: list[tuple[float, float]] | None,
    fallback: float,
):
    if not curve:
        return lambda _t: fallback

    times = [c[0] for c in curve]
    tempos = [c[1] for c in curve]

    def lookup(t: float) -> float:
        if t <= times[0]:
            return tempos[0]
        if t >= times[-1]:
            return tempos[-1]
        # linear interpolate
        for i in range(1, len(times)):
            if t <= times[i]:
                x0, x1 = times[i - 1], times[i]
                y0, y1 = tempos[i - 1], tempos[i]
                w = (t - x0) / max(x1 - x0, 1e-9)
                return y0 * (1 - w) + y1 * w
        return fallback

    return lookup
