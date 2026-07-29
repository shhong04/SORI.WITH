from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class SessionMode(str, Enum):
    PERSONAL_PRACTICE = "personal_practice"
    ENSEMBLE_ROOM = "ensemble_room"
    AI_SESSIONIST = "ai_sessionist"
    REHEARSAL_COACHING = "rehearsal_coaching"
    OFFLINE_ANALYSIS = "offline_analysis"


class EnsembleStateLabel(str, Enum):
    STABLE = "stable"
    DRIFT = "drift"
    BREAKDOWN = "breakdown"
    RECOVERY = "recovery"


class RelationType(str, Enum):
    LEADS = "leads"
    FOLLOWS = "follows"
    MAINTAINS_REFERENCE = "maintains_reference"
    DEVIATES = "deviates"
    PROPAGATES_DRIFT = "propagates_drift"
    SUPPORTS_RECOVERY = "supports_recovery"


class AlignmentStatus(str, Enum):
    ALIGNED = "aligned"
    UNCERTAIN = "uncertain"
    REPEATED = "repeated"
    SKIPPED = "skipped"
    EXTENDED = "extended"
    LOST = "lost"
    RECOVERED = "recovered"


class Participant(BaseModel):
    user_id: str
    part_id: str
    instrument: str
    input_device: str | None = None
    estimated_latency_ms: float | None = None


class SessionCreate(BaseModel):
    mode: SessionMode = SessionMode.OFFLINE_ANALYSIS
    song_id: str = "song_001"
    score_id: str | None = None
    network_mode: Literal["realtime", "hybrid", "review"] | None = "review"
    participants: list[Participant] = Field(default_factory=list)


class Session(BaseModel):
    session_id: str
    mode: SessionMode
    song_id: str
    score_id: str | None = None
    participants: list[Participant] = Field(default_factory=list)
    started_at: float
    ended_at: float | None = None
    network_mode: Literal["realtime", "hybrid", "review"] | None = None
    status: Literal["created", "uploaded", "analyzing", "ready", "failed"] = "created"
    artifact_paths: dict[str, str] = Field(default_factory=dict)
    error: str | None = None


class ScorePosition(BaseModel):
    section_id: str
    bar: int
    beat: float
    sub_beat: float = 0.0
    tempo: float
    confidence: float
    alignment_status: AlignmentStatus = AlignmentStatus.ALIGNED


class PartConfidence(BaseModel):
    onset: float = 0.0
    pitch: float | None = None
    pitch_supported: bool = False
    tempo: float = 0.0
    position: float = 0.0


class PartState(BaseModel):
    session_id: str
    part_id: str
    instrument: str
    timestamp: float
    score_position: ScorePosition
    tempo: float
    onset_detected: bool = False
    onset_timestamp: float | None = None
    pitch: float | None = None
    dynamics: float = 0.5
    is_active: bool = True
    is_resting: bool = False
    confidence: PartConfidence = Field(default_factory=PartConfidence)


class EnsembleClock(BaseModel):
    timestamp: float
    tempo: float
    phase: float
    bar: int
    beat: float
    reference_type: str
    reference_part_id: str | None = None
    stability: float
    tempo_trend: Literal["stable", "accelerating", "decelerating"] = "stable"


class EnsembleRelation(BaseModel):
    source_part_id: str
    target_part_id: str
    relation_type: RelationType
    start_timestamp: float
    end_timestamp: float
    lag_ms: float
    strength: float
    confidence: float
    start_bar: int | None = None
    end_bar: int | None = None
    evidence_count: int = 0
    note: str = "probable influence (not causal)"


class EnsembleState(BaseModel):
    timestamp: float
    state: EnsembleStateLabel
    ensemble_clock: EnsembleClock
    leader_part_ids: list[str] = Field(default_factory=list)
    follower_part_ids: list[str] = Field(default_factory=list)
    deviating_part_ids: list[str] = Field(default_factory=list)
    timing_spread_ms: float
    tempo_variance: float
    score_position_spread: float
    breakdown_risk: float
    natural_recovery_probability: float
    confidence: float


class EnsembleEvent(BaseModel):
    event_id: str
    session_id: str
    type: str
    start_time: float
    end_time: float | None = None
    start_bar: int
    start_beat: float
    end_bar: int | None = None
    end_beat: float | None = None
    involved_part_ids: list[str]
    probable_source_part_id: str | None = None
    reference_part_id: str | None = None
    severity: float
    confidence: float
    evidence: list[dict[str, Any]] = Field(default_factory=list)


class RecommendedPractice(BaseModel):
    parts: list[str]
    start_bar: int
    end_bar: int
    tempo: float
    goal: str


class PropagationStep(BaseModel):
    from_part: str = Field(alias="from")
    to: str
    start_bar: int
    effect: str

    model_config = {"populate_by_name": True}


