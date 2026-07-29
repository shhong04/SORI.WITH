from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from sori_with.api.uploads import (
    ANALYSIS_FAILED,
    read_upload_limited,
    require_path_analyze_enabled,
    resolve_allowed_path,
    validate_midi_bytes,
    validate_wav_bytes,
)
from sori_with.audio.render import render_sessionist_bundle
from sori_with.config import get_settings
from sori_with.engines.sessionist import plan_sessionist_schedule
from sori_with.midi.score import load_midi_score
from sori_with.models.schemas import (
    RoomCreate,
    RoomJoinRequest,
    SessionistMode,
)
from sori_with.pipeline.offline_analysis import (
    report_to_dashboard_payload,
    run_offline_ensemble_analysis,
    save_report,
)
from sori_with.realtime.hub import hub
from sori_with.storage.memory import store as session_store
from sori_with.storage.rooms import room_store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["ensemble-room"])


@router.post("/rooms")
async def create_room(body: RoomCreate) -> dict:
    room = room_store.create_room(body)
    await hub.publish(
        room.room_id,
        {"type": "room_created", "room": room.model_dump(mode="json")},
    )
    return room.model_dump(mode="json")


@router.get("/rooms")
def list_rooms() -> list[dict]:
    return [r.model_dump(mode="json") for r in room_store.list_rooms()]


@router.get("/rooms/{room_id}")
def get_room(room_id: str) -> dict:
    room = room_store.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    return room.model_dump(mode="json")


@router.post("/rooms/{room_id}/join")
async def join_room(room_id: str, body: RoomJoinRequest) -> dict:
    if not room_store.get(room_id):
        raise HTTPException(status_code=404, detail="room not found")
    try:
        room = room_store.join(room_id, body)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await hub.publish(
        room_id,
        {
            "type": "member_joined",
            "roomId": room_id,
            "member": {
                "userId": body.user_id,
                "partId": body.part_id,
                "displayName": body.display_name or body.user_id,
            },
            "members": [m.model_dump(mode="json") for m in room.members],
        },
    )
    return room.model_dump(mode="json")


@router.post("/rooms/{room_id}/score")
async def upload_room_score(
    room_id: str,
    midi: UploadFile = File(...),
) -> dict:
    room = room_store.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    settings = get_settings()
    dest_dir = settings.upload_dir / room_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    midi_bytes = await read_upload_limited(midi, settings=settings)
    validate_midi_bytes(midi_bytes)
    midi_path = dest_dir / "score.mid"
    midi_path.write_bytes(midi_bytes)
    room = room_store.set_midi(room_id, str(midi_path))
    await hub.publish(room_id, {"type": "score_uploaded", "roomId": room_id})
    return room.model_dump(mode="json")


@router.post("/rooms/{room_id}/parts/{user_id}/audio")
async def upload_member_audio(
    room_id: str,
    user_id: str,
    audio: UploadFile = File(...),
) -> dict:
    room = room_store.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    if not any(m.user_id == user_id for m in room.members):
        raise HTTPException(status_code=404, detail="member not found")
    settings = get_settings()
    dest_dir = settings.upload_dir / room_id / "parts"
    dest_dir.mkdir(parents=True, exist_ok=True)
    member = next(m for m in room.members if m.user_id == user_id)
    data = await read_upload_limited(audio, settings=settings)
    validate_wav_bytes(data)
    dest = dest_dir / f"{member.part_id}_{user_id}.wav"
    dest.write_bytes(data)
    room = room_store.set_member_audio(room_id, user_id, str(dest))
    await hub.publish(
        room_id,
        {
            "type": "audio_uploaded",
            "roomId": room_id,
            "userId": user_id,
            "partId": member.part_id,
        },
    )
    return room.model_dump(mode="json")


@router.post("/rooms/{room_id}/score/path")
async def set_score_path(room_id: str, midi_path: str = Form(...)) -> dict:
    require_path_analyze_enabled()
    if not room_store.get(room_id):
        raise HTTPException(status_code=404, detail="room not found")
    resolved = resolve_allowed_path(midi_path)
    room = room_store.set_midi(room_id, str(resolved))
    return room.model_dump(mode="json")


@router.post("/rooms/{room_id}/parts/{user_id}/audio/path")
async def set_audio_path(
    room_id: str,
    user_id: str,
    audio_path: str = Form(...),
) -> dict:
    require_path_analyze_enabled()
    if not room_store.get(room_id):
        raise HTTPException(status_code=404, detail="room not found")
    resolved = resolve_allowed_path(audio_path)
    try:
        room = room_store.set_member_audio(room_id, user_id, str(resolved))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="member not found") from exc
    return room.model_dump(mode="json")

@router.post("/rooms/{room_id}/start")
async def start_rehearsal(room_id: str) -> dict:
    room = room_store.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    room.status = "rehearsing"
    room_store.update(room)
    await hub.publish(room_id, {"type": "rehearsal_started", "roomId": room_id})
    return room.model_dump(mode="json")


