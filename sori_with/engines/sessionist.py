"""P2 Adaptive Sessionist: score content → transport → scheduler → renderer actions.

Layers
------
1. Score content  — MIDI role notes, else pattern fallback on score grid
2. Transport      — cumulative tempo integration (score time → performance time)
3. Scheduler      — look-ahead note reservation with section-aware fills
4. Live control   — stateful tick with musical fail-safes (hold / phrase / reenter)
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sori_with.config import get_thresholds
from sori_with.midi.score import ScoreGraph
from sori_with.models.schemas import SessionistAction, SessionistMode

# ---------------------------------------------------------------------------
# 1) Score content
# ---------------------------------------------------------------------------

# (beat_in_bar 1-indexed, pitch, duration_beats) — used when MIDI has no role notes
_ROLE_PATTERN: dict[str, list[tuple[float, int, float]]] = {
    "drums": [
        (1.0, 36, 0.25),
        (2.0, 42, 0.25),
        (3.0, 38, 0.25),
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

_ROLE_PITCH_RANGE: dict[str, tuple[int, int]] = {
    "bass": (24, 50),
    "guitar": (40, 76),
    "keyboard": (48, 84),
    "vocal": (53, 81),
    "drums": (35, 81),  # GM percussion-ish; click scores often use 36/42
}


@dataclass(frozen=True)
class ScoreNote:
    score_time: float
    bar: int
    beat: float
    pitch: int
    duration_beats: float
    section_id: str
    velocity: int = 90
    source: str = "score"  # score | pattern


def extract_role_content(score: ScoreGraph, role: str) -> list[ScoreNote]:
    """Prefer MIDI events in the role pitch band; else expand pattern on the grid."""
    role = role if role in _ROLE_PATTERN else "bass"
    lo, hi = _ROLE_PITCH_RANGE.get(role, (0, 127))
    notes: list[ScoreNote] = []

    if score.events:
        # Estimate duration_beats from consecutive same-pitch gaps (crude)
        role_events = [
            e for e in score.events if e.pitch is not None and lo <= int(e.pitch) <= hi
        ]
        # Avoid treating the whole click-track as every instrument:
        # if almost all events match (shared click pitches), prefer pattern for non-drums.
        frac = len(role_events) / max(len(score.events), 1)
        use_score = len(role_events) >= 4 and (role == "drums" or frac < 0.85)

        if use_score:
            beat_dur = 60.0 / max(score.tempo_bpm, 1e-6)
            for i, ev in enumerate(role_events):
                if i + 1 < len(role_events):
                    gap_beats = (role_events[i + 1].time_sec - ev.time_sec) / beat_dur
                    dur = float(np.clip(gap_beats * 0.9, 0.2, 4.0))
                else:
                    dur = 0.5
                notes.append(
                    ScoreNote(
                        score_time=float(ev.time_sec),
                        bar=int(ev.bar),
                        beat=float(ev.beat),
                        pitch=int(ev.pitch),
                        duration_beats=dur,
                        section_id=ev.section_id,
                        velocity=100 if ev.is_downbeat else 85,
                        source="score",
                    )
                )
            return notes

    return _pattern_content(score, role)


def _pattern_content(score: ScoreGraph, role: str) -> list[ScoreNote]:
    pattern = _ROLE_PATTERN[role]
    beats_per_bar = score.time_signature[0]
    beat_dur = 60.0 / max(score.tempo_bpm, 1e-6)
    n_bars = max(1, int(score.duration_sec / (beat_dur * beats_per_bar)) + 1)
    notes: list[ScoreNote] = []
    for bar in range(1, n_bars + 1):
        t0 = (bar - 1) * beats_per_bar * beat_dur
        section = score.section_at(t0)
        for beat_pos, pitch, dur in pattern:
            if beat_pos > beats_per_bar + 1e-6:
                continue
            t_score = ((bar - 1) * beats_per_bar + (beat_pos - 1)) * beat_dur
            notes.append(
                ScoreNote(
                    score_time=float(t_score),
                    bar=bar,
                    beat=float(beat_pos),
                    pitch=pitch,
                    duration_beats=dur,
                    section_id=section,
                    velocity=100 if abs(beat_pos - 1.0) < 1e-6 else 80,
                    source="pattern",
                )
            )
    return notes


# ---------------------------------------------------------------------------
# 2) Transport — cumulative tempo integration
# ---------------------------------------------------------------------------


def _make_tempo_lookup(
    curve: list[tuple[float, float]] | None,
    fallback: float,
):
    if not curve:
        return lambda _t: fallback

    times = [float(c[0]) for c in curve]
    tempos = [float(c[1]) for c in curve]

    def lookup(t: float) -> float:
        if t <= times[0]:
            return tempos[0]
        if t >= times[-1]:
            return tempos[-1]
        for i in range(1, len(times)):
            if t <= times[i]:
                x0, x1 = times[i - 1], times[i]
                y0, y1 = tempos[i - 1], tempos[i]
                w = (t - x0) / max(x1 - x0, 1e-9)
                return y0 * (1 - w) + y1 * w
        return fallback

    return lookup


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


@dataclass
class TransportMap:
    """Maps score time → performance time via integrated local tempo."""

    score_grid: np.ndarray
    perf_grid: np.ndarray
    score_tempo_bpm: float

    def performance_time(self, score_time: float) -> float:
        if len(self.score_grid) < 2:
            return float(score_time)
        return float(np.interp(score_time, self.score_grid, self.perf_grid))

    def score_time(self, performance_time: float) -> float:
        if len(self.perf_grid) < 2:
            return float(performance_time)
        return float(np.interp(performance_time, self.perf_grid, self.score_grid))


def build_transport_map(
    score: ScoreGraph,
    user_tempo_curve: list[tuple[float, float]] | None,
    mode: SessionistMode,
    *,
    grid_step_sec: float = 0.05,
) -> TransportMap:
    cfg = get_thresholds()
    raw = _make_tempo_lookup(user_tempo_curve, score.tempo_bpm)
    duration = max(score.duration_sec, 1.0)
    grid = np.arange(0.0, duration + grid_step_sec, grid_step_sec, dtype=np.float64)
    perf = np.zeros_like(grid)
    prev_tempo: float | None = None
    for i in range(1, len(grid)):
        mid = 0.5 * (grid[i - 1] + grid[i])
        measured = float(np.clip(raw(mid), cfg.tempo_min_bpm, cfg.tempo_max_bpm))
        local = _tempo_smooth(prev_tempo, measured, mode)
        prev_tempo = local
        dt_score = float(grid[i] - grid[i - 1])
        # Faster local tempo → less performance time for the same score span
        perf[i] = perf[i - 1] + dt_score * (score.tempo_bpm / max(local, 1e-3))
    return TransportMap(score_grid=grid, perf_grid=perf, score_tempo_bpm=score.tempo_bpm)


def local_tempo_at(transport: TransportMap, score_time: float, mode: SessionistMode) -> float:
    # Infer from derivative of perf vs score
    eps = 0.05
    t0 = max(0.0, score_time - eps)
    t1 = score_time + eps
    dp = transport.performance_time(t1) - transport.performance_time(t0)
    ds = max(t1 - t0, 1e-9)
    # dp/ds = score_bpm / local_bpm  → local = score_bpm / (dp/ds)
    ratio = dp / ds
    if ratio <= 1e-9:
        return transport.score_tempo_bpm
    return float(transport.score_tempo_bpm / ratio)


# ---------------------------------------------------------------------------
# 3) Scheduler
# ---------------------------------------------------------------------------


def plan_sessionist_schedule(
    score: ScoreGraph,
    role: str,
    mode: SessionistMode = SessionistMode.FOLLOW,
    user_tempo_curve: list[tuple[float, float]] | None = None,
    confidence_floor: float | None = None,
) -> list[SessionistAction]:
    """
    Offline schedule: score content notes placed on the performance timeline
    via cumulative tempo transport.
    """
    cfg = get_thresholds()
    floor = (
        confidence_floor
        if confidence_floor is not None
        else getattr(cfg, "sessionist_confidence_floor", 0.45)
    )
    role = role if role in _ROLE_PATTERN else "bass"
    content = extract_role_content(score, role)
    transport = build_transport_map(score, user_tempo_curve, mode)
    beats_per_bar = score.time_signature[0]

    actions: list[SessionistAction] = []
    for note in content:
        t_perf = transport.performance_time(note.score_time)
        tempo = local_tempo_at(transport, note.score_time, mode)
        conf = 0.95 if note.source == "score" else 0.88
        action = "play"
        fill_type = None

        if mode == SessionistMode.ACCOMPANY and abs(note.beat - beats_per_bar) < 1e-6:
            if note.bar % 4 == 0:
                action = "fill"
                fill_type = "end_of_phrase"
                conf = 0.9

        if conf < floor:
            action = "hold"

        dynamics = 0.75 if "chorus" in (note.section_id or "") else 0.6
        actions.append(
            SessionistAction(
                timestamp=float(t_perf),
                role=role,  # type: ignore[arg-type]
                mode=mode,
                target_bar=note.bar,
                target_beat=note.beat,
                target_tempo=float(tempo),
                action=action,  # type: ignore[arg-type]
                pitch=note.pitch,
                velocity=note.velocity,
                duration_beats=note.duration_beats,
                dynamics=dynamics,
                fill_type=fill_type,
                confidence=conf,
                articulation=note.source,
            )
        )
    actions.sort(key=lambda a: (a.timestamp, a.target_bar, a.target_beat))
    return actions


def next_action_at(
    schedule: list[SessionistAction],
    timestamp: float,
) -> SessionistAction | None:
    upcoming = [a for a in schedule if a.timestamp >= timestamp - 1e-6]
    return upcoming[0] if upcoming else None


def schedule_lookahead(
    schedule: list[SessionistAction],
    timestamp: float,
    *,
    horizon_sec: float = 1.0,
) -> list[SessionistAction]:
    return [
        a
        for a in schedule
        if timestamp - 1e-6 <= a.timestamp <= timestamp + horizon_sec
        and a.action not in {"hold", "stop"}
    ]


# ---------------------------------------------------------------------------
# 4) Live controller + fail-safes
# ---------------------------------------------------------------------------


@dataclass
class LiveSessionistController:
    role: str
    mode: SessionistMode
    score: ScoreGraph | None = None
    content: list[ScoreNote] = field(default_factory=list)
    confidence_floor: float = 0.45
    _played: set[tuple[int, int, int]] = field(default_factory=set)
    _last_play: SessionistAction | None = None
    _low_conf_streak: int = 0
    _waiting_reenter: bool = False

    def ensure_content(self, score: ScoreGraph | None = None) -> None:
        if score is not None:
            self.score = score
        if self.score is not None and not self.content:
            self.content = extract_role_content(self.score, self.role)

    def tick(
        self,
        *,
        bar: int,
        beat: float,
        tempo: float,
        confidence: float,
        timestamp: float,
    ) -> SessionistAction:
        self.ensure_content()
        beats_per_bar = self.score.time_signature[0] if self.score else 4

        # --- fail-safe path ---
        if confidence < self.confidence_floor:
            self._low_conf_streak += 1
            return self._fail_safe(
                bar=bar,
                beat=beat,
                tempo=tempo,
                confidence=confidence,
                timestamp=timestamp,
                beats_per_bar=beats_per_bar,
            )

        # recovery after low confidence → reenter on next downbeat
        if self._waiting_reenter or self._low_conf_streak > 0:
            self._low_conf_streak = 0
            if abs(beat - 1.0) > 0.35:
                self._waiting_reenter = True
                return SessionistAction(
                    timestamp=timestamp,
                    role=self.role,  # type: ignore[arg-type]
                    mode=self.mode,
                    target_bar=bar,
                    target_beat=beat,
                    target_tempo=tempo,
                    action="hold",
                    confidence=confidence,
                    articulation="wait_safe_boundary",
                )
            self._waiting_reenter = False
            note = self._nearest_content_note(bar, 1.0)
            return SessionistAction(
                timestamp=timestamp,
                role=self.role,  # type: ignore[arg-type]
                mode=self.mode,
                target_bar=bar,
                target_beat=1.0,
                target_tempo=tempo,
                action="reenter",
                pitch=note.pitch if note else None,
                velocity=100,
                duration_beats=note.duration_beats if note else 0.5,
                confidence=confidence,
                articulation="reenter_downbeat",
            )

        # --- look-ahead: nearest unplayed content note near current beat ---
        candidates = [
            n
            for n in self.content
            if n.bar == bar and abs(n.beat - beat) <= 0.6
        ]
        if not candidates:
            candidates = [
                n
                for n in self.content
                if n.bar == bar + (1 if beat > beats_per_bar - 0.2 else 0)
                and abs(n.beat - ((beat % beats_per_bar) or beat)) <= 1.0
            ]
        if not candidates:
            note = self._nearest_content_note(bar, beat)
        else:
            note = min(candidates, key=lambda n: abs(n.beat - beat))

        key = (note.bar, int(round(note.beat * 4)), note.pitch) if note else None
        if note and key in self._played and abs(note.beat - beat) < 0.15:
            # already emitted this grid slot
            return SessionistAction(
                timestamp=timestamp,
                role=self.role,  # type: ignore[arg-type]
                mode=self.mode,
                target_bar=bar,
                target_beat=beat,
                target_tempo=tempo,
                action="hold",
                confidence=confidence,
                articulation="already_scheduled",
            )

        action = "play"
        fill_type = None
        if (
            self.mode == SessionistMode.ACCOMPANY
            and note
            and abs(note.beat - beats_per_bar) < 1e-6
        ):
            action = "fill"
            fill_type = "bar_end"

        result = SessionistAction(
            timestamp=timestamp,
            role=self.role,  # type: ignore[arg-type]
            mode=self.mode,
            target_bar=note.bar if note else bar,
            target_beat=note.beat if note else beat,
            target_tempo=tempo,
            action=action,  # type: ignore[arg-type]
            pitch=note.pitch if note else None,
            velocity=note.velocity if note else 90,
            duration_beats=note.duration_beats if note else 0.5,
            fill_type=fill_type,
            confidence=confidence,
            articulation=note.source if note else "pattern",
        )
        if key is not None:
            self._played.add(key)
        self._last_play = result
        return result

    def _nearest_content_note(self, bar: int, beat: float) -> ScoreNote | None:
        if not self.content:
            return None
        return min(
            self.content,
            key=lambda n: abs(n.bar - bar) * 10 + abs(n.beat - beat),
        )

    def _fail_safe(
        self,
        *,
        bar: int,
        beat: float,
        tempo: float,
        confidence: float,
        timestamp: float,
        beats_per_bar: int,
    ) -> SessionistAction:
        # Short dip: hold current phrase (no new attacks)
        if self._low_conf_streak <= 2:
            return SessionistAction(
                timestamp=timestamp,
                role=self.role,  # type: ignore[arg-type]
                mode=self.mode,
                target_bar=bar,
                target_beat=beat,
                target_tempo=tempo,
                action="hold",
                pitch=self._last_play.pitch if self._last_play else None,
                duration_beats=self._last_play.duration_beats if self._last_play else 0.5,
                confidence=confidence,
                articulation="maintain_phrase",
            )

        # Longer uncertainty: wait for bar boundary then soft repeat last downbeat idea
        if abs(beat - 1.0) < 0.35 and self._last_play and self._last_play.pitch is not None:
            self._waiting_reenter = True
            return SessionistAction(
                timestamp=timestamp,
                role=self.role,  # type: ignore[arg-type]
                mode=self.mode,
                target_bar=bar,
                target_beat=1.0,
                target_tempo=tempo,
                action="repeat",
                pitch=self._last_play.pitch,
                velocity=70,
                duration_beats=1.0,
                confidence=confidence,
                articulation="safe_boundary_repeat",
            )

        return SessionistAction(
            timestamp=timestamp,
            role=self.role,  # type: ignore[arg-type]
            mode=self.mode,
            target_bar=bar,
            target_beat=beat,
            target_tempo=tempo,
            action="hold",
            confidence=confidence,
            articulation="hold_until_boundary",
        )


_controllers: dict[str, LiveSessionistController] = {}


def clear_sessionist_controllers() -> None:
    _controllers.clear()


def get_live_controller(
    session_id: str,
    role: str,
    mode: SessionistMode,
    score: ScoreGraph | None = None,
) -> LiveSessionistController:
    cfg = get_thresholds()
    floor = getattr(cfg, "sessionist_confidence_floor", 0.45)
    key = f"{session_id}:{role}:{mode.value}"
    ctrl = _controllers.get(key)
    if ctrl is None:
        ctrl = LiveSessionistController(
            role=role,
            mode=mode,
            score=score,
            confidence_floor=float(floor),
        )
        ctrl.ensure_content(score)
        _controllers[key] = ctrl
    elif score is not None:
        ctrl.ensure_content(score)
    return ctrl


def control_from_live_tick(
    *,
    role: str,
    mode: SessionistMode,
    bar: int,
    beat: float,
    tempo: float,
    confidence: float,
    timestamp: float,
    session_id: str = "live",
    score: ScoreGraph | None = None,
) -> SessionistAction:
    """Realtime controller used by /live/tick and WebSocket."""
    ctrl = get_live_controller(session_id, role, mode, score=score)
    return ctrl.tick(
        bar=bar,
        beat=beat,
        tempo=tempo,
        confidence=confidence,
        timestamp=timestamp,
    )
