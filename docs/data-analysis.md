# Data analysis

[Docs home](README.md) · [Architecture](structure.md) · [Development](development.md) · [Deployment](deployment.md) · [nginx](nginx.md) · [Operations](operations.md) · [Data analysis](data-analysis.md) · [Project README](../README.md)

Jupyter notebooks run on your own machine and read the live database through an SSH tunnel.
PostgreSQL stays closed to the network: the tunnel forwards a local port to its socket on
the server, and PostgreSQL sees you as your own account on the server.

- [Database logins](#database-logins)
- [Connecting from a notebook](#connecting-from-a-notebook)
- [Old data](#old-data)

## Database logins

Rights in the database are defined in [`deploy/db-permissions.sql`](../deploy/db-permissions.sql).
To change them, edit that file, commit, and deploy with `manage.sh update`, which applies it.

| Schema | What goes there | `pis_analyst` | `pis_viewer` |
| --- | --- | --- | --- |
| `public` | Django's tables | read the `survey_*` tables only | nothing |
| `processed_data` | Results of the processing notebooks | read and write | nothing |
| `static_data` | Data from outside Django, such as the old survey | read and write | nothing |
| `published_data` | What viewers may see | read and write | read |

Every member of the `pythonsupport` group gets a database login named like their account, with
the `pis_analyst` role. PostgreSQL can't check Linux groups itself, so `deploy/manage.sh users`
creates the logins from the group's member list, and removes the logins of people who are no
longer in it (their tables stay, owned by `pis_analyst`). `setup.sh` runs it; run it again
whenever someone joins or leaves the group:

```sh
sudo /srv/pythonsupport-survey/deploy/manage.sh users
```

It only sees members listed in the group itself (`getent group pythonsupport`); someone
whose primary group is `pythonsupport` isn't listed there.

Every analyst session switches to `pis_analyst`, so tables the notebooks create belong to
`pis_analyst`, every analyst can change them, and they are covered by
[backups and restores](operations.md#backups-and-restore). Its `search_path` is
`processed_data, public`: tables created without a schema go to `processed_data`.

Viewers are added by hand, and `manage.sh users` leaves them alone:

```sh
sudo -u postgres psql -d pis_survey -c 'CREATE ROLE "<account>" LOGIN IN ROLE pis_viewer'
sudo -u postgres psql -d pis_survey -c 'DROP ROLE "<account>"'   # to remove them again
```


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

# Processing: raw data in, a redacted table out, in processed_data.
raw = pd.read_sql("SELECT * FROM survey_satisfactionsurveyresponse", db)
processed = raw.drop(columns=["student_number", "username"])
processed.to_sql("responses", db, schema="processed_data", if_exists="replace", index=False)

# Visualization: only the processed table.
df = pd.read_sql('SELECT * FROM processed_data.responses', db)
```

Django keeps its tables in `public`, the default schema, and its migrations may change
anything there; analysts can only read its `survey_*` tables.

## Old data

Responses from the old SharePoint survey are not in Django. Load the aggregated CSV into
its own table in `static_data` once, from a notebook connected as above:

```python
old = pd.read_csv("Aggregated_CustomerData.csv", na_values="N/A", parse_dates=["created_at"])
old["created_at"] = old["created_at"].dt.tz_localize("Europe/Copenhagen")  # CSV times are local
old.to_sql("old_responses", db, schema="static_data", if_exists="fail", index=False)
```

`if_exists="fail"` stops a second load from replacing or duplicating the table. Merge it
with Django's table in your processing step. The CSV contains student numbers; never commit
it, and delete your copy once it is loaded.
