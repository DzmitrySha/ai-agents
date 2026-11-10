"""Failure taxonomy for run retry/fallback decisions."""

from __future__ import annotations

import asyncio

from app.runtime.models import FailureKind

RETRYABLE_KINDS = frozenset(
    {FailureKind.transient.value, FailureKind.rate_limit.value}
)


def _status_code(exc: BaseException) -> int | None:
    for source in (exc, getattr(exc, "response", None)):
        if source is None:
            continue
        for attr in ("status_code", "status"):
            value = getattr(source, attr, None)
            if isinstance(value, int):
                return value
    return None


def classify_failure(
    exc: BaseException | None,
    *,
    timed_out: bool = False,
    token_budget: bool = False,
    step_limit: bool = False,
    tool_calls: int = 0,
    approval_rejected: bool = False,
    cancelled: bool = False,
) -> str:
    """Map an exception to a stable FailureKind value.

    Tool failures are never retried in P1: a tool may have executed side effects.
    """
    if cancelled:
        return FailureKind.cancelled.value
    if token_budget:
        return FailureKind.token_budget.value
    if step_limit:
        return FailureKind.step_limit.value
    if approval_rejected:
        return FailureKind.approval_rejected.value
    if tool_calls:
        return FailureKind.tool.value
    if timed_out or isinstance(exc, (TimeoutError, asyncio.TimeoutError)):
        return FailureKind.timeout.value
    if exc is None:
        return FailureKind.internal.value

    status = _status_code(exc)
    if status == 429:
        return FailureKind.rate_limit.value
    if status is not None and status >= 500:
        return FailureKind.transient.value

    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "ratelimit" in name or "rate limit" in text or "too many requests" in text:
        return FailureKind.rate_limit.value
    if "timeout" in name or "timed out" in text:
        return FailureKind.timeout.value
    if (
        "connection" in name
        or "apiconnection" in name
        or "internalserver" in name
        or "service unavailable" in text
        or "bad gateway" in text
        or "stream" in text and "closed" in text
    ):
        return FailureKind.transient.value
    return FailureKind.internal.value


def failure_is_retryable(kind: str, *, tool_calls: int) -> bool:
    return kind in RETRYABLE_KINDS and tool_calls == 0


def redacted_error(exc: BaseException) -> str:
    from app.redaction import redact_text

    return redact_text(f"{type(exc).__name__}: {exc}")


__all__ = [
    "RETRYABLE_KINDS",
    "classify_failure",
    "failure_is_retryable",
    "redacted_error",
]
