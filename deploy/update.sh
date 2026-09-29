#!/usr/bin/env bash
# Deploy the latest code of a branch (default: main). See "Updating" in the root README.
#
#   sudo /srv/pythonsupport-survey/deploy/update.sh [branch]
BRANCH=${1:-main}
source "$(dirname "$0")/common.sh"

step "Code ($BRANCH)"
git fetch origin
git checkout "$BRANCH"
git pull --ff-only origin "$BRANCH"

# Re-exec the freshly pulled script, so changes to update.sh itself apply to this run.
if [[ -z ${PIS_UPDATE_REEXEC:-} ]]; then
  PIS_UPDATE_REEXEC=1 exec "$APP_DIR/deploy/update.sh" "$BRANCH"
fi

step "Backup before migrating"
sudo -u "$APP_USER" "$APP_DIR/deploy/backup.sh"

step "Python dependencies"
sync_deps

step "Database and static files"
manage_as "$APP_USER" migrate
manage_as root collectstatic --no-input

step "Restart"
install_service
systemctl restart $SERVICE
check_service

step "Done. Frontend files are served straight from the checkout, so they are live already."
