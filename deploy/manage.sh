#!/usr/bin/env bash
# Day-to-day jobs on the server, after setup.sh. See docs/operations.md.
#
#   sudo /srv/pythonsupport-survey/deploy/manage.sh update [branch]   # deploy a branch (default: main)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh backup            # dump the database (also daily from cron)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh users             # sync notebook logins with the group
#   sudo /srv/pythonsupport-survey/deploy/manage.sh pipeline          # rebuild the dashboard now (also from cron)
#   sudo /srv/pythonsupport-survey/deploy/manage.sh fetch             # fetch the student data from AIT
set -euo pipefail
USAGE="usage: manage.sh update [branch] | backup | users | pipeline | fetch"
source "$(dirname "$0")/lib/common.sh"

# One job at a time, and never during a pipeline run: a rollback's restore rewrites the
# pipeline's tables. pipeline and fetch take this lock themselves; update's re-exec keeps it.
if [[ ${1:-} != pipeline && ${1:-} != fetch && -z ${PIS_UPDATE_FROM:-} ]]; then
  exec 9>"$PIPELINE_LOCK"
  flock -n 9 || { echo "Waiting for the pipeline or another manage.sh job..." >&2; flock -w 1800 9; } || exit 75
fi

case ${1:-} in
  update) update_app "${2:-main}" ;;
  backup) backup_db ;;
  users)  sync_db_users ;;
  pipeline) run_pipeline ;;
  fetch)  run_pipeline fetch ;;
  *)      echo "$USAGE" >&2; exit 2 ;;
esac
