# If a step after pulling fails, rollback restores the previous code and, once migrations have
# started, the database.

update_app() {
  local branch=$1
  if [[ -z ${PIS_UPDATE_FROM:-} ]]; then
    step "Code ($branch)"
    local from
    from=$(git rev-parse HEAD)
    git fetch origin
    git checkout "$branch"
    git pull --ff-only origin "$branch"
    # Re-exec, so changes to the deploy scripts apply to this run.
    PIS_UPDATE_FROM=$from exec "$APP_DIR/deploy/manage.sh" update "$branch"
  fi

  BACKUP=
  trap '[[ $? -eq 0 ]] || rollback' EXIT

  step "Python dependencies"
  sync_deps
  manage_as root collectstatic --no-input

  # Stopped, so a restore can't lose responses. Supporters' devices queue them meanwhile.
  step "Backup and migrations"
  systemctl stop $SERVICE
  BACKUP=$(backup_db)
  manage_as "$APP_USER" migrate
  apply_db_permissions

  step "Start"
  install_service
  # The cron jobs may point at scripts that have moved.
  install_backup_cron
  setup_pipeline
  systemctl start $SERVICE
  check_service

  step "Done. Frontend files are served straight from the checkout, so they are live already."
}

rollback() {
  set +e
  trap - EXIT
  step "FAILED. Rolling back to $PIS_UPDATE_FROM"
  systemctl stop $SERVICE
  if [[ -n $BACKUP ]]; then
    echo "Restoring the database from $BACKUP"
    # pis can't open the root-only backup directory, so pass the dump on stdin.
    runuser -u "$APP_USER" -- pg_restore --clean --if-exists --single-transaction --dbname="$DATABASE_NAME" < "$BACKUP"
  fi
  git checkout --detach "$PIS_UPDATE_FROM"
  sync_deps
  manage_as root collectstatic --no-input
  install_service
  systemctl start $SERVICE
  if check_service; then
    echo "The previous version is running again. Fix the problem, then run 'manage.sh update' again."
  else
    echo "The previous version did not come back up either. The site is down." >&2
  fi
  exit 1
}
