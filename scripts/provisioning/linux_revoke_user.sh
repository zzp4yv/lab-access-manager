#!/usr/bin/env bash
#
# Revoga o acesso de um usuário Linux de laboratório SEM apagar seus
# dados (a remoção definitiva é feita depois por linux_purge_user.sh,
# 30 dias após a revogação, conforme política de retenção).
#
# Uso: linux_revoke_user.sh --username <nome>
#
set -euo pipefail

USERNAME=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --username) USERNAME="$2"; shift 2 ;;
    *) echo "Argumento desconhecido: $1" >&2; exit 2 ;;
  esac
done

if [[ -z "$USERNAME" ]]; then
  echo "Erro: --username é obrigatório" >&2
  exit 2
fi

if ! id "$USERNAME" &>/dev/null; then
  echo "Usuário '$USERNAME' não existe; nada a revogar."
  exit 0
fi

# Bloqueia login (senha + expira a conta imediatamente) e encerra
# quaisquer sessões ativas.
passwd --lock "$USERNAME"
usermod --expiredate 1 "$USERNAME"
usermod --shell /usr/sbin/nologin "$USERNAME"

if command -v pkill &>/dev/null; then
  pkill -KILL -u "$USERNAME" || true
fi

echo "Acesso do usuário '$USERNAME' revogado (dados mantidos até a purga)."
