"""ASGI middleware that records API usage (path, status, latency, principal).

Streaming responses (SSE) are measured until their body completes, so a long
run stream shows up with its real duration.
"""

from __future__ import annotations

import re
import time

from app.repos import usage as usage_repo

SKIP_PREFIXES = ("/health", "/docs", "/redoc", "/openapi.json", "/favicon.ico")
SKIP_METHODS = frozenset({"OPTIONS"})
_UUID_RE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
)
_NUMBER_RE = re.compile(r"/\d+(?=/|$)")


def normalize_path(path: str) -> str:
    """Group `/v1/runs/<uuid>` and numeric ids so charts show endpoints, not instances."""
    return _NUMBER_RE.sub("/{n}", _UUID_RE.sub("{id}", path))


class UsageMiddleware:
    def __init__(self, app, session_factory) -> None:
        self.app = app
        self.session_factory = session_factory

    async def __call__(self, scope, receive, send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "")
        if method in SKIP_METHODS or path.startswith(SKIP_PREFIXES):
            await self.app(scope, receive, send)
            return

        started = time.perf_counter()
        status_code: int | None = None

        async def _send(message):
            nonlocal status_code
            if message.get("type") == "http.response.start":
                status_code = int(message.get("status") or 0)
            await send(message)

        try:
            await self.app(scope, receive, _send)
        finally:
            principal = (scope.get("state") or {}).get("principal")
            usage_repo.spawn(
                self.session_factory,
                kind="api",
                method=method,
                path=normalize_path(path),
                status_code=status_code,
                duration_ms=int((time.perf_counter() - started) * 1000),
                principal_kind=getattr(principal, "kind", "") or "",
                principal_id=getattr(principal, "id", "") or "",
            )
