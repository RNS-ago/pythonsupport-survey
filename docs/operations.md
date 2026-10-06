# Operations

[Docs home](README.md) · [Architecture](structure.md) · [Development](development.md) · [Deployment](deployment.md) · [nginx](nginx.md) · [Operations](operations.md) · [Data analysis](data-analysis.md) · [Project README](../README.md)

Running the server after [deployment](deployment.md).

- [Changing settings](#changing-settings)
- [Permissions](#permissions)
- [Backups and restore](#backups-and-restore)
- [Useful commands](#useful-commands)

## Changing settings

Production settings are in `/srv/pythonsupport-survey/backend/.env`:

| Variable | Meaning |
| --- | --- |
| `SECRET_KEY` | Django's signing key. Changing it logs everyone out. |
| `ALLOWED_HOSTS` | Space-separated host names the site answers to |
| `FRONTEND_ORIGINS` | Space-separated origins allowed to call the API from a browser |
| `SURVEY_PASSWORD` | The supporter password (daily code) |
| `DATABASE_NAME` | The PostgreSQL database: `pis_survey`. If you change it, also change `DB` in `deploy/backup.sh` and the database name in `deploy/update.sh`. Unset means the SQLite file `backend/pythonsupport/db.sqlite3`, which is only meant for local development. |
| `DEBUG` | Leave unset in production. `1` turns on debug mode. |

Edit it with `sudo`, then run `sudo systemctl restart pis-survey`.

## Permissions

Django runs as the `pis` user, and `pis` can change only the data, never the program. The
people working on the project, the server's `pythonsupport` group, can change the program:

| Path | Owner | `pythonsupport` can | `pis` can |
| --- | --- | --- | --- |
| `/srv/pythonsupport-survey/` (code, `backend/.venv`, `backend/staticfiles`), except `backend/.env` | root, group `pythonsupport` | read and write | read |
| `/srv/pythonsupport-survey/backend/.env` | root, group `pis` | nothing | read |
| `/opt/uv-python/` (the Python that uv installs) | root | read | read |
| The `pis_survey` database | PostgreSQL user `pis` | through a [notebook login](data-analysis.md#database-logins) | read and write |
| `/var/backups/pis-survey/` | root | nothing | nothing |

`backend/.env` holds the secrets (`SECRET_KEY` and the supporter password), so `setup.sh`
takes it out of the group's access: it removes the ACL the rest of the checkout gets, and
sets the owner to root, group `pis`, mode `640`.

If an attacker ever finds a bug that lets them run code inside Django, that code runs as
`pis`. It can reach the data, since the app needs that to work, but it cannot plant a
backdoor in the backend or change the JavaScript that supporters' browsers load. Fixing the
bug and restarting the service removes them.

This is why the scripts run `git`, `uv sync` and `collectstatic` as root, and only the
commands that touch the database (`migrate`, `createsuperuser`, `pg_dump`) as `pis`. Run
manual commands the same way: `sudo` (or your own account, if you're in `pythonsupport`)
for anything in the checkout, `sudo -u pis` for anything that touches the database. Never
add `pis` to the `pythonsupport` group.

`setup.sh` sets up the checkout for the group:

- The group owns every file, and new directories inherit it (setgid).
- A default ACL gives every file created later, by anyone or by `git pull`, read and write
  for the group, whatever the creator's umask. `core.sharedRepository=group` does the same
  for git's own files.
- The checkout is marked as a git `safe.directory` for everyone, because git otherwise
  refuses to work in a repository owned by another user (root).

Members can run `git` in the checkout and edit files there, but deploying with
`update.sh` still needs `sudo`. Edits in the checkout are live: frontend files at once,
backend code after `sudo systemctl restart pis-survey`. Prefer committing and deploying
with `update.sh`; its `git pull --ff-only` stops if the checkout has local commits or
conflicting edits.

## Backups and restore

`deploy/backup.sh` runs daily at 03:00 and before every update. It writes
`/var/backups/pis-survey/db-<date>.dump` (a `pg_dump` of the whole database, including the
`analysis` schema) and deletes dumps older than 30 days (`KEEP_DAYS` in the script). The
backups contain student numbers: keep them only on storage the team controls, and only as
long as the retention policy allows.

The script runs as root: `pg_dump` runs as `pis`, which owns the database, and root writes
the dump to a directory only root can open. Code running as `pis` (for example after a bug
in Django is exploited) can corrupt the database, but not the existing backups. Dumps made
after such corruption contain it too, so the older dumps are the ones to restore. The
backups do not survive a compromise of root; for that, copy them off the server.

To restore a backup:

```sh
sudo systemctl stop pis-survey
sudo cat /var/backups/pis-survey/db-<date>.dump \
  | sudo -u pis pg_restore --clean --if-exists --single-transaction --dbname=pis_survey
sudo systemctl start pis-survey
```

`pis` can't open the backup directory, so root reads the dump and passes it on stdin.
`--single-transaction` means a failed restore changes nothing.

## Useful commands

```sh
sudo systemctl status pis-survey         # is gunicorn running?
sudo journalctl -u pis-survey -f         # backend log
sudo -u pis psql pis_survey              # SQL shell on the database
```
