"""Fail-fast when SESSION_SECRET_KEY is weak outside lab/dev."""

from __future__ import annotations

import pytest

from app.settings import Settings, _assert_session_secret


def test_weak_secret_rejected_in_production():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SESSION_SECRET_KEY="dev-only-change-me",
    )
    with pytest.raises(RuntimeError, match="SESSION_SECRET_KEY"):
        _assert_session_secret(settings)


def test_strong_secret_ok_in_production():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="production",
        SESSION_SECRET_KEY="prod-secret-at-least-16",
    )
    _assert_session_secret(settings)


def test_weak_secret_allowed_in_lab():
    settings = Settings(
        _env_file=None,
        ENVIRONMENT="lab",
        SESSION_SECRET_KEY="dev-only-change-me",
    )
    _assert_session_secret(settings)


def test_mcp_allowed_hosts_include_docker_aliases_and_extras():
    settings = Settings(
        _env_file=None,
        PUBLIC_URL="https://ai-agents-dev.example.com",
        MCP_ALLOWED_HOSTS="custom.lab, custom.lab:*",
    )
    hosts = settings.mcp_allowed_hosts
    assert "ai-agents-dev.example.com" in hosts
    assert "ai-agents-dev.example.com:*" in hosts
    assert "127.0.0.1" in hosts
    assert "host.docker.internal" in hosts
    assert "host.docker.internal:*" in hosts
    assert "custom.lab" in hosts
    assert "custom.lab:*" in hosts
