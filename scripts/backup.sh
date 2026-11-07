#!/usr/bin/env sh
set -eu

DIAS="${DIAS:-14}"
BACKUP_COPIA="${BACKUP_COPIA:-}"
cd "$(dirname "$0")/.."
mkdir -p backups

NOME="erp_$(date +%Y%m%d_%H%M%S).dump"
docker compose -f docker-compose.prod.yml exec -T db \
  sh -c "pg_dump -U \"\$POSTGRES_USER\" -d \"\$POSTGRES_DB\" -Fc -f /backups/$NOME"

if [ ! -s "backups/$NOME" ]; then
  echo "backup vazio ou ausente: backups/$NOME" >&2
  exit 1
fi
echo "backup ok: backups/$NOME ($(du -k "backups/$NOME" | cut -f1) KB)"

find backups -name 'erp_*.dump' -mtime +"$DIAS" -print -delete

if [ -n "$BACKUP_COPIA" ]; then
  mkdir -p "$BACKUP_COPIA"
  cp "backups/$NOME" "$BACKUP_COPIA/$NOME"
  if [ "$(wc -c < "backups/$NOME")" -ne "$(wc -c < "$BACKUP_COPIA/$NOME")" ]; then
    echo "copia externa com tamanho diferente: $BACKUP_COPIA/$NOME" >&2
    exit 1
  fi
  echo "copia externa ok: $BACKUP_COPIA/$NOME"
  find "$BACKUP_COPIA" -name 'erp_*.dump' -mtime +"$DIAS" -print -delete
else
  echo "AVISO: sem copia externa (BACKUP_COPIA): o backup esta so neste disco" >&2
fi
