"""Delivery outbox: webhook and Telegram notifications for terminal runs."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from datetime import datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import select

from app.agents.url_safety import assert_public_http_url
from app.logging_setup import logger
from app.models import DeliveryRow, NotificationChannelRow, RunRow, utcnow
from app.redaction import redact_text
from app.settings import Settings

TELEGRAM_LIMIT = 4000
DELIVERY_TIMEOUT_SECONDS = 15.0


def _payload(run: RunRow) -> dict[str, Any]:
    return {
        "run_id": run.id,
        "agent_id": run.agent_slug,
        "status": run.status,
        "output": run.output,
        "error": run.error,
        "failure_kind": run.failure_kind,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
    }


def _telegram_text(run: RunRow) -> str:
    parts = [
        f"Run {run.id}",
        f"Agent: {run.agent_slug}",
        f"Status: {run.status}",
    ]
    if run.error:
        parts.append(f"Error: {run.error}")
    elif run.output:
        parts.append(run.output)
    return "\n".join(parts)[:TELEGRAM_LIMIT]


async def enqueue_for_run(session_factory, run_id: str) -> None:
    try:
        async with session_factory() as session:
            run = await session.get(RunRow, run_id)
            if run is None or run.status not in {"succeeded", "failed", "cancelled"}:
                return
            channels = list(
                (
                    await session.execute(
                        select(NotificationChannelRow).where(
                            NotificationChannelRow.enabled.is_(True)
                        )
                    )
                ).scalars()
            )
            if not channels:
                return
            existing = set(
                (
                    await session.execute(
                        select(DeliveryRow.channel_id).where(
                            DeliveryRow.run_id == run_id
                        )
                    )
                ).scalars()
            )
            now = utcnow()
            for channel in channels:
                if channel.id in existing:
                    continue
                session.add(
                    DeliveryRow(
                        run_id=run_id,
                        channel_id=channel.id,
                        status="pending",
                        attempts=0,
                        next_attempt_at=now,
                    )
                )
            await session.commit()
    except Exception as exc:  # noqa: BLE001 - delivery must never break a run
        logger.warning("delivery enqueue failed: {}", exc)


async def _send_webhook(
    channel: NotificationChannelRow, run: RunRow
) -> None:
    if not channel.url:
        raise ValueError("webhook URL is empty")
    assert_public_http_url(channel.url)
    body = json.dumps(_payload(run), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if channel.secret:
        digest = hmac.new(
            channel.secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        headers["X-Ai-Agents-Signature"] = f"sha256={digest}"
    async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
        response = await client.post(channel.url, content=body, headers=headers)
    if response.status_code >= 400:
        raise RuntimeError(f"webhook HTTP {response.status_code}: {response.text[:200]}")


async def _send_telegram(
    channel: NotificationChannelRow, run: RunRow, settings: Settings
) -> None:
    token = (settings.telegram_bot_token or "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is empty")
    if not channel.chat_id:
        raise ValueError("chat_id is empty")
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        async with httpx.AsyncClient(timeout=DELIVERY_TIMEOUT_SECONDS) as client:
            response = await client.post(
                url,
                json={"chat_id": channel.chat_id, "text": _telegram_text(run)},
            )
    except Exception as exc:  # noqa: BLE001 - URL contains the bot token
        raise RuntimeError(
            f"telegram request failed: {type(exc).__name__}"
        ) from None
    if response.status_code >= 400:
        raise RuntimeError(f"telegram HTTP {response.status_code}: {response.text[:200]}")


async def _deliver(
    channel: NotificationChannelRow, run: RunRow, settings: Settings
) -> None:
    if channel.kind == "webhook":
        await _send_webhook(channel, run)
    elif channel.kind == "telegram":
        await _send_telegram(channel, run, settings)
    else:
        raise ValueError(f"unknown channel kind {channel.kind}")


async def run_delivery_queue(
    session_factory,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> int:
    current = now or utcnow()
    async with session_factory() as session:
        stmt = (
            select(DeliveryRow)
            .where(
                DeliveryRow.status == "pending",
                DeliveryRow.next_attempt_at.is_not(None),
                DeliveryRow.next_attempt_at <= current,
            )
            .order_by(DeliveryRow.next_attempt_at)
            .limit(50)
            .with_for_update(skip_locked=True)
        )
        ids = [row.id for row in (await session.execute(stmt)).scalars()]
    processed = 0
    for delivery_id in ids:
        async with session_factory() as session:
            delivery = await session.get(DeliveryRow, delivery_id)
            if delivery is None or delivery.status != "pending":
                continue
            channel = await session.get(NotificationChannelRow, delivery.channel_id)
            run = await session.get(RunRow, delivery.run_id)
            if (
                channel is None
                or not channel.enabled
                or run is None
            ):
                delivery.status = "failed"
                delivery.last_error = "channel or run is unavailable"
                await session.commit()
                continue
            try:
                await _deliver(channel, run, settings)
                delivery.status = "sent"
                delivery.attempts += 1
                delivery.sent_at = current
                delivery.last_error = None
            except Exception as exc:  # noqa: BLE001 - retry/fail per delivery
                delivery.attempts += 1
                delivery.last_error = redact_text(
                    f"{type(exc).__name__}: {exc}"
                )[:2000]
                if delivery.attempts >= settings.run_delivery_max_attempts:
                    delivery.status = "failed"
                else:
                    delay = min(5 * (2 ** (delivery.attempts - 1)), 300)
                    delivery.next_attempt_at = current + timedelta(seconds=delay)
            await session.commit()
            processed += 1
    return processed


async def delivery_loop(session_factory, settings: Settings) -> None:
    while True:
        try:
            await run_delivery_queue(session_factory, settings)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - keep the loop alive
            logger.warning("delivery loop failed: {}", exc)
        await asyncio.sleep(max(1, settings.run_delivery_poll_seconds))
