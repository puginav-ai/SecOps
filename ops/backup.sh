#!/bin/bash
# Бэкап GRC: pg_dump (сжатый) + снапшот S3-хранилища (SeaweedFS).
# Запуск: ops/backup.sh или systemd timer (ops/systemd/).
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="docker compose -f ops/compose.yaml"
BACKUP_DIR="${BACKUP_DIR:-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
STAMP="$(date +%F_%H%M)"

mkdir -p "$BACKUP_DIR/pg" "$BACKUP_DIR/s3"

echo "[$(date +%T)] pg_dump → $BACKUP_DIR/pg/db_$STAMP.sql.gz"
$COMPOSE exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB"' \
    | gzip > "$BACKUP_DIR/pg/db_$STAMP.sql.gz"

echo "[$(date +%T)] S3-снапшот → $BACKUP_DIR/s3/data_$STAMP.tar.gz"
# Консистентность: хранилище кратко останавливается (бэкап ночью, RPO 24 ч).
$COMPOSE stop s3 >/dev/null 2>&1 || true
docker run --rm \
    -v secops_s3data:/data:ro \
    -v "$PWD/$BACKUP_DIR/s3:/export" \
    alpine:3.22 sh -c \
    "tar -czf /export/data_$STAMP.tar.gz -C /data . && chown $(id -u):$(id -g) /export/data_$STAMP.tar.gz"
$COMPOSE start s3 >/dev/null

echo "[$(date +%T)] ретенция: > $RETENTION_DAYS дней"
find "$BACKUP_DIR/pg" -name 'db_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR/s3" -name 'data_*.tar.gz' -mtime +"$RETENTION_DAYS" -delete

echo "[$(date +%T)] готово: $(du -sh "$BACKUP_DIR" | cut -f1) в $BACKUP_DIR"
