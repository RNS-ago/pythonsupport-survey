#!/usr/bin/env bash
# Give every member of the developers' group a database login for the notebooks, and remove
# the logins of people who have left it. See "Notebooks" in the root README.
#
#   sudo /srv/pythonsupport-survey/deploy/notebook-access.sh
#
# setup.sh runs it; run it again whenever someone joins or leaves the group.
#
# PostgreSQL can't check Linux groups, so each member gets a login named like their account
# (peer authentication: no passwords). Each login has the same rights as the app, its sessions
# switch to pis, so tables the notebooks create belong to pis and are covered by backups and
# restores, and tables created without a schema go to analysis, not between Django's tables.
source "$(dirname "$0")/common.sh"

psql_admin() { sudo -u postgres psql -v ON_ERROR_STOP=1 -qtAd pis_survey -c "$1"; }

# Only members listed in the group itself; someone whose primary group it is isn't listed.
members=" $(getent group "$DEV_GROUP" | cut -d: -f4 | tr , ' ') "

for user in $members; do
  # Names come from the directory service and go into SQL: allow only plain account names.
  [[ $user =~ ^[a-z0-9_.-]+$ ]] || { echo "Skipping unusual account name: $user" >&2; continue; }
  [[ $(psql_admin "SELECT 1 FROM pg_roles WHERE rolname = '$user'") == 1 ]] \
    || psql_admin "CREATE ROLE \"$user\" LOGIN IN ROLE $APP_USER"
  psql_admin "ALTER ROLE \"$user\" SET role = $APP_USER"
  psql_admin "ALTER ROLE \"$user\" SET search_path = analysis, public"
  echo "Notebook access: $user"
done

# Every other login that is a member of pis belongs to someone who has left the group.
for user in $(psql_admin "SELECT r.rolname FROM pg_auth_members m
                          JOIN pg_roles r ON r.oid = m.member
                          JOIN pg_roles p ON p.oid = m.roleid
                          WHERE p.rolname = '$APP_USER'"); do
  [[ $members == *" $user "* ]] && continue
  # Anything the login still owns goes to pis first, so no data is lost.
  psql_admin "REASSIGN OWNED BY \"$user\" TO $APP_USER; DROP OWNED BY \"$user\"; DROP ROLE \"$user\""
  echo "Removed notebook access: $user"
done
