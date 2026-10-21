# The machine: packages, uv, the service user and the shared checkout.

install_packages() {
  apt-get update
  apt-get install -y git sudo curl openssl cron acl postgresql
}

install_uv() {
  command -v uv >/dev/null \
    || curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin UV_NO_MODIFY_PATH=1 sh
}

create_app_user() {
  id "$APP_USER" &>/dev/null \
    || useradd --system --create-home --home-dir "/var/lib/$APP_USER" --shell /usr/sbin/nologin "$APP_USER"
}

# Members of the group can change the checkout and run git in it; the app (pis, not a member)
# can only read it. The default ACL gives files created later, by anyone, the same group rights.
share_checkout() {
  if ! getent group "$DEV_GROUP" >/dev/null; then
    # The real server gets the group from DTU's directory; only a test machine may create it.
    [[ -n ${TEST_MODE:-} ]] || { echo "The group '$DEV_GROUP' doesn't exist on this server." >&2; exit 1; }
    groupadd "$DEV_GROUP"
  fi
  chown -R root:"$DEV_GROUP" "$APP_DIR"
  setfacl -R -m g::rwX -m d:g::rwX -m o::rX -m d:o::rX "$APP_DIR"
  find "$APP_DIR" -type d -exec chmod g+s {} +
  git config core.sharedRepository group
  # git refuses to work in a repository owned by someone else unless it is marked safe.
  git config --system --get-all safe.directory | grep -qxF "$APP_DIR" \
    || git config --system --add safe.directory "$APP_DIR"
}
