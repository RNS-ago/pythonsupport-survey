#!/usr/bin/env bash
# Copy the SQLite database to /var/backups/pis-survey and delete old copies.
# Runs daily from cron (installed by setup.sh) and before every update.sh.
set -euo pipefail

# Must match DATABASE_PATH in backend/.env (written by setup.sh).
DB=/var/lib/pis-survey/db.sqlite3
BACKUP_DIR=/var/backups/pis-survey
# The database holds student numbers: keep copies only as long as the retention policy allows.
KEEP_DAYS=30

[[ -f $DB ]] || { echo "No database at $DB yet, nothing to back up."; exit 0; }

# .backup is safe while gunicorn is writing, unlike a plain cp.
sqlite3 "$DB" ".backup '$BACKUP_DIR/db-$(date +%F-%H%M%S).sqlite3'"
find "$BACKUP_DIR" -name 'db-*.sqlite3' -mtime +"$KEEP_DAYS" -delete
