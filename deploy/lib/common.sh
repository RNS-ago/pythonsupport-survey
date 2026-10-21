# Settings and helpers shared by setup.sh and manage.sh, which source this file; it then loads
# the other files in deploy/lib. Not meant to be run on its own.
# The settings below are the only place to change these values in the scripts. pis-survey.service
# and deploy/db-permissions.sql can't read them, so change them there by hand too.
#
# Ownership (see "Permissions" in docs/operations.md):
#   root owns the checkout, including backend/.venv and backend/staticfiles, and runs git and uv;
#   the developers' group can change the checkout too; pis is not in it;
#   pis runs the app and can only write the database; root owns the backups.
set -euo pipefail

APP_DIR=/srv/pythonsupport-survey
APP_USER=pis
SERVICE=pis-survey
# Must match DATABASE_NAME in backend/.env (written by setup.sh).
DB=pis_survey
# The server's group for the people working on this project (gid 15118 on psqdb).
DEV_GROUP=pythonsupport
# The database role the developers' logins get (deploy/db-permissions.sql defines its rights).
ANALYST_ROLE=pis_analyst
# gunicorn's port; nginx forwards to it.
PORT=2810

# Root-only, so a compromised app (running as pis) can't delete or change the backups.
BACKUP_DIR=/var/backups/pis-survey
# The database holds student numbers: keep copies only as long as the retention policy allows.
KEEP_DAYS=30
# When the daily backup runs (cron format: minute hour day month weekday).
BACKUP_SCHEDULE='0 3 * * *'

[[ $EUID -eq 0 ]] || { echo "Run this script as root (sudo)." >&2; exit 1; }
[[ "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)" == "$APP_DIR" ]] \
  || { echo "The repository must be cloned to $APP_DIR." >&2; exit 1; }
cd "$APP_DIR"

# uv would install Python under /root, which pis can't enter; put it somewhere pis can run it.
export UV_PYTHON_INSTALL_DIR=/opt/uv-python

step() { if [ -t 1 ]; then printf '\n\033[1;36m=====>\033[0m \033[1;35m%s\033[0m\n' "$*"; else printf '\n=====> %s\n' "$*"; fi; }

# The other files only define functions.
for lib in deploy/lib/*.sh; do
  [[ $lib == deploy/lib/common.sh ]] || source "$lib"
done