@router.post("/rooms/{room_id}/analyze")
async def analyze_room(
    room_id: str,
    fill_missing_with_ai: bool = True,
    sessionist_mode: SessionistMode = SessionistMode.FOLLOW,
) -> dict:
    room = room_store.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    if not room.midi_path:
        raise HTTPException(status_code=400, detail="upload score first")

    human_parts = {
        m.part_id: m.audio_path
        for m in room.members
        if m.has_audio and m.audio_path
    }
    if len(human_parts) < 1:
        raise HTTPException(status_code=400, detail="at least one member audio required")

    settings = get_settings()
    work = Path(tempfile.mkdtemp(prefix=f"{room_id}_", dir=settings.upload_dir))
    room.status = "analyzing"
    room_store.update(room)

    try:
        part_wavs = dict(human_parts)
        ai_parts: list[str] = []

        if fill_missing_with_ai:
            needed = ["drums", "bass", "guitar", "vocal"]
            missing = [p for p in needed if p not in part_wavs]
            if missing:
                score = load_midi_score(room.midi_path, default_tempo_bpm=room.tempo_bpm)
                from sori_with.engines.part_understanding import analyze_part

                first_part, first_wav = next(iter(human_parts.items()))
                human = analyze_part(
                    session_id=room.session_id,
                    part_id=first_part,
                    instrument=first_part,
                    wav_path=first_wav,
                    score=score,
                )
                tempo_curve = [
                    (
                        float(t),
                        float(human.tempo_curve[i])
                        if i < len(human.tempo_curve)
                        else human.tempo_bpm,
                    )
                    for i, t in enumerate(human.onset_times)
                ]
                schedule = []
                for role in missing[:2]:  # fill up to 2 AI parts
                    schedule.extend(
                        plan_sessionist_schedule(
                            score,
                            role=role,
                            mode=sessionist_mode,
                            user_tempo_curve=tempo_curve or None,
                        )
                    )
                    ai_parts.append(role)
                if schedule:
                    stems = render_sessionist_bundle(
                        schedule,
                        work / "ai_fills",
                        stem_name="ai_fill",
                        tempo_bpm=room.tempo_bpm,
                    )
                    for role in ai_parts:
                        key = f"{role}_wav"
                        if key in stems:
                            part_wavs[role] = str(stems[key])

        report = run_offline_ensemble_analysis(
            session_id=room.session_id,
            song_id=room.song_id,
            midi_path=room.midi_path,
            part_wavs=part_wavs,
            tempo_bpm=room.tempo_bpm,
        )
        report_path = save_report(report)
        session_store.save_report(report)

        room.status = "ready"
        room.report_session_id = room.session_id
        room.ai_sessionist_parts = ai_parts
        room_store.update(room)

        payload = {
            "type": "room_analyzed",
            "roomId": room_id,
            "aiSessionistParts": ai_parts,
            "dashboard": report_to_dashboard_payload(report),
        }
        await hub.publish(room_id, payload)
        return {
            "room": room.model_dump(mode="json"),
            "report": report.model_dump(mode="json"),
            "reportPath": str(report_path),
            "aiSessionistParts": ai_parts,
        }
    except HTTPException:
        raise
    except Exception as exc:
        room.status = "open"
        room_store.update(room)
        logger.exception("room analyze failed: %s", exc)
        raise HTTPException(status_code=500, detail=ANALYSIS_FAILED) from exc
    finally:
        if not settings.keep_upload_artifacts:
            shutil.rmtree(work, ignore_errors=True)


@router.get("/rooms/{room_id}/dashboard")
def room_dashboard(room_id: str) -> dict:
    room = room_store.get(room_id)
    if not room or not room.report_session_id:
        raise HTTPException(status_code=404, detail="room report not ready")
    report = session_store.get_report(room.report_session_id)
    if not report:
        raise HTTPException(status_code=404, detail="report missing")
    return report_to_dashboard_payload(report)


@router.get("/rooms/{room_id}/files/{kind}")
def download_room_file(room_id: str, kind: str) -> FileResponse:
    """kind examples: score.mid — currently only score."""
    room = room_store.get(room_id)
    if not room:
        raise HTTPException(status_code=404, detail="room not found")
    if kind == "score" and room.midi_path and Path(room.midi_path).exists():
        return FileResponse(room.midi_path, filename="score.mid")
    raise HTTPException(status_code=404, detail="file not found")


@router.websocket("/ws/rooms/{room_id}")
async def room_ws(websocket: WebSocket, room_id: str) -> None:
    await websocket.accept()
    queue = await hub.subscribe(room_id)
    room = room_store.get(room_id)
    await websocket.send_json(
        {
            "type": "subscribed",
            "roomId": room_id,
            "room": room.model_dump(mode="json") if room else None,
        }
    )
    try:
        while True:
            # Prefer hub events; also accept client pings
            try:
                msg = await asyncio_wait_message(websocket, queue)
            except WebSocketDisconnect:
                break
            if msg is None:
                continue
            if isinstance(msg, str):
                await websocket.send_text(msg)
            else:
                await websocket.send_json(msg)
    finally:
        await hub.unsubscribe(room_id, queue)


async def asyncio_wait_message(websocket: WebSocket, queue):
    import asyncio
    import json

    get_task = asyncio.create_task(queue.get())
    recv_task = asyncio.create_task(websocket.receive_text())
    done, pending = await asyncio.wait(
        {get_task, recv_task},
        return_when=asyncio.FIRST_COMPLETED,
    )
    for t in pending:
        t.cancel()
    if get_task in done:
        return get_task.result()
    if recv_task in done:
        raw = recv_task.result()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"type": "noop"}
        if data.get("type") == "ping":
            return {"type": "pong"}
        return {"type": "client_event", "payload": data}
    return None