class AnalysisReport(BaseModel):
    session_id: str
    song_id: str
    duration_sec: float
    parts: list[str]
    ensemble_clock_summary: dict[str, Any]
    state_timeline: list[EnsembleState]
    relations: list[EnsembleRelation]
    events: list[EnsembleEvent]
    breakdown_point: dict[str, Any] | None = None
    recovery_point: dict[str, Any] | None = None
    part_timing_deviation_ms: dict[str, float]
    part_signed_timing_deviation_ms: dict[str, float] = Field(default_factory=dict)
    part_alignment_confidence: dict[str, float] = Field(default_factory=dict)
    timing_windows: list[dict[str, Any]] = Field(default_factory=list)
    recommended_practice: list[RecommendedPractice] = Field(default_factory=list)
    evidence_notes: list[str] = Field(default_factory=list)


class OfflineAnalyzeRequest(BaseModel):
    """JSON body alternative when files already exist on disk."""

    song_id: str = "song_001"
    midi_path: str
    parts: dict[str, str]
    """Map instrument/part name -> wav path. e.g. {\"drums\": \".../drums.wav\"}"""
    tempo_bpm: float | None = None
    time_signature: tuple[int, int] = (4, 4)


class SessionistMode(str, Enum):
    FOLLOW = "follow"
    ACCOMPANY = "accompany"
    LEAD = "lead"
    INTERACT = "interact"


class SessionistAction(BaseModel):
    timestamp: float
    role: Literal["drums", "bass", "keyboard", "guitar", "vocal"]
    mode: SessionistMode
    target_bar: int
    target_beat: float
    target_tempo: float
    action: Literal["play", "hold", "repeat", "transition", "fill", "stop", "reenter"]
    pitch: int | None = None
    velocity: int = 90
    duration_beats: float = 0.5
    dynamics: float = 0.7
    articulation: str | None = None
    fill_type: str | None = None
    confidence: float = 1.0


class CoachingEvent(BaseModel):
    coaching_event_id: str
    source_ensemble_event_id: str | None = None
    target_part_ids: list[str]
    delivery_target: Literal["individual", "team", "leader"] = "team"
    delivery_timing: Literal[
        "immediate", "next_beat", "next_bar", "next_section", "after_playing"
    ] = "next_bar"
    message: str
    priority: int
    confidence: float
    evidence: dict[str, Any] = Field(default_factory=dict)
    delivered_at: float | None = None


class PracticeRequest(BaseModel):
    song_id: str = "practice_001"
    midi_path: str
    user_part: str = "guitar"
    user_wav_path: str
    sessionist_parts: list[str] = Field(default_factory=lambda: ["bass", "drums"])
    sessionist_mode: SessionistMode = SessionistMode.FOLLOW
    tempo_bpm: float | None = None
    render_audio: bool = True


class PracticeReport(BaseModel):
    session_id: str
    song_id: str
    user_part: str
    duration_sec: float
    accuracy: dict[str, float]
    ensemble_readiness: dict[str, Any]
    recommended_practice: list[RecommendedPractice] = Field(default_factory=list)
    sessionist_schedule: list[SessionistAction] = Field(default_factory=list)
    coaching_events: list[CoachingEvent] = Field(default_factory=list)
    user_tempo_bpm: float
    score_tempo_bpm: float
    render_paths: dict[str, str] = Field(default_factory=dict)


class LiveTickRequest(BaseModel):
    """Simulate a realtime player tick for Sessionist + coaching."""

    session_id: str
    timestamp: float
    bar: int
    beat: float
    tempo: float
    confidence: float = 0.9
    user_part: str = "guitar"
    sessionist_role: Literal["drums", "bass", "keyboard", "guitar", "vocal"] = "bass"
    sessionist_mode: SessionistMode = SessionistMode.FOLLOW
    timing_spread_ms: float = 20.0
    state: EnsembleStateLabel = EnsembleStateLabel.STABLE
    deviating_parts: list[str] = Field(default_factory=list)
    reference_part: str | None = "drums"


class RoomCreate(BaseModel):
    song_id: str = "room_song"
    room_name: str = "Ensemble Room"
    network_mode: Literal["realtime", "hybrid", "review"] = "hybrid"
    max_parts: int = 4
    tempo_bpm: float | None = 120.0


class RoomJoinRequest(BaseModel):
    user_id: str
    part_id: Literal["vocal", "guitar", "bass", "drums", "keyboard"]
    display_name: str | None = None


class RoomMember(BaseModel):
    user_id: str
    part_id: str
    display_name: str
    connected: bool = True
    has_audio: bool = False
    audio_path: str | None = None
    joined_at: float


class EnsembleRoom(BaseModel):
    room_id: str
    room_name: str
    song_id: str
    session_id: str
    network_mode: Literal["realtime", "hybrid", "review"] = "hybrid"
    status: Literal["open", "rehearsing", "analyzing", "ready", "closed"] = "open"
    max_parts: int = 4
    tempo_bpm: float = 120.0
    midi_path: str | None = None
    members: list[RoomMember] = Field(default_factory=list)
    created_at: float
    report_session_id: str | None = None
    ai_sessionist_parts: list[str] = Field(default_factory=list)
