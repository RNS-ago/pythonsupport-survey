"""Connect a notebook to our databases. Both functions read a .env file first.

get_pg_engine(): pis_survey. On the server, over the local socket with no password. Elsewhere,
over TLS with your DTU login: PGUSER, else the local account name, or pass it
(get_pg_engine("s123456")). The password comes from PGPASSWORD, else you are asked for it.

query_ait(sql): runs a query on AIT's student data through their SOAP service and returns a
DataFrame of strings, None for NULL. Needs AIT_USERNAME and AIT_PASSWORD and never prompts, so it
can run unattended.
"""
import os
import socket
import xml.etree.ElementTree as ET
from getpass import getpass
from pathlib import Path

import certifi
import pandas as pd
from dotenv import dotenv_values, load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

# Use only names that mean the same here as on the server: DASHBOARD_HTML is a server path.
SETTINGS = dotenv_values(Path(__file__).resolve().parents[3] / "deploy" / "settings.env")

PG_SERVER = "psqdb.compute.dtu.dk"
PG_DATABASE = SETTINGS["DATABASE_NAME"]
PG_SOCKET_DIR = "/var/run/postgresql"

AIT_URL = "https://idmservices.ait.dtu.dk/arcanicdbsoap/arcanicdbsoap.asmx/XMLSQLQuery"
AIT_DATABASE = "dtubasen"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"


def get_pg_engine(user=None):
    load_dotenv()
    if socket.gethostname().split(".")[0] == PG_SERVER.split(".")[0]:
        url = URL.create("postgresql+psycopg", username=user, host=PG_SOCKET_DIR, database=PG_DATABASE)
    else:
        url = URL.create(
            "postgresql+psycopg",
            username=user,  # None: libpq uses PGUSER, else the local account name
            password=os.environ.get("PGPASSWORD") or getpass("DTU password: "),
            host=PG_SERVER,
            port=5432,
            database=PG_DATABASE,
            query={
                "sslmode": "verify-full",
                "sslnegotiation": "direct",  # required: the nginx port only speaks direct TLS
                "sslrootcert": certifi.where(),
            },
        )
    return create_engine(url, pool_pre_ping=True)


def query_ait(sql):
    import requests  # in the student-data group, so get_pg_engine works without it

    load_dotenv()
    missing = [name for name in ("AIT_USERNAME", "AIT_PASSWORD") if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    response = requests.post(
        AIT_URL,
        data={
            # ELEMENTS XSINIL keeps NULL columns, which plain FOR XML leaves out.
            "sql": f"{sql} FOR XML RAW, ELEMENTS XSINIL",
            "Username": os.environ["AIT_USERNAME"],
            "Password": os.environ["AIT_PASSWORD"],
            "DBVersion": AIT_DATABASE,
        },
        timeout=300,
    )
    if not response.ok:
        raise RuntimeError(f"AIT answered {response.status_code}: {response.text[:500]}")
    return parse_ait_rows(response.content)


def _local(tag):
    return tag.rpartition("}")[2]


def _raise_ait_error(root):
    for element in root.iter():
        if _local(element.tag) == "Error":
            raise RuntimeError("AIT: " + "".join(element.itertext()).strip()[:500])


def parse_ait_rows(content):
    root = ET.fromstring(content)
    _raise_ait_error(root)
    if len(root) == 0 and root.text and root.text.strip():
        # The rows came as escaped XML text inside the answer's <string>.
        root = ET.fromstring(f"<rows>{root.text}</rows>")
        _raise_ait_error(root)
    rows = [
        {_local(column.tag): None if column.get(XSI_NIL) == "true" else column.text or "" for column in row}
        for row in root.iter()
        if _local(row.tag) == "row"
    ]
    return pd.DataFrame(rows, dtype=object)
