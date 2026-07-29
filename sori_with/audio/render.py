from __future__ import annotations

import math
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

from sori_with.models.schemas import SessionistAction

# MIDI note -> approx Hz
def _midi_to_hz(note: int) -> float:
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


def _synth_tone(
    sr: int,
    duration_sec: float,
    freq: float,
    velocity: int = 90,
    kind: str = "bass",
) -> np.ndarray:
    n = max(1, int(duration_sec * sr))
    t = np.arange(n, dtype=np.float64) / sr
    amp = (velocity / 127.0) * 0.35
    if kind == "drums":
        # noise burst with exponential decay; freq biases filter-ish envelope
        noise = np.random.default_rng(int(freq)).normal(0, 1, n)
        decay = np.exp(-t * (12.0 + freq / 40.0))
        # add a low thud for kick-ish pitches
        thud = np.sin(2 * np.pi * max(40.0, freq / 4) * t) * np.exp(-t * 18.0)
        wave = 0.7 * noise * decay + 0.3 * thud
    elif kind == "keyboard":
        wave = (
            np.sin(2 * np.pi * freq * t)
            + 0.35 * np.sin(2 * np.pi * freq * 2 * t)
            + 0.15 * np.sin(2 * np.pi * freq * 3 * t)
        )
        wave *= np.exp(-t * 2.5)
    else:  # bass / guitar / vocal-ish
        wave = np.sin(2 * np.pi * freq * t) + 0.25 * np.sin(2 * np.pi * freq * 2 * t)
        wave *= np.exp(-t * 3.5)
    # tiny attack
    attack = min(n, int(0.005 * sr))
    if attack > 1:
        wave[:attack] *= np.linspace(0, 1, attack)
    return (amp * wave).astype(np.float64)


def render_schedule_to_audio(
    schedule: list[SessionistAction],
    *,
    sr: int = 48000,
    duration_sec: float | None = None,
) -> np.ndarray:
    if not schedule:
        return np.zeros(int(sr * 1.0), dtype=np.float64)

    end = duration_sec
    if end is None:
        last = schedule[-1]
        beat_dur = 60.0 / max(last.target_tempo, 1e-3)
        end = last.timestamp + last.duration_beats * beat_dur + 0.5
    n = int(math.ceil(end * sr))
    mix = np.zeros(n, dtype=np.float64)

    for act in schedule:
        if act.action in {"hold", "stop"} or act.pitch is None:
            continue
        beat_dur = 60.0 / max(act.target_tempo, 1e-3)
        dur = max(0.03, act.duration_beats * beat_dur)
        if act.action == "fill":
            dur *= 1.2
        start = int(act.timestamp * sr)
        if start >= n:
            continue
        tone = _synth_tone(
            sr,
            dur,
            _midi_to_hz(act.pitch),
            velocity=act.velocity,
            kind=act.role if act.role in {"drums", "bass", "keyboard", "guitar", "vocal"} else "bass",
        )
        end_i = min(n, start + len(tone))
        mix[start:end_i] += tone[: end_i - start]

    peak = np.max(np.abs(mix)) + 1e-9
    return (mix / peak * 0.9).astype(np.float64)


def write_wav(path: Path | str, audio: np.ndarray, sr: int = 48000) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sr)
    return path


def write_midi_from_schedule(
    path: Path | str,
    schedule: list[SessionistAction],
    tempo_bpm: float = 120.0,
) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mid = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    mid.tracks.append(track)
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))

    tpb = mid.ticks_per_beat
    events: list[tuple[int, str, int, int]] = []  # abs_tick, on/off, note, vel
    for act in schedule:
        if act.action in {"hold", "stop"} or act.pitch is None:
            continue
        tick = int(round(act.timestamp * (tempo_bpm / 60.0) * tpb))
        dur_ticks = max(10, int(round(act.duration_beats * tpb)))
        events.append((tick, "on", act.pitch, act.velocity))
        events.append((tick + dur_ticks, "off", act.pitch, 0))
    events.sort(key=lambda x: (x[0], 0 if x[1] == "off" else 1))

    last = 0
    for abs_tick, kind, note, vel in events:
        delta = max(0, abs_tick - last)
        if kind == "on":
            track.append(mido.Message("note_on", note=note, velocity=vel, time=delta))
        else:
            track.append(mido.Message("note_off", note=note, velocity=0, time=delta))
        last = abs_tick

    mid.save(str(path))
    return path


def render_sessionist_bundle(
    schedule: list[SessionistAction],
    out_dir: Path | str,
    *,
    stem_name: str = "sessionist",
    sr: int = 48000,
    tempo_bpm: float = 120.0,
) -> dict[str, Path]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    audio = render_schedule_to_audio(schedule, sr=sr)
    wav = write_wav(out_dir / f"{stem_name}.wav", audio, sr=sr)
    midi = write_midi_from_schedule(out_dir / f"{stem_name}.mid", schedule, tempo_bpm=tempo_bpm)

    # also per-role stems if multiple roles present
    roles = sorted({a.role for a in schedule})
    stems: dict[str, Path] = {"mix_wav": wav, "mix_midi": midi}
    for role in roles:
        role_sched = [a for a in schedule if a.role == role]
        role_audio = render_schedule_to_audio(role_sched, sr=sr, duration_sec=len(audio) / sr)
        stems[f"{role}_wav"] = write_wav(out_dir / f"{stem_name}_{role}.wav", role_audio, sr=sr)
    return stems
