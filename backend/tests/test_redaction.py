"""Secret redaction in diagnostics and logs."""

from __future__ import annotations

from tests.conftest import AUTH


def test_redact_text_patterns():
    from app.redaction import redact_text

    assert redact_text("Authorization: Bearer abc123") == "Authorization: Bearer ***"
    assert "abc123" not in redact_text("token=abc123")
    assert redact_text("sk-abcdefghijklmnop") == "sk-***"
    assert redact_text("sk-lm-XqOP******") == "sk-***"
    assert redact_text("ghp_abcdefghijklmnopqrst") == "ghp_***"
    assert "xoxb-secret-token" not in redact_text("xoxb-secret-token")
    assert "p" not in redact_text("postgresql://u:p@h/db").split("://", 1)[1].split("@", 1)[0]


def test_run_error_and_log_are_redacted(client, fake_graph):
    fake_graph(failure=RuntimeError("Authorization: Bearer abc123"))
    agent = client.post(
        "/v1/agents",
        json={
            "slug": "redact-runner",
            "name": "Redact",
            "system_prompt": "hi",
        },
        headers=AUTH,
    ).json()
    client.post(
        f"/v1/agents/{agent['slug']}/publish",
        json={"visibility": "shared"},
        headers=AUTH,
    )
    run_id = client.post(
        "/v1/runs", json={"agent_id": agent["slug"], "input": "hi"}, headers=AUTH
    ).json()["run_id"]

    import time

    deadline = time.time() + 5
    run = {}
    while time.time() < deadline:
        run = client.get(f"/v1/runs/{run_id}", headers=AUTH).json()
        if run["status"] == "failed":
            break
        time.sleep(0.02)
    assert run["error"].endswith("Authorization: Bearer ***")
    assert "abc123" not in run["error"]

    from app.logging_setup import logger

    messages: list[str] = []
    handle = logger.add(lambda message: messages.append(message), format="{message}")
    try:
        logger.warning("Authorization: Bearer abc123")
    finally:
        logger.remove(handle)
    assert any("Bearer ***" in message for message in messages)
    assert all("abc123" not in message for message in messages)
