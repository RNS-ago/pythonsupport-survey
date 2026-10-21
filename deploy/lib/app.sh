# The Django app: settings, dependencies, manage.py and the gunicorn service.

# Writes backend/.env once (needs DOMAIN, URL and TEST_MODE from setup.sh); keeps an existing one.
write_env_file() {
  local env_file=backend/.env
  if [[ -f $env_file ]]; then
    echo "Keeping the existing $env_file."
  else
    local password
    read -rsp "Supporter password (the daily code): " password; echo
    install -m 640 -o root -g "$APP_USER" /dev/null "$env_file"
    cat > "$env_file" <<EOF
SECRET_KEY=$(openssl rand -hex 32)
ALLOWED_HOSTS=$DOMAIN
FRONTEND_ORIGINS=$URL
SURVEY_PASSWORD=$password
DATABASE_NAME=$DB
EOF
    # No nginx in front in test mode: let the browser reach gunicorn directly.
    [[ -z $TEST_MODE ]] || printf 'DEBUG=1\nPIS_BIND=0.0.0.0:%s\n' "$PORT" >> "$env_file"
  fi
  # pis reads the settings but can't change them. They hold the secret key and the password,
  # so the developers' group gets no access (setfacl -b drops the ACL from share_checkout).
  setfacl -b "$env_file"
  chown root:"$APP_USER" "$env_file"
  chmod 640 "$env_file"
}

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
    curl -fsS -o /dev/null --max-time 5 -H "Host: $host" http://127.0.0.1:$PORT/admin/login/ 2>/dev/null && return 0
  done
  echo "Django did not answer on http://127.0.0.1:$PORT/admin/login/ within 15 seconds." >&2
  journalctl -u $SERVICE -n 30 --no-pager
  return 1
}
