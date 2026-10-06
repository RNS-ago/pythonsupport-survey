# Data analysis

[Docs home](README.md) · [Architecture](structure.md) · [Development](development.md) · [Deployment](deployment.md) · [nginx](nginx.md) · [Operations](operations.md) · [Data analysis](data-analysis.md) · [Project README](../README.md)

Jupyter notebooks run on your own machine and read the live database through an SSH tunnel.
PostgreSQL stays closed to the network: the tunnel forwards a local port to its socket on
the server, and PostgreSQL sees you as your own account on the server.

- [Database logins](#database-logins)
- [Connecting from a notebook](#connecting-from-a-notebook)

## Database logins

Every member of the `pythonsupport` group gets a database login named like their account.
PostgreSQL can't check Linux groups itself, so `deploy/notebook-access.sh` creates the logins
from the group's member list, and removes the logins of people who are no longer in it.
`setup.sh` runs it; run it again whenever someone joins or leaves the group:

```sh
sudo /srv/pythonsupport-survey/deploy/notebook-access.sh
```

It only sees members listed in the group itself (`getent group pythonsupport`); someone
whose primary group is `pythonsupport` isn't listed there.

Each login has the same rights as the app: it can read and change everything, including
student numbers. Every session switches to `pis`, so tables the notebooks create belong to
`pis` and are covered by [backups and restores](operations.md#backups-and-restore) like the
rest. Its `search_path` is `analysis, public`: tables created without a schema go to
`analysis`, and Django's tables in `public` can still be read without a prefix.

## Connecting from a notebook

Open the tunnel (leave it running while you work):

```sh
ssh -N -L 5432:/var/run/postgresql/.s.PGSQL.5432 <your account>@psqdb.compute.dtu.dk
```

Then, in a notebook (needs `pandas`, `sqlalchemy` and `psycopg[binary]`):

```python
import pandas as pd
from sqlalchemy import create_engine

db = create_engine("postgresql+psycopg://<your account>@localhost:5432/pis_survey")

# Processing: raw data in, a redacted table out, in the analysis schema.
raw = pd.read_sql('SELECT * FROM "surveryBackend_satisfactionsurveyresponse"', db)
processed = raw.drop(columns=["student_number", "username"])
processed.to_sql("responses", db, schema="analysis", if_exists="replace", index=False)

# Visualization: only the processed table.
df = pd.read_sql("SELECT * FROM analysis.responses", db)
```

Django's table names contain capital letters (`surveryBackend_...`), so quote them in SQL.
Django keeps its tables in `public`, the default schema, and its migrations may change
anything there; keep your own tables in `analysis`.
