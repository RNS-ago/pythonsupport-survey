#!/usr/bin/env bash
# First-time setup of a fresh Debian/Ubuntu server. See "Deployment" in the root README.
#
#   sudo git clone https://github.com/RNS-ago/pythonsupport-survey.git /srv/pythonsupport-survey
#   sudo /srv/pythonsupport-survey/deploy/setup.sh psqdb.compute.dtu.dk
#
# Test mode, for trying the setup on a local machine or container (never in production):
#
#   sudo /srv/pythonsupport-survey/deploy/setup.sh --test [host]    # host defaults to localhost
#
# There is no nginx in front, so gunicorn serves plain HTTP on port 2810 to any machine, with
# DEBUG=1, because without HTTPS the production session cookie (HTTPS-only) would make
# logging in impossible.
#
# Safe to run again after a failure: finished steps are skipped or repeated harmlessly.
USAGE="usage: setup.sh <domain>  |  setup.sh --test [host]"
if [[ ${1:-} == --test ]]; then
  TEST_MODE=1
  DOMAIN=${2:-localhost}
  URL=http://$DOMAIN:2810
else
  TEST_MODE=
  DOMAIN=${1:?$USAGE}
  URL=https://$DOMAIN
fi
source "$(dirname "$0")/common.sh"

test_mode_warning() {
  # Bold red on a terminal, like step()'s colours; plain text when piped to a log.
  local on='' off=''
  [ -t 1 ] && { on='\033[1;31m'; off='\033[0m'; }
  printf "\n${on}!!! TEST MODE: plain HTTP, DEBUG=1, and gunicorn reachable from other machines.${off}\n"
  printf "${on}!!! Do not use this setup in production. Run setup.sh <domain> on the real server.${off}\n"
}
[[ -z $TEST_MODE ]] || test_mode_warning

step "System packages"
apt-get update
apt-get install -y git sudo curl openssl cron postgresql

step "uv"
command -v uv >/dev/null \
  || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

step "Service user '$APP_USER'"
id "$APP_USER" &>/dev/null \
  || useradd --system --create-home --home-dir "/var/lib/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
# The app can read its code but not change it.
chown -R root:root "$APP_DIR"

step "PostgreSQL database"
# apt doesn't start services everywhere (e.g. Docker images), so make sure PostgreSQL runs.
systemctl enable --now postgresql
psql_admin() { sudo -u postgres psql -v ON_ERROR_STOP=1 -qtAc "$1"; }
# pis connects over the local socket as itself (peer authentication), so no password is needed.
[[ $(psql_admin "SELECT 1 FROM pg_roles WHERE rolname = '$APP_USER'") == 1 ]] \
  || sudo -u postgres createuser "$APP_USER"
[[ $(psql_admin "SELECT 1 FROM pg_database WHERE datname = 'pis_survey'") == 1 ]] \
  || sudo -u postgres createdb --owner="$APP_USER" pis_survey
# Processed tables from the notebooks live here, apart from the tables Django manages.
sudo -u "$APP_USER" psql -v ON_ERROR_STOP=1 -qd pis_survey -c "CREATE SCHEMA IF NOT EXISTS analysis"

step "Notebook access for ${SUDO_USER:-nobody}"
# The person running this script (through sudo) gets a database login with the same rights as
# the app, for the notebooks (see "Notebooks" in the root README). Every session switches to
# pis, so tables the notebooks create belong to pis and are covered by backups and restores.
if [[ -n ${SUDO_USER:-} && $SUDO_USER != root ]]; then
  [[ $(psql_admin "SELECT 1 FROM pg_roles WHERE rolname = '$SUDO_USER'") == 1 ]] \
    || psql_admin "CREATE ROLE \"$SUDO_USER\" LOGIN IN ROLE $APP_USER"
  psql_admin "ALTER ROLE \"$SUDO_USER\" SET role = $APP_USER"
else
  echo "Skipped: run setup.sh with sudo from your own account to get notebook access."
fi

step "Settings (backend/.env)"
ENV_FILE=backend/.env
if [[ -f $ENV_FILE ]]; then
  echo "Keeping the existing $ENV_FILE."
else
  read -rsp "Supporter password (the daily code): " SURVEY_PASSWORD; echo
  install -m 640 -o root -g "$APP_USER" /dev/null "$ENV_FILE"
  cat > "$ENV_FILE" <<EOF
SECRET_KEY=$(openssl rand -hex 32)
ALLOWED_HOSTS=$DOMAIN
FRONTEND_ORIGINS=$URL
SURVEY_PASSWORD=$SURVEY_PASSWORD
DATABASE_NAME=pis_survey
EOF
  # No nginx in front in test mode: let the browser reach gunicorn directly (port 2810).
  [[ -z $TEST_MODE ]] || printf 'DEBUG=1\nPIS_BIND=0.0.0.0:2810\n' >> "$ENV_FILE"
fi
# pis reads the settings but can't change them.
chown root:"$APP_USER" "$ENV_FILE"
chmod 640 "$ENV_FILE"

step "Python dependencies"
sync_deps

step "Database and static files"
manage_as "$APP_USER" migrate
manage_as root collectstatic --no-input

step "Backups (daily at 03:00)"
install -d -m 700 -o "$APP_USER" -g "$APP_USER" /var/backups/pis-survey
echo "0 3 * * * $APP_USER $APP_DIR/deploy/backup.sh" > /etc/cron.d/pis-survey
# apt doesn't start services everywhere (e.g. Docker images), so make sure cron runs.
systemctl enable --now cron

step "gunicorn service"
install_service
systemctl enable --now $SERVICE
systemctl restart $SERVICE
check_service

step "Admin account for $URL/admin/"
manage_as "$APP_USER" createsuperuser

step "Done: $URL"
[[ -z $TEST_MODE ]] || test_mode_warning
