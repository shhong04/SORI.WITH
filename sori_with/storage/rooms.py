from __future__ import annotations

import threading
import time
import uuid

from sori_with.models.schemas import (
    EnsembleRoom,
    RoomCreate,
    RoomJoinRequest,
    RoomMember,
    SessionCreate,
    SessionMode,
)
from sori_with.storage.memory import store as session_store


class RoomStore:
    def __init__(self) -> None:
        self._rooms: dict[str, EnsembleRoom] = {}
        self._lock = threading.Lock()

    def create_room(self, body: RoomCreate) -> EnsembleRoom:
        room_id = f"room_{uuid.uuid4().hex[:8]}"
        session = session_store.create_session(
            SessionCreate(
                mode=SessionMode.ENSEMBLE_ROOM,
                song_id=body.song_id,
                network_mode=body.network_mode,
            )
        )
        room = EnsembleRoom(
            room_id=room_id,
            room_name=body.room_name,
            song_id=body.song_id,
            session_id=session.session_id,
            network_mode=body.network_mode,
            max_parts=body.max_parts,
            tempo_bpm=body.tempo_bpm or 120.0,
            created_at=time.time(),
        )
        with self._lock:
            self._rooms[room_id] = room
        return room

    def get(self, room_id: str) -> EnsembleRoom | None:
        with self._lock:
            return self._rooms.get(room_id)

    def list_rooms(self) -> list[EnsembleRoom]:
        with self._lock:
            return list(self._rooms.values())

    def update(self, room: EnsembleRoom) -> EnsembleRoom:
        with self._lock:
            self._rooms[room.room_id] = room
        return room

    def join(self, room_id: str, body: RoomJoinRequest) -> EnsembleRoom:
        with self._lock:
            room = self._rooms[room_id]
            if len(room.members) >= room.max_parts:
                raise ValueError("room is full")
            if any(m.part_id == body.part_id for m in room.members):
                raise ValueError(f"part '{body.part_id}' already taken")
            if any(m.user_id == body.user_id for m in room.members):
                raise ValueError("user already joined")
            room.members.append(
                RoomMember(
                    user_id=body.user_id,
                    part_id=body.part_id,
                    display_name=body.display_name or body.user_id,
                    joined_at=time.time(),
                )
            )
            self._rooms[room_id] = room
            return room

    def set_member_audio(self, room_id: str, user_id: str, audio_path: str) -> EnsembleRoom:
        with self._lock:
            room = self._rooms[room_id]
            for m in room.members:
                if m.user_id == user_id:
                    m.audio_path = audio_path
                    m.has_audio = True
                    break
            else:
                raise KeyError("member not found")
            self._rooms[room_id] = room
            return room

    def set_midi(self, room_id: str, midi_path: str) -> EnsembleRoom:
        with self._lock:
            room = self._rooms[room_id]
            room.midi_path = midi_path
            self._rooms[room_id] = room
            return room

    def clear(self) -> None:
        with self._lock:
            self._rooms.clear()


room_store = RoomStore()
