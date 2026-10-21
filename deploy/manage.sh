#!/usr/bin/env bash
# Day-to-day jobs on the server, after setup.sh. See docs/deployment.md and docs/operations.md.
#
#   sudo /srv/pythonsupport-survey/deploy/manage.sh update [branch]   # deploy a branch (default: main)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh backup            # dump the database (also daily from cron)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh users             # sync notebook logins with the group
set -euo pipefail
USAGE="usage: manage.sh update [branch] | backup | users"
source "$(dirname "$0")/lib/common.sh"

case ${1:-} in
  update) update_app "${2:-main}" ;;
  backup) backup_db ;;
  users)  sync_db_users ;;
  *)      echo "$USAGE" >&2; exit 2 ;;
esac
