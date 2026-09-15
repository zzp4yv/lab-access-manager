"""
Configuração central da aplicação.

Todos os valores sensíveis (senhas, tokens, chaves SSH, endpoints de API)
devem ser fornecidos via variáveis de ambiente / arquivo .env — nunca
hard-coded. Veja `.env.example` na raiz do projeto para a lista completa.

Importante: os valores são lidos de `os.environ` dentro de `__init__`
(portanto a cada instanciação de `Settings()`), e não como atributos de
classe. Isso é o que permite que testes automatizados troquem variáveis
de ambiente em tempo de execução (via `monkeypatch.setenv` +
`get_settings.cache_clear()`) e vejam o efeito — com atributos de
classe, o valor ficaria "congelado" no momento em que o módulo fosse
importado pela primeira vez.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

# Raiz do projeto (lab-access-manager/), calculada relativa a este
# arquivo: backend/app/config.py -> parents[2] == raiz do projeto.
# Isso faz com que o frontend estático seja encontrado tanto em
# desenvolvimento local (`uvicorn app.main:app` dentro de backend/)
# quanto dentro do container, desde que a estrutura de pastas do
# repositório seja preservada (ver Dockerfile).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


class Settings:
    def __init__(self) -> None:
        # --- Aplicação ---------------------------------------------------
        self.APP_NAME: str = "Instituto Oxigênio - Gestão de Acessos ao Laboratório"
        self.ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
        self.DEBUG: bool = os.getenv("DEBUG", "false").lower() == "true"

        # --- Banco de dados ------------------------------------------------
        # SQLite por padrão (definido na fase de esclarecimento com o usuário).
        # Pode ser trocado por qualquer URL suportada pelo SQLAlchemy.
        self.DATABASE_URL: str = os.getenv(
            "DATABASE_URL", f"sqlite:///{_PROJECT_ROOT / 'backend' / 'data' / 'lab_access.db'}"
        )

        # --- Frontend estático -------------------------------------------
        self.FRONTEND_DIR: str = os.getenv("FRONTEND_DIR", str(_PROJECT_ROOT / "frontend"))

        # --- Upload de documentos -------------------------------------------
        self.UPLOAD_DIR: str = os.getenv(
            "UPLOAD_DIR", str(_PROJECT_ROOT / "backend" / "data" / "uploads")
        )
        self.MAX_UPLOAD_SIZE_MB: int = int(os.getenv("MAX_UPLOAD_SIZE_MB", "20"))
        self.ALLOWED_UPLOAD_EXTENSIONS: list[str] = _split_csv(
            os.getenv("ALLOWED_UPLOAD_EXTENSIONS", "pdf,doc,docx,png,jpg,jpeg,txt")
        )

        # --- Autenticação / JWT --------------------------------------------
        self.SECRET_KEY: str = os.getenv("SECRET_KEY", "changeme-generate-a-real-secret")
        self.ALGORITHM: str = "HS256"
        self.ACCESS_TOKEN_EXPIRE_MINUTES: int = int(
            os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "480")
        )

        # --- Regras de ciclo de vida de acesso -------------------------------
        self.DEFAULT_ACCESS_DAYS: int = int(os.getenv("DEFAULT_ACCESS_DAYS", "30"))
        self.MAX_ACCESS_DAYS: int = int(os.getenv("MAX_ACCESS_DAYS", "365"))
        self.DATA_RETENTION_DAYS_AFTER_REVOKE: int = int(
            os.getenv("DATA_RETENTION_DAYS_AFTER_REVOKE", "30")
        )
        self.LIFECYCLE_CHECK_INTERVAL_MINUTES: int = int(
            os.getenv("LIFECYCLE_CHECK_INTERVAL_MINUTES", "60")
        )

        # --- Infraestrutura do laboratório -----------------------------------
        # Máquinas Dell DGX GB10 (Linux) que recebem provisionamento de usuário.
        self.LINUX_HOSTS: list[str] = _split_csv(os.getenv("LINUX_HOSTS", "tars,case"))
        self.LINUX_SSH_PORT: int = int(os.getenv("LINUX_SSH_PORT", "22"))
        self.LINUX_SSH_ADMIN_USER: str = os.getenv("LINUX_SSH_ADMIN_USER", "labadmin")
        # Caminho da chave privada SSH usada para automação (nunca a senha).
        self.LINUX_SSH_PRIVATE_KEY_PATH: str = os.getenv(
            "LINUX_SSH_PRIVATE_KEY_PATH", "/app/secrets/id_ed25519_provisioning"
        )
        self.LINUX_DEFAULT_GROUP: str = os.getenv("LINUX_DEFAULT_GROUP", "lab-visitantes")
        self.LINUX_HOME_BASE: str = os.getenv("LINUX_HOME_BASE", "/home")

        # Pangolin (VPN)
        self.PANGOLIN_API_URL: str = os.getenv(
            "PANGOLIN_API_URL", "https://pangolin.internal.oxigenio/api"
        )
        self.PANGOLIN_API_TOKEN: str = os.getenv("PANGOLIN_API_TOKEN", "")
        self.PANGOLIN_ORG_ID: str = os.getenv("PANGOLIN_ORG_ID", "")
        self.PANGOLIN_SITE_ID: str = os.getenv("PANGOLIN_SITE_ID", "")

        # Next Term (shell + RDP)
        self.NEXT_TERM_API_URL: str = os.getenv(
            "NEXT_TERM_API_URL", "https://nextterm.internal.oxigenio/api"
        )
        self.NEXT_TERM_API_TOKEN: str = os.getenv("NEXT_TERM_API_TOKEN", "")

        # --- Modo de operação dos adaptadores de provisionamento --------------
        # "live"  -> executa chamadas reais (SSH/API) contra a infraestrutura.
        # "dry_run" -> loga o que seria feito, sem executar (padrão seguro).
        self.PROVISIONING_MODE: str = os.getenv("PROVISIONING_MODE", "dry_run")

        # --- CORS ------------------------------------------------------------
        self.CORS_ORIGINS: list[str] = _split_csv(os.getenv("CORS_ORIGINS", "*"))

        # --- Admin inicial (bootstrap) -----------------------------------------
        self.BOOTSTRAP_ADMIN_EMAIL: str = os.getenv("BOOTSTRAP_ADMIN_EMAIL", "")
        self.BOOTSTRAP_ADMIN_PASSWORD: str = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "")
        self.BOOTSTRAP_ADMIN_NAME: str = os.getenv("BOOTSTRAP_ADMIN_NAME", "Administrador")


@lru_cache
def get_settings() -> Settings:
    return Settings()
