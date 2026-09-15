from __future__ import annotations


def test_me_endpoint_returns_current_admin(client, auth_headers):
    resp = client.get("/api/auth/me", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["email"] == "admin@oxigenioaceleradora.com.br"


def test_list_admins_requires_auth(client):
    resp = client.get("/api/admins")
    assert resp.status_code == 401


def test_create_and_list_admins(client, auth_headers):
    resp = client.post(
        "/api/admins",
        headers=auth_headers,
        json={
            "full_name": "Novo Admin",
            "email": "novo.admin@oxigenioaceleradora.com.br",
            "password": "OutraSenhaForte123!",
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["is_active"] is True

    listed = client.get("/api/admins", headers=auth_headers)
    assert listed.status_code == 200
    emails = {a["email"] for a in listed.json()}
    assert "novo.admin@oxigenioaceleradora.com.br" in emails


def test_create_admin_duplicate_email_rejected(client, auth_headers):
    payload = {
        "full_name": "Duplicado",
        "email": "dup.admin@oxigenioaceleradora.com.br",
        "password": "SenhaForte123!",
    }
    first = client.post("/api/admins", headers=auth_headers, json=payload)
    assert first.status_code == 201
    second = client.post("/api/admins", headers=auth_headers, json=payload)
    assert second.status_code == 409


def test_admin_cannot_deactivate_own_account(client, auth_headers):
    me = client.get("/api/auth/me", headers=auth_headers).json()
    resp = client.patch(f"/api/admins/{me['id']}", headers=auth_headers, json={"is_active": False})
    assert resp.status_code == 400


def test_admin_can_deactivate_another_admin(client, auth_headers):
    created = client.post(
        "/api/admins",
        headers=auth_headers,
        json={
            "full_name": "Para Desativar",
            "email": "desativar@oxigenioaceleradora.com.br",
            "password": "SenhaForte123!",
        },
    ).json()

    resp = client.patch(f"/api/admins/{created['id']}", headers=auth_headers, json={"is_active": False})
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


def test_update_admin_not_found(client, auth_headers):
    resp = client.patch(
        "/api/admins/does-not-exist", headers=auth_headers, json={"full_name": "X"}
    )
    assert resp.status_code == 404
