# PostgreSQL: the app's database, its rights (deploy/db-permissions.sql), password logins
# through PAM, and the developers' logins.

pg_admin() { runuser -u postgres -- psql -X -qtA -v ON_ERROR_STOP=1 "$@"; }

# pis connects over the local socket as itself (peer authentication), so no password is needed.
setup_database() {
  # apt doesn't start services everywhere (e.g. Docker images), so make sure PostgreSQL runs.
  systemctl enable --now postgresql
  [[ $(pg_admin -c "SELECT 1 FROM pg_roles WHERE rolname = '$APP_USER'") == 1 ]] \
    || runuser -u postgres -- createuser "$APP_USER"
  [[ $(pg_admin -c "SELECT 1 FROM pg_database WHERE datname = '$DB'") == 1 ]] \
    || runuser -u postgres -- createdb --owner="$APP_USER" "$DB"
}

# Schemas, group roles and their rights, from the file maintainers edit.
apply_db_permissions() {
  pg_admin -1 -d "$DB" < deploy/db-permissions.sql
}

# Users log in with their cluster (SSSD) username and password through PAM.
#
# The pg_hba.conf rule is for logins arriving through nginx. nginx terminates TLS, so
# PostgreSQL sees plain connections from nginx's address: "host", not "hostssl" (which would
# never match). Allowing only nginx's address stops anyone skipping TLS. Check the address
# from a remote session with: SELECT inet_client_addr();
HBA_LINE=${HBA_LINE:-'host all all 127.0.0.1/32 pam pamservice=postgresql'}

setup_pam_auth() {
  # The PAM service PostgreSQL uses (pamservice=postgresql). pam_sss asks the SSSD daemon, so
  # it works as the postgres user. root-owned: whoever can edit this file can make every
  # password succeed.
  install -o root -g root -m 644 /dev/stdin /etc/pam.d/postgresql <<'EOF'
auth     required  pam_sss.so
account  required  pam_sss.so
EOF

  # Insert the rule before the first host* line, because the first matching line wins.
  local hba
  hba=$(pg_admin -c 'SHOW hba_file')
  cp -p "$hba" "$hba.bak"
  if ! grep -qxF "$HBA_LINE" "$hba"; then
    awk -v l="$HBA_LINE" '!done && /^host/ {print l; done=1} {print} END {if (!done) print l}' "$hba" > "$hba.new"
    cat "$hba.new" > "$hba" && rm "$hba.new"   # cat keeps the file's owner and mode
  fi

  # Check pg_hba.conf before reloading; on errors put the old file back, since PostgreSQL
  # won't start with an invalid one.
  if pg_admin -c "SELECT 'pg_hba.conf line ' || line_number || ': ' || error
                  FROM pg_hba_file_rules WHERE error IS NOT NULL" | grep .; then
    cat "$hba.bak" > "$hba"
    echo "pg_hba.conf left unchanged." >&2
    return 1
  fi
  pg_admin -c 'SELECT pg_reload_conf()' >/dev/null
}

# Give every member of the developers' group a database login for the notebooks, and remove
# the logins of people who have left it. See docs/data-analysis.md.
#
# PostgreSQL can't check Linux groups, so each member gets a login named like their account.
# Each login is a member of pis_analyst (rights in deploy/db-permissions.sql), and its sessions
# switch to pis_analyst, so all analysts share the tables they create, and tables created
# without a schema go to processed_data. Needs apply_db_permissions to have run.
sync_db_users() {
  local members user
  # Only members listed in the group itself; someone whose primary group it is isn't listed.
  members=" $(getent group "$DEV_GROUP" | cut -d: -f4 | tr , ' ') "

  for user in $members; do
    # Names come from the directory service and go into SQL: allow only plain account names.
    [[ $user =~ ^[a-z0-9_.-]+$ ]] || { echo "Skipping unusual account name: $user" >&2; continue; }
    [[ $(pg_admin -d "$DB" -c "SELECT 1 FROM pg_roles WHERE rolname = '$user'") == 1 ]] \
      || pg_admin -d "$DB" -c "CREATE ROLE \"$user\" LOGIN"
    [[ $(pg_admin -d "$DB" -c "SELECT pg_has_role('$user', '$ANALYST_ROLE', 'MEMBER')") == t ]] \
      || pg_admin -d "$DB" -c "GRANT $ANALYST_ROLE TO \"$user\""
    pg_admin -d "$DB" -c "ALTER ROLE \"$user\" SET role = $ANALYST_ROLE"
    pg_admin -d "$DB" -c "ALTER ROLE \"$user\" SET search_path = processed_data, public"
    echo "Notebook access: $user"
  done

  # Every other login in pis_analyst belongs to someone who has left the group (pis is a member
  # too, for backups). Viewers (pis_viewer only) are added by hand and left alone.
  for user in $(pg_admin -d "$DB" -c "SELECT r.rolname FROM pg_auth_members m
                                      JOIN pg_roles r ON r.oid = m.member
                                      JOIN pg_roles p ON p.oid = m.roleid
                                      WHERE p.rolname = '$ANALYST_ROLE' AND r.rolname <> '$APP_USER'"); do
    [[ $members == *" $user "* ]] && continue
    # Anything the login still owns goes to pis_analyst first, so no data is lost.
    pg_admin -d "$DB" -c "REASSIGN OWNED BY \"$user\" TO $ANALYST_ROLE; DROP OWNED BY \"$user\"; DROP ROLE \"$user\""
    echo "Removed notebook access: $user"
  done
}
