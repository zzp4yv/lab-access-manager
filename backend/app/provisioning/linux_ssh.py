"""Adaptador de provisionamento para as máquinas Linux do laboratório
(Dell DGX GB10 "tars" e "case").

Estratégia: em vez de manipular usuários do sistema diretamente via
biblioteca SSH (o que exigiria elevar privilégios root remotamente de
forma pouco auditável), este adaptador invoca scripts idempotentes
já presentes em `scripts/provisioning/` na máquina remota via SSH,
usando autenticação por chave (nunca senha). Isso mantém toda a lógica
de "o que o comando faz" versionada e revisável em texto puro, e
permite que a equipe de infraestrutura rode os mesmos scripts
manualmente para depuração.

Pré-requisitos reais (a preencher pela equipe, ver `.env.example`):
  - Uma chave SSH dedicada à automação, sem senha, autorizada em
    `~labadmin/.ssh/authorized_keys` em tars e case, com sudo restrito
    (via `sudoers.d`) aos três scripts de `scripts/provisioning/`.
  - Os scripts `linux_create_user.sh`, `linux_revoke_user.sh` e
    `linux_purge_user.sh` copiados para um diretório fixo nas máquinas
    remotas (ex.: `/opt/lab-access-manager/scripts/`).
"""
from __future__ import annotations

import logging

from app.config import get_settings
from app.models import LabUser, ProvisioningEnvironment
from app.provisioning.base import ProvisioningAdapter, ProvisioningResult

logger = logging.getLogger("provisioning.linux_ssh")

REMOTE_SCRIPTS_DIR = "/opt/lab-access-manager/scripts"


class LinuxSSHProvisioner(ProvisioningAdapter):
    """Um adaptador por host (tars / case). `environment` diferencia os
    registros no banco (`linux_tars` vs `linux_case`)."""

    def __init__(self, host: str, environment: ProvisioningEnvironment):
        self.host = host
        self.environment = environment
        self.settings = get_settings()

    # ------------------------------------------------------------------
    def _run_remote(self, command: str) -> tuple[bool, str]:
        """Executa um comando via SSH no host remoto.

        Em modo `dry_run` (padrão), apenas loga o comando que seria
        executado — nenhuma conexão de rede é feita, o que mantém os
        testes automatizados determinísticos e seguros.
        """
        if self.settings.PROVISIONING_MODE != "live":
            logger.info("[DRY-RUN][%s] executaria: %s", self.host, command)
            return True, f"dry-run: comando simulado em {self.host}"

        try:
            import paramiko  # import tardio: dependência opcional em dev/test
        except ImportError as exc:  # pragma: no cover
            return False, f"paramiko não instalado: {exc}"

        client = paramiko.SSHClient()
        client.load_system_host_keys()  # le ~/.ssh/known_hosts (bind mount de SSH_KNOWN_HOSTS_PATH)
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        # RejectPolicy exige que o host esteja em known_hosts — evita
        # MITM silencioso. A equipe deve popular known_hosts no build
        # da imagem (ver Dockerfile) com as chaves reais de tars/case.
        try:
            client.connect(
                hostname=self.host,
                port=self.settings.LINUX_SSH_PORT,
                username=self.settings.LINUX_SSH_ADMIN_USER,
                key_filename=self.settings.LINUX_SSH_PRIVATE_KEY_PATH,
                timeout=15,
            )
            _stdin, stdout, stderr = client.exec_command(command, timeout=60)
            exit_code = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            if exit_code != 0:
                return False, f"exit={exit_code} stderr={err.strip()}"
            return True, out.strip() or "ok"
        except Exception as exc:  # noqa: BLE001 - queremos capturar qualquer falha de rede/auth
            return False, str(exc)
        finally:
            client.close()

    # ------------------------------------------------------------------
    def provision(self, user: LabUser) -> ProvisioningResult:
        username = user.matricula
        cmd = (
            f"sudo {REMOTE_SCRIPTS_DIR}/linux_create_user.sh "
            f"--username {username} "
            f"--group {self.settings.LINUX_DEFAULT_GROUP} "
            f"--home-base {self.settings.LINUX_HOME_BASE} "
            f"--expires-at {user.expires_at.strftime('%Y-%m-%d')}"
        )
        ok, message = self._run_remote(cmd)
        return ProvisioningResult(success=ok, external_identifier=username if ok else None, message=message)

    def revoke(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a revogar (nunca provisionado)")
        cmd = f"sudo {REMOTE_SCRIPTS_DIR}/linux_revoke_user.sh --username {external_identifier}"
        ok, message = self._run_remote(cmd)
        return ProvisioningResult(success=ok, external_identifier=external_identifier, message=message)

    def purge(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        if not external_identifier:
            return ProvisioningResult(success=True, message="nada a purgar")
        cmd = f"sudo {REMOTE_SCRIPTS_DIR}/linux_purge_user.sh --username {external_identifier}"
        ok, message = self._run_remote(cmd)
        return ProvisioningResult(success=ok, external_identifier=external_identifier, message=message)


def build_linux_provisioners() -> list[LinuxSSHProvisioner]:
    """Constrói um provisionador por host configurado em LINUX_HOSTS,
    mapeando para o enum de ambiente correspondente."""
    settings = get_settings()
    env_map = {
        "tars": ProvisioningEnvironment.LINUX_TARS,
        "case": ProvisioningEnvironment.LINUX_CASE,
    }
    provisioners = []
    for host in settings.LINUX_HOSTS:
        environment = env_map.get(host)
        if environment is None:
            logger.warning("Host Linux '%s' sem mapeamento de ambiente conhecido; ignorando.", host)
            continue
        provisioners.append(LinuxSSHProvisioner(host=host, environment=environment))
    return provisioners
