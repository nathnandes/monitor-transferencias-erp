#!/usr/bin/env sh
set -eu

cd "$(dirname "$0")/.."
ARQUIVO="${1:-$(ls -t backups/erp_*.dump 2>/dev/null | head -n 1 | xargs -r basename)}"
if [ -z "$ARQUIVO" ] || [ ! -s "backups/$ARQUIVO" ]; then
  echo "backup nao encontrado: ${ARQUIVO:-nenhum em backups/}" >&2
  exit 1
fi

BANCO=erp_verificacao
no_db() {
  docker compose -f docker-compose.prod.yml exec -T db sh -c "$1"
}
limpar() {
  no_db "dropdb --if-exists -U \"\$POSTGRES_USER\" $BANCO" >/dev/null 2>&1 || true
}
trap limpar EXIT

echo "restaurando $ARQUIVO em $BANCO..."
no_db "dropdb --if-exists -U \"\$POSTGRES_USER\" $BANCO && createdb -U \"\$POSTGRES_USER\" $BANCO"
no_db "pg_restore -U \"\$POSTGRES_USER\" -d $BANCO --no-owner --exit-on-error /backups/$ARQUIVO"

VERSAO="$(no_db "psql -U \"\$POSTGRES_USER\" -d $BANCO -tAc 'SELECT version_num FROM alembic_version'" | tr -d '[:space:]')"
EMPRESAS="$(no_db "psql -U \"\$POSTGRES_USER\" -d $BANCO -tAc 'SELECT count(*) FROM empresas'" | tr -d '[:space:]')"
if [ -z "$VERSAO" ]; then
  echo "restaurado sem alembic_version: o schema nao veio" >&2
  exit 1
fi
if [ "${EMPRESAS:-0}" -lt 1 ]; then
  echo "restaurado sem empresas: o dump parece vazio" >&2
  exit 1
fi
echo "restauracao ok: $ARQUIVO (schema $VERSAO, $EMPRESAS empresas)"
