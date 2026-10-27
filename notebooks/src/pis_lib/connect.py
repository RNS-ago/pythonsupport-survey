"""Connect a notebook to our databases.

get_pg_engine(): our PostgreSQL database, pis_survey. On the server (a pipeline running
there) it uses PostgreSQL's local socket, as the account running the notebook, with no
password. Anywhere else it connects to psqdb.compute.dtu.dk over TLS and logs in with your
DTU account and password. The login defaults to PGUSER, else the account running the
notebook; pass get_pg_engine("s123456") if your local account is named differently. The
password comes from PGPASSWORD, else you are asked for it.

get_ait_engine(): AIT's SQL Server with the student data, AIT_DATABASE on AIT_SERVER (needs
SQLAlchemy 2.1 and mssql-python). The login comes only from AIT_USERNAME and AIT_PASSWORD,
both required, with no prompts, so it can run unattended.

Both read a .env file first, from the notebook's folder or above.
"""
import os
import socket
from getpass import getpass

import certifi
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

import mssql_python

PG_SERVER = "psqdb.compute.dtu.dk"
SOCKET_DIR = "/var/run/postgresql"

AIT_SERVER = "AIT-PIMSQLAG1L.win.dtu.dk"
AIT_DATABASE = "DTU_Matrikel"


def get_pg_engine(user=None):
    load_dotenv()
    if socket.gethostname().split(".")[0] == PG_SERVER.split(".")[0]:
        url = URL.create("postgresql+psycopg", username=user, host=SOCKET_DIR, database="pis_survey")
    else:
        url = URL.create(
            "postgresql+psycopg",
            username=user,  # None: libpq uses PGUSER, else the local account name
            password=os.environ.get("PGPASSWORD") or getpass("DTU password: "),
            host=PG_SERVER,
            port=5432,
            database="pis_survey",
            query={
                "sslmode": "verify-full",
                "sslnegotiation": "direct",  # required: the nginx port only speaks direct TLS
                "sslrootcert": certifi.where(),     # verify the server certificate
            },
        )
    return create_engine(url, pool_pre_ping=True)


def _quote(value: str) -> str:
    # Braces keep ';' or '=' in a password from breaking the connection string.
    return "{" + value.replace("}", "}}") + "}"


def get_ait_engine():
    load_dotenv()
    missing = [name for name in ("AIT_USERNAME", "AIT_PASSWORD") if not os.getenv(name)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    conn_str = (
        f"Server={AIT_SERVER};"
        f"Database={AIT_DATABASE};"
        f"UID={_quote(os.environ['AIT_USERNAME'])};"
        f"PWD={_quote(os.environ['AIT_PASSWORD'])};"
        "Encrypt=yes;"
        "TrustServerCertificate=yes;"
    )

    return create_engine("mssql+mssqlpython://", creator=lambda: mssql_python.connect(conn_str))
