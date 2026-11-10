"""Platform doctor endpoint and individual check contracts."""

from __future__ import annotations

from pathlib import Path

from tests.conftest import AUTH

CHECKS = [
    "db",
    "migrations",
    "llm",
    "mcp",
    "auth",
    "storage",
    "queue",
    "retention",
    "approvals",
    "runs",
]


def test_doctor_returns_checks(client, settings, monkeypatch, tmp_path):
    from app.runtime import doctor
    from app.runtime.models import DoctorCheck

    settings.storage_path = str(tmp_path)
    Path(tmp_path).mkdir(exist_ok=True)

    async def ok(check_id: str):
        return DoctorCheck(id=check_id, status="ok", message="ok")

    monkeypatch.setattr(doctor, "_check_migrations", lambda _s: ok("migrations"))
    monkeypatch.setattr(doctor, "_check_llm", lambda: ok("llm"))
    monkeypatch.setattr(doctor, "_check_mcp", lambda _s: ok("mcp"))

    response = client.get("/v1/doctor", headers=AUTH)
    assert response.status_code == 200, response.text
    body = response.json()
    assert [item["id"] for item in body["checks"]] == CHECKS
    assert body["ok"] is True
    assert all("duration_ms" in item for item in body["checks"])


def test_doctor_requires_admin(client, login):
    headers = login("doctor-user", app_role="user")
    assert client.get("/v1/doctor", headers=headers).status_code == 403
