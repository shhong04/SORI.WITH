from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from sori_with.config import get_settings
from sori_with.engines.ensemble_clock import estimate_ensemble_clock
from sori_with.engines.ensemble_relationship import estimate_relations, timing_deviation_ms
from sori_with.engines.ensemble_state import (
    build_events,
    build_state_timeline,
    detect_breakdown_recovery,
)
from sori_with.engines.part_understanding import PartAnalysis, analyze_part
from sori_with.midi.score import ScoreGraph, load_midi_score
from sori_with.models.schemas import AnalysisReport, RecommendedPractice

logger = logging.getLogger(__name__)


def run_offline_ensemble_analysis(
    session_id: str,
    song_id: str,
    midi_path: str | Path,
    part_wavs: dict[str, str | Path],
    tempo_bpm: float | None = None,
    time_signature: tuple[int, int] = (4, 4),
) -> AnalysisReport:
    """
    Phase 1 pipeline:
    part WAVs + MIDI -> PartState -> EnsembleClock -> relations/state -> report
    """
    midi_path = Path(midi_path)
    score: ScoreGraph = load_midi_score(
        midi_path,
        default_tempo_bpm=tempo_bpm or 120.0,
        time_signature=time_signature,
    )
    if tempo_bpm:
        score.tempo_bpm = tempo_bpm

    parts: list[PartAnalysis] = []
    for part_id, wav in part_wavs.items():
        instrument = part_id  # part_id is instrument name in MVP
        logger.info("Analyzing part=%s path=%s", part_id, wav)
        parts.append(
            analyze_part(
                session_id=session_id,
                part_id=part_id,
                instrument=instrument,
                wav_path=str(wav),
                score=score,
            )
        )

    clocks = estimate_ensemble_clock(parts)
    relations = estimate_relations(parts)
    timeline = build_state_timeline(parts, clocks)
    ref = clocks[0].reference_part_id if clocks else None
    deviations = timing_deviation_ms(parts, ref)
    events = build_events(session_id, parts, timeline, relations)
    breakdown, recovery = detect_breakdown_recovery(timeline)

    # Recommended practice around breakdown / highest deviation
    recommended: list[RecommendedPractice] = []
    if breakdown:
        worst = max(deviations.items(), key=lambda kv: kv[1])[0] if deviations else "bass"
        recommended.append(
            RecommendedPractice(
                parts=[worst, ref or "drums"],
                start_bar=max(1, int(breakdown["bar"]) - 2),
                end_bar=int(breakdown["bar"]) + 4,
                tempo=max(70.0, (clocks[0].tempo if clocks else score.tempo_bpm) * 0.85),
                goal="first-beat alignment",
            )
        )
    elif deviations:
        worst = max(deviations.items(), key=lambda kv: kv[1])
        if worst[1] > 40:
            recommended.append(
                RecommendedPractice(
                    parts=[worst[0], ref or "drums"],
                    start_bar=1,
                    end_bar=8,
                    tempo=score.tempo_bpm * 0.9,
                    goal="timing consolidation",
                )
            )

    duration = max((p.audio_duration for p in parts), default=0.0)
    report = AnalysisReport(
        session_id=session_id,
        song_id=song_id,
        duration_sec=duration,
        parts=[p.part_id for p in parts],
        ensemble_clock_summary={
            "median_tempo": float(
                sorted(c.tempo for c in clocks)[len(clocks) // 2] if clocks else score.tempo_bpm
            ),
            "reference_part_id": ref,
            "mean_stability": float(
                sum(c.stability for c in clocks) / len(clocks) if clocks else 0.0
            ),
            "n_clock_samples": len(clocks),
        },
        state_timeline=timeline,
        relations=relations,
        events=events,
        breakdown_point=breakdown,
        recovery_point=recovery,
        part_timing_deviation_ms=deviations,
        recommended_practice=recommended,
        evidence_notes=[
            "Relations are probable influence estimates, not definitive blame.",
            "Realtime coaching should use confidence thresholds before surfacing messages.",
        ],
    )
    return report


def save_report(report: AnalysisReport, path: str | Path | None = None) -> Path:
    settings = get_settings()
    out = Path(path) if path else settings.report_dir / f"{report.session_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    return out


def report_to_dashboard_payload(report: AnalysisReport) -> dict[str, Any]:
    """Compact payload for a future web dashboard."""
    return {
        "sessionId": report.session_id,
        "songId": report.song_id,
        "durationSec": report.duration_sec,
        "parts": report.parts,
        "clock": report.ensemble_clock_summary,
        "breakdownPoint": report.breakdown_point,
        "recoveryPoint": report.recovery_point,
        "partTimingDeviationMs": report.part_timing_deviation_ms,
        "stateHistogram": _state_histogram(report),
        "relations": [r.model_dump(mode="json") for r in report.relations],
        "events": [e.model_dump(mode="json") for e in report.events],
        "recommendedPractice": [
            r.model_dump(mode="json") for r in report.recommended_practice
        ],
        "timelineSparse": [
            {
                "t": s.timestamp,
                "state": s.state.value,
                "tempo": s.ensemble_clock.tempo,
                "spreadMs": s.timing_spread_ms,
                "bar": s.ensemble_clock.bar,
                "beat": s.ensemble_clock.beat,
            }
            for s in report.state_timeline[::4]
        ],
    }


def _state_histogram(report: AnalysisReport) -> dict[str, int]:
    hist: dict[str, int] = {}
    for s in report.state_timeline:
        hist[s.state.value] = hist.get(s.state.value, 0) + 1
    return hist
