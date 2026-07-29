from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from sori_with.audio.processing import detect_onsets, estimate_tempo_curve, load_mono
from sori_with.config import get_thresholds
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
    if abs(tempo_bpm - score.tempo_bpm) > 25:
        # Prefer score tempo if onset tempo is unreliable
        tempo_bpm = score.tempo_bpm
        tempo_curve = np.full(max(len(onsets), 1), tempo_bpm)

    states: list[PartState] = []
    for i, t in enumerate(onsets):
        bar, beat = score.bar_beat_at(float(t))
        section = score.section_at(float(t))
        local_tempo = float(tempo_curve[i]) if i < len(tempo_curve) else tempo_bpm
        conf = 0.9 if len(onsets) > 4 else 0.6
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
                    confidence=conf,
                    alignment_status=AlignmentStatus.ALIGNED,
                ),
                tempo=local_tempo,
                onset_detected=True,
                onset_timestamp=float(t),
                dynamics=0.5,
                confidence=PartConfidence(
                    onset=conf, pitch=0.5, tempo=conf, position=conf
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
    )
