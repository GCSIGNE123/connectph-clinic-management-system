"""Structured request logging middleware.

Phase 16 (Production Hardening) extends the original method/path/status/
duration logging with a request-ID: every inbound request is assigned a
UUID (reused from the client's `X-Request-ID` header if it already sent
one, e.g. from an upstream gateway), the id is stashed on `request.state`
so any handler/service/exception handler can pick it up for its own log
lines, included in this middleware's own structured log line, and returned
on the response as `X-Request-ID` - so a single request can be traced
end-to-end through logs (client -> access log -> any error log) without
needing timestamps/IP-address correlation.
"""

import logging
import time
import uuid

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Logs method, path, status code, duration, and request-id for every request."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get(REQUEST_ID_HEADER) or str(uuid.uuid4())
        request.state.request_id = request_id

        start_time = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start_time) * 1000

        response.headers[REQUEST_ID_HEADER] = request_id

        clinic_id = getattr(request.state, "clinic_id", None)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": round(duration_ms, 2),
                "clinic_id": clinic_id,
            },
        )
        return response
