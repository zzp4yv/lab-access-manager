# Runbook — Colocando em produção contra a infraestrutura real

Este código foi gerado sem acesso à rede/VPN/credenciais do Instituto
Oxigênio. Este documento é o checklist para a equipe sair de
`PROVISIONING_MODE=dry_run` (seguro, não toca em nada) para
`PROVISIONING_MODE=live` (executa de verdade contra tars, case,
Pangolin e Next Term).

## 1. Repositório GitHub

1. Criar o repositório (ex.: `oxigenio/lab-access-manager`) e fazer
   push deste código.
2. Habilitar branch protection em `main` exigindo o status check
   `CI — Validação de código / validate` antes de permitir merge —
   isso garante que nenhuma versão com nota ≤ 9 chegue a `main`.
3. Cadastrar os secrets do repositório (Settings → Secrets and
   variables → Actions) usados por `cd.yml`:
   - `DEPLOY_HOST` — hostname/IP do host Docker de destino (ex.: a VM/CT
     em `gargantua` reservada para este serviço).
   - `DEPLOY_USER` — usuário SSH com permissão de rodar `docker compose`.
   - `DEPLOY_SSH_KEY` — chave privada SSH dedicada ao deploy (par
     separado da chave de provisionamento).
   - `DEPLOY_PORT` — porta SSH (opcional, padrão 22).
   - `DEPLOY_PATH` — diretório no host com `docker-compose.yml`
     (copiado de `docker-compose.prod.yml`) e `.env`.

## 2. Host de deploy (gargantua/Proxmox ou VM/CT dedicada)

1. Instalar Docker + Docker Compose plugin.
2. Criar o diretório `DEPLOY_PATH` e copiar para lá:
   - `docker-compose.prod.yml` → renomear para `docker-compose.yml`.
   - `.env` preenchido a partir de `.env.example` (ver seção 4).
   - `secrets/id_ed25519_provisioning` (chave privada de automação).
   - `secrets/known_hosts` (chaves públicas SSH de `tars` e `case`,
     geradas com `ssh-keyscan tars case >> known_hosts` a partir de um
     host confiável).
3. Garantir que este host tenha rota de rede até `tars`, `case`, o
   endpoint do Pangolin e o endpoint do Next Term (via VPN Pangolin,
   se for o caso).

## 3. Máquinas Dell DGX GB10 (tars / case)

Em cada uma das duas máquinas:

1. Criar o usuário de automação (ex.: `labadmin`) com permissão de
   `sudo` restrita aos três scripts de provisionamento:

   ```bash
   sudo useradd --system --create-home --shell /bin/bash labadmin
   sudo mkdir -p /opt/lab-access-manager/scripts
   sudo cp scripts/provisioning/*.sh /opt/lab-access-manager/scripts/
   sudo chmod +x /opt/lab-access-manager/scripts/*.sh
   ```

2. Autorizar a chave pública de automação:

   ```bash
   sudo -u labadmin mkdir -p /home/labadmin/.ssh
   echo "<conteúdo de id_ed25519_provisioning.pub>" | sudo -u labadmin tee -a /home/labadmin/.ssh/authorized_keys
   ```

3. Restringir o `sudo` do `labadmin` apenas aos três scripts (arquivo
   `/etc/sudoers.d/lab-access-manager`):

   ```
   labadmin ALL=(root) NOPASSWD: /opt/lab-access-manager/scripts/linux_create_user.sh, \
                                  /opt/lab-access-manager/scripts/linux_revoke_user.sh, \
                                  /opt/lab-access-manager/scripts/linux_purge_user.sh
   ```

4. Criar o grupo de visitantes (os scripts também criam automaticamente
   na primeira execução, mas pode ser feito antes):

   ```bash
   sudo groupadd lab-visitantes
   ```

## 4. Pangolin (VPN)

1. Obter (com o administrador do Pangolin self-hosted): URL da API,
   um token de API com permissão de criar/desativar/remover
   usuários/peers, o `orgId` e o `siteId` corretos para o laboratório.
2. Preencher no `.env` do host de deploy: `PANGOLIN_API_URL`,
   `PANGOLIN_API_TOKEN`, `PANGOLIN_ORG_ID`, `PANGOLIN_SITE_ID`.
3. **Importante**: o payload exato esperado pela API do Pangolin pode
   variar conforme a versão instalada. Revisar
   `backend/app/provisioning/pangolin.py` (métodos `provision`,
   `revoke`, `purge`) e ajustar o formato do payload/endpoints
   conforme a documentação da instância real antes de habilitar modo
   `live`.

## 5. Next Term (shell + RDP)

1. Obter a URL da API do Next Term e um token com permissão de criar
   e revogar concessões de acesso (`access-grants`).
2. Preencher `NEXT_TERM_API_URL` e `NEXT_TERM_API_TOKEN` no `.env`.
3. Revisar `backend/app/provisioning/next_term.py` da mesma forma que
   o Pangolin — ajustar o "shape" do payload conforme a API real.

## 6. Habilitando modo `live`

Só depois de validar os passos 1-5 (idealmente testando cada
adaptador isoladamente, ex.: criando um usuário de teste pela
interface e conferindo manualmente em tars/case/Pangolin/Next Term):

1. No `.env` do host de deploy, mudar `PROVISIONING_MODE=dry_run`
   para `PROVISIONING_MODE=live`.
2. `docker compose up -d` para recarregar com a nova configuração.
3. Cadastrar um usuário de teste pela interface e conferir nos quatro
   ambientes (aba "Usuários" mostra o status de cada
   `ProvisioningRecord` — ver também `GET /api/users/{id}`).

## 7. Operação contínua

- O painel (`dashboard.html`) mostra usuários ativos, expirando em 7
  dias e falhas de provisionamento — checar periodicamente.
- Um usuário com status "Falha no provisionamento" pode ser
  reprocessado com o botão "Tentar novamente" (endpoint
  `POST /api/users/{id}/retry-provisioning`) — a operação é
  idempotente em todos os adaptadores.
- Backup: o SQLite fica no volume Docker `lab_access_data`
  (`/app/data/lab_access.db` dentro do container) — incluir esse
  volume na rotina de backup do host.
