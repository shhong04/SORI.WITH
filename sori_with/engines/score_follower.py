"""Offline / online score following based on onset–score DTW alignment.

This is a first real alignment layer (not wall-clock → bar/beat).
It matches performance onsets to score beat/event times and yields signed
timing errors (positive = late).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

import numpy as np

from sori_with.midi.score import ScoreEvent, ScoreGraph, expected_beat_times
from sori_with.models.schemas import AlignmentStatus


@dataclass
class MatchedOnset:
    onset_time: float
    score_time: float
    score_event_index: int
    bar: int
    beat: float
    section_id: str
    signed_error_ms: float
    confidence: float
    alignment_status: AlignmentStatus = AlignmentStatus.ALIGNED


@dataclass
class ScoreFollowerState:
    """Snapshot used by online updates and offline batch results."""

    timestamp: float
    bar: int
    beat: float
    section_id: str
    score_time: float | None
    signed_error_ms: float | None
    confidence: float
    alignment_status: AlignmentStatus
    tempo_ratio: float = 1.0


@dataclass
class ScoreFollowerResult:
    matches: list[MatchedOnset] = field(default_factory=list)
    unmatched_onset_times: list[float] = field(default_factory=list)
    unmatched_score_indices: list[int] = field(default_factory=list)
    mean_abs_error_ms: float = 0.0
    mean_signed_error_ms: float = 0.0
    alignment_confidence: float = 0.0
    tempo_ratio: float = 1.0
    path: list[tuple[int, int]] = field(default_factory=list)


class ScoreFollower(Protocol):
    def initialize(self, score: ScoreGraph) -> None: ...

    def update(
        self,
        timestamp: float,
        *,
        onset_detected: bool = False,
        previous_state: ScoreFollowerState | None = None,
    ) -> ScoreFollowerState: ...


def score_reference_times(score: ScoreGraph) -> tuple[np.ndarray, list[ScoreEvent]]:
    """Prefer unique beat-grid times; fall back to MIDI note events."""
    if score.events:
        # Deduplicate near-identical times (chords)
        times: list[float] = []
        events: list[ScoreEvent] = []
        for ev in sorted(score.events, key=lambda e: e.time_sec):
            if times and abs(ev.time_sec - times[-1]) < 1e-3:
                continue
            times.append(float(ev.time_sec))
            events.append(ev)
        return np.asarray(times, dtype=np.float64), events

    beats = expected_beat_times(score)
    beat_dur = 60.0 / max(score.tempo_bpm, 1e-6)
    bpb = score.time_signature[0]
    events = []
    for i, t in enumerate(beats):
        bar = int(i // bpb) + 1
        beat = float(i % bpb) + 1.0
        events.append(
            ScoreEvent(
                time_sec=float(t),
                bar=bar,
                beat=beat,
                pitch=None,
                section_id=score.section_at(float(t)),
                is_downbeat=abs(beat - 1.0) < 1e-6,
            )
        )
    return beats.astype(np.float64), events


def estimate_tempo_ratio(onsets: np.ndarray, score_beat_dur: float) -> float:
    if len(onsets) < 3 or score_beat_dur <= 0:
        return 1.0
    iois = np.diff(onsets)
    iois = iois[(iois > score_beat_dur * 0.35) & (iois < score_beat_dur * 2.5)]
    if len(iois) == 0:
        return 1.0
    med = float(np.median(iois))
    ratio = med / score_beat_dur
    return float(np.clip(ratio, 0.7, 1.4))


def _dtw_path(
    onsets: np.ndarray,
    score_times: np.ndarray,
    *,
    skip_score_cost: float = 0.06,
    skip_onset_cost: float = 0.09,
) -> list[tuple[int, int]]:
    """Needleman–Wunsch style alignment with skips for rests / extra onsets."""
    n, m = len(onsets), len(score_times)
    if n == 0 or m == 0:
        return []

    inf = 1e18
    d = np.full((n + 1, m + 1), inf, dtype=np.float64)
    ptr = np.zeros((n + 1, m + 1), dtype=np.int8)  # 1=diag, 2=skip score, 3=skip onset
    d[0, 0] = 0.0
    for j in range(m):
        d[0, j + 1] = d[0, j] + skip_score_cost
        ptr[0, j + 1] = 2
    for i in range(n):
        d[i + 1, 0] = d[i, 0] + skip_onset_cost
        ptr[i + 1, 0] = 3

    for i in range(n):
        for j in range(m):
            match = d[i, j] + abs(float(onsets[i]) - float(score_times[j]))
            skip_s = d[i + 1, j] + skip_score_cost
            skip_o = d[i, j + 1] + skip_onset_cost
            best = match
            p = 1
            if skip_s < best:
                best = skip_s
                p = 2
            if skip_o < best:
                best = skip_o
                p = 3
            d[i + 1, j + 1] = best
            ptr[i + 1, j + 1] = p

    # backtrack
    i, j = n, m
    path: list[tuple[int, int]] = []
    while i > 0 or j > 0:
        p = int(ptr[i, j])
        if p == 1 and i > 0 and j > 0:
            path.append((i - 1, j - 1))
            i -= 1
            j -= 1
        elif p == 2 and j > 0:
            j -= 1
        elif p == 3 and i > 0:
            i -= 1
        else:
            break
    path.reverse()
    return path


def follow_score_offline(
    onset_times: np.ndarray | list[float],
    score: ScoreGraph,
    *,
    max_match_sec: float = 0.25,
) -> ScoreFollowerResult:
    """
    Align performance onsets to score reference times.

    Signed error = (onset_time - score_time) * 1000
    → positive means the performer is late relative to the score event.
    """
    onsets = np.asarray(onset_times, dtype=np.float64)
    onsets = onsets[np.isfinite(onsets)]
    onsets = np.unique(np.round(onsets, 6))
    score_times, score_events = score_reference_times(score)
    if len(onsets) == 0 or len(score_times) == 0:
        return ScoreFollowerResult(alignment_confidence=0.0)

    beat_dur = 60.0 / max(score.tempo_bpm, 1e-6)
    tempo_ratio = estimate_tempo_ratio(onsets, beat_dur)
    # Warp score times into performance time base: t_perf ≈ t_score * tempo_ratio
    warped = score_times * tempo_ratio

    path = _dtw_path(onsets, warped)
    matches: list[MatchedOnset] = []
    used_onsets: set[int] = set()
    used_score: set[int] = set()

    for oi, sj in path:
        err_sec = float(onsets[oi]) - float(warped[sj])
        if abs(err_sec) > max_match_sec:
            continue
        ev = score_events[sj]
        # confidence: closer match + path support
        conf = float(np.clip(1.0 - abs(err_sec) / max_match_sec, 0.05, 1.0))
        status = AlignmentStatus.ALIGNED
        if conf < 0.35:
            status = AlignmentStatus.UNCERTAIN
        matches.append(
            MatchedOnset(
                onset_time=float(onsets[oi]),
                score_time=float(score_times[sj]),
                score_event_index=int(sj),
                bar=int(ev.bar),
                beat=float(ev.beat),
                section_id=ev.section_id,
                signed_error_ms=err_sec * 1000.0,
                confidence=conf,
                alignment_status=status,
            )
        )
        used_onsets.add(oi)
        used_score.add(sj)

    unmatched_onsets = [float(onsets[i]) for i in range(len(onsets)) if i not in used_onsets]
    unmatched_score = [i for i in range(len(score_times)) if i not in used_score]

    if matches:
        abs_err = float(np.mean([abs(m.signed_error_ms) for m in matches]))
        signed = float(np.mean([m.signed_error_ms for m in matches]))
        match_ratio = len(matches) / max(len(score_times), 1)
        mean_conf = float(np.mean([m.confidence for m in matches]))
        alignment_confidence = float(np.clip(0.5 * match_ratio + 0.5 * mean_conf, 0.0, 1.0))
    else:
        abs_err = 0.0
        signed = 0.0
        alignment_confidence = 0.0

    return ScoreFollowerResult(
        matches=matches,
        unmatched_onset_times=unmatched_onsets,
        unmatched_score_indices=unmatched_score,
        mean_abs_error_ms=abs_err,
        mean_signed_error_ms=signed,
        alignment_confidence=alignment_confidence,
        tempo_ratio=tempo_ratio,
        path=path,
    )


class OnlineScoreFollower:
    """
    Lightweight online wrapper: buffers recent onsets and re-runs offline DTW
    on a sliding window (good enough for live tick prototyping).
    """

    def __init__(self, window_sec: float = 8.0) -> None:
        self.score: ScoreGraph | None = None
        self.window_sec = window_sec
        self._onsets: list[float] = []
        self._last_result = ScoreFollowerResult()

    def initialize(self, score: ScoreGraph) -> None:
        self.score = score
        self._onsets.clear()
        self._last_result = ScoreFollowerResult()

    def update(
        self,
        timestamp: float,
        *,
        onset_detected: bool = False,
        previous_state: ScoreFollowerState | None = None,
    ) -> ScoreFollowerState:
        if self.score is None:
            raise RuntimeError("OnlineScoreFollower.initialize(score) required")
        if onset_detected:
            self._onsets.append(float(timestamp))
            # keep window
            self._onsets = [t for t in self._onsets if timestamp - t <= self.window_sec]
            self._last_result = follow_score_offline(np.asarray(self._onsets), self.score)

        # pick best match near timestamp
        near = [
            m
            for m in self._last_result.matches
            if abs(m.onset_time - timestamp) < 0.35
        ]
        if near:
            m = min(near, key=lambda x: abs(x.onset_time - timestamp))
            return ScoreFollowerState(
                timestamp=timestamp,
                bar=m.bar,
                beat=m.beat,
                section_id=m.section_id,
                score_time=m.score_time,
                signed_error_ms=m.signed_error_ms,
                confidence=m.confidence * self._last_result.alignment_confidence,
                alignment_status=m.alignment_status,
                tempo_ratio=self._last_result.tempo_ratio,
            )

        # fallback: warped grid projection with low confidence
        ratio = self._last_result.tempo_ratio or 1.0
        score_t = timestamp / max(ratio, 1e-6)
        bar, beat = self.score.bar_beat_at(score_t)
        return ScoreFollowerState(
            timestamp=timestamp,
            bar=bar,
            beat=beat,
            section_id=self.score.section_at(score_t),
            score_time=score_t,
            signed_error_ms=None,
            confidence=0.2,
            alignment_status=AlignmentStatus.LOST
            if not self._last_result.matches
            else AlignmentStatus.UNCERTAIN,
            tempo_ratio=ratio,
        )
