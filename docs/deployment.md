# Deployment

[Docs home](README.md) · [Architecture](structure.md) · [Development](development.md) · [Deployment](deployment.md) · [nginx](nginx.md) · [Operations](operations.md) · [Data analysis](data-analysis.md) · [Project README](../README.md)

- [What runs on the server](#what-runs-on-the-server)
- [Before you start](#before-you-start)
- [First-time setup](#first-time-setup)
- [Trying the setup locally (test mode)](#trying-the-setup-locally-test-mode)
- [Importing the old data](#importing-the-old-data)
- [Updating](#updating)

## What runs on the server

HTTPS is handled by DTU's nginx, which is already set up on the server
(`/etc/nginx/conf.d/psqdb.conf`, not part of this repository; see [nginx](nginx.md)). Our
part only has to answer on `127.0.0.1:2810`.

The server runs two processes:

- **gunicorn**: runs Django as the systemd service `pis-survey`, as the system user
  `pis`, listening on `127.0.0.1:2810` only (for the forwarding details, see
  [Architecture](structure.md#request-flow)).
- **PostgreSQL**: the database `pis_survey`, owned by the database user `pis`, backed up
  daily. Django's tables are in the `public` schema; processed tables from the notebooks go
  in the `analysis` schema (see [Data analysis](data-analysis.md)).

The code lives in one checkout at `/srv/pythonsupport-survey`, and the scripts and config
files expect that path. The data lives in PostgreSQL, so re-cloning or cleaning the checkout
can never delete it.

Django and the notebooks connect over PostgreSQL's local socket, as the operating-system user
they run as (peer authentication), so there are no database passwords. PostgreSQL does not
listen on the network.

| File in `deploy/` | Purpose |
| --- | --- |
| `setup.sh` | First-time setup of a fresh server |
| `update.sh` | Deploy new code |
| `backup.sh` | Back up the database (daily from cron, and before every update) |
| `common.sh` | Paths and helpers shared by the scripts |
| `notebook-access.sh` | Database logins for the `pythonsupport` group (see [Data analysis](data-analysis.md#database-logins)) |
| `pis-survey.service` | systemd unit for gunicorn |

## Before you start

- A Debian or Ubuntu server where you have `sudo`, with the `pythonsupport` group for the
  people working on the project (see [Permissions](operations.md#permissions)).
- nginx on that server forwarding `https://psqdb.compute.dtu.dk` to port 2810, configured
  as in [nginx](nginx.md).
- The supporter password you want to use. Avoid spaces, quotes, `#`, `$` and `\`: it is
  stored in an environment file, where those characters get special meaning.

## First-time setup

1. Clone the repository to `/srv/pythonsupport-survey`:

   ```sh
   sudo git clone https://github.com/RNS-ago/pythonsupport-survey.git /srv/pythonsupport-survey
   ```

   If the repository is private, add a
   [deploy key](https://docs.github.com/en/authentication/connecting-to-github-with-ssh/managing-deploy-keys)
   for root (in `/root/.ssh/`) and clone with the `git@github.com:` URL instead.
   `update.sh` runs `git` as root.

2. Run the setup script with your domain:

   ```sh
   sudo /srv/pythonsupport-survey/deploy/setup.sh psqdb.compute.dtu.dk
   ```

   It will:

   1. Install git, PostgreSQL and uv.
   2. Create the `pis` system user, and make root and the `pythonsupport` group the owners
      of the checkout.
   3. Create the PostgreSQL user `pis`, the database `pis_survey` and its `analysis`
      schema, and a database login for every member of `pythonsupport` for the
      [notebooks](data-analysis.md).
   4. Ask for the supporter password and write `backend/.env` with a random
      `SECRET_KEY`, `ALLOWED_HOSTS`, `FRONTEND_ORIGINS` and
      `DATABASE_NAME=pis_survey`. Root owns it; `pis` can only read it.
   5. Install the Python dependencies, create Django's tables, and collect the admin's
      static files.
   6. Install the daily backup cron job.
   7. Start the `pis-survey` service on `127.0.0.1:2810`, and check that Django answers.
   8. Ask you to create the first admin account for `/admin/`.

   If a step fails, fix the cause and run the script again. It keeps the existing
   `.env`, so rerunning it is safe.

3. Open `https://psqdb.compute.dtu.dk`, log in with the supporter password, and submit a
   test response and a test problem log. Check that both appear under
   `https://psqdb.compute.dtu.dk/admin/`.

The site only works over HTTPS: in production the session cookie is HTTPS-only, so
logging in over plain HTTP fails. If the site answers `400 Bad Request` or `502 Bad
Gateway`, check [nginx](nginx.md) and `sudo systemctl status pis-survey`.

## Trying the setup locally (test mode)

To try `setup.sh` without a domain, for example in a Debian or Ubuntu container or VM,
clone the repository to `/srv/pythonsupport-survey` as above and run:

```sh
sudo /srv/pythonsupport-survey/deploy/setup.sh --test            # serves http://localhost:2810
sudo /srv/pythonsupport-survey/deploy/setup.sh --test my-vm.lan  # or another host name
```

Test mode differs from a real setup in two ways, both written to `backend/.env`:

- `PIS_BIND=0.0.0.0:2810`: there is no nginx in front, so gunicorn serves plain HTTP on
  port 2810 to other machines too, not only to localhost.
- `DEBUG=1`: without HTTPS, the production session cookie (HTTPS-only) would never be sent
  back, and logging in would fail.

The script prints a warning at the start and the end. **Never use test mode in
production**: debug mode shows detailed error pages, and without HTTPS the supporter
password travels unencrypted.

Test mode only writes these when it creates `backend/.env`. If a `.env` already exists
from an earlier run without `--test`, add them by hand, then run
`sudo systemctl restart pis-survey`.

In a container, run it with systemd as the init process (the script manages services with
`systemctl`), and publish port 2810, for example `-p 8080:2810`. The site is then at
<http://localhost:8080>.

## Importing the old data

To load the old SharePoint export once, copy the CSV to the server outside the
repository, somewhere the `pis` user can read it, and run:

```sh
cd /srv/pythonsupport-survey/backend/pythonsupport
sudo -u pis -H uv run --no-sync --env-file ../.env python manage.py import_legacy_csv /path/to/Raw_customer_entries.csv --dry-run
sudo -u pis -H uv run --no-sync --env-file ../.env python manage.py import_legacy_csv /path/to/Raw_customer_entries.csv
```

The file contains student numbers. Delete it from the server afterwards.

## Updating

Merge your changes to `main`, then on the server:

```sh
sudo /srv/pythonsupport-survey/deploy/update.sh
```

To deploy another branch, for example for testing: `sudo /srv/pythonsupport-survey/deploy/update.sh my-branch`.

The script pulls the code, installs dependencies and collects static files. It then stops
gunicorn, backs up the database, applies migrations and starts gunicorn again. The site is
down for the few seconds of the migrations; supporters' devices queue survey responses
meanwhile.

After starting gunicorn, the script checks that Django answers. If any step after the pull
fails, it rolls back: it restores the database from the backup it just made (if migrations
had started), checks out the previous commit and starts that version again. The checkout is
then on a detached commit; the next `update.sh` returns to the branch.

Frontend changes are live as soon as the code is pulled. Tablets in kiosk mode may keep
old files cached until they reload the page.
