#!/usr/bin/env bash
#
# Remove definitivamente a conta e os dados de um usuário Linux de
# laboratório. Chamado 30 dias após a revogação (DATA_RETENTION_DAYS_AFTER_REVOKE).
#
# Uso: linux_purge_user.sh --username <nome>
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
  echo "Usuário '$USERNAME' não existe; nada a purgar."
  exit 0
fi

if command -v pkill &>/dev/null; then
  pkill -KILL -u "$USERNAME" || true
fi

# --remove apaga o diretório home e o mail spool do usuário.
userdel --remove --force "$USERNAME"

echo "Usuário '$USERNAME' e seus dados foram removidos permanentemente."
