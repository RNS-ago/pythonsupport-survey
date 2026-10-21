# Database backups in BACKUP_DIR, on BACKUP_SCHEDULE from cron and before every update.
# pis reads the database; root writes the dumps, so a compromised app can't touch them.

# Dump the database and delete old dumps. Prints the dump's path, and nothing else on stdout:
# update_app restores from it on failure.
backup_db() {
  local file
  file=$BACKUP_DIR/db-$(date +%F-%H%M%S).dump
  # A consistent snapshot, also while gunicorn is writing. Includes the analysts' schemas.
  # The shell creates the file before pg_dump runs, so remove it if the dump fails.
  runuser -u "$APP_USER" -- pg_dump --format=custom "$DB" > "$file" || { rm -f "$file"; return 1; }
  echo "$file"
  find "$BACKUP_DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
}

install_backup_cron() {
  install -d -m 700 -o root -g root "$BACKUP_DIR"
  echo "$BACKUP_SCHEDULE root $APP_DIR/deploy/manage.sh backup" > /etc/cron.d/$SERVICE
  # apt doesn't start services everywhere (e.g. Docker images), so make sure cron runs.
  systemctl enable --now cron
}
