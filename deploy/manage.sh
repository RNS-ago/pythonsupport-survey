#!/usr/bin/env bash
# Day-to-day jobs on the server, after setup.sh. See docs/deployment.md and docs/operations.md.
#
#   sudo /srv/pythonsupport-survey/deploy/manage.sh update [branch]   # deploy a branch (default: main)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh backup            # dump the database (also daily from cron)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh users             # sync notebook logins with the group
#   sudo /srv/pythonsupport-survey/deploy/manage.sh pipeline          # rebuild the dashboard now (also from cron)
set -euo pipefail
USAGE="usage: manage.sh update [branch] | backup | users | pipeline"
source "$(dirname "$0")/lib/common.sh"

case ${1:-} in
  update) update_app "${2:-main}" ;;
  backup) backup_db ;;
  users)  sync_db_users ;;
  pipeline) run_pipeline ;;
  *)      echo "$USAGE" >&2; exit 2 ;;
esac
