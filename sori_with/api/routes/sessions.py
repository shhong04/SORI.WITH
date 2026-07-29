from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from sori_with.config import get_settings
from sori_with.models.schemas import (
    OfflineAnalyzeRequest,
    Participant,
    SessionCreate,
    SessionMode,
)
from sori_with.pipeline.offline_analysis import (
    report_to_dashboard_payload,
    run_offline_ensemble_analysis,
    save_report,
)
from sori_with.storage.memory import store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["sessions"])


@router.post("/sessions")
def create_session(body: SessionCreate) -> dict:
    session = store.create_session(body)
    return session.model_dump(mode="json")


@router.get("/sessions")
def list_sessions() -> list[dict]:
    return [s.model_dump(mode="json") for s in store.list_sessions()]


@router.get("/sessions/{session_id}")
def get_session(session_id: str) -> dict:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")
    return session.model_dump(mode="json")


@router.post("/sessions/{session_id}/participants")
def add_participant(session_id: str, participant: Participant) -> dict:
    if not store.get_session(session_id):
        raise HTTPException(status_code=404, detail="session not found")
    session = store.add_participant(session_id, participant)
    return session.model_dump(mode="json")


@router.post("/sessions/{session_id}/analyze")
async def analyze_session_upload(
    session_id: str,
    midi: UploadFile = File(...),
    vocal: UploadFile | None = File(None),
    guitar: UploadFile | None = File(None),
    bass: UploadFile | None = File(None),
    drums: UploadFile | None = File(None),
    tempo_bpm: float | None = Form(None),
) -> JSONResponse:
    session = store.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="session not found")

    uploads = {
        "vocal": vocal,
        "guitar": guitar,
        "bass": bass,
        "drums": drums,
    }
    present = {k: v for k, v in uploads.items() if v is not None}
    if len(present) < 2:
        raise HTTPException(
            status_code=400,
            detail="Upload at least 2 part WAV files among vocal/guitar/bass/drums",
        )

    settings = get_settings()
    work = Path(tempfile.mkdtemp(prefix=f"{session_id}_", dir=settings.upload_dir))
    try:
        midi_path = work / "score.mid"
        midi_path.write_bytes(await midi.read())
        part_paths: dict[str, Path] = {}
        for name, uf in present.items():
            dest = work / f"{name}.wav"
            dest.write_bytes(await uf.read())
            part_paths[name] = dest

        session.status = "analyzing"
        store.update_session(session)

        report = run_offline_ensemble_analysis(
            session_id=session_id,
            song_id=session.song_id,
            midi_path=midi_path,
            part_wavs=part_paths,
            tempo_bpm=tempo_bpm,
        )
        report_path = save_report(report)
        store.save_report(report)
        session.status = "ready"
        session.artifact_paths = {
            "report": str(report_path),
            "workdir": str(work),
        }
        store.update_session(session)
        return JSONResponse(report.model_dump(mode="json"))
    except Exception as exc:
        logger.exception("analyze failed")
        session.status = "failed"
        session.error = str(exc)
        store.update_session(session)
        shutil.rmtree(work, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/sessions/analyze/path")
def analyze_from_paths(body: OfflineAnalyzeRequest) -> dict:
    """Analyze using local filesystem paths (dev/test)."""
    session = store.create_session(
        SessionCreate(
            mode=SessionMode.OFFLINE_ANALYSIS,
            song_id=body.song_id,
            network_mode="review",
        )
    )
    try:
        report = run_offline_ensemble_analysis(
            session_id=session.session_id,
            song_id=body.song_id,
            midi_path=body.midi_path,
            part_wavs=body.parts,
            tempo_bpm=body.tempo_bpm,
            time_signature=body.time_signature,
        )
        path = save_report(report)
        store.save_report(report)
        session.status = "ready"
        session.artifact_paths = {"report": str(path)}
        store.update_session(session)
        return report.model_dump(mode="json")
    except Exception as exc:
        session.status = "failed"
        session.error = str(exc)
        store.update_session(session)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/sessions/{session_id}/report")
def get_report(session_id: str) -> dict:
    report = store.get_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report.model_dump(mode="json")


@router.get("/sessions/{session_id}/dashboard")
def get_dashboard(session_id: str) -> dict:
    report = store.get_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found")
    return report_to_dashboard_payload(report)


@router.get("/sessions/{session_id}/state")
def get_latest_state(session_id: str) -> dict:
    """Phase 1 stub: returns last timeline sample from offline report."""
    report = store.get_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="report not found; run analyze first")
    if not report.state_timeline:
        return {"type": "ensemble_state", "payload": None}
    last = report.state_timeline[-1]
    return {
        "type": "ensemble_state",
        "payload": {
            "state": last.state.value,
            "bar": last.ensemble_clock.bar,
            "beat": last.ensemble_clock.beat,
            "tempo": last.ensemble_clock.tempo,
            "leader": last.leader_part_ids[0] if last.leader_part_ids else None,
            "deviatingParts": last.deviating_part_ids,
            "breakdownRisk": last.breakdown_risk,
        },
    }
