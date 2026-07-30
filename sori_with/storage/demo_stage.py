"""In-memory participatory demo stage (local Mac live demos)."""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PARTS = ("vocal", "guitar", "bass", "drums")


@dataclass
class DemoMember:
    user_id: str
    display_name: str
    part_id: str
    has_audio: bool = False
    audio_path: str | None = None
    joined_at: float = field(default_factory=time.time)


@dataclass
class DemoStage:
    stage_id: str = "main"
    midi_path: str | None = None
    tempo_bpm: float = 120.0
    members: dict[str, DemoMember] = field(default_factory=dict)
    highlighted_parts: set[str] = field(default_factory=set)
    status: str = "open"  # open | analyzing | ready
    dashboard: dict[str, Any] | None = None
    last_error: str | None = None
    updated_at: float = field(default_factory=time.time)

    def snapshot(self) -> dict[str, Any]:
        return {
            "stageId": self.stage_id,
            "status": self.status,
            "tempoBpm": self.tempo_bpm,
            "midiReady": bool(self.midi_path),
            "highlightedParts": sorted(self.highlighted_parts),
            "members": [
                {
                    "userId": m.user_id,
                    "displayName": m.display_name,
                    "partId": m.part_id,
                    "hasAudio": m.has_audio,
                }
                for m in sorted(self.members.values(), key=lambda x: x.joined_at)
            ],
            "partsWithAudio": sorted(
                {m.part_id for m in self.members.values() if m.has_audio}
            ),
            "dashboard": self.dashboard,
            "lastError": self.last_error,
            "updatedAt": self.updated_at,
        }


class DemoStageStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stage = DemoStage()
        self._workdir: Path | None = None

    def reset(self, workdir: Path) -> dict[str, Any]:
        with self._lock:
            self._workdir = workdir
            workdir.mkdir(parents=True, exist_ok=True)
            self._stage = DemoStage()
            return self._stage.snapshot()

    def ensure_workdir(self, workdir: Path) -> Path:
        with self._lock:
            if self._workdir is None:
                self._workdir = workdir
                workdir.mkdir(parents=True, exist_ok=True)
            return self._workdir

    def get(self) -> DemoStage:
        with self._lock:
            return self._stage

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return self._stage.snapshot()

    def set_midi(self, path: str) -> dict[str, Any]:
        with self._lock:
            self._stage.midi_path = path
            self._stage.updated_at = time.time()
            return self._stage.snapshot()

    def select_part(
        self, *, user_id: str | None, display_name: str, part_id: str
    ) -> dict[str, Any]:
        if part_id not in PARTS:
            raise ValueError(f"invalid part: {part_id}")
        with self._lock:
            uid = user_id or f"u_{uuid.uuid4().hex[:8]}"
            # one seat per part: replace previous occupant of that part
            for mid, m in list(self._stage.members.items()):
                if m.part_id == part_id and mid != uid:
                    del self._stage.members[mid]
            existing = self._stage.members.get(uid)
            if existing and existing.part_id != part_id:
                # moving seats — keep audio only if same file role reused later
                existing.has_audio = False
                existing.audio_path = None
            member = DemoMember(
                user_id=uid,
                display_name=display_name or part_id,
                part_id=part_id,
                has_audio=bool(existing and existing.part_id == part_id and existing.has_audio),
                audio_path=existing.audio_path
                if existing and existing.part_id == part_id
                else None,
            )
            self._stage.members[uid] = member
            self._stage.highlighted_parts = {
                m.part_id for m in self._stage.members.values()
            }
            self._stage.updated_at = time.time()
            snap = self._stage.snapshot()
            snap["you"] = {
                "userId": uid,
                "displayName": member.display_name,
                "partId": member.part_id,
                "hasAudio": member.has_audio,
            }
            return snap

    def set_audio(self, user_id: str, path: str) -> dict[str, Any]:
        with self._lock:
            m = self._stage.members.get(user_id)
            if not m:
                raise KeyError("member not found — select a part first")
            m.audio_path = path
            m.has_audio = True
            self._stage.status = "open"
            self._stage.dashboard = None
            self._stage.last_error = None
            self._stage.updated_at = time.time()
            return self._stage.snapshot()

    def part_wavs(self) -> dict[str, str]:
        with self._lock:
            out: dict[str, str] = {}
            for m in self._stage.members.values():
                if m.has_audio and m.audio_path:
                    out[m.part_id] = m.audio_path
            return out

    def mark_analyzing(self) -> dict[str, Any]:
        with self._lock:
            self._stage.status = "analyzing"
            self._stage.last_error = None
            self._stage.updated_at = time.time()
            return self._stage.snapshot()

    def mark_ready(self, dashboard: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._stage.status = "ready"
            self._stage.dashboard = dashboard
            self._stage.last_error = None
            self._stage.updated_at = time.time()
            return self._stage.snapshot()

    def mark_failed(self, message: str) -> dict[str, Any]:
        with self._lock:
            self._stage.status = "open"
            self._stage.last_error = message
            self._stage.updated_at = time.time()
            return self._stage.snapshot()


demo_stage_store = DemoStageStore()
