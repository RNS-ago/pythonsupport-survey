#!/usr/bin/env bash
# First-time setup of a fresh Debian/Ubuntu server. See "Deployment" in the root README.
#
#   sudo git clone https://github.com/RNS-ago/pythonsupport-survey.git /srv/pythonsupport-survey
#   sudo /srv/pythonsupport-survey/deploy/setup.sh survey.example.dk
#
# Safe to run again after a failure: finished steps are skipped or repeated harmlessly.
DOMAIN=${1:?usage: setup.sh <domain>}
source "$(dirname "$0")/common.sh"

step "System packages"
apt-get update
apt-get install -y git sudo curl openssl sqlite3 nginx certbot python3-certbot-nginx

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
FRONTEND_ORIGINS=https://$DOMAIN
SURVEY_PASSWORD=$SURVEY_PASSWORD
DATABASE_PATH=/var/lib/pis-survey/db.sqlite3
EOF
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

step "gunicorn service"
install_service
systemctl enable --now $SERVICE
systemctl restart $SERVICE
check_service

step "nginx"
SITE=/etc/nginx/sites-available/pis-survey
# Never overwrite: certbot has added the HTTPS config to the installed copy.
[[ -f $SITE ]] || sed "s/__DOMAIN__/$DOMAIN/" deploy/nginx.conf > "$SITE"
ln -sf "$SITE" /etc/nginx/sites-enabled/pis-survey
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx

step "HTTPS certificate"
# Needs DNS for $DOMAIN pointing at this server and ports 80/443 open.
certbot --nginx -d "$DOMAIN" --redirect \
  || echo "certbot failed. Fix DNS/firewall, then run: sudo certbot --nginx -d $DOMAIN --redirect"

step "Admin account for https://$DOMAIN/admin/"
manage_as "$APP_USER" createsuperuser

step "Done: https://$DOMAIN"
