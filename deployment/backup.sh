#!/usr/bin/env bash
# Lounge Coin - Database Backup Script
# Usage: Run via cron daily (see deployment/crontab)
#
# Requires: pg_dump, gzip
# Environment: DB_NAME, DB_USER (from .env or defaults below)

set -euo pipefail

BACKUP_DIR="/var/backups/loungecoin"
DB_NAME="${DB_NAME:-loungecoin}"
DB_USER="${DB_USER:-loungecoin}"
RETENTION_DAYS=30

mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/db_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting backup of database '${DB_NAME}'..."

pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_FILE"

echo "[$(date)] Backup saved to ${BACKUP_FILE}"

# Clean up old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +${RETENTION_DAYS} -delete

echo "[$(date)] Cleaned backups older than ${RETENTION_DAYS} days."
