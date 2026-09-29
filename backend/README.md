# PIS Backend

A small Django backend for the PIS satisfaction survey. It receives survey
responses from the frontend, stores them in a database we own, and gives staff
an admin site to browse them.

## Why this replaces the Microsoft workflow

The survey used to run on Microsoft 365: a Microsoft Form collected answers,
Power Automate flows moved them around, and the results ended up in SharePoint
lists, with Azure providing the hosting and identity around it. It worked, but:

- **The data lived in Microsoft's systems.** Student numbers sat in SharePoint,
  under tenant policies and retention rules we did not set, and getting them
  out meant a manual CSV export.
- **The logic was spread across flows.** Validation, the "Online" location for
  link submissions, and who could submit were split between form settings and
  Power Automate steps that are hard to review, test, or version.
- **Changes were slow.** Adding a question or a new kind of submission meant
  editing the form, the flows and the list, and hoping they stayed in sync.

This backend replaces all of that with one codebase:

| Before | Now |
| --- | --- |
| Microsoft Form | The frontend posts JSON to `/api/responses/` |
| Power Automate validation | `SatisfactionSurveyResponseForm` and model validators, covered by tests |
| SharePoint list | The `SatisfactionSurveyResponse` table in our own database |
| Browsing the SharePoint list | The Django admin at `/admin/` |
| Form sharing settings | A shared survey password and one-time links |
| CSV export from SharePoint | Direct database access; old data imported with `import_legacy_csv` |

**We control the data.** Responses stay in a database on a server we choose.
Nothing is sent to a third party, backups are a file copy, and deleting a
student's data is one query.

**It is built to grow.** New survey fields are a model field plus a migration.
New endpoints, reports or exports are ordinary Django views. Every rule is in
Python and checked by the test suite, so changes can be reviewed in a pull
request instead of clicked together in a flow editor.

## How it works

- `POST /api/csrf/` with `{"password": "..."}`: checks the shared survey
  password (`SURVEY_PASSWORD`), marks the session as authorized, and returns a
  CSRF token. The password must be re-entered once a day (`SESSION_COOKIE_AGE`).
- `POST /api/responses/`: saves a response. The caller needs either an
  authorized session plus the `X-CSRFToken` header, or a one-time link `token`
  in the body.
- `POST /api/problem-logs/`: saves the internal supporter problem log. It uses
  the same authorized session and CSRF token as the survey. The JSON body is
  `{"problems": ["Files and Folders", "Antivirus"], "other": "Optional note"}`.
- `POST /api/links/`: an authorized supporter creates a one-time link for a
  student (for example on Discord). It is valid for 24 hours and is deleted on
  use. Link submissions are recorded with the building `Online`.
- `/admin/`: the Django admin, for staff accounts.

The code lives in `pythonsupport/surveryBackend/`; the project settings are in
`pythonsupport/pythonsupport/settings.py`.

## Development

Requirements: [uv](https://docs.astral.sh/uv/). uv installs the right Python
(3.12) itself.

```sh
git clone <this repo> && cd PIS_backend
uv sync

# Local settings. .env is git-ignored.
cat > .env <<'EOF'
SURVEY_PASSWORD=devpassword
FRONTEND_ORIGINS=http://localhost:5500
EOF

cd pythonsupport
uv run --env-file ../.env python manage.py migrate
uv run --env-file ../.env python manage.py createsuperuser   # for /admin/
uv run --env-file ../.env python manage.py runserver
```

The API is now on `http://localhost:8000`. `FRONTEND_ORIGINS` is a
space-separated list of origins allowed to call the API from a browser; set it
to wherever you serve the frontend.

Run the tests (from `pythonsupport/`):

```sh
uv run python manage.py test
```

After changing `models.py`:

```sh
uv run python manage.py makemigrations
uv run python manage.py migrate
```

Commit the generated migration together with the model change.

### Importing the old data

The old SharePoint export can be imported once per database. The CSV contains
student numbers, so it is git-ignored; never commit it.

```sh
uv run python manage.py import_legacy_csv ../Raw_customer_entries.csv --dry-run
uv run python manage.py import_legacy_csv ../Raw_customer_entries.csv
```

The dry run reports skipped rows and blanked course names without saving.

## Deployment

The backend is one Python process plus a SQLite file. Any Linux server with uv
works.

### 1. Make the settings production-safe

`settings.py` is currently set up for development. Before the first
deployment, change it so that:

- `SECRET_KEY` comes from the environment, for example
  `os.environ['DJANGO_SECRET_KEY']`. Generate a value with
  `python -c "import secrets; print(secrets.token_urlsafe(50))"`.
- `DEBUG = False`.
- `ALLOWED_HOSTS` lists the backend's hostname, for example
  `['survey-api.example.dk']`.
- `STATIC_ROOT = BASE_DIR / 'static'`, so the admin's CSS can be collected.
- `SESSION_COOKIE_SECURE = True` and `CSRF_COOKIE_SECURE = True`, since the
  site runs over HTTPS.

If the frontend and backend are on different sites (not just different
subdomains of the same domain), browsers will not send the session cookie. In
that case also set `SESSION_COOKIE_SAMESITE = 'None'` and
`CSRF_COOKIE_SAMESITE = 'None'`.

### 2. Install and configure

```sh
git clone <this repo> /srv/pis-backend && cd /srv/pis-backend
uv sync --no-dev
uv add gunicorn          # once; commit the change so later deploys get it

cat > .env <<'EOF'
DJANGO_SECRET_KEY=<generated value>
SURVEY_PASSWORD=<the survey password>
FRONTEND_ORIGINS=https://survey.example.dk
EOF
chmod 600 .env

cd pythonsupport
uv run --env-file ../.env python manage.py migrate
uv run --env-file ../.env python manage.py collectstatic --no-input
uv run --env-file ../.env python manage.py createsuperuser
```

### 3. Run it

Run gunicorn under systemd, for example in
`/etc/systemd/system/pis-backend.service`:

```ini
[Unit]
Description=PIS survey backend
After=network.target

[Service]
WorkingDirectory=/srv/pis-backend/pythonsupport
EnvironmentFile=/srv/pis-backend/.env
ExecStart=/srv/pis-backend/.venv/bin/gunicorn pythonsupport.wsgi --bind 127.0.0.1:8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```sh
sudo systemctl enable --now pis-backend
```

Put a reverse proxy with HTTPS in front of it (nginx or Caddy). Forward all
requests to `127.0.0.1:8000`, and serve `/static/` from
`/srv/pis-backend/pythonsupport/static/`. With Caddy:

```
survey-api.example.dk {
    handle_path /static/* {
        root * /srv/pis-backend/pythonsupport/static
        file_server
    }
    reverse_proxy 127.0.0.1:8000
}
```

### 4. Update

```sh
cd /srv/pis-backend && git pull && uv sync --no-dev
cd pythonsupport
uv run --env-file ../.env python manage.py migrate
uv run --env-file ../.env python manage.py collectstatic --no-input
sudo systemctl restart pis-backend
```

### Backups

All data is in `pythonsupport/db.sqlite3`. Back it up with a safe online copy,
for example from a daily cron job:

```sh
sqlite3 /srv/pis-backend/pythonsupport/db.sqlite3 ".backup '/backups/pis-$(date +%F).sqlite3'"
```

The database contains student numbers. Keep backups on storage we control and
delete them according to our retention policy.
