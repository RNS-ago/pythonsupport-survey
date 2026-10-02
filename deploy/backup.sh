#!/usr/bin/env bash
# Dump the PostgreSQL database to /var/backups/pis-survey and delete old dumps.
# Runs daily from cron (installed by setup.sh) and before every update.sh, as pis.
set -euo pipefail

# Must match DATABASE_NAME in backend/.env (written by setup.sh).
DB=pis_survey
BACKUP_DIR=/var/backups/pis-survey
# The database holds student numbers: keep copies only as long as the retention policy allows.
KEEP_DAYS=30

# Prints the backup's path, and nothing else on stdout: update.sh restores from it on failure.
FILE=$BACKUP_DIR/db-$(date +%F-%H%M%S).dump
# A consistent snapshot, also while gunicorn is writing. Includes the analysis schema.
pg_dump --format=custom --file="$FILE" "$DB"
echo "$FILE"
find "$BACKUP_DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
