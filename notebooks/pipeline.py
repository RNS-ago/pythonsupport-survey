"""Rebuild the processed tables and the dashboard: runs the notebooks in order and stops at the
first error. Outputs are not saved into the notebooks.

    uv run python pipeline.py                                    # on your machine, in notebooks/
    sudo -u pis DASHBOARD_HTML=/var/lib/pis/dashboard.html \\
      /srv/pythonsupport-survey/notebooks/.venv/bin/python \\
      /srv/pythonsupport-survey/notebooks/pipeline.py           # on the server

DASHBOARD_HTML is where the dashboard is saved; unset, it goes to visualization/dashboard.html.
"""
import os
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

# The tables belong to pis_analyst, as when an analyst runs the notebooks, so either can replace
# them. pis (on the server) and every analyst are members.
os.environ["PGOPTIONS"] = "-c role=pis_analyst"

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
