"""Envio do e-mail de instruções de acesso ao visitante, disparado
logo após o provisionamento ser concluído com sucesso (ver
`routers/users.py`).

Usa SMTP simples (smtplib), sem dependência de um provedor especfico
— funciona com qualquer servidor SMTP padrão (Gmail com senha de app,
SES, Mailgun, etc.), configurado via `SMTP_*` no `.env`. Se
`SMTP_HOST` não estiver configurado, o envio é pulado (logado como
aviso) em vez de falhar o provisionamento — o e-mail é um "extra", a
ausência de configuração de SMTP não deve bloquear o fluxo principal.
"""
from __future__ import annotations

import logging
import re
import smtplib
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment, ProvisioningStatus

logger = logging.getLogger("services.email")

_PASSWORD_RE = re.compile(r"senha inicial:\s*(\S+)")
_INVITE_LINK_RE = re.compile(r"(https?://\S+)")


def _build_body(user: LabUser) -> str:
    settings = get_settings()
    records = {r.environment: r for r in user.provisioning_records}

    first_name = user.full_name.split()[0] if user.full_name.split() else "usuario"
    password = f"{first_name.lower()}{datetime.now().year}"

    lines = [
        f"Olá, {user.full_name}!",
        "",
        "Seu acesso temporário ao laboratório do Instituto Oxigênio foi provisionado.",
        f"Válido até: {user.expires_at.strftime('%d/%m/%Y')}.",
        "",
    ]

    next_term = records.get(ProvisioningEnvironment.NEXT_TERM)
    if next_term and next_term.status == ProvisioningStatus.SUCCESS:
        lines += [
            "== Acesso shell/RDP (Nexterm) ==",
            f"URL: {settings.NEXT_TERM_PUBLIC_URL}",
            f"Usuário: {next_term.external_identifier}",
            f"Senha: {password}",
        ]
        lines.append("")

    pangolin = records.get(ProvisioningEnvironment.PANGOLIN_VPN)
    if pangolin and pangolin.status == ProvisioningStatus.SUCCESS:
        link_match = _INVITE_LINK_RE.search(pangolin.last_message or "")
        if link_match:
            lines += [
                "== Convite de acesso à rede (Pangolin) ==",
                "Clique no link abaixo e defina sua senha para concluir o acesso:",
                link_match.group(1),
                "",
            ]

    linux_usernames = {
        env: rec.external_identifier
        for env, rec in records.items()
        if env in (ProvisioningEnvironment.LINUX_TARS, ProvisioningEnvironment.LINUX_CASE)
        and rec.status == ProvisioningStatus.SUCCESS
    }
    if linux_usernames:
        lines.append("== Máquinas do laboratório ==")
        if ProvisioningEnvironment.LINUX_TARS in linux_usernames:
            lines.append(f"tars — usuário: {linux_usernames[ProvisioningEnvironment.LINUX_TARS]}")
        if ProvisioningEnvironment.LINUX_CASE in linux_usernames:
            lines.append(f"case — usuário: {linux_usernames[ProvisioningEnvironment.LINUX_CASE]}")
        lines += [
            "O acesso a essas máquinas é feito pelo terminal web do Nexterm acima.",
            "",
        ]

    lines.append("Qualquer dúvida, entre em contato com o administrador do laboratório.")
    return "\n".join(lines)


def send_access_instructions(user: LabUser) -> bool:
    """Envia o e-mail de instruções de acesso. Retorna True se enviado
    (ou se o SMTP não está configurado — nesse caso apenas loga e não
    conta como falha do provisionamento), False se o envio falhou."""
    settings = get_settings()
    if not settings.SMTP_HOST:
        logger.info("[email] SMTP não configurado — pulando envio para %s", user.personal_email)
        return True

    first_name = user.full_name.split()[0] if user.full_name.split() else "usuario"
    password = f"{first_name.lower()}{datetime.now().year}"

    message = MIMEMultipart()
    message["From"] = "acessolab@starlab.ia.br"
    message["To"] = user.personal_email
    message["Subject"] = "Acesso ao laboratório — Instituto Oxigênio"
    body = _build_body(user)
    # Substituir a senha na body pelo password calculado (já está em _build_body,
    # mas garantimos o valor correto se houver qualquer discrepância)
    body = re.sub(
        r"Senha: [^\n]+",
        f"Senha: {password}",
        body,
    )
    message.attach(MIMEText(body, "plain", "utf-8"))

    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USERNAME:
                server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception:  # noqa: BLE001
        logger.exception("[email] falha ao enviar instruções de acesso para %s", user.personal_email)
        return False
