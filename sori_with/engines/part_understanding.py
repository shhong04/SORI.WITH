from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from sori_with.audio.processing import detect_onsets, estimate_tempo_curve, load_mono
from sori_with.config import get_thresholds
from sori_with.engines.score_follower import MatchedOnset, ScoreFollowerResult, follow_score_offline
from sori_with.midi.score import ScoreGraph
from sori_with.models.schemas import (
    AlignmentStatus,
    PartConfidence,
    PartState,
    ScorePosition,
)


@dataclass
class PartAnalysis:
    part_id: str
    instrument: str
    onset_times: np.ndarray
    tempo_bpm: float
    tempo_curve: np.ndarray
    states: list[PartState]
    audio_duration: float
    matches: list[MatchedOnset] = field(default_factory=list)
    alignment: ScoreFollowerResult | None = None
    alignment_confidence: float = 0.0
    mean_signed_error_ms: float = 0.0
    mean_abs_error_ms: float = 0.0


def analyze_part(
    session_id: str,
    part_id: str,
    instrument: str,
    wav_path: str,
    score: ScoreGraph,
) -> PartAnalysis:
    cfg = get_thresholds()
    audio, sr = load_mono(wav_path, target_sr=cfg.sample_rate)
    onsets = detect_onsets(audio, sr, cfg)
    tempo_bpm, tempo_curve = estimate_tempo_curve(onsets, cfg)

    alignment = follow_score_offline(onsets, score)
    # Prefer score-informed tempo when onset IOI tempo is unreliable
    if abs(tempo_bpm - score.tempo_bpm) > 25:
        tempo_bpm = score.tempo_bpm * alignment.tempo_ratio
        tempo_curve = np.full(max(len(onsets), 1), tempo_bpm)

    match_by_idx: dict[int, MatchedOnset] = {}
    if len(onsets):
        for m in alignment.matches:
            idx = int(np.argmin(np.abs(onsets - m.onset_time)))
            if abs(float(onsets[idx]) - m.onset_time) < 1e-3:
                match_by_idx[idx] = m

    states: list[PartState] = []
    for i, t in enumerate(onsets):
        m = match_by_idx.get(i)
        local_tempo = float(tempo_curve[i]) if i < len(tempo_curve) else tempo_bpm
        if m is not None:
            bar, beat = m.bar, m.beat
            section = m.section_id
            conf = m.confidence * max(alignment.alignment_confidence, 0.2)
            status = m.alignment_status
            onset_conf = float(np.clip(m.confidence, 0.0, 1.0))
        else:
            # Unmatched onset — project via tempo ratio, mark uncertain/lost
            ratio = alignment.tempo_ratio or 1.0
            score_t = float(t) / max(ratio, 1e-6)
            bar, beat = score.bar_beat_at(score_t)
            section = score.section_at(score_t)
            conf = 0.15
            status = AlignmentStatus.UNCERTAIN if alignment.matches else AlignmentStatus.LOST
            onset_conf = 0.4 if len(onsets) > 4 else 0.25

        states.append(
            PartState(
                session_id=session_id,
                part_id=part_id,
                instrument=instrument,
                timestamp=float(t),
                score_position=ScorePosition(
                    section_id=section,
                    bar=bar,
                    beat=beat,
                    sub_beat=0.0,
                    tempo=local_tempo,
                    confidence=float(conf),
                    alignment_status=status,
                ),
                tempo=local_tempo,
                onset_detected=True,
                onset_timestamp=float(t),
                pitch=None,
                dynamics=0.5,
                confidence=PartConfidence(
                    onset=onset_conf,
                    pitch=None,
                    pitch_supported=False,
                    tempo=float(np.clip(0.7 if abs(tempo_bpm - score.tempo_bpm) < 15 else 0.4, 0, 1)),
                    position=float(conf),
                ),
            )
        )

    return PartAnalysis(
        part_id=part_id,
        instrument=instrument,
        onset_times=onsets,
        tempo_bpm=float(tempo_bpm),
        tempo_curve=tempo_curve,
        states=states,
        audio_duration=len(audio) / sr,
        matches=alignment.matches,
        alignment=alignment,
        alignment_confidence=alignment.alignment_confidence,
        mean_signed_error_ms=alignment.mean_signed_error_ms,
        mean_abs_error_ms=alignment.mean_abs_error_ms,
    )
