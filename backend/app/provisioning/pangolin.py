"""Adaptador de provisionamento para a VPN gerenciada pelo Pangolin
(github.com/fosrl/pangolin), via a Integration API real da instância.

Modelo confirmado contra a instância real (ver /v1/openapi.json exposto
pela própria Integration API, e docs.pangolin.net/manage/integration-api):
  - Base: PANGOLIN_API_URL (ex.: https://api.<dominio>) + "/v1"
  - Auth: header "Authorization: Bearer <token>" — a Integration API
    precisa estar habilitada na org self-hosted (flags.enable_integration_api
    no config.yml do Pangolin) e roteada pelo proxy reverso até a porta
    dedicada (ver docs.pangolin.net/self-host/advanced/integration-api).

Decisão de produto: "conceder acesso VPN" aqui significa tornar o
visitante um MEMBRO da organização com uma role restrita (PANGOLIN_ROLE_NAME,
padrão "Member") — acesso via login SSO aos recursos HTTP publicados no
Pangolin. Isso é diferente de um "Client" (peer WireGuard de verdade,
que exigiria instalar o app Olm no notebook do visitante antes — fora do
escopo deste fluxo, que precisa funcionar sem nenhuma ação prévia do
visitante).

Como a Integration API não permite definir senha na criação direta de
um usuário de org, o provisionamento usa o fluxo de convite
(POST /org/{orgId}/create-invite, com sendEmail=false) — a resposta traz
um link de convite pronto, que o admin comunica ao visitante (o próprio
visitante define a senha ao aceitar). Isso evita depender do envio de
e-mail pelo Pangolin.
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment
from app.provisioning.base import ProvisioningAdapter, ProvisioningResult

logger = logging.getLogger("provisioning.pangolin")


class PangolinProvisioner(ProvisioningAdapter):
    environment = ProvisioningEnvironment.PANGOLIN_VPN

    def __init__(self):
        self.settings = get_settings()

    def _client(self):
        import httpx

        return httpx.Client(
            base_url=f"{self.settings.PANGOLIN_API_URL.rstrip('/')}/v1",
            headers={
                "Authorization": f"Bearer {self.settings.PANGOLIN_API_TOKEN}",
                "Content-Type": "application/json",
            },
            timeout=15.0,
        )

    def _org_path(self, suffix: str) -> str:
        return f"/org/{self.settings.PANGOLIN_ORG_ID}{suffix}"

    def _find_role_id(self, client) -> int | None:
        resp = client.get(self._org_path("/roles"))
        resp.raise_for_status()
        for role in resp.json().get("data", {}).get("roles", []):
            if role.get("name") == self.settings.PANGOLIN_ROLE_NAME:
                return role.get("roleId")
        return None

    def _find_org_user(self, client, email: str) -> dict | None:
        resp = client.get(self._org_path("/users"))
        resp.raise_for_status()
        for account in resp.json().get("data", {}).get("users", []):
            if account.get("email") == email:
                return account
        return None

    def _find_pending_invite(self, client, email: str) -> str | None:
        resp = client.get(self._org_path("/invitations"))
        resp.raise_for_status()
        for invite in resp.json().get("data", {}).get("invitations", []):
            if invite.get("email") == email:
                return invite.get("inviteId")
        return None

    def provision(self, user: LabUser) -> ProvisioningResult:
        if self.settings.PROVISIONING_MODE != "live":
            logger.info(
                "[DRY-RUN][pangolin] convidaria %s para a org com role '%s'",
                user.personal_email,
                self.settings.PANGOLIN_ROLE_NAME,
            )
            return ProvisioningResult(success=True, external_identifier=user.personal_email, message="dry-run")

        try:
            with self._client() as client:
                role_id = self._find_role_id(client)
                if role_id is None:
                    return ProvisioningResult(
                        success=False,
                        message=f"role '{self.settings.PANGOLIN_ROLE_NAME}' não encontrada na org",
                    )
                resp = client.post(
                    self._org_path("/create-invite"),
                    json={
                        "email": user.personal_email,
                        "roleId": role_id,
                        "validHours": 168,
                        "sendEmail": False,
                        # Idempotente: se já existir um convite pendente para
                        # este e-mail (ex.: retry de provisionamento), o
                        # Pangolin regenera o link em vez de retornar 409.
                        "regenerate": True,
                    },
                )
                resp.raise_for_status()
                invite_link = resp.json().get("data", {}).get("inviteLink", "")
                return ProvisioningResult(
                    success=True,
                    external_identifier=user.personal_email,
                    message=f"convite criado — compartilhar com o visitante: {invite_link}",
                )
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def revoke(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a revogar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][pangolin] revogaria acesso de %s", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                account = self._find_org_user(client, external_identifier)
                if account:
                    for role in account.get("roles", []):
                        resp = client.delete(
                            f"/user/{account['id']}/remove-role/{role['roleId']}"
                        )
                        resp.raise_for_status()
                    return ProvisioningResult(
                        success=True, external_identifier=external_identifier, message="acesso removido (sem roles)"
                    )

                invite_id = self._find_pending_invite(client, external_identifier)
                if invite_id:
                    resp = client.delete(self._org_path(f"/invitations/{invite_id}"))
                    resp.raise_for_status()
                    return ProvisioningResult(
                        success=True, external_identifier=external_identifier, message="convite pendente cancelado"
                    )

                return ProvisioningResult(
                    success=True, external_identifier=external_identifier, message="nada a revogar (já ausente)"
                )
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))

    def purge(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a purgar")

        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][pangolin] removeria %s da org definitivamente", external_identifier)
            return ProvisioningResult(success=True, external_identifier=external_identifier, message="dry-run")

        try:
            with self._client() as client:
                account = self._find_org_user(client, external_identifier)
                if account:
                    resp = client.delete(self._org_path(f"/user/{account['id']}"))
                    resp.raise_for_status()
                    return ProvisioningResult(
                        success=True, external_identifier=external_identifier, message="removido da org"
                    )

                invite_id = self._find_pending_invite(client, external_identifier)
                if invite_id:
                    resp = client.delete(self._org_path(f"/invitations/{invite_id}"))
                    resp.raise_for_status()
                    return ProvisioningResult(
                        success=True, external_identifier=external_identifier, message="convite pendente removido"
                    )

                return ProvisioningResult(
                    success=True, external_identifier=external_identifier, message="nada a purgar (já ausente)"
                )
        except Exception as exc:  # noqa: BLE001
            return ProvisioningResult(success=False, message=str(exc))
