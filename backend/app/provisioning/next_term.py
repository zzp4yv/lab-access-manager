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
"""
from __future__ import annotations

import logging
import secrets

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment
from app.provisioning.base import ProvisioningAdapter, ProvisioningResult, nextterm_username

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

    def provision(self, user: LabUser) -> ProvisioningResult:
        username = nextterm_username(user.full_name, user.matricula)
        first_name, _, last_name = user.full_name.strip().partition(" ")
        password = secrets.token_urlsafe(12)
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
                return ProvisioningResult(
                    success=True,
                    external_identifier=username,
                    message=(
                        f"criado — usuário: {username} / senha inicial: {password} "
                        "(comunicar ao visitante por canal seguro; não é mostrada de novo)"
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
