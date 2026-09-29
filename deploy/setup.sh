#!/usr/bin/env bash
# First-time setup of a fresh Debian/Ubuntu server. See "Deployment" in the root README.
#
#   sudo git clone https://github.com/RNS-ago/pythonsupport-survey.git /srv/pythonsupport-survey
#   sudo /srv/pythonsupport-survey/deploy/setup.sh survey.example.dk
#
# Test mode, for trying the setup on a local machine or container (never in production):
#
#   sudo /srv/pythonsupport-survey/deploy/setup.sh --test [host]    # host defaults to localhost
#
# It serves plain HTTP without a certificate, with DEBUG=1, because without HTTPS the
# production session cookie (HTTPS-only) would make logging in impossible.
#
# Safe to run again after a failure: finished steps are skipped or repeated harmlessly.
USAGE="usage: setup.sh <domain>  |  setup.sh --test [host]"
if [[ ${1:-} == --test ]]; then
  TEST_MODE=1
  DOMAIN=${2:-localhost}
  SCHEME=http
  SITE_ADDRESS=http://$DOMAIN
else
  TEST_MODE=
  DOMAIN=${1:?$USAGE}
  SCHEME=https
  SITE_ADDRESS=$DOMAIN
fi
source "$(dirname "$0")/common.sh"

test_mode_warning() {
  # Bold red on a terminal, like step()'s colours; plain text when piped to a log.
  local on='' off=''
  [ -t 1 ] && { on='\033[1;31m'; off='\033[0m'; }
  printf "\n${on}!!! TEST MODE: plain HTTP, DEBUG=1 and no HTTPS certificate.${off}\n"
  printf "${on}!!! Do not use this setup in production. Run setup.sh <domain> on the real server.${off}\n"
}
[[ -z $TEST_MODE ]] || test_mode_warning

step "System packages"
apt-get update
apt-get install -y git sudo curl openssl sqlite3 cron caddy

step "uv"
command -v uv >/dev/null \
  || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh

step "Service user '$APP_USER'"
id "$APP_USER" &>/dev/null \
  || useradd --system --create-home --home-dir "/var/lib/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
# The app can read its code but not change it.
chown -R root:root "$APP_DIR"

step "Database folder"
# Outside the checkout, so re-cloning or cleaning the repository can never delete the data.
install -d -m 700 -o "$APP_USER" -g "$APP_USER" /var/lib/pis-survey

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
FRONTEND_ORIGINS=$SCHEME://$DOMAIN
SURVEY_PASSWORD=$SURVEY_PASSWORD
DATABASE_PATH=/var/lib/pis-survey/db.sqlite3
EOF
  [[ -z $TEST_MODE ]] || echo "DEBUG=1" >> "$ENV_FILE"
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

step "Caddy (web server and HTTPS certificate)"
# Replaces the package's default site. The site itself is deploy/Caddyfile in the checkout.
echo "import $APP_DIR/deploy/Caddyfile $SITE_ADDRESS" > /etc/caddy/Caddyfile
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
# Start Caddy if apt didn't (e.g. in Docker), reload it if it is already running.
systemctl enable caddy
systemctl reload-or-restart caddy
# Without test mode, Caddy now fetches the certificate in the background. That needs DNS for
# $DOMAIN pointing at this server and ports 80/443 open; see: journalctl -u caddy

step "Admin account for $SCHEME://$DOMAIN/admin/"
manage_as "$APP_USER" createsuperuser

step "Done: $SCHEME://$DOMAIN"
[[ -z $TEST_MODE ]] || test_mode_warning
