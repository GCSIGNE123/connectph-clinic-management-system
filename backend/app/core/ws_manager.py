"""In-process WebSocket connection manager for realtime queue broadcast.

Mirrors the documented degrade-gracefully approach used by
`app/core/rate_limit.py`: this in-memory manager only fans out events to
connections held by *this* process. It is NOT safe across multiple
API worker processes/instances.

TODO(production, multi-instance): replace the in-process broadcast with
Redis pub/sub (`settings.REDIS_URL`, already used as the rate-limiter's
optional backend) so an event published by one worker reaches WebSocket
clients connected to any other worker. Sketch: each worker subscribes to a
`queue-events:{clinic_id}` Redis channel on startup and republishes messages
received on that channel to its own local connections, and `broadcast()`
here becomes a `PUBLISH` instead of (or in addition to) iterating
`self._connections` directly.
"""

import json
from collections import defaultdict
from uuid import UUID

from fastapi import WebSocket


class QueueConnectionManager:
    def __init__(self) -> None:
        self._connections: dict[UUID, set[WebSocket]] = defaultdict(set)

    async def connect(self, clinic_id: UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[clinic_id].add(websocket)

    def disconnect(self, clinic_id: UUID, websocket: WebSocket) -> None:
        self._connections[clinic_id].discard(websocket)
        if not self._connections[clinic_id]:
            self._connections.pop(clinic_id, None)

    async def broadcast(self, clinic_id: UUID, event: str, payload: dict) -> None:
        connections = list(self._connections.get(clinic_id, ()))
        if not connections:
            return
        message = json.dumps({"event": event, "data": payload}, default=str)
        for ws in connections:
            try:
                await ws.send_text(message)
            except Exception:  # pragma: no cover - best-effort broadcast
                self.disconnect(clinic_id, ws)


queue_connection_manager = QueueConnectionManager()
