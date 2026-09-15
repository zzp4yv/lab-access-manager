"""Adaptador de provisionamento para a VPN gerenciada pelo Pangolin.

A API pública do Pangolin gira em torno de "sites", "resources" e
"users"/"peers" associados a um site/organização. Este adaptador cria
um usuário/peer com acesso restrito ao(s) recurso(s) do laboratório e
o desativa/remove ao revogar/purgar.

Preencher em produção (ver `.env.example`):
  PANGOLIN_API_URL, PANGOLIN_API_TOKEN, PANGOLIN_ORG_ID, PANGOLIN_SITE_ID

Como os detalhes exatos do payload podem variar entre versões do
Pangolin self-hosted, os métodos abaixo isolam o "shape" da requisição
em métodos privados (`_create_payload`, endpoints) para facilitar o
ajuste fino pela equipe sem tocar na lógica de orquestração.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment
from app.provisioning.base import ProvisioningAdapter, ProvisioningResult, slugify_username

logger = logging.getLogger("provisioning.pangolin")


class PangolinProvisioner(ProvisioningAdapter):
    environment = ProvisioningEnvironment.PANGOLIN_VPN

    def __init__(self):
        self.settings = get_settings()

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=self.settings.PANGOLIN_API_URL,
            headers={
                "Authorization": f"Bearer {self.settings.PANGOLIN_API_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def provision(self, user: LabUser) -> ProvisioningResult:
        username = slugify_username(user.full_name, user.matricula)
        payload = {
            "orgId": self.settings.PANGOLIN_ORG_ID,
            "siteId": self.settings.PANGOLIN_SITE_ID,
            "username": username,
            "email": user.personal_email,
            "expiresAt": user.expires_at.isoformat(),
            "metadata": {"matricula": user.matricula, "origem": "lab-access-manager"},
        }

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][pangolin] criaria peer VPN: %s", payload)
            return ProvisioningResult(success=True, external_identifier=username, message="dry-run")

        try:
            with self._client() as client:
                resp = client.post(f"/v1/org/{self.settings.PANGOLIN_ORG_ID}/users", json=payload)
                resp.raise_for_status()
                data = resp.json()
                external_id = data.get("id", username)
                return ProvisioningResult(success=True, external_identifier=external_id, message="criado")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def revoke(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a revogar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][pangolin] desativaria peer %s", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                resp = client.post(
                    f"/v1/org/{self.settings.PANGOLIN_ORG_ID}/users/{external_identifier}/disable"
                )
                resp.raise_for_status()
                return ProvisioningResult(success=True, external_identifier=external_identifier, message="desativado")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def purge(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a purgar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][pangolin] removeria peer %s definitivamente", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                resp = client.delete(
                    f"/v1/org/{self.settings.PANGOLIN_ORG_ID}/users/{external_identifier}"
                )
                resp.raise_for_status()
                return ProvisioningResult(success=True, external_identifier=external_identifier, message="removido")
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))
