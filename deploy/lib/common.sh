# Helpers shared by setup.sh and manage.sh, which source this file; it loads the settings from
# deploy/settings.env and the other files in deploy/lib. Not meant to be run on its own.
#
# Ownership (see "Permissions" in docs/operations.md):
#   root owns the checkout, including backend/.venv and backend/staticfiles, and runs git and uv;
#   the developers' group can change the checkout too; pis is not in it;
#   pis runs the app and can only write the database; root owns the backups;
#   pis-pipeline runs the notebook pipeline and writes the dashboard, which pis can only read.
set -euo pipefail

# The settings: paths, users, database, port, schedules.
source "$(dirname "${BASH_SOURCE[0]}")/../settings.env"

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
