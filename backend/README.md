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
- `POST /api/qr-codes/`: an authorized supporter creates a reusable link for a
  QR code. The body is `{"building_number": 302, "valid_days": 7}`; the link
  records that building and stays valid for 1-365 days.
- `/admin/`: the Django admin, for staff accounts.

The code lives in `pythonsupport/surveryBackend/`; the project settings are in
`pythonsupport/pythonsupport/settings.py`.

## Development and deployment

Local development, how the backend works with the frontend, and the server deployment
(`deploy/`) are described in the [documentation](../docs/README.md).

Run the tests (from `pythonsupport/`):

```sh
uv run --env-file ../.env python manage.py test
```

After changing `models.py`:

```sh
uv run --env-file ../.env python manage.py makemigrations
uv run --env-file ../.env python manage.py migrate
```

Commit the generated migration together with the model change.

### Importing the old data

The old SharePoint export can be imported once per database. The CSV contains
student numbers, so it is git-ignored; never commit it.

```sh
uv run --env-file ../.env python manage.py import_legacy_csv ../Raw_customer_entries.csv --dry-run
uv run --env-file ../.env python manage.py import_legacy_csv ../Raw_customer_entries.csv
```

The dry run reports skipped rows and blanked course names without saving.
