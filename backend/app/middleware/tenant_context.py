"""Middleware that extracts the tenant (clinic_id) from the JWT into request.state."""

import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.security import TokenPayloadError, TokenType, decode_token

logger = logging.getLogger(__name__)


class TenantContextMiddleware(BaseHTTPMiddleware):
    """Best-effort extraction of clinic_id/user_id/role from the Authorization header.

    Populates `request.state.clinic_id`, `request.state.user_id`, and
    `request.state.role` when a valid bearer access token is present. Does not
    reject requests on missing/invalid tokens: authorization enforcement is the
    responsibility of route-level dependencies (see app.core.dependencies).
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.clinic_id = None
        request.state.user_id = None
        request.state.role = None

        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.lower().startswith("bearer "):
            token = auth_header.split(" ", 1)[1]
            try:
                payload = decode_token(token, expected_type=TokenType.ACCESS)
                request.state.clinic_id = payload.get("clinic_id")
                request.state.user_id = payload.get("user_id")
                request.state.role = payload.get("role")
            except TokenPayloadError:
                logger.debug("Could not extract tenant context from token", exc_info=False)

        return await call_next(request)
