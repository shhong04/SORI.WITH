"""Participatory local demo: audience upload/select → monitor HUD."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, WebSocket, WebSocketDisconnect

from sori_with.api.uploads import (
    ANALYSIS_FAILED,
    read_upload_limited,
    validate_wav_bytes,
)
from sori_with.config import get_settings
from sori_with.pipeline.offline_analysis import (
    report_to_dashboard_payload,
    run_offline_ensemble_analysis,
)
from sori_with.realtime.hub import hub
from sori_with.storage.demo_stage import PARTS, demo_stage_store
from sori_with.tools.synthetic import build_synthetic_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["demo-stage"])

STAGE_WS_ID = "demo_stage"


async def _broadcast(snap: dict) -> None:
    await hub.publish(STAGE_WS_ID, {"type": "demo_stage", "stage": snap})


def _workdir() -> Path:
    settings = get_settings()
    return demo_stage_store.ensure_workdir(settings.upload_dir / "demo_stage")


def _ensure_score() -> Path:
    """Generate synthetic score+stems once into demo workdir if missing."""
    work = _workdir()
    midi = work / "score.mid"
    if midi.exists() and all((work / f"{p}.wav").exists() for p in PARTS):
        demo_stage_store.set_midi(str(midi))
        return midi
    paths = build_synthetic_session(work)
    demo_stage_store.set_midi(str(paths["midi"]))
    return paths["midi"]


@router.get("/demo/stage")
async def get_stage() -> dict:
    _ensure_score()
    return demo_stage_store.snapshot()


@router.post("/demo/stage/reset")
async def reset_stage() -> dict:
    settings = get_settings()
    work = settings.upload_dir / "demo_stage"
    if work.exists():
        shutil.rmtree(work, ignore_errors=True)
    snap = demo_stage_store.reset(work)
    _ensure_score()
    snap = demo_stage_store.snapshot()
    await _broadcast(snap)
    return snap


@router.post("/demo/stage/select")
async def select_part(
    part_id: str = Form(...),
    display_name: str = Form(""),
    user_id: str | None = Form(None),
) -> dict:
    try:
        snap = demo_stage_store.select_part(
            user_id=user_id,
            display_name=display_name.strip() or part_id,
            part_id=part_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await _broadcast(snap)
    return snap


@router.post("/demo/stage/audio")
async def upload_audio(
    user_id: str = Form(...),
    audio: UploadFile = File(...),
) -> dict:
    _ensure_score()
    settings = get_settings()
    data = await read_upload_limited(audio, settings=settings)
    validate_wav_bytes(data)
    work = _workdir()
    member_snap = demo_stage_store.snapshot()
    part = next(
        (m["partId"] for m in member_snap["members"] if m["userId"] == user_id),
        None,
    )
    if not part:
        raise HTTPException(status_code=404, detail="member not found — select a part first")
    dest = work / f"upload_{user_id}_{part}.wav"
    dest.write_bytes(data)
    try:
        snap = demo_stage_store.set_audio(user_id, str(dest))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _broadcast(snap)
    return snap


@router.post("/demo/stage/sample")
async def use_sample(
    user_id: str = Form(...),
) -> dict:
    """Attach the synthetic stem for the member's selected part (no mic needed)."""
    midi = _ensure_score()
    work = midi.parent
    snap0 = demo_stage_store.snapshot()
    part = next(
        (m["partId"] for m in snap0["members"] if m["userId"] == user_id),
        None,
    )
    if not part:
        raise HTTPException(status_code=404, detail="member not found — select a part first")
    src = work / f"{part}.wav"
    if not src.exists():
        raise HTTPException(status_code=500, detail="sample stem missing")
    dest = work / f"upload_{user_id}_{part}.wav"
    shutil.copyfile(src, dest)
    try:
        snap = demo_stage_store.set_audio(user_id, str(dest))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    await _broadcast(snap)
    return snap


@router.post("/demo/stage/analyze")
async def analyze_stage() -> dict:
    stage = demo_stage_store.get()
    if not stage.midi_path:
        _ensure_score()
        stage = demo_stage_store.get()
    part_wavs = demo_stage_store.part_wavs()
    if len(part_wavs) < 2:
        raise HTTPException(
            status_code=400,
            detail="Need audio from at least 2 parts (select + upload/sample)",
        )

    snap = demo_stage_store.mark_analyzing()
    await _broadcast(snap)
    try:
        report = run_offline_ensemble_analysis(
            session_id=f"demo_{int(stage.updated_at)}",
            song_id="demo_stage",
            midi_path=stage.midi_path,
            part_wavs=part_wavs,
            tempo_bpm=stage.tempo_bpm,
        )
        dashboard = report_to_dashboard_payload(report)
        snap = demo_stage_store.mark_ready(dashboard)
        await _broadcast(snap)
        return snap
    except Exception as exc:
        logger.exception("demo stage analyze failed: %s", exc)
        snap = demo_stage_store.mark_failed(ANALYSIS_FAILED["message"])
        await _broadcast(snap)
        raise HTTPException(status_code=500, detail=ANALYSIS_FAILED) from exc


@router.websocket("/ws/demo/stage")
async def demo_stage_ws(ws: WebSocket) -> None:
    await ws.accept()
    _ensure_score()
    q = await hub.subscribe(STAGE_WS_ID)
    try:
        await ws.send_json({"type": "demo_stage", "stage": demo_stage_store.snapshot()})
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=25.0)
                await ws.send_text(msg)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(STAGE_WS_ID, q)
