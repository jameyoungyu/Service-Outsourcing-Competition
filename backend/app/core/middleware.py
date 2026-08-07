import logging
import time
from uuid import UUID, uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logging import request_id_context

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    supplied = request.headers.get("X-Request-ID")
    if supplied:
        try:
            parsed = UUID(supplied)
            if parsed.version == 4:
                return str(parsed)
        except ValueError:
            pass
    return str(uuid4())


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a UUIDv4 request id, response header and structured completion log."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = _request_id(request)
        request.state.request_id = request_id
        context_token = request_id_context.set(request_id)
        start = time.perf_counter()
        try:
            response = await call_next(request)
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            response.headers["X-Request-ID"] = request_id
            logger.info(
                "request_completed",
                extra={
                    "duration_ms": duration_ms,
                    "status_code": response.status_code,
                    "method": request.method,
                    "path": request.url.path,
                },
            )
            return response
        finally:
            request_id_context.reset(context_token)
