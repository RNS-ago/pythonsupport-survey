"""Rebuild the processed tables and the dashboard: runs the notebooks in order and stops at the
first error. Outputs are not saved into the notebooks.

    uv run python pipeline.py                                    # on your machine, in notebooks/
    sudo /srv/pythonsupport-survey/deploy/manage.sh pipeline     # on the server

On the server, cron runs it as pis-pipeline (deploy/lib/pipeline.sh).
DASHBOARD_HTML is where the dashboard is saved; unset, it goes to visualization/dashboard.html.
The tables it writes belong to pis_analyst, because every analyst's login and pis-pipeline's
switch to that role when they log in (analyst_login in deploy/lib/postgres.sh).
"""
import tempfile
from pathlib import Path

import nbclient
import nbformat
from traitlets.config import Config

NOTEBOOKS = [
    "processing/aggregated_customer_data.ipynb",
    "processing/new_proccess_data.ipynb",
    "visualization/dashboard.ipynb",
]

# The kernels talk over Unix sockets in a folder only this user can open. Over TCP on localhost,
# other users of the server could read the outputs, the dashboard's rows among them.
with tempfile.TemporaryDirectory() as sockets:
    config = Config()
    config.KernelManager.transport = "ipc"
    config.KernelManager.ip = f"{sockets}/kernel"

    for name in NOTEBOOKS:
        path = Path(__file__).parent / name
        print("Running", name, flush=True)
        # In the notebook's folder, as in Jupyter, so relative paths work the same.
        nbclient.execute(nbformat.read(path, as_version=4), cwd=path.parent, config=config)
