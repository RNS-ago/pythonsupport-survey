#!/usr/bin/env bash
# Deploy the latest code of a branch (default: main). See "Updating" in the root README.
#
#   sudo /srv/pythonsupport-survey/deploy/update.sh [branch]
#
# If any step after pulling fails, the previous code (and, once migrations have started,
# the database from the backup taken just before) is put back and the old version restarted.
BRANCH=${1:-main}
source "$(dirname "$0")/common.sh"

if [[ -z ${PIS_UPDATE_FROM:-} ]]; then
  step "Code ($BRANCH)"
  FROM=$(git rev-parse HEAD)
  git fetch origin
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
  # Re-exec the freshly pulled script, so changes to update.sh itself apply to this run.
  PIS_UPDATE_FROM=$FROM exec "$APP_DIR/deploy/update.sh" "$BRANCH"
fi

DB=/var/lib/pis-survey/db.sqlite3   # must match DATABASE_PATH in backend/.env
BACKUP=

rollback() {
  set +e
  trap - EXIT
  step "FAILED. Rolling back to $PIS_UPDATE_FROM"
  systemctl stop $SERVICE
  if [[ -n $BACKUP ]]; then
    echo "Restoring the database from $BACKUP"
    sudo -u "$APP_USER" cp "$BACKUP" "$DB"
    # A journal left by an interrupted migration would be replayed onto the restored copy.
    rm -f "$DB-journal"
  fi
  git checkout --detach "$PIS_UPDATE_FROM"
  sync_deps
  manage_as root collectstatic --no-input
  install_service
  systemctl start $SERVICE
  if check_service; then
    echo "The previous version is running again. Fix the problem, then run update.sh again."
  else
    echo "The previous version did not come back up either. The site is down." >&2
  fi
  exit 1
}
trap '[[ $? -eq 0 ]] || rollback' EXIT

step "Python dependencies"
sync_deps
manage_as root collectstatic --no-input

# Stop the app while migrating, so no response written in the meantime is lost if the
# backup has to be restored. Supporters' devices queue survey responses while it is down.
step "Backup and migrations"
systemctl stop $SERVICE
BACKUP=$(sudo -u "$APP_USER" "$APP_DIR/deploy/backup.sh")
manage_as "$APP_USER" migrate

step "Start"
install_service
systemctl start $SERVICE
check_service

step "Done. Frontend files are served straight from the checkout, so they are live already."
