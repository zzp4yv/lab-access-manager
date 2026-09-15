"""Adaptador de provisionamento para o Next Term (acesso via shell e RDP
liberado por túnel/proxy).

Assume-se uma API REST simples do Next Term para conceder/revogar
sessões de um usuário a um "target" (host) com um determinado protocolo
(`ssh` e/ou `rdp`). Ajustar os endpoints/payloads conforme a versão
real instalada (ver `.env.example` para configuração de URL/token).
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment
from app.provisioning.base import ProvisioningAdapter, ProvisioningResult, slugify_username

logger = logging.getLogger("provisioning.next_term")


class NextTermProvisioner(ProvisioningAdapter):
    environment = ProvisioningEnvironment.NEXT_TERM

    def __init__(self):
        self.settings = get_settings()

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=self.settings.NEXT_TERM_API_URL,
            headers={
                "Authorization": f"Bearer {self.settings.NEXT_TERM_API_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def provision(self, user: LabUser) -> ProvisioningResult:
        username = slugify_username(user.full_name, user.matricula)
        payload = {
            "username": username,
            "displayName": user.full_name,
            "email": user.personal_email,
            "protocols": ["shell", "rdp"],
            "expiresAt": user.expires_at.isoformat(),
            "tags": ["lab-access-manager", user.matricula],
        }

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][next_term] criaria acesso shell+RDP: %s", payload)
            return ProvisioningResult(success=True, external_identifier=username, message="dry-run")

        try:
            with self._client() as client:
                resp = client.post("/v1/access-grants", json=payload)
                resp.raise_for_status()
                data = resp.json()
                return ProvisioningResult(
                    success=True, external_identifier=data.get("id", username), message="criado"
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
                resp = client.post(f"/v1/access-grants/{external_identifier}/revoke")
                resp.raise_for_status()
                return ProvisioningResult(success=True, external_identifier=external_identifier, message="revogado")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def purge(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a purgar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][next_term] removeria acesso %s definitivamente", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                resp = client.delete(f"/v1/access-grants/{external_identifier}")
                resp.raise_for_status()
                return ProvisioningResult(success=True, external_identifier=external_identifier, message="removido")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def check_last_access(self, user: LabUser, external_identifier: str | None) -> str | None:
        """Consulta o último login registrado pelo Next Term para este
        usuário — usado pelo job de sincronização para popular
        `last_access_at` no dashboard."""
        if not external_identifier or self.settings.PROVISIONING_MODE != "live":
            return None
        try:
            with self._client() as client:
                resp = client.get(f"/v1/access-grants/{external_identifier}/sessions/last")
                resp.raise_for_status()
                data = resp.json()
                return data.get("occurredAt")
        except Exception:  # noqa: BLE001
            return None
