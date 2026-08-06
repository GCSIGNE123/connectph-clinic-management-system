"""WebSocket endpoint broadcasting live queue events for a clinic.

`GET /api/v1/ws/queues/{clinic_id}?token=<access_token>` - upgrades to a
WebSocket connection and streams JSON messages `{"event": "...", "data": {...}}`
for `queue.created` / `queue.updated` / `queue.status_changed`, published by
`QueueService` via `app.core.ws_manager.queue_connection_manager`.

This channel exists so the Reception Dashboard can subscribe to live updates
instead of polling, and (Phase 13) so the public/private TV Display can
attach to the exact same channel rather than a separate one - see
docs/API.md's WebSocket section for the "why one channel, not two" rationale.
See `ws_manager.py` for the documented Redis pub/sub TODO needed before
running more than one API worker process in production.

Auth (extended in Phase 13): WebSocket handshakes cannot carry an
`Authorization` header from a browser `WebSocket` client, so a credential is
passed as the `token` query param. Two distinct credential types are
accepted:

1. A normal JWT access token (unchanged Phase 5 behavior) - its
   `clinic_id` claim must match the `{clinic_id}` path segment.
2. (Phase 13, new) A TV display's `public_slug` - looked up via
   `TvDisplayConfigRepository.get_by_public_slug`, which already enforces
   `is_public=True, is_active=True, is_deleted=False`. If it resolves, the
   connection is scoped to *that display config's own* `clinic_id`
   (ignoring/overriding the `{clinic_id}` path segment - a public display
   only ever needs to hear events for its own clinic, and trusting the URL
   segment instead of the resolved value would let a slug be replayed
   against an arbitrary clinic_id in the path). This was chosen over
   minting short-lived JWTs for anonymous kiosks: it reuses the exact same
   secret-token-as-credential model the public HTTP endpoint already uses,
   requires no new token-issuance/rotation machinery, and revoking display
   access is just deleting/deactivating the `TvDisplayConfig` row (which
   already invalidates the HTTP endpoint too).

A token that is neither a valid JWT nor a valid public slug is rejected
with policy-violation close code 1008, same as before.
"""

from uuid import UUID

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status

from app.core.security import TokenPayloadError, TokenType, decode_token
from app.core.ws_manager import queue_connection_manager
from app.db.session import AsyncSessionLocal
from app.repositories.tv_display_repository import TvDisplayConfigRepository

router = APIRouter(tags=["queues-ws"])


async def _resolve_clinic_id_from_public_slug(token: str) -> UUID | None:
    """Returns the clinic_id a TV display public_slug resolves to, or None
    if `token` isn't a known, active, public slug. Uses its own short-lived
    session since WebSocket handlers sit outside the normal `Depends(get_db)`
    request-scoped-session flow."""
    async with AsyncSessionLocal() as session:
        repo = TvDisplayConfigRepository(session)
        config = await repo.get_by_public_slug(token)
        return config.clinic_id if config is not None else None


@router.websocket("/ws/queues/{clinic_id}")
async def queue_events_ws(websocket: WebSocket, clinic_id: UUID) -> None:
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    resolved_clinic_id: UUID | None = None
    try:
        payload = decode_token(token, expected_type=TokenType.ACCESS)
        token_clinic_id = payload.get("clinic_id")
        if token_clinic_id is not None and UUID(token_clinic_id) == clinic_id:
            resolved_clinic_id = clinic_id
    except TokenPayloadError:
        pass

    if resolved_clinic_id is None:
        # Not a valid JWT for this clinic - try it as a TV display public
        # slug instead (Phase 13). See module docstring for the rationale.
        resolved_clinic_id = await _resolve_clinic_id_from_public_slug(token)

    if resolved_clinic_id is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    clinic_id = resolved_clinic_id
    await queue_connection_manager.connect(clinic_id, websocket)
    try:
        while True:
            # No inbound protocol yet - this channel is broadcast-only. We
            # still need to await something so the connection stays open and
            # `WebSocketDisconnect` is raised promptly when the client closes.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        queue_connection_manager.disconnect(clinic_id, websocket)
