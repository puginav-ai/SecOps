#!/bin/bash
# Ежемесячная проверка восстановления (обязательство из SDD §6):
# последний (или указанный) pg_dump → временная БД → sanity-проверки → удаление.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f ops/compose.yaml"
DUMP="${1:-$(ls -1t backups/pg/db_*.sql.gz 2>/dev/null | head -1)}"
RESTORE_DB="secops_restore_check"

if [ -z "${DUMP:-}" ] || [ ! -f "$DUMP" ]; then
    echo "Нет дампа для проверки (сначала make backup)" >&2
    exit 1
fi

echo "[$(date +%T)] restore-check: $DUMP → временная БД $RESTORE_DB"
$COMPOSE exec -T postgres sh -c "dropdb -U \"\$POSTGRES_USER\" --if-exists $RESTORE_DB && createdb -U \"\$POSTGRES_USER\" $RESTORE_DB"
gunzip -c "$DUMP" | $COMPOSE exec -T postgres sh -c "psql -q -U \"\$POSTGRES_USER\" -d $RESTORE_DB"

users=$($COMPOSE exec -T postgres sh -c "psql -tA -U \"\$POSTGRES_USER\" -d $RESTORE_DB -c 'select count(*) from core_user'")
migrations=$($COMPOSE exec -T postgres sh -c "psql -tA -U \"\$POSTGRES_USER\" -d $RESTORE_DB -c 'select count(*) from django_migrations'")
audit=$($COMPOSE exec -T postgres sh -c "psql -tA -U \"\$POSTGRES_USER\" -d $RESTORE_DB -c 'select count(*) from core_auditlog'")

$COMPOSE exec -T postgres sh -c "dropdb -U \"\$POSTGRES_USER\" $RESTORE_DB"

if [ "$migrations" -lt 1 ]; then
    echo "ПРОВАЛ: в восстановленной БД нет миграций" >&2
    exit 1
fi
echo "OK: пользователей $users, миграций $migrations, записей аудита $audit; временная БД удалена"
