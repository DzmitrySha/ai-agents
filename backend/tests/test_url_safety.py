"""SSRF guard for outbound HTTP URLs."""

from __future__ import annotations

import ipaddress
import socket

import pytest

from app.agents.url_safety import UnsafeUrlError, assert_public_http_url
from tests.conftest import AUTH

TOOL = {
    "slug": "ssrf",
    "name": "SSRF",
    "description": "probe",
    "method": "GET",
    "url": "https://example.com/{q}",
    "headers": {},
    "query": {},
    "parameters": [{"name": "q", "type": "string", "required": True}],
    "timeout_seconds": 5,
}


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/secret",
        "https://localhost/x",
        "http://10.0.0.5/admin",
        "http://192.168.1.1/",
        "http://169.254.169.254/latest/meta-data/",
        "http://[::1]/",
        "http://user:pass@example.com/",
        "ftp://example.com/",
        "https://{host}/path",
    ],
)
def test_assert_rejects_unsafe_urls(url: str):
    with pytest.raises(UnsafeUrlError):
        assert_public_http_url(url, resolve=False)


def test_assert_allows_public_shape_without_dns():
    assert assert_public_http_url("https://api.example.com/v1/{id}", resolve=False)


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("http://host.docker.internal:8811/mcp", ["host.docker.internal"]),
        ("http://192.168.65.254:8811/mcp", ["192.168.65.0/24"]),
        ("http://mcp.corp.local/mcp", ["*.corp.local"]),
    ],
)
def test_assert_allows_allowlisted_private_targets(url: str, allowed: list[str]):
    assert assert_public_http_url(url, allowed_hosts=allowed)


def test_assert_allowlist_does_not_leak_to_other_hosts(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        del port, args, kwargs
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.9.9.9", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="non-public"):
        assert_public_http_url(
            "http://other.internal/mcp", allowed_hosts=["allowed.internal"]
        )


def test_assert_rejects_hostname_resolving_to_private(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        del port, args, kwargs
        assert host == "evil.internal"
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.1.2.3", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(UnsafeUrlError, match="non-public"):
        assert_public_http_url("https://evil.internal/mcp", resolve=True)


def test_assert_allows_hostname_resolving_to_public(monkeypatch):
    def fake_getaddrinfo(host, port, *args, **kwargs):
        del port, args, kwargs
        return [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0)),
        ]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert assert_public_http_url("https://example.com/ok", resolve=True)
    # sanity: public IP helper
    assert not ipaddress.ip_address("93.184.216.34").is_private


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://10.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://localhost/x",
    ],
)
def test_create_tool_rejects_ssrf_urls(client, url: str):
    response = client.post(
        "/v1/tools",
        json={**TOOL, "slug": "bad-ssrf", "url": url},
        headers=AUTH,
    )
    assert response.status_code == 422, response.text


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/mcp",
        "http://169.254.169.254/mcp",
        "http://localhost/mcp",
    ],
)
def test_create_mcp_connection_rejects_ssrf_urls(client, url: str):
    response = client.post(
        "/v1/mcp-connections",
        json={
            "slug": "bad-mcp",
            "name": "Bad",
            "url": url,
            "headers": {},
            "timeout_seconds": 10,
            "enabled": True,
        },
        headers=AUTH,
    )
    assert response.status_code == 422, response.text


def test_create_mcp_connection_allows_egress_allowlist(client, monkeypatch):
    from app.settings import get_settings

    monkeypatch.setenv("MCP_EGRESS_ALLOWED_HOSTS", "192.168.65.0/24,*.corp.local")
    get_settings.cache_clear()
    try:
        for slug, url in [
            ("gw", "http://192.168.65.254:8811/mcp"),
            ("corp", "http://mcp.corp.local/mcp"),
        ]:
            response = client.post(
                "/v1/mcp-connections",
                json={
                    "slug": slug,
                    "name": slug,
                    "url": url,
                    "headers": {},
                    "timeout_seconds": 10,
                    "enabled": True,
                },
                headers=AUTH,
            )
            assert response.status_code == 201, response.text
    finally:
        get_settings.cache_clear()
