from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any


class RealtimeHub:
    """In-process pub/sub for session WebSocket clients."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[asyncio.Queue[str]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, session_id: str) -> asyncio.Queue[str]:
        q: asyncio.Queue[str] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._rooms[session_id].add(q)
        return q

    async def unsubscribe(self, session_id: str, q: asyncio.Queue[str]) -> None:
        async with self._lock:
            self._rooms[session_id].discard(q)
            if not self._rooms[session_id]:
                del self._rooms[session_id]

    async def publish(self, session_id: str, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False)
        async with self._lock:
            queues = list(self._rooms.get(session_id, set()))
        for q in queues:
            try:
                q.put_nowait(payload)
            except asyncio.QueueFull:
                # drop oldest-style: ignore if client is slow
                pass


hub = RealtimeHub()
