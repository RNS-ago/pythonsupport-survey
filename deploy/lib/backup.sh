# pis reads the database; root writes the dumps, so a compromised app can't touch them.

# Prints only the dump's path on stdout: update_app restores from it on failure.
backup_db() {
  local file
  file=$BACKUP_DIR/db-$(date +%F-%H%M%S).dump
  # The shell creates the file before pg_dump runs, so remove it if the dump fails.
  runuser -u "$APP_USER" -- pg_dump --format=custom "$DATABASE_NAME" > "$file" || { rm -f "$file"; return 1; }
  echo "$file"
  find "$BACKUP_DIR" -name 'db-*.dump' -mtime +"$KEEP_DAYS" -delete
}

install_backup_cron() {
  install -d -m 700 -o root -g root "$BACKUP_DIR"
  echo "$BACKUP_SCHEDULE root $APP_DIR/deploy/manage.sh backup" > /etc/cron.d/$SERVICE
  # apt doesn't start services in Docker images.
  systemctl enable --now cron
}
