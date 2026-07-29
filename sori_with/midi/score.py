from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import mido
import numpy as np


@dataclass
class ScoreEvent:
    time_sec: float
    bar: int
    beat: float
    pitch: int | None
    section_id: str
    is_downbeat: bool = False


@dataclass
class ScoreGraph:
    tempo_bpm: float
    time_signature: tuple[int, int]
    duration_sec: float
    events: list[ScoreEvent] = field(default_factory=list)
    section_markers: list[tuple[float, str]] = field(default_factory=list)

    def section_at(self, t: float) -> str:
        current = "intro"
        for mark_t, name in self.section_markers:
            if t >= mark_t:
                current = name
            else:
                break
        return current

    def bar_beat_at(self, t: float) -> tuple[int, float]:
        beats_per_bar = self.time_signature[0]
        beat_dur = 60.0 / self.tempo_bpm
        total_beats = t / beat_dur
        bar = int(total_beats // beats_per_bar) + 1
        beat = (total_beats % beats_per_bar) + 1.0
        return max(1, bar), float(beat)


def load_midi_score(
    path: Path | str,
    default_tempo_bpm: float = 120.0,
    time_signature: tuple[int, int] = (4, 4),
) -> ScoreGraph:
    mid = mido.MidiFile(str(path))
    tempo_bpm = default_tempo_bpm
    ts = time_signature
    events: list[ScoreEvent] = []
    section_markers: list[tuple[float, str]] = [(0.0, "verse")]

    t = 0.0
    for msg in mid:
        t += msg.time
        if msg.type == "set_tempo":
            tempo_bpm = float(mido.tempo2bpm(msg.tempo))
        elif msg.type == "time_signature":
            ts = (int(msg.numerator), int(msg.denominator))
        elif msg.type in {"marker", "text"}:
            text = getattr(msg, "text", "") or ""
            if text:
                section_markers.append((t, text.lower().replace(" ", "_")))
        elif msg.type == "note_on" and msg.velocity > 0:
            beat_dur = 60.0 / tempo_bpm
            beats_per_bar = ts[0]
            total_beats = t / beat_dur
            bar = int(total_beats // beats_per_bar) + 1
            beat = (total_beats % beats_per_bar) + 1.0
            events.append(
                ScoreEvent(
                    time_sec=t,
                    bar=bar,
                    beat=beat,
                    pitch=msg.note,
                    section_id=section_markers[-1][1],
                    is_downbeat=abs(beat - 1.0) < 0.05,
                )
            )

    duration = max((e.time_sec for e in events), default=t)
    if duration <= 0:
        duration = 8.0
    if len(section_markers) == 1:
        section_markers = [(0.0, "verse"), (duration * 0.5, "chorus")]

    return ScoreGraph(
        tempo_bpm=tempo_bpm,
        time_signature=ts,
        duration_sec=duration,
        events=events,
        section_markers=sorted(section_markers, key=lambda x: x[0]),
    )


def synthesize_click_midi(
    path: Path | str,
    bars: int = 16,
    tempo_bpm: float = 120.0,
    time_signature: tuple[int, int] = (4, 4),
) -> ScoreGraph:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    track.append(
        mido.MetaMessage(
            "time_signature",
            numerator=time_signature[0],
            denominator=time_signature[1],
            time=0,
        )
    )
    track.append(mido.MetaMessage("marker", text="verse", time=0))

    tpb = mid.ticks_per_beat
    last_tick = 0
    chorus_tick = (bars // 2) * time_signature[0] * tpb
    chorus_written = False

    for bar in range(bars):
        for beat in range(time_signature[0]):
            abs_tick = (bar * time_signature[0] + beat) * tpb
            if not chorus_written and abs_tick >= chorus_tick:
                track.append(
                    mido.MetaMessage("marker", text="chorus", time=abs_tick - last_tick)
                )
                last_tick = abs_tick
                chorus_written = True
                delta = 0
            else:
                delta = abs_tick - last_tick
            pitch = 42 if beat == 0 else 36
            track.append(mido.Message("note_on", note=pitch, velocity=90, time=delta))
            last_tick = abs_tick
            track.append(mido.Message("note_off", note=pitch, velocity=0, time=20))
            last_tick += 20

    mid.save(str(path))
    return load_midi_score(path, default_tempo_bpm=tempo_bpm, time_signature=time_signature)


def expected_beat_times(score: ScoreGraph, duration_sec: float | None = None) -> np.ndarray:
    dur = duration_sec or score.duration_sec
    beat_dur = 60.0 / score.tempo_bpm
    n_beats = int(np.floor(dur / beat_dur)) + 1
    return np.arange(n_beats, dtype=np.float64) * beat_dur
