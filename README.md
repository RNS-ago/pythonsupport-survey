# DTU Python Support Survey

Tools for DTU Python Support (PIS) supporters:

- **Customer satisfaction survey**: students rate the help they got, on a supporter's
  screen, on a tablet in kiosk mode, or through a one-time link or QR code.
- **Internal problem log**: supporters record which common problems they helped with.

The project has two parts that are deployed together on one server:

| Part | Folder | What it is |
| --- | --- | --- |
| Frontend | [`frontend/`](frontend/) | Static HTML, CSS and JavaScript modules. No build step. |
| Backend | [`backend/`](backend/) | Django app with an SQLite database. Stores responses and problem logs, checks the supporter password, issues links and QR codes, and hosts the admin site. |
| Deployment | [`deploy/`](deploy/) | Scripts and config for setting up and updating the server. |

More detail on each part: [`frontend/readme.md`](frontend/readme.md) and
[`backend/README.md`](backend/README.md).

## How the frontend and backend work together

```
browser ──▶ nginx ──┬─ /api/, /admin/  ──▶ gunicorn ──▶ Django ──▶ SQLite (DATABASE_PATH)
                    ├─ /static/        ──▶ backend/staticfiles/ (admin CSS/JS)
                    └─ everything else ──▶ frontend/
```

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

The database is `backend/pythonsupport/db.sqlite3` (git-ignored). To keep it somewhere
else, add `DATABASE_PATH=/path/to/db.sqlite3` to `.env`; the server does this to keep
its database outside the checkout.

Run the backend tests from `backend/pythonsupport/`:

```sh
uv run --env-file ../.env python manage.py test
```

## Deployment

The production setup is one Debian or Ubuntu server running:

- **nginx**: serves `frontend/` and the admin's static files, terminates HTTPS, and
  forwards `/api/` and `/admin/` to gunicorn.
- **gunicorn**: runs Django as the systemd service `pis-survey`, as the system user
  `pis`, listening on `127.0.0.1:8000` only.
- **SQLite**: `/var/lib/pis-survey/db.sqlite3`, outside the checkout, backed up daily.
- **certbot**: gets and renews the Let's Encrypt certificate.

The code lives in one checkout at `/srv/pythonsupport-survey`, and the scripts and config
files expect that path. The database is kept apart from it in `/var/lib/pis-survey/`, so
re-cloning or cleaning the checkout can never delete the data.

| File in `deploy/` | Purpose |
| --- | --- |
| `setup.sh` | First-time setup of a fresh server |
| `update.sh` | Deploy new code |
| `backup.sh` | Back up the database (daily from cron, and before every update) |
| `common.sh` | Paths and helpers shared by the scripts |
| `pis-survey.service` | systemd unit for gunicorn |
| `nginx.conf` | nginx site |

### Before you start

- A Debian or Ubuntu server where you have `sudo`.
- A domain name (for example `survey.example.dk`) whose DNS points at the server.
- Ports 80 and 443 open to the internet. Let's Encrypt needs port 80 to issue the
  certificate.
- The supporter password you want to use. Avoid spaces, quotes, `#`, `$` and `\`: it is
  stored in an environment file, where those characters get special meaning.

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
   sudo /srv/pythonsupport-survey/deploy/setup.sh survey.example.dk
   ```

   It will:

   1. Install git, nginx, sqlite3, certbot and uv.
   2. Create the `pis` system user, and make root the owner of the checkout.
   3. Create `/var/lib/pis-survey/` for the database, readable only by `pis`.
   4. Ask for the supporter password and write `backend/.env` with a random
      `SECRET_KEY`, `ALLOWED_HOSTS`, `FRONTEND_ORIGINS` and
      `DATABASE_PATH=/var/lib/pis-survey/db.sqlite3`. Root owns it; `pis` can only read it.
   5. Install the Python dependencies, create the database, and collect the admin's
      static files.
   6. Install the daily backup cron job.
   7. Start the `pis-survey` service and configure nginx.
   8. Run certbot to get the HTTPS certificate. It asks for an email address and for you
      to accept the terms.
   9. Ask you to create the first admin account for `/admin/`.

   If a step fails, fix the cause and run the script again. It keeps the existing
   `.env` and nginx site, so rerunning it is safe.

