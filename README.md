# DTU Python Support Survey

Tools for DTU Python Support (PIS) supporters:

- **Customer satisfaction survey**: students rate the help they got, on a supporter's
  screen, on a tablet in kiosk mode, or through a one-time link or QR code.
- **Internal problem log**: supporters record which common problems they helped with.

The project has two parts that are deployed together on one server:

| Part | Folder | What it is |
| --- | --- | --- |
| Frontend | [`frontend/`](frontend/) | Static HTML, CSS and JavaScript modules. No build step. |
| Backend | [`backend/`](backend/) | Django app with a PostgreSQL database (SQLite in local development). Stores responses and problem logs, checks the supporter password, issues links and QR codes, and hosts the admin site. |
| Deployment | [`deploy/`](deploy/) | Scripts and config for setting up and updating the server. |

More detail on each part: [`frontend/readme.md`](frontend/readme.md) and
[`backend/README.md`](backend/README.md).

## Contents

- [How the frontend and backend work together](#how-the-frontend-and-backend-work-together)
  - [Supporters](#supporters)
  - [Students](#students)
  - [Endpoints](#endpoints)
- [Local development](#local-development)
- [Deployment](#deployment)
  - [Before you start](#before-you-start)
  - [nginx](#nginx)
  - [First-time setup](#first-time-setup)
  - [Trying the setup locally (test mode)](#trying-the-setup-locally-test-mode)
  - [Importing the old data](#importing-the-old-data)
  - [Updating](#updating)
  - [Changing settings](#changing-settings)
  - [Permissions](#permissions)
  - [Backups and restore](#backups-and-restore)
  - [Useful commands](#useful-commands)
  - [Notebooks](#notebooks)

## How the frontend and backend work together

```
browser ──▶ nginx (DTU, HTTPS) ──▶ gunicorn on 127.0.0.1:2810 ──▶ Django ──┬─ /api/, /admin/ ──▶ PostgreSQL (pis_survey)
                                                                        ├─ /static/        ──▶ backend/staticfiles/ (admin CSS/JS)
                                                                        └─ everything else ──▶ frontend/
```

DTU runs nginx on the server, with the certificate for `https://psqdb.compute.dtu.dk`. It
forwards every request to `http://127.0.0.1:2810`, where Django answers all of them,
including the frontend files (see `backend/pythonsupport/pythonsupport/urls.py`).

The frontend and the API are served from the same address, so the frontend calls the
API with relative URLs (`apiBase = ""` in `frontend/js/config.js`). No cross-origin
requests are needed.

### Supporters

1. The supporter opens the site and enters the daily code. The frontend sends it to
   `POST /api/csrf/`. If it matches `SURVEY_PASSWORD`, the backend marks the session as
   authorized and returns a CSRF token. The session cookie lasts 24 hours.
2. The frontend keeps the token in `localStorage` and sends it as the `X-CSRFToken`
   header on every later request.
3. The supporter chooses a form:
   - **Customer Satisfaction**: pick a building, then the student fills in the survey.
     It is sent to `POST /api/responses/`.
   - **Internal Logging**: tick common problems or describe another one. It is sent to
     `POST /api/problem-logs/`.
4. If the backend is unreachable, the supporter can continue without a code: survey
   responses are queued on the device and uploaded once the backend answers and the code
   has been entered. Problem logs are not queued.

### Students

Students never log in. A supporter creates a link for them:

| Supporter action | Endpoint | Link | Valid |
| --- | --- | --- | --- |
| "Discord link" button | `POST /api/links/` | `?token=…` | 24 hours, one use, building recorded as `Online` |
| "QR" button | `POST /api/qr-codes/` | `?t=…` | 1–365 days, reusable, fixed building |

The student's survey posts to `POST /api/responses/` with the link's token in the body
instead of a session. The backend decides the building from the token.

### Endpoints

| Endpoint | Who | Purpose |
| --- | --- | --- |
| `POST /api/csrf/` | anyone with the password | Log in; returns the CSRF token |
| `POST /api/responses/` | logged-in supporter, or a student with a link token | Save a survey response |
| `POST /api/problem-logs/` | logged-in supporter | Save a problem log |
| `POST /api/links/` | logged-in supporter | Create a one-time link |
| `POST /api/qr-codes/` | logged-in supporter | Create a reusable QR link |
| `/admin/` | Django staff accounts | Browse and export the data |

The Analytics page in the frontend embeds a Power BI report; it does not read from this
backend.

## Local development

Requirements: [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 itself).

```sh
cd backend
uv sync

# Local settings. .env is git-ignored.
cat > .env <<'EOF'
DEBUG=1
SECRET_KEY=dev
ALLOWED_HOSTS=localhost 127.0.0.1
SURVEY_PASSWORD=devpassword
FRONTEND_ORIGINS=http://localhost:8000
EOF

cd pythonsupport
uv run --env-file ../.env python manage.py migrate
uv run --env-file ../.env python manage.py createsuperuser   # for /admin/
uv run --env-file ../.env python manage.py runserver
```

Open <http://localhost:8000/>. In development Django serves the frontend itself (see
`backend/pythonsupport/pythonsupport/urls.py`), so changes to `frontend/` show up on
reload.

`DEBUG=1` matters locally: without it the session cookie is HTTPS-only, and logging in
over `http://localhost` fails.

Locally, the database is the SQLite file `backend/pythonsupport/db.sqlite3` (git-ignored),
so you don't need to install PostgreSQL. The server uses PostgreSQL, which Django switches
to when `DATABASE_NAME` is set (see [Changing settings](#changing-settings)). The code only
uses Django's ORM, so both behave the same.

Run the backend tests from `backend/pythonsupport/`:

```sh
uv run --env-file ../.env python manage.py test
```

## Deployment

HTTPS is handled by DTU's nginx, which is already set up on the server
(`/etc/nginx/conf.d/psqdb.conf`, not part of this repository). Our part only has to answer
on `127.0.0.1:2810`.

The server runs:

- **gunicorn**: runs Django as the systemd service `pis-survey`, as the system user
  `pis`, listening on `127.0.0.1:2810` only.
- **PostgreSQL**: the database `pis_survey`, owned by the database user `pis`, backed up
  daily. Django's tables are in the `public` schema; processed tables from the notebooks go
  in the `analysis` schema (see [Notebooks](#notebooks)).

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
| `pis-survey.service` | systemd unit for gunicorn |

### Before you start

- A Debian or Ubuntu server where you have `sudo`, with the `pythonsupport` group for the
  people working on the project (see [Permissions](#permissions)).
- nginx on that server forwarding `https://psqdb.compute.dtu.dk` to port 2810, configured
  as in [nginx](#nginx).
- The supporter password you want to use. Avoid spaces, quotes, `#`, `$` and `\`: it is
  stored in an environment file, where those characters get special meaning.

### nginx

nginx was set up by DTU before this project, in `/etc/nginx/conf.d/psqdb.conf`, together
with the certificate (`/etc/nginx/conf.d/ssl-compute.dtu.dk.conf`). It is not part of this
repository and the scripts never touch it. This is the version it should contain:

```nginx
server {
    listen 80;
    listen [::]:80;
    server_name psqdb.compute.dtu.dk;
    return 301 https://$host$request_uri;
}

server {
    listen       443 ssl;
    listen       [::]:443 ssl;
    http2        on;
    server_name  psqdb.compute.dtu.dk;
    root         /usr/share/nginx/html;

    include /etc/nginx/conf.d/ssl-compute.dtu.dk.conf;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:2810;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    error_page 404 /404.html;
    location = /40x.html {
    }

    error_page 500 502 503 504 /50x.html;
    location = /50x.html {
    }
}
```

What it does:

- **Port 80** redirects to HTTPS. The site never works over plain HTTP, because the session
  cookie is HTTPS-only, and the supporter password must not travel unencrypted.
- **Port 443** forwards every request to gunicorn on `127.0.0.1:2810`. Django serves the API,
  the admin, `/static/` and the frontend, so nginx serves none of this project's files.
- `proxy_set_header Host $host` passes on the real host name. Without it, nginx sends
  `Host: 127.0.0.1:2810`, and Django answers `400 Bad Request`, because only
  `psqdb.compute.dtu.dk` is in `ALLOWED_HOSTS`.
- `proxy_set_header X-Forwarded-Proto $scheme` tells Django the request arrived over HTTPS
  (`SECURE_PROXY_SSL_HEADER` in `settings.py`).
- `root /usr/share/nginx/html` and the `error_page` lines are for nginx's own error pages,
  such as `50x.html` when gunicorn is down.

Changes from the configuration DTU set up:

| Change | Why |
| --- | --- |
| The port 80 server redirects to HTTPS instead of forwarding to gunicorn. | Over plain HTTP, logging in fails (the session cookie is HTTPS-only) and the supporter password would travel unencrypted. |
| `proxy_pass http://127.0.0.1:2810` instead of `http://localhost:2810`. | `localhost` can resolve to `::1` first. gunicorn only listens on `127.0.0.1`, so nginx would log a failed connection to `[::1]:2810` before falling back. |
| Removed `proxy_ssl_server_name on`. | It only applies when nginx connects to the backend over HTTPS; the connection to gunicorn is plain HTTP. |
| Removed `client_max_body_size` from the port 80 server. | That server only redirects now, so it never receives a request body. |
| Removed a doubled blank line, and indented the two `location = /...html` blocks like the `location /` block. | Readability only; nginx ignores both. |

One thing is left as DTU had it: `error_page 404 /404.html` points to `/404.html`, but the
`location` below it is `/40x.html`. This changes nothing in practice: nginx only uses
`error_page` for errors it produces itself, and 404s come from Django.

To apply it, edit the file (or ask whoever manages nginx), then check and reload:

```sh
sudo nano /etc/nginx/conf.d/psqdb.conf
sudo nginx -t && sudo systemctl reload nginx
curl -sI http://psqdb.compute.dtu.dk/ | head -n 3     # expect 301 and Location: https://...
```

nginx does not need to serve any files of this project. If traffic ever grows enough for
Django's file serving to matter, add WhiteNoise to Django rather than changing nginx.

### First-time setup

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
      schema, and a database login for you (the account you ran `sudo` from) for the
      [notebooks](#notebooks).
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
Gateway`, check [nginx](#nginx) and
`sudo systemctl status pis-survey`.

### Trying the setup locally (test mode)

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

### Importing the old data

To load the old SharePoint export once, copy the CSV to the server outside the
repository, somewhere the `pis` user can read it, and run:

```sh
cd /srv/pythonsupport-survey/backend/pythonsupport
sudo -u pis -H uv run --no-sync --env-file ../.env python manage.py import_legacy_csv /path/to/Raw_customer_entries.csv --dry-run
sudo -u pis -H uv run --no-sync --env-file ../.env python manage.py import_legacy_csv /path/to/Raw_customer_entries.csv
```

The file contains student numbers. Delete it from the server afterwards.

### Updating

Merge your changes to `main`, then on the server:

```sh
sudo /srv/pythonsupport-survey/deploy/update.sh
```

To deploy another branch, for example for testing: `sudo /srv/pythonsupport-survey/deploy/update.sh my-branch`.

The script pulls the code, installs dependencies and collects static files. It then stops
gunicorn, backs up the database, applies migrations and starts gunicorn again. The site is down for the few seconds of the migrations; supporters' devices queue
survey responses meanwhile.

After starting gunicorn, the script checks that Django answers. If any step after the pull
fails, it rolls back: it restores the database from the backup it just made (if migrations
had started), checks out the previous commit and starts that version again. The checkout is
then on a detached commit; the next `update.sh` returns to the branch.

Frontend changes are live as soon as the code is pulled. Tablets in kiosk mode may keep
old files cached until they reload the page.

### Changing settings

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

### Permissions

Django runs as the `pis` user, and `pis` can change only the data, never the program. The
people working on the project, the server's `pythonsupport` group, can change the program:

| Path | Owner | `pythonsupport` can | `pis` can |
| --- | --- | --- | --- |
| `/srv/pythonsupport-survey/` (code, `backend/.venv`, `backend/staticfiles`) | root, group `pythonsupport` | read and write | read |
| `/srv/pythonsupport-survey/backend/.env` | root, group `pis` | nothing | read |
| `/opt/uv-python/` (the Python that uv installs) | root | read | read |
| The `pis_survey` database | PostgreSQL user `pis` | through a [notebook login](#notebooks) | read and write |
| `/var/backups/pis-survey/` | `pis` | nothing | read and write |

If an attacker ever finds a bug that lets them run code inside Django, that code runs as
`pis`. It can reach the data, since the app needs that to work, but it cannot plant a
backdoor in the backend or change the JavaScript that supporters' browsers load. Fixing the
bug and restarting the service removes them.

This is why the scripts run `git`, `uv sync` and `collectstatic` as root, and only the
commands that touch the database (`migrate`, `createsuperuser`, backups) as `pis`. Run
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

### Backups and restore

`deploy/backup.sh` runs daily at 03:00 and before every update. It writes
`/var/backups/pis-survey/db-<date>.dump` (a `pg_dump` of the whole database, including the
`analysis` schema) and deletes dumps older than 30 days (`KEEP_DAYS` in the script). The backups contain student numbers: keep them only on
storage the team controls, and only as long as the retention policy allows.

To restore a backup:

```sh
sudo systemctl stop pis-survey
sudo -u pis pg_restore --clean --if-exists --single-transaction --dbname=pis_survey \
  /var/backups/pis-survey/db-<date>.dump
sudo systemctl start pis-survey
```

`--single-transaction` means a failed restore changes nothing.

### Useful commands

```sh
sudo systemctl status pis-survey         # is gunicorn running?
sudo journalctl -u pis-survey -f         # backend log
sudo -u pis psql pis_survey              # SQL shell on the database
```

### Notebooks

Jupyter notebooks run on your own machine and read the live database through an SSH tunnel.
PostgreSQL stays closed to the network: the tunnel forwards a local port to its socket on
the server, and PostgreSQL sees you as your own account on the server.

`setup.sh` gives the account that ran it a database login. To give another server account
`alice` one:

```sh
sudo -u postgres psql -c 'CREATE ROLE "alice" LOGIN IN ROLE pis' -c 'ALTER ROLE "alice" SET role = pis'
```

The login has the same rights as the app: it can read and change everything, including
student numbers. Every session switches to `pis`, so tables the notebooks create belong to
`pis` and are covered by backups and restores like the rest.

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
Keep your own tables in `analysis`: `public` belongs to Django's migrations.
