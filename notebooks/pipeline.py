"""Run a group of notebooks in order: the dashboard (default) or fetch. Stops at the first error;
outputs aren't saved.

    uv run --group pipeline python pipeline.py [dashboard|fetch]   # on your machine, in notebooks/
    sudo /srv/pythonsupport-survey/deploy/manage.sh pipeline       # on the server: dashboard
    sudo /srv/pythonsupport-survey/deploy/manage.sh fetch          # on the server: fetch
"""
import sys
import tempfile
from pathlib import Path

import nbclient
import nbformat
from sqlalchemy import inspect
from traitlets.config import Config

from pis_lib.connect import get_pg_engine

GROUPS = {
    "dashboard": [
        "processing/aggregated_customer_data.ipynb",
        "processing/new_proccess_data.ipynb",
        "visualization/dashboard.ipynb",
    ],
    "fetch": [
        "fetching_data/get_student_data.ipynb",
    ],
}
STATIC_TABLES = ["old_responses", "students", "courses", "fetched"]  # what the dashboard group reads from static_data

group = sys.argv[1] if len(sys.argv) > 1 else "dashboard"
if group not in GROUPS:
    sys.exit(f"Unknown group {group!r}. Groups: {', '.join(GROUPS)}")

if group == "dashboard":
    with get_pg_engine().connect() as db:
        missing = [table for table in STATIC_TABLES if not inspect(db).has_table(table, schema="static_data")]
    if missing:
        sys.exit("Load the static data first (see docs/data-analysis.md). Missing: "
                 + ", ".join(f"static_data.{table}" for table in missing))

# Unix sockets in a private folder: over TCP, other users of the server could read the outputs.
with tempfile.TemporaryDirectory() as sockets:
    config = Config()
    config.KernelManager.transport = "ipc"
    config.KernelManager.ip = f"{sockets}/kernel"

    for name in GROUPS[group]:
        path = Path(__file__).parent / name
        print("Running", name, flush=True)
        # In the notebook's folder, as in Jupyter, so a .env there is found.
        nbclient.execute(nbformat.read(path, as_version=4), cwd=path.parent, config=config)
