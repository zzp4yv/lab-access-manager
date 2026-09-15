#!/usr/bin/env bash
#
# Cria (de forma idempotente) um usuário Linux temporário de laboratório
# nas máquinas Dell DGX GB10 (tars/case). Executado remotamente via SSH
# pelo backend (app/provisioning/linux_ssh.py), tipicamente com `sudo`
# restrito a este script via /etc/sudoers.d/.
#
# Uso:
#   linux_create_user.sh --username <nome> --group <grupo> \
#       --home-base </home> --expires-at <YYYY-MM-DD>
#
set -euo pipefail

USERNAME=""
GROUP="lab-visitantes"
HOME_BASE="/home"
EXPIRES_AT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --username) USERNAME="$2"; shift 2 ;;
    --group) GROUP="$2"; shift 2 ;;
    --home-base) HOME_BASE="$2"; shift 2 ;;
    --expires-at) EXPIRES_AT="$2"; shift 2 ;;
    *) echo "Argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$USERNAME" ]]; then
  echo "Erro: --username é obrigatório" >&2
  exit 2
fi

if [[ ! "$USERNAME" =~ ^[a-z][a-z0-9_-]{2,31}$ ]]; then
  echo "Erro: username inválido: $USERNAME" >&2
  exit 2
fi

# Garante que o grupo de visitantes do laboratório exista.
if ! getent group "$GROUP" > /dev/null; then
  groupadd "$GROUP"
  echo "Grupo '$GROUP' criado."
fi

# Idempotência: se o usuário já existe, apenas garante grupo/expiração e sai.
if id "$USERNAME" &>/dev/null; then
  usermod -aG "$GROUP" "$USERNAME"
  if [[ -n "$EXPIRES_AT" ]]; then
    chage -E "$EXPIRES_AT" "$USERNAME"
  fi
  echo "Usuário '$USERNAME' já existia; grupo/expiração atualizados."
  exit 0
fi

useradd \
  --create-home \
  --base-dir "$HOME_BASE" \
  --shell /bin/bash \
  --groups "$GROUP" \
  --comment "Acesso temporário de laboratório (lab-access-manager)" \
  "$USERNAME"

# Conta sem senha utilizável — o acesso real acontece via chave SSH
# provisionada pelo Next Term / VPN Pangolin, nunca por senha estática.
passwd --lock "$USERNAME"

if [[ -n "$EXPIRES_AT" ]]; then
  chage -E "$EXPIRES_AT" "$USERNAME"
fi

# Diretório dedicado para os dados de teste do usuário (referenciado
# pela descrição do que ele deseja testar, cadastrada no sistema).
install -d -m 750 -o "$USERNAME" -g "$GROUP" "$HOME_BASE/$USERNAME/workspace"

echo "Usuário '$USERNAME' criado com sucesso (expira em: ${EXPIRES_AT:-sem data definida})."
