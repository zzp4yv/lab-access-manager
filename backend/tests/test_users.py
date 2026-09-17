from __future__ import annotations

import io


def test_login_requires_valid_credentials(client, admin_token):
    resp = client.post(
        "/api/auth/login",
        json={"email": "admin@oxigenioaceleradora.com.br", "password": "senha-errada"},
    )
    assert resp.status_code == 401


def test_create_user_requires_auth(client):
    resp = client.post("/api/users", data={"full_name": "X"})
    assert resp.status_code == 401


def test_create_user_happy_path(client, auth_headers):
    resp = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Maria Teste",
            "matricula": "MT-0001",
            "personal_email": "maria@example.com",
            "phone": "+55 11 99999-0000",
            "test_description": "Testar inferência em GPU compartilhada",
            "access_days": "15",
        },
        files={"document": ("proposta.pdf", io.BytesIO(b"%PDF-1.4 fake"), "application/pdf")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "active"
    assert body["matricula"] == "MT-0001"
    # Um registro de provisionamento por ambiente (2x linux + pangolin + next_term)
    assert len(body["provisioning_records"]) == 4
    assert all(r["status"] == "success" for r in body["provisioning_records"])


def test_create_user_rejects_disallowed_file_extension(client, auth_headers):
    resp = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Extensão Inválida",
            "matricula": "EXT-01",
            "personal_email": "ext@example.com",
            "phone": "11922221111",
            "test_description": "Teste de extensão",
            "access_days": "5",
        },
        files={"document": ("script.exe", io.BytesIO(b"MZ fake exe"), "application/octet-stream")},
    )
    assert resp.status_code == 400


def test_create_user_duplicate_matricula_rejected(client, auth_headers):
    payload = {
        "full_name": "Duplicado",
        "matricula": "DUP-01",
        "personal_email": "dup@example.com",
        "phone": "11999999999",
        "test_description": "Teste qualquer",
        "access_days": "5",
    }
    first = client.post("/api/users", headers=auth_headers, data=payload)
    assert first.status_code == 201

    second = client.post("/api/users", headers=auth_headers, data=payload)
    assert second.status_code == 409


def test_list_users_and_dashboard_stats(client, auth_headers):
    client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Usuário Dashboard",
            "matricula": "DASH-01",
            "personal_email": "dash@example.com",
            "phone": "11988887777",
            "test_description": "Teste de benchmark",
            "access_days": "10",
        },
    )

    listed = client.get("/api/users", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    stats = client.get("/api/dashboard/stats", headers=auth_headers)
    assert stats.status_code == 200
    data = stats.json()
    assert data["total_users"] == 1
    assert data["active_users"] == 1


def test_get_user_not_found(client, auth_headers):
    resp = client.get("/api/users/does-not-exist", headers=auth_headers)
    assert resp.status_code == 404


def test_update_user_fields(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Nome Original",
            "matricula": "UPD-01",
            "personal_email": "original@example.com",
            "phone": "11966665555",
            "test_description": "Descrição original",
            "access_days": "10",
        },
    ).json()

    resp = client.patch(
        f"/api/users/{created['id']}",
        headers=auth_headers,
        json={"full_name": "Nome Atualizado", "access_days": 20},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["full_name"] == "Nome Atualizado"
    assert body["access_days"] == 20


def test_update_user_not_found(client, auth_headers):
    resp = client.patch("/api/users/does-not-exist", headers=auth_headers, json={"full_name": "X"})
    assert resp.status_code == 404


def test_retry_provisioning(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Retry User",
            "matricula": "RETRY-01",
            "personal_email": "retry@example.com",
            "phone": "11955554444",
            "test_description": "Teste de retry",
            "access_days": "7",
        },
    ).json()

    resp = client.post(f"/api/users/{created['id']}/retry-provisioning", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_revoke_already_revoked_user_rejected(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Duas Revogações",
            "matricula": "REV-02",
            "personal_email": "duasrev@example.com",
            "phone": "11944443333",
            "test_description": "Teste de dupla revogação",
            "access_days": "5",
        },
    ).json()

    first = client.post(f"/api/users/{created['id']}/revoke-now", headers=auth_headers)
    assert first.status_code == 200

    second = client.post(f"/api/users/{created['id']}/revoke-now", headers=auth_headers)
    assert second.status_code == 400


def test_run_lifecycle_now(client, auth_headers):
    resp = client.post("/api/users/run-lifecycle-now", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"provisioned", "revoked", "purged"}


def test_create_user_invalid_access_days_rejected(client, auth_headers):
    resp = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Access Days Inválido",
            "matricula": "BAD-DAYS",
            "personal_email": "bad@example.com",
            "phone": "11933332222",
            "test_description": "Teste",
            "access_days": "9999",
        },
    )
    assert resp.status_code == 400


def test_revoke_now(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Para Revogar",
            "matricula": "REV-01",
            "personal_email": "revogar@example.com",
            "phone": "11977776666",
            "test_description": "Teste de revogação manual",
            "access_days": "20",
        },
    ).json()

    resp = client.post(f"/api/users/{created['id']}/revoke-now", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "revoked"
    assert body["purge_after"] is not None


def test_delete_user_permanently_removes_record(client, auth_headers):
    created = client.post(
        "/api/users",
        headers=auth_headers,
        data={
            "full_name": "Para Excluir",
            "matricula": "DEL-01",
            "personal_email": "excluir@example.com",
            "phone": "11966665555",
            "test_description": "Teste de exclusão definitiva",
            "access_days": "10",
        },
    ).json()

    resp = client.delete(f"/api/users/{created['id']}", headers=auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["success"] is True

    assert client.get(f"/api/users/{created['id']}", headers=auth_headers).status_code == 404


def test_delete_user_requires_auth(client):
    resp = client.delete("/api/users/algum-id")
    assert resp.status_code == 401


def test_delete_nonexistent_user_returns_404(client, auth_headers):
    resp = client.delete("/api/users/nao-existe", headers=auth_headers)
    assert resp.status_code == 404
