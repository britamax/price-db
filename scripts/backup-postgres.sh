#!/bin/bash
# Daily PostgreSQL backup for Price DB
set -e

BACKUP_DIR="/opt/price-db/backups/postgres"
KEEP_DAYS=14
TS=$(date +%Y%m%d-%H%M%S)
LOG="$BACKUP_DIR/backup.log"

mkdir -p "$BACKUP_DIR"

# Read DB credentials from .env
set -a
source /opt/price-db/.env
set +a

OUT="$BACKUP_DIR/pricedb-$TS.sql.gz"

cd /opt/price-db
docker compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
  pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --no-owner --clean --if-exists \
  | gzip -9 > "$OUT"

SIZE=$(du -h "$OUT" | cut -f1)
echo "[$TS] backup OK $OUT ($SIZE)" >> "$LOG"

# Cleanup old backups
find "$BACKUP_DIR" -name 'pricedb-*.sql.gz' -mtime +$KEEP_DAYS -delete

# Keep log under 200 lines
tail -n 200 "$LOG" > "$LOG.tmp" && mv "$LOG.tmp" "$LOG"
