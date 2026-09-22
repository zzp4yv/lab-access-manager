"""Interface comum para todos os adaptadores de provisionamento.

Cada ambiente (Linux/SSH, Pangolin VPN, Next Term) implementa esta
interface. Isso permite que o orquestrador (`orchestrator.py`) trate
todos os ambientes de forma uniforme e que novos ambientes sejam
adicionados sem alterar a lógica de negócio em `routers/users.py` ou
`services/lifecycle.py`.

IMPORTANTE — sobre credenciais e testes contra a infraestrutura real:
Este código foi gerado sem acesso à rede/VPN/credenciais do Instituto
Oxigênio. As classes abaixo implementam a lógica completa de
integração (comandos SSH, payloads de API), mas precisam que a equipe
preencha os endpoints e segredos reais (ver `.env.example`) antes de
rodar em modo "live". Enquanto isso, `PROVISIONING_MODE=dry_run`
(padrão) faz os adaptadores apenas logarem a ação e retornarem sucesso
simulado — seguro para desenvolvimento e para os testes automatizados.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass

from app.models import LabUser, ProvisioningEnvironment

logger = logging.getLogger("provisioning")


@dataclass
class ProvisioningResult:
    success: bool
    external_identifier: str | None = None
    message: str = ""


class ProvisioningAdapter(ABC):
    """Contrato que todo adaptador de ambiente deve implementar."""

    environment: ProvisioningEnvironment

    @abstractmethod
    def provision(self, user: LabUser) -> ProvisioningResult:
        """Cria/concede acesso ao usuário neste ambiente."""

    @abstractmethod
    def revoke(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        """Revoga o acesso do usuário (mantendo dados, se aplicável)."""

    @abstractmethod
    def purge(self, user: LabUser, external_identifier: str | None) -> ProvisioningResult:
        """Remove definitivamente os dados/contas do usuário neste ambiente."""

    def check_last_access(self, user: LabUser, external_identifier: str | None) -> str | None:
        """Ponto de extensão opcional: adaptadores que expõem logs de
        login (ex.: Next Term, Pangolin) podem sobrescrever este método
        para sincronizar `last_access_at`. Retorna um timestamp ISO-8601
        ou None caso não haja dado disponível."""
        return None


def slugify_username(full_name: str, matricula: str) -> str:
    """Gera um nome de usuário a partir da matrícula exclusivamente (minúscula para compatibilidade Linux)."""
    return matricula.lower()


NEXTTERM_USERNAME_MAX_LENGTH = 15  # limite real da API do Nexterm


def nextterm_username(full_name: str, matricula: str) -> str:
    """Gera o username do Next Term a partir da matrícula exclusivamente (minúscula)."""
    return matricula.lower()