3. Open `https://survey.example.dk`, log in with the supporter password, and submit a
   test response and a test problem log. Check that both appear under
   `https://survey.example.dk/admin/`.

The site only works over HTTPS: in production the session cookie is HTTPS-only, so
logging in over plain HTTP fails. If certbot failed, fix DNS or the firewall and run
`sudo certbot --nginx -d survey.example.dk --redirect`.

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

The script pulls the code, backs up the database, installs dependencies, applies
migrations, collects static files and restarts gunicorn. If gunicorn does not come back
up, it prints the service log and exits with an error.

Frontend changes are live as soon as the code is pulled. Tablets in kiosk mode may keep
old files cached until they reload the page.

`update.sh` never touches the nginx site, because certbot has edited the installed copy.
If you change `deploy/nginx.conf`, apply the same change to
`/etc/nginx/sites-available/pis-survey` by hand, then run
`sudo nginx -t && sudo systemctl reload nginx`.

### Changing settings

Production settings are in `/srv/pythonsupport-survey/backend/.env`:

| Variable | Meaning |
| --- | --- |
| `SECRET_KEY` | Django's signing key. Changing it logs everyone out. |
| `ALLOWED_HOSTS` | Space-separated host names the site answers to |
| `FRONTEND_ORIGINS` | Space-separated origins allowed to call the API from a browser |
| `SURVEY_PASSWORD` | The supporter password (daily code) |
| `DATABASE_PATH` | The SQLite file: `/var/lib/pis-survey/db.sqlite3`. If you change it, also change `DB` in `deploy/backup.sh`, and move the file. Unset means `backend/pythonsupport/db.sqlite3`, which is only meant for local development. |
| `DEBUG` | Leave unset in production. `1` turns on debug mode. |

Edit it with `sudo`, then run `sudo systemctl restart pis-survey`.

### Permissions

Django runs as the `pis` user, and `pis` can change only the data, never the program:

| Path | Owner | `pis` can |
| --- | --- | --- |
| `/srv/pythonsupport-survey/` (code, `backend/.venv`, `backend/staticfiles`) | root | read |
| `/srv/pythonsupport-survey/backend/.env` | root, group `pis` | read |
| `/opt/uv-python/` (the Python that uv installs) | root | read |
| `/var/lib/pis-survey/` (the database) | `pis` | read and write |
| `/var/backups/pis-survey/` | `pis` | read and write |

If an attacker ever finds a bug that lets them run code inside Django, that code runs as
`pis`. It can reach the data, since the app needs that to work, but it cannot plant a
backdoor in the backend or change the JavaScript that nginx sends to supporters. Fixing the
bug and restarting the service removes them.

This is why the scripts run `git`, `uv sync` and `collectstatic` as root, and only the
commands that touch the database (`migrate`, `createsuperuser`, backups) as `pis`. Run
manual commands the same way: `sudo` for anything in the checkout, `sudo -u pis` for
anything that touches the database.

### Backups and restore

`deploy/backup.sh` runs daily at 03:00 and before every update. It writes
`/var/backups/pis-survey/db-<date>.sqlite3` and deletes copies older than 30 days
(`KEEP_DAYS` in the script). The backups contain student numbers: keep them only on
storage the team controls, and only as long as the retention policy allows.

To restore a backup:

```sh
sudo systemctl stop pis-survey
sudo -u pis cp /var/backups/pis-survey/db-<date>.sqlite3 /var/lib/pis-survey/db.sqlite3
sudo systemctl start pis-survey
```

### Useful commands

```sh
sudo systemctl status pis-survey         # is gunicorn running?
sudo journalctl -u pis-survey -f         # backend log
sudo tail -f /var/log/nginx/error.log    # nginx log
sudo certbot renew --dry-run             # check that certificate renewal works
```
