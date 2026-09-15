# Gestão de Acessos ao Laboratório — Instituto Oxigênio

Sistema web para gerenciar o acesso temporário de usuários externos ao
laboratório do Instituto Oxigênio (Porto Seguro), incluindo
provisionamento automático em Linux (Dell DGX GB10 "tars" e "case"),
VPN Pangolin e Next Term (shell/RDP), com revogação e purga
automáticas por prazo.

## Stack

| Camada | Tecnologia |
|---|---|
| Backend | Python 3.11 + FastAPI + SQLAlchemy |
| Banco de dados | SQLite (arquivo único, persistido em volume Docker) |
| Frontend | HTML/CSS/JS puro (sem etapa de build), responsivo |
| Autenticação | JWT (login de administrador) |
| Agendamento | APScheduler (job interno de revogação/purga) |
| Container | Docker + docker-compose |
| CI/CD | GitHub Actions (lint, testes, cobertura, agente de validação, build, deploy) |

Estas escolhas foram definidas junto com o solicitante antes da
implementação (backend FastAPI+SQLite, frontend sem build, agente de
validação como gate determinístico de CI, adaptadores de
provisionamento prontos para preencher com credenciais reais).

## Estrutura do projeto

```
lab-access-manager/
├── backend/                  # API FastAPI
│   ├── app/
│   │   ├── main.py           # bootstrap da aplicação, serve o frontend estático
│   │   ├── config.py         # configuração via variáveis de ambiente
│   │   ├── models.py         # LabUser, Admin, ProvisioningRecord, AuditLog
│   │   ├── schemas.py        # schemas Pydantic (request/response)
│   │   ├── security.py       # hashing de senha + JWT
│   │   ├── routers/          # auth, users, admins, dashboard
│   │   ├── provisioning/     # adaptadores: linux_ssh, pangolin, next_term + orquestrador
│   │   └── services/         # lifecycle (revogação/purga), scheduler, audit
│   ├── tests/                # pytest (unit + integração via TestClient)
│   ├── Dockerfile
│   └── requirements*.txt
├── frontend/                 # HTML/CSS/JS puro, responsivo
│   ├── index.html            # login
│   ├── dashboard.html        # métricas (ativos, expirando, último acesso)
│   ├── users.html            # usuários + administradores (mesma interface)
│   └── css/ js/
├── scripts/
│   ├── entrypoint.sh          # entrypoint do container
│   └── provisioning/          # scripts idempotentes executados via SSH em tars/case
├── validation_agent/
│   └── validate.py            # agente de validação de código (nota 1-10)
├── .github/workflows/
│   ├── ci.yml                 # lint + testes + cobertura + agente de validação
│   └── cd.yml                 # build, push (GHCR) e deploy (só se nota > 9)
├── docker-compose.yml          # uso local/dev (builda a imagem)
├── docker-compose.prod.yml     # produção (consome imagem do GHCR)
├── .env.example
└── docs/
    ├── ARCHITECTURE.md
    └── RUNBOOK.md
```

## Como rodar localmente

```bash
cp .env.example .env
# edite .env: pelo menos SECRET_KEY, BOOTSTRAP_ADMIN_EMAIL e
# BOOTSTRAP_ADMIN_PASSWORD

docker compose up --build
```

A aplicação sobe em `http://localhost:8000` (API em `/api/*`,
frontend estático servido na raiz). No primeiro start, um
administrador é criado automaticamente a partir de
`BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD`.

Por padrão, `PROVISIONING_MODE=dry_run`: os adaptadores de
provisionamento **não** tocam em nenhum sistema real — apenas logam o
que fariam. Isso é intencional (ver `docs/RUNBOOK.md` para o
checklist de configuração antes de mudar para `PROVISIONING_MODE=live`).

### Rodando sem Docker (desenvolvimento)

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp ../.env.example ../.env   # ou exporte as variáveis manualmente
uvicorn app.main:app --reload
```

### Testes

```bash
cd backend
pytest -q                                  # suíte completa (40 testes)
pytest --cov=app --cov-report=term-missing # com cobertura
```

### Agente de validação de código

```bash
python validation_agent/validate.py
```

Roda lint (ruff), testes+cobertura (pytest/pytest-cov) e complexidade
ciclomática (radon), combina tudo em uma nota de 1 a 10 e só retorna
sucesso (exit code 0) se a nota for **maior que 9**. É o mesmo comando
executado pelo GitHub Actions em `ci.yml`/`cd.yml` como gate
obrigatório antes de build/deploy.

## Requisitos atendidos

- **Gestão de usuários**: cadastro com nome, matrícula, email pessoal,
  telefone e documento anexado (`users.html`, `POST /api/users`),
  provisionamento automático em Linux (tars/case), Pangolin e Next
  Term disparado na criação; controle de tempo de acesso em dias com
  revogação automática ao expirar e remoção de dados 30 dias depois
  (`app/services/lifecycle.py`, configurável via
  `DATA_RETENTION_DAYS_AFTER_REVOKE`).
- **Gestão administrativa**: administradores na mesma interface de
  usuários (aba "Administradores" em `users.html`), nunca
  provisionados nos ambientes do laboratório; painel com usuários
  ativos e último acesso de cada um (`dashboard.html`,
  `GET /api/dashboard/stats`).
- **Agente de validação de código**: `validation_agent/validate.py`,
  nota 1-10, gate de produção em nota > 9, integrado ao CI/CD.
- **Infraestrutura**: Docker + docker-compose, código no GitHub,
  pipeline GitHub Actions de build e deploy automático condicionado à
  aprovação do agente de validação.

## Sobre as integrações reais (Pangolin, Next Term, SSH)

Este projeto foi gerado sem acesso à rede/VPN/credenciais do
Instituto Oxigênio. Os adaptadores em `backend/app/provisioning/`
implementam a lógica completa de integração (comandos SSH, payloads
de API), mas os endpoints e segredos reais precisam ser preenchidos
pela equipe antes de operar em modo `live` — ver `docs/RUNBOOK.md`
para o passo a passo.
