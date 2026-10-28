# The notebook pipeline (notebooks/pipeline.py): rebuilds the processed tables and the dashboard
# on PIPELINE_SCHEDULE. See "Dashboard pipeline" in docs/operations.md.
#
# It runs as its own user, not pis. pis only reads the dashboard it shows to admins. And Jupyter
# runs startup files from the running account's home, so code running as pis (after a bug in
# Django is exploited) could otherwise plant some there that survives a restart.

# One run at a time: a run that would overlap the previous one is skipped (exit code 75), and a
# run that hangs, for example waiting for a table an analyst has open, is stopped after 30
# minutes. The lock is in the pipeline's home, where pis can't take it.
PIPELINE_RUN="flock -n -E 75 /var/lib/$PIPELINE_USER/pipeline.lock timeout 30m \
env DASHBOARD_HTML=$DASHBOARD_HTML $APP_DIR/notebooks/.venv/bin/python $APP_DIR/notebooks/pipeline.py"

# The user, its database login, the dashboard's folder and the cron job.
# Needs apply_db_permissions to have run.
setup_pipeline() {
  create_system_user "$PIPELINE_USER"
  # Logs in over the local socket as itself, like pis, with the analysts' rights.
  analyst_login "$PIPELINE_USER"
  install -d -m 750 -o "$PIPELINE_USER" -g "$APP_USER" "${DASHBOARD_HTML%/*}"   # its folder
  # Output goes to the journal: journalctl -t pis-pipeline
  echo "$PIPELINE_SCHEDULE $PIPELINE_USER $PIPELINE_RUN 2>&1 | systemd-cat -t $PIPELINE_USER" \
    > /etc/cron.d/$PIPELINE_USER
}

# Run it now, as cron would, with the output in the terminal.
run_pipeline() {
  # Unquoted on purpose: PIPELINE_RUN is a command with its arguments.
  sudo -u "$PIPELINE_USER" -H $PIPELINE_RUN \
    || { local status=$?; [[ $status -ne 75 ]] || echo "Another pipeline run is still going." >&2; return $status; }
}
