# Its own user, not pis: Jupyter runs startup files from the account's home, which an exploited
# Django could plant there.

# Overlapping runs are skipped (exit 75) and hung ones stopped. The lock is where pis can't take it.
PIPELINE_RUN="flock -n -E 75 /var/lib/$PIPELINE_USER/pipeline.lock timeout 30m \
env DASHBOARD_HTML=$DASHBOARD_HTML $APP_DIR/notebooks/.venv/bin/python $APP_DIR/notebooks/pipeline.py"

# Needs apply_db_permissions to have run.
setup_pipeline() {
  create_system_user "$PIPELINE_USER"
  analyst_login "$PIPELINE_USER"
  install -d -m 750 -o "$PIPELINE_USER" -g "$APP_USER" "${DASHBOARD_HTML%/*}"
  echo "$PIPELINE_SCHEDULE $PIPELINE_USER $PIPELINE_RUN 2>&1 | systemd-cat -t $PIPELINE_USER" \
    > /etc/cron.d/$PIPELINE_USER
}

run_pipeline() {
  # Unquoted on purpose: PIPELINE_RUN is a command with its arguments.
  sudo -u "$PIPELINE_USER" -H $PIPELINE_RUN \
    || { local status=$?; [[ $status -ne 75 ]] || echo "Another pipeline run is still going." >&2; return $status; }
}
