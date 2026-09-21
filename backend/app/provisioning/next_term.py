"""Adaptador de provisionamento para o Nexterm (github.com/gnmyt/Nexterm),
usado para conceder acesso via shell (SSH) e RDP.

API real confirmada em produção (ver docs.nexterm.dev/api-reference):
  - Base: NEXT_TERM_API_URL + "/api" (ex.: http://192.168.10.28:6989/api)
  - Auth: header "Authorization: Bearer <token>" (token com prefixo "nxt_")
  - PUT  /users              cria conta (campos obrigatórios: username,
    password, firstName, lastName) — não aceita e-mail nem protocolo,
    o acesso SSH/RDP é definido depois pelo próprio usuário/via grupo.
  - GET  /users/list?search= busca por username (não há endpoint por
    username direto; local izamos o accountId numérico assim antes de
    revogar/purgar).
  - DELETE /users/{accountId}         remove a conta definitivamente.
  - Não existe endpoint de "desativar sem apagar": a revogação é feita
    trocando a senha para um valor aleatório que não é comunicado a
    ninguém, efetivamente bloqueando novos logins sem apagar a conta
    (os dados/sessões residuais somem só na purga).

Máquinas pré-configuradas no perfil (SSH/RDP para tars e case):
  - Entradas ("entries") e credenciais ("identities") são estritamente
    pessoais — vinculadas à conta que as cria, sem qualquer campo para
    criar "em nome de" outra conta (a API rejeita com "accountId is
    not allowed"). Não existe organização configurada nessa instância
    para compartilhar entradas entre contas.
  - Contorno: POST /users/{accountId}/login ("impersonate", exige a
    permissão "users.impersonate" na API key) devolve um token de
    sessão da própria conta criada; usando esse token (em vez da API
    key do sistema) para criar as entradas, elas passam a pertencer de
    fato à nova conta — confirmado manualmente antes de implementar.
  - As entradas não recebem identidade/credencial (senha de SSH/RDP)
    — o mesmo padrão já usado no perfil de referência (zzp4yv), onde
    "TARS ssh" também não tem identidade associada.
"""
from __future__ import annotations

import logging
import secrets
import socket
from datetime import datetime

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment
from app.provisioning.base import ProvisioningAdapter, ProvisioningResult

logger = logging.getLogger("provisioning.next_term")


class NextTermProvisioner(ProvisioningAdapter):
    environment = ProvisioningEnvironment.NEXT_TERM

    def __init__(self):
        self.settings = get_settings()

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=f"{self.settings.NEXT_TERM_API_URL.rstrip('/')}/api",
            headers={
                "Authorization": f"Bearer {self.settings.NEXT_TERM_API_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def _find_account_id(self, client, username: str) -> int | None:
        resp = client.get("/users/list", params={"search": username})
        resp.raise_for_status()
        for account in resp.json().get("users", []):
            if account.get("username") == username:
                return account.get("id")
        return None

    def _resolve_ip(self, hostname: str) -> str:
        try:
            return socket.gethostbyname(hostname)
        except OSError:
            return hostname

    def _session_client(self, session_token: str):
        import httpx

        return httpx.Client(
            base_url=f"{self.settings.NEXT_TERM_API_URL.rstrip('/')}/api",
            headers={"Authorization": f"Bearer {session_token}", "Content-Type": "application/json"},
            timeout=15.0,
        )

    def _create_default_entries(self, admin_client, account_id: int) -> None:
        """Cria as entradas SSH/RDP de tars e case no perfil da conta
        recém-criada, usando um token de sessão dela mesma (ver
        docstring do módulo — a API não permite criar em nome de
        outra conta pela API key do sistema). Idempotente: pula
        entradas cujo nome já existe (o orquestrador reprovisiona todos
        os ambientes a cada retry, mesmo os que já tiveram sucesso)."""
        resp = admin_client.post(f"/users/{account_id}/login")
        resp.raise_for_status()
        session_token = resp.json().get("token")
        if not session_token:
            return

        with self._session_client(session_token) as session_client:
            existing = session_client.get("/entries/list")
            existing.raise_for_status()
            existing_names = {entry.get("name") for entry in existing.json()}

            for host in self.settings.LINUX_HOSTS:
                ip = self._resolve_ip(host)
                ssh_name, rdp_name = f"{host} ssh", f"{host} rdp"
                if ssh_name not in existing_names:
                    session_client.put(
                        "/entries",
                        json={
                            "type": "server",
                            "name": ssh_name,
                            "icon": "mdiConsole",
                            "config": {"protocol": "ssh", "ip": ip, "port": "22"},
                        },
                    )
                if rdp_name not in existing_names:
                    session_client.put(
                        "/entries",
                        json={
                            "type": "server",
                            "name": rdp_name,
                            "icon": "mdiMicrosoftWindows",
                            "config": {"protocol": "rdp", "ip": ip, "port": "3389"},
                        },
                    )

    def provision(self, user: LabUser) -> ProvisioningResult:
        username = user.matricula
        first_name, _, last_name = user.full_name.strip().partition(" ")
        # Senha determinística: primeiro nome em minúsculo + ano atual (4 dígitos)
        password = f"{first_name.lower()}{datetime.now().year}"
        payload = {
            "username": username,
            "password": password,
            "firstName": first_name or username,
            "lastName": last_name or "-",
        }

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][next_term] criaria conta: %s", {**payload, "password": "***"})
            return ProvisioningResult(success=True, external_identifier=username, message="dry-run")

        try:
            with self._client() as client:
                resp = client.put("/users", json=payload)
                resp.raise_for_status()

                entries_note = ""
                account_id = self._find_account_id(client, username)
                if account_id is not None:
                    try:
                        self._create_default_entries(client, account_id)
                    except Exception:  # noqa: BLE001
                        logger.exception("[next_term] falha ao criar entradas padrão para %s", username)
                        entries_note = " (máquinas padrão não puderam ser criadas automaticamente)"

                return ProvisioningResult(
                    success=True,
                    external_identifier=username,
                    message=(
                        f"criado — usuário: {username} / senha inicial: {password} "
                        "(comunicar ao visitante por canal seguro; não é mostrada de novo)" + entries_note
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def revoke(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a revogar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][next_term] revogaria acesso %s", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                account_id = self._find_account_id(client, external_identifier)
                if account_id is None:
                    return ProvisioningResult(
                        success=True, external_identifier=external_identifier, message="conta já não existe"
                    )
                resp = client.patch(
                    f"/users/{account_id}/password", json={"password": secrets.token_urlsafe(24)}
                )
                resp.raise_for_status()
                return ProvisioningResult(success=True, external_identifier=external_identifier, message="revogado")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def purge(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a purgar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][next_term] removeria conta %s definitivamente", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                account_id = self._find_account_id(client, external_identifier)
                if account_id is None:
                    return ProvisioningResult(
                        success=True, external_identifier=external_identifier, message="conta já não existia"
                    )
                resp = client.delete(f"/users/{account_id}")
                resp.raise_for_status()
                return ProvisioningResult(success=True, external_identifier=external_identifier, message="removido")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def check_last_access(self, user: LabUser, external_identifier: str | None) -> str | None:
        """Não há um endpoint confirmado de "último login por usuário" na
        API do Nexterm — deixado como no-op até validarmos isso."""
        return None
