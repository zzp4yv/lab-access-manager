# Arquitetura

## Visão geral

```
                        ┌─────────────────────────────┐
                        │   Navegador (admin)         │
                        │   frontend/ (HTML/CSS/JS)   │
                        └──────────────┬───────────────┘
                                       │ HTTPS (JWT Bearer)
                        ┌──────────────▼───────────────┐
                        │        FastAPI (app/)        │
                        │  routers: auth/users/admins/  │
                        │           dashboard           │
                        └───┬───────────────────────┬───┘
                            │                       │
                  ┌─────────▼─────────┐   ┌──────────▼──────────┐
                  │  SQLite (SQLAlchemy) │  │ services/lifecycle.py │
                  │  lab_users, admins,   │  │ (revoga/purga por    │
                  │  provisioning_records,│  │  prazo, agendado via │
                  │  audit_logs           │  │  APScheduler)        │
                  └────────────────────┘   └──────────┬──────────┘
                                                       │
                                     ┌─────────────────▼─────────────────┐
                                     │  provisioning/orchestrator.py      │
                                     │  (1 adaptador por ambiente)        │
                                     └───┬─────────┬─────────┬───────────┘
                                         │         │         │
                            ┌────────────▼──┐ ┌────▼─────┐ ┌─▼────────────┐
                            │ linux_ssh.py   │ │pangolin.py│ │next_term.py  │
                            │ (tars + case,  │ │(API REST) │ │(API REST)    │
                            │  via SSH+script)│ │           │ │              │
                            └────────────────┘ └───────────┘ └──────────────┘
```

## Decisões de design e por quê

### Backend FastAPI + SQLite
Definido junto com o solicitante (Oxigenio), que já usa FastAPI em
outro projeto (avatar-jayme-docker). SQLite elimina a necessidade de
um serviço de banco separado, adequado ao volume esperado de usuários
de laboratório (dezenas/centenas, não milhões de linhas). O código usa
SQLAlchemy ORM, então trocar para PostgreSQL no futuro é uma mudança
de uma linha (`DATABASE_URL`) — os modelos não usam nenhum recurso
específico do SQLite.

### Frontend HTML/CSS/JS puro
Sem etapa de build (webpack/vite/etc.): o `docker-compose` fica mais
simples (um único estágio de build no Dockerfile), o deploy é mais
rápido, e a equipe pode editar uma página sem precisar de Node.js
instalado. O preço é menos "developer experience" de frameworks
modernos — aceitável para o escopo (poucas telas, CRUD simples).

### Um `ProvisioningRecord` por (usuário, ambiente)
Em vez de um único campo de status no usuário, cada ambiente
(`linux_tars`, `linux_case`, `pangolin_vpn`, `next_term`) tem sua
própria linha de estado. Isso é essencial porque os quatro
provisionamentos são operações de rede independentes que podem falhar
de forma parcial (ex.: Pangolin fora do ar mas Next Term ok) — o
sistema precisa saber exatamente o que retentar, e o dashboard precisa
mostrar isso por ambiente.

### Adaptadores com interface comum (`ProvisioningAdapter`)
`provision()` / `revoke()` / `purge()` — o mesmo contrato para SSH e
para APIs REST. Isso mantém `orchestrator.py` e `services/lifecycle.py`
completamente desacoplados de como cada ambiente específico funciona,
e torna trivial adicionar um quinto ambiente no futuro (basta
implementar a interface e registrá-lo em
`orchestrator.get_all_adapters()`).

### `PROVISIONING_MODE=dry_run` como padrão
Como este código foi gerado sem acesso à infraestrutura real do
laboratório, todos os adaptadores por padrão apenas logam a ação que
tomariam, sem se conectar a nada. Isso permite: (1) rodar a aplicação
e os testes automatizados com segurança em qualquer lugar, e (2) a
equipe validar o fluxo de ponta a ponta pela interface antes de virar
a chave para `live`.

### Provisionamento Linux via scripts + SSH, não biblioteca direta
`linux_ssh.py` não manipula usuários do sistema diretamente — ele
executa `scripts/provisioning/*.sh` no host remoto via SSH (chave,
nunca senha). Vantagens: os scripts podem ser revisados/rodados
manualmente pela equipe de infra para depuração, o `sudo` pode ser
restrito especificamente a esses três scripts via `sudoers.d` (em vez
de dar root total à automação), e a lógica de "o que o comando faz"
fica em bash simples, não escondida em uma lib Python.

### Revogação e purga automáticas (ciclo de vida)
`services/lifecycle.py` roda em um job agendado
(`services/scheduler.py`, via APScheduler, intervalo configurável) que:
1. Provisiona usuários `PENDING` pendentes (rede de segurança caso o
   provisionamento síncrono no cadastro tenha falhado por algum motivo
   transitório).
2. Revoga usuários `ACTIVE`/`FAILED` cujo `expires_at` já passou.
3. Purga (remove definitivamente + anonimiza no banco) usuários
   `REVOKED` cujo `purge_after` (revogação + 30 dias, configurável)
   já passou.

A revogação e a purga também podem ser disparadas manualmente por um
admin (`POST /api/users/{id}/revoke-now`,
`POST /api/users/run-lifecycle-now`).

### Agente de validação de código como gate determinístico
Optado, junto com o solicitante, por um gate **determinístico** (não
um agente de IA chamando uma API externa) para não depender de uma
`ANTHROPIC_API_KEY` no pipeline nem de latência/custo de chamadas de
modelo a cada push. `validation_agent/validate.py` combina lint
(ruff), taxa de sucesso de testes (pytest), cobertura de código
(pytest-cov) e complexidade ciclomática (radon) em uma nota ponderada
de 1 a 10, com gate rígido adicional (qualquer teste falhando reprova
independente da nota). Isso é 100% reproduzível e auditável — mesma
entrada, mesma nota, sempre.

## Segurança

- Senhas de administrador: hash bcrypt (via passlib), nunca texto puro.
- Autenticação: JWT com expiração configurável (`ACCESS_TOKEN_EXPIRE_MINUTES`).
- Usuários de laboratório: contas Linux criadas com senha bloqueada
  (`passwd --lock`) — acesso real via chave SSH/VPN/Next Term, nunca
  senha estática.
- SSH de automação: chave dedicada, `RejectPolicy` (exige
  `known_hosts` populado, rejeita host desconhecido — evita MITM).
- Dados pessoais (PII): anonimizados no banco após a purga (LGPD),
  documentos anexados removidos do disco.
- CORS: restrito via `CORS_ORIGINS` (ajustar em produção; `*` é o
  padrão apenas para desenvolvimento).
