from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from sori_with.audio.render import render_sessionist_bundle
from sori_with.config import get_settings
from sori_with.engines.coaching import CoachingPolicyState, decide_coaching
from sori_with.engines.ensemble_clock import estimate_ensemble_clock
from sori_with.engines.ensemble_state import build_state_timeline
from sori_with.engines.part_understanding import analyze_part
from sori_with.engines.sessionist import plan_sessionist_schedule
from sori_with.midi.score import load_midi_score
from sori_with.models.schemas import (
    PracticeReport,
    RecommendedPractice,
    SessionistMode,
)

logger = logging.getLogger(__name__)


def run_personal_practice(
    session_id: str,
    song_id: str,
    midi_path: str | Path,
    user_part: str,
    user_wav_path: str | Path,
    sessionist_parts: list[str],
    sessionist_mode: SessionistMode = SessionistMode.FOLLOW,
    tempo_bpm: float | None = None,
    render_audio: bool = True,
) -> PracticeReport:
    score = load_midi_score(midi_path, default_tempo_bpm=tempo_bpm or 120.0)
    if tempo_bpm:
        score.tempo_bpm = tempo_bpm

    user = analyze_part(
        session_id=session_id,
        part_id=user_part,
        instrument=user_part,
        wav_path=str(user_wav_path),
        score=score,
    )

    # Fake companion stems as quantized score clicks for readiness context:
    # use user onsets as the live human, sessionist planned against user tempo curve.
    tempo_curve = [
        (float(t), float(user.tempo_curve[i]) if i < len(user.tempo_curve) else user.tempo_bpm)
        for i, t in enumerate(user.onset_times)
    ]

    schedule = []
    for role in sessionist_parts:
        schedule.extend(
            plan_sessionist_schedule(
                score=score,
                role=role,
                mode=sessionist_mode,
                user_tempo_curve=tempo_curve or None,
            )
        )
    schedule.sort(key=lambda a: a.timestamp)

    # Accuracy from score-matched timing (P1); pitch AMT still unsupported
    if user.matches:
        timing = float(np.clip(1.0 - user.mean_abs_error_ms / 200.0, 0.0, 1.0))
        rhythm = timing
    elif len(user.onset_times) >= 2:
        beat_dur = 60.0 / score.tempo_bpm
        ioi = np.diff(user.onset_times)
        rhythm_err = float(np.mean(np.abs(ioi - beat_dur) / beat_dur))
        timing = float(np.clip(1.0 - rhythm_err, 0.0, 1.0))
        rhythm = timing
    else:
        timing = 0.5
        rhythm = 0.5

    accuracy = {
        "pitch": 0.0,  # not measured (pitch_supported=False)
        "rhythm": rhythm,
        "timing": timing,
        "noteDuration": 0.8,
        "alignmentConfidence": float(user.alignment_confidence),
    }

    # Ensemble readiness using a one-part timeline + synthetic stability
    clocks = estimate_ensemble_clock([user])
    timeline = build_state_timeline([user], clocks)
    stable_ratio = (
        sum(1 for s in timeline if s.state.value == "stable") / max(len(timeline), 1)
    )
    readiness = {
        "score": float(np.clip((timing + rhythm + stable_ratio) / 3, 0, 1)),
        "tempoFollowing": "high" if abs(user.tempo_bpm - score.tempo_bpm) < 8 else "medium",
        "sectionTransition": "medium",
        "unexpectedRepeatResponse": "low",
    }

    # Produce a couple of coaching events from unstable states
    policy = CoachingPolicyState(cooldown_sec=0.0)
    coaching = []
    for st in timeline:
        if st.state.value in {"drift", "breakdown"}:
            ev = decide_coaching(ensemble_state=st, policy=policy, now=st.timestamp)
            if ev:
                coaching.append(ev)
                if len(coaching) >= 3:
                    break

    recommended: list[RecommendedPractice] = []
    if timing < 0.85:
        recommended.append(
            RecommendedPractice(
                parts=[user_part] + sessionist_parts[:1],
                start_bar=1,
                end_bar=8,
                tempo=max(70.0, score.tempo_bpm * 0.9),
                goal="first-beat alignment with AI sessionist",
            )
        )

    render_paths: dict[str, str] = {}
    if render_audio and schedule:
        out_dir = get_settings().report_dir / session_id / "sessionist"
        stems = render_sessionist_bundle(
            schedule,
            out_dir,
            stem_name="sessionist",
            tempo_bpm=score.tempo_bpm,
        )
        render_paths = {k: str(v) for k, v in stems.items()}

    return PracticeReport(
        session_id=session_id,
        song_id=song_id,
        user_part=user_part,
        duration_sec=user.audio_duration,
        accuracy=accuracy,
        ensemble_readiness=readiness,
        recommended_practice=recommended,
        sessionist_schedule=schedule,
        coaching_events=coaching,
        user_tempo_bpm=user.tempo_bpm,
        score_tempo_bpm=score.tempo_bpm,
        render_paths=render_paths,
    )
