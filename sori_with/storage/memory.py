from __future__ import annotations

import threading
import time
import uuid

from sori_with.models.schemas import (
    AnalysisReport,
    Participant,
    PracticeReport,
    Session,
    SessionCreate,
)


class InMemoryStore:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        self._reports: dict[str, AnalysisReport] = {}
        self._practice_reports: dict[str, PracticeReport] = {}
        self._lock = threading.Lock()

    def create_session(self, body: SessionCreate, session_id: str | None = None) -> Session:
        sid = session_id or f"sess_{uuid.uuid4().hex[:10]}"
        session = Session(
            session_id=sid,
            mode=body.mode,
            song_id=body.song_id,
            score_id=body.score_id,
            participants=list(body.participants),
            started_at=time.time(),
            network_mode=body.network_mode,
            status="created",
        )
        with self._lock:
            self._sessions[sid] = session
        return session

    def ensure_session(self, session_id: str, body: SessionCreate | None = None) -> Session:
        with self._lock:
            existing = self._sessions.get(session_id)
            if existing:
                return existing
        return self.create_session(
            body
            or SessionCreate(song_id="live", network_mode="realtime"),
            session_id=session_id,
        )

    def get_session(self, session_id: str) -> Session | None:
        with self._lock:
            return self._sessions.get(session_id)

    def update_session(self, session: Session) -> Session:
        with self._lock:
            self._sessions[session.session_id] = session
        return session

    def add_participant(self, session_id: str, participant: Participant) -> Session:
        with self._lock:
            session = self._sessions[session_id]
            session.participants.append(participant)
            self._sessions[session_id] = session
            return session

    def save_report(self, report: AnalysisReport) -> None:
        with self._lock:
            self._reports[report.session_id] = report

    def get_report(self, session_id: str) -> AnalysisReport | None:
        with self._lock:
            return self._reports.get(session_id)

    def save_practice_report(self, report: PracticeReport) -> None:
        with self._lock:
            self._practice_reports[report.session_id] = report

    def get_practice_report(self, session_id: str) -> PracticeReport | None:
        with self._lock:
            return self._practice_reports.get(session_id)

    def list_sessions(self) -> list[Session]:
        with self._lock:
            return list(self._sessions.values())

    def clear(self) -> None:
        with self._lock:
            self._sessions.clear()
            self._reports.clear()
            self._practice_reports.clear()


store = InMemoryStore()
