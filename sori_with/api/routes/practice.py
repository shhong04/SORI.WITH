from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect

from sori_with.api.uploads import (
    ANALYSIS_FAILED,
    require_path_analyze_enabled,
    resolve_allowed_path,
)
from sori_with.config import get_settings
from sori_with.engines.coaching import CoachingPolicyState, decide_coaching
from sori_with.engines.sessionist import control_from_live_tick
from sori_with.models.schemas import (
    EnsembleClock,
    EnsembleState,
    EnsembleStateLabel,
    LiveTickRequest,
    PracticeRequest,
    SessionCreate,
    SessionMode,
)
from sori_with.pipeline.practice import run_personal_practice
from sori_with.realtime.hub import hub
from sori_with.storage.memory import store

logger = logging.getLogger(__name__)
router = APIRouter(tags=["practice-sessionist"])

# per-session coaching cooldown state
_policies: dict[str, CoachingPolicyState] = {}


def clear_coaching_policies() -> None:
    _policies.clear()


@router.post("/practice/analyze")
def practice_analyze(body: PracticeRequest) -> dict:
    require_path_analyze_enabled()
    settings = get_settings()
    midi_path = resolve_allowed_path(body.midi_path, settings=settings)
    user_wav = resolve_allowed_path(body.user_wav_path, settings=settings)

    session = store.create_session(
        SessionCreate(
            mode=SessionMode.PERSONAL_PRACTICE,
            song_id=body.song_id,
            network_mode="review",
        )
    )
    try:
        report = run_personal_practice(
            session_id=session.session_id,
            song_id=body.song_id,
            midi_path=midi_path,
            user_part=body.user_part,
            user_wav_path=user_wav,
            sessionist_parts=body.sessionist_parts,
            sessionist_mode=body.sessionist_mode,
            tempo_bpm=body.tempo_bpm,
            render_audio=body.render_audio,
        )
        out = settings.report_dir / f"{session.session_id}_practice.json"
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        store.save_practice_report(report)
        session.status = "ready"
        session.artifact_paths = {"practice_report": str(out)}
        store.update_session(session)
        return report.model_dump(mode="json")
    except HTTPException:
        raise
    except Exception as exc:
        session.status = "failed"
        session.error = ANALYSIS_FAILED["message"]
        store.update_session(session)
        logger.exception("practice analyze failed: %s", exc)
        raise HTTPException(status_code=500, detail=ANALYSIS_FAILED) from exc


@router.get("/practice/{session_id}/report")
def get_practice_report(session_id: str) -> dict:
    report = store.get_practice_report(session_id)
    if not report:
        raise HTTPException(status_code=404, detail="practice report not found")
    return report.model_dump(mode="json")


@router.post("/live/tick")
async def live_tick(body: LiveTickRequest) -> dict:
    """
    Simulate one realtime frame:
    Sessionist action + optional coaching, published to WebSocket subscribers.
    """
    store.ensure_session(
        body.session_id,
        SessionCreate(
            mode=SessionMode.AI_SESSIONIST,
            song_id="live",
            network_mode="realtime",
        ),
    )

    action = control_from_live_tick(
        role=body.sessionist_role,
        mode=body.sessionist_mode,
        bar=body.bar,
        beat=body.beat,
        tempo=body.tempo,
        confidence=body.confidence,
        timestamp=body.timestamp,
        session_id=body.session_id,
    )

    clock = EnsembleClock(
        timestamp=body.timestamp,
        tempo=body.tempo,
        phase=(body.beat % 1.0),
        bar=body.bar,
        beat=body.beat,
        reference_type=body.reference_part or "drums",
        reference_part_id=body.reference_part,
        stability=max(0.0, 1.0 - body.timing_spread_ms / 200.0),
    )
    state = EnsembleState(
        timestamp=body.timestamp,
        state=body.state,
        ensemble_clock=clock,
        leader_part_ids=[body.reference_part] if body.reference_part else [],
        follower_part_ids=[body.user_part],
        deviating_part_ids=body.deviating_parts,
        timing_spread_ms=body.timing_spread_ms,
        tempo_variance=0.0,
        score_position_spread=body.timing_spread_ms / 50.0,
        breakdown_risk=0.8 if body.state == EnsembleStateLabel.BREAKDOWN else 0.3,
        natural_recovery_probability=0.4 if body.state != EnsembleStateLabel.STABLE else 0.9,
        confidence=body.confidence,
    )

    policy = _policies.setdefault(body.session_id, CoachingPolicyState())
    coaching = decide_coaching(ensemble_state=state, policy=policy, now=body.timestamp)

    payload = {
        "type": "live_tick",
        "sessionId": body.session_id,
        "ensembleState": {
            "state": state.state.value,
            "bar": body.bar,
            "beat": body.beat,
            "tempo": body.tempo,
            "leader": body.reference_part,
            "deviatingParts": body.deviating_parts,
            "breakdownRisk": state.breakdown_risk,
        },
        "sessionistAction": action.model_dump(mode="json"),
        "coaching": coaching.model_dump(mode="json") if coaching else None,
    }
    await hub.publish(body.session_id, payload)
    return payload


@router.websocket("/ws/sessions/{session_id}")
async def session_ws(websocket: WebSocket, session_id: str) -> None:
    await websocket.accept()
    queue = await hub.subscribe(session_id)
    await websocket.send_json({"type": "subscribed", "sessionId": session_id})
    try:
        while True:
            get_task = asyncio.create_task(queue.get())
            recv_task = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait(
                {get_task, recv_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            if get_task in done:
                msg = get_task.result()
                await websocket.send_text(msg)
            if recv_task in done:
                try:
                    raw = recv_task.result()
                except WebSocketDisconnect:
                    break
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                elif data.get("type") == "live_tick":
                    body = LiveTickRequest.model_validate(data.get("payload", data))
                    body.session_id = session_id
                    result = await live_tick(body)
                    await websocket.send_json(result)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.unsubscribe(session_id, queue)
