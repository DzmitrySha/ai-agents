"""Bootstrap superadmin (SUPERADMIN_EMAILS) — единственный, кто управляет суперадминами."""

from __future__ import annotations

BOOTSTRAP_EMAIL = "admin@example.com"

USER = {"sub": "candidate", "email": "candidate@example.test", "display_name": "Кандидат"}
ADMIN = {"sub": "deputy", "email": "deputy@example.test", "display_name": "Заместитель"}


def test_me_reports_bootstrap_capability(client, login):
    bootstrap = login("root", is_superadmin=True, email=BOOTSTRAP_EMAIL)
    me = client.get("/auth/me", headers=bootstrap).json()["user"]
    assert me["can_manage_superadmins"] is True
    assert me["app_role"] == "superadmin"
    assert me["name"] == "root"  # display_name из UserIdentity

    regular = login("boss", is_superadmin=True)
    other = client.get("/auth/me", headers=regular).json()["user"]
    assert other["can_manage_superadmins"] is False


def test_bootstrap_appoints_and_demotes_superadmins(client, login):
    headers = login("root", is_superadmin=True, email=BOOTSTRAP_EMAIL)

    created = client.post(
        "/api/admin/users", json={**USER, "app_role": "superadmin"}, headers=headers
    )
    assert created.status_code == 201, created.text
    assert created.json()["app_role"] == "superadmin"
    assert created.json()["is_superadmin"] is True

    demoted = client.patch(
        "/api/admin/users/candidate", json={"app_role": "admin"}, headers=headers
    )
    assert demoted.status_code == 200, demoted.text
    assert demoted.json()["app_role"] == "admin"
    assert demoted.json()["is_superadmin"] is False

    promoted = client.patch(
        "/api/admin/users/candidate", json={"app_role": "superadmin"}, headers=headers
    )
    assert promoted.status_code == 200, promoted.text
    assert promoted.json()["is_superadmin"] is True


def test_regular_superadmin_cannot_touch_superadmins(client, login):
    bootstrap = login("root", is_superadmin=True, email=BOOTSTRAP_EMAIL)
    assert (
        client.post(
            "/api/admin/users",
            json={**USER, "app_role": "superadmin"},
            headers=bootstrap,
        ).status_code
        == 201
    )
    assert (
        client.post(
            "/api/admin/users", json={**ADMIN, "app_role": "admin"}, headers=bootstrap
        ).status_code
        == 201
    )

    regular = login("boss", is_superadmin=True)

    # создать суперадмина нельзя
    blocked_create = client.post(
        "/api/admin/users",
        json={"sub": "third", "email": "third@example.test", "app_role": "superadmin"},
        headers=regular,
    )
    assert blocked_create.status_code == 403, blocked_create.text
    assert "bootstrap" in blocked_create.json()["detail"]

    # понизить существующего суперадмина нельзя
    blocked_demote = client.patch(
        "/api/admin/users/candidate", json={"app_role": "admin"}, headers=regular
    )
    assert blocked_demote.status_code == 403, blocked_demote.text

    # повысить админа до суперадмина нельзя
    blocked_promote = client.patch(
        "/api/admin/users/deputy", json={"app_role": "superadmin"}, headers=regular
    )
    assert blocked_promote.status_code == 403, blocked_promote.text

    # но обычные роли менять можно
    allowed = client.patch(
        "/api/admin/users/deputy", json={"app_role": "user"}, headers=regular
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["app_role"] == "user"
    assert (
        client.patch(
            "/api/admin/users/deputy", json={"app_role": "admin"}, headers=regular
        ).status_code
        == 200
    )


def test_bootstrap_account_cannot_be_demoted(client, login):
    bootstrap = login("root", is_superadmin=True, email=BOOTSTRAP_EMAIL)
    response = client.patch(
        "/api/admin/users/root", json={"app_role": "admin"}, headers=bootstrap
    )
    assert response.status_code == 409, response.text
    assert "bootstrap" in response.json()["detail"]
