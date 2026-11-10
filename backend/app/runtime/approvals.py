"""In-process gate for human tool approvals (single backend replica)."""

from __future__ import annotations

import asyncio

from app.agents.approval import ApprovalDenied


class ApprovalGate:
    def __init__(self) -> None:
        self._pending: dict[str, asyncio.Future[bool]] = {}
        self._by_run: dict[str, set[str]] = {}

    def register(self, run_id: str, approval_id: str) -> asyncio.Future[bool]:
        future = asyncio.get_running_loop().create_future()
        self._pending[approval_id] = future
        self._by_run.setdefault(run_id, set()).add(approval_id)
        return future

    def unregister(self, run_id: str, approval_id: str) -> None:
        self._pending.pop(approval_id, None)
        ids = self._by_run.get(run_id)
        if ids is not None:
            ids.discard(approval_id)
            if not ids:
                self._by_run.pop(run_id, None)

    async def wait(
        self, future: asyncio.Future[bool], timeout: float
    ) -> bool:
        try:
            return await asyncio.wait_for(future, timeout)
        except TimeoutError as exc:
            raise ApprovalDenied("approval timed out") from exc

    def resolve(self, approval_id: str, approved: bool) -> bool:
        future = self._pending.get(approval_id)
        if future is None or future.done():
            return False
        future.set_result(approved)
        return True

    def cancel_run(self, run_id: str) -> int:
        ids = list(self._by_run.get(run_id, ()))
        for approval_id in ids:
            future = self._pending.get(approval_id)
            if future is not None and not future.done():
                future.set_result(False)
        return len(ids)

    def pending_ids(self, run_id: str) -> list[str]:
        return list(self._by_run.get(run_id, ()))
