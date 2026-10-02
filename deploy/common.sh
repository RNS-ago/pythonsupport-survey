# Shared by setup.sh and update.sh; not meant to be run on its own.
# The paths here must match pis-survey.service and backup.sh.
#
# Ownership (see "Permissions" in the root README):
#   root owns the checkout, including backend/.venv and backend/staticfiles, and runs git and uv;
#   the developers' group can change the checkout too; pis is not in it;
#   pis runs the app and can only write the database and the backups.
set -euo pipefail

APP_DIR=/srv/pythonsupport-survey
APP_USER=pis
SERVICE=pis-survey
# The server's group for the people working on this project (gid 15118 on psqdb).
DEV_GROUP=pythonsupport

[[ $EUID -eq 0 ]] || { echo "Run this script as root (sudo)." >&2; exit 1; }
[[ "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" == "$APP_DIR" ]] \
  || { echo "The repository must be cloned to $APP_DIR." >&2; exit 1; }
cd "$APP_DIR"

# uv would install Python under /root, which pis can't enter; put it somewhere pis can run it.
export UV_PYTHON_INSTALL_DIR=/opt/uv-python

# Install dependencies into backend/.venv as root: pis can run them but not change them.
sync_deps() {
  uv sync --directory backend --locked --no-dev --compile-bytecode
  # pis can't write __pycache__ into the root-owned checkout, so compile the app's code now.
  backend/.venv/bin/python -m compileall -q backend/pythonsupport
}

# manage.py with the production settings from backend/.env, as the given user:
# pis for anything touching the database, root for collectstatic.
manage_as() {
  local user=$1; shift
  sudo -u "$user" -H uv run --no-sync --directory "$APP_DIR/backend/pythonsupport" \
    --env-file "$APP_DIR/backend/.env" python manage.py "$@"
}

install_service() {
  install -m 644 deploy/$SERVICE.service /etc/systemd/system/$SERVICE.service
  systemctl daemon-reload
}

# Fail loudly if Django doesn't answer, instead of leaving a dead site.
# Asks gunicorn directly for the admin login page, as nginx would: the Host header must be in
# ALLOWED_HOSTS.
check_service() {
  local host
  host=$(sed -n 's/^ALLOWED_HOSTS=\([^ ]*\).*/\1/p' backend/.env)
  for _ in {1..15}; do
    sleep 1
    curl -fsS -o /dev/null -H "Host: $host" http://127.0.0.1:2810/admin/login/ 2>/dev/null && return 0
  done
  echo "Django did not answer on http://127.0.0.1:2810/admin/login/ within 15 seconds." >&2
  journalctl -u $SERVICE -n 30 --no-pager
  return 1
}

step() { if [ -t 1 ]; then printf '\n\033[1;36m=====>\033[0m \033[1;35m%s\033[0m\n' "$*"; else printf '\n=====> %s\n' "$*"; fi; }
