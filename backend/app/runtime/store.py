"""Live SSE fan-out; event history lives in PostgreSQL (`run_events`)."""

from __future__ import annotations

import asyncio
import time

from app.runtime.models import RunEvent

# Closed run ids linger so late subscribers get an immediate EOF; prune after TTL.
_CLOSED_TTL_SECONDS = 300.0


class LiveHub:
    """Per-run subscriber queues for in-flight events."""

    def __init__(self, *, closed_ttl_seconds: float = _CLOSED_TTL_SECONDS) -> None:
        self._subscribers: dict[str, set[asyncio.Queue[RunEvent | None]]] = {}
        self._closed_at: dict[str, float] = {}
        self._closed_ttl_seconds = closed_ttl_seconds

    def _prune_closed(self, now: float | None = None) -> None:
        deadline = (now if now is not None else time.monotonic()) - self._closed_ttl_seconds
        stale = [run_id for run_id, closed_at in self._closed_at.items() if closed_at <= deadline]
        for run_id in stale:
            self._closed_at.pop(run_id, None)

    async def subscribe(self, run_id: str) -> asyncio.Queue[RunEvent | None]:
        self._prune_closed()
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        if run_id in self._closed_at:
            queue.put_nowait(None)
            return queue
        self._subscribers.setdefault(run_id, set()).add(queue)
        return queue

    async def unsubscribe(
        self, run_id: str, queue: asyncio.Queue[RunEvent | None]
    ) -> None:
        subscribers = self._subscribers.get(run_id)
        if subscribers is not None:
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(run_id, None)

    async def publish(self, run_id: str, event: RunEvent) -> None:
        if run_id in self._closed_at:
            return
        for queue in list(self._subscribers.get(run_id, ())):
            queue.put_nowait(event)

    async def close(self, run_id: str) -> None:
        self._prune_closed()
        if run_id in self._closed_at:
            return
        self._closed_at[run_id] = time.monotonic()
        for queue in self._subscribers.pop(run_id, set()):
            queue.put_nowait(None)
