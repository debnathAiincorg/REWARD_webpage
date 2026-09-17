# ADIRI — Daily Performance Bonus

An internal Flask webapp for tracking and reporting daily employee performance
bonuses. It reads and writes a single Excel table on SharePoint (`Table1` in
the "Daily Performance Bonus" sheet) via the Microsoft Graph API — there's no
local database.

---

## Features

**Dashboard** (`/dashboard`)
- KPI row: total employees, total weekly points, total weekly amount, and
  employees with zero points this week.
- **Previous Day Performance** — category-level scores for yesterday.
- **Weekly Performance Report** — week-to-date totals per employee (points,
  amount, previous-day figures) with a TOTAL row.

**Add Entry** (`/add`)
- Form for recording or editing a performance entry. Submitting for an
  employee/date that already has a row updates it in place instead of
  creating a duplicate.
- Searchable employee dropdown backed by its own roster (`employees.json`),
  kept separate from the sheet — add or retire a name without touching that
  person's past entries. Editing a row from History links back here with the
  form pre-filled.

**History** (`/history`)
- Every row in `Table1`, filterable by employee and/or date range, with
  inline edit and delete.

Columns are never hardcoded: whatever headers exist in the sheet's first row
are auto-detected (`webapp/logic.py: detect_columns`) into Date, Name, an
optional Index, free-text columns (e.g. `Notes`), and everything else treated
as a numeric category column. `KNOWN_WIDGETS` in `webapp/app.py` gives a
handful of known categories a nicer input widget (a 0/1 toggle for
Punctuality, L&D, Fluency Compliance, Innovation; a decimal field for Extra
Hours) — an unlisted category still works, just as a plain number input.

Built with Flask + Jinja, styled with Tailwind CSS (via CDN, no build step)
and Lucide icons.

---

## Project layout

The application lives entirely under `webapp/`:

```
webapp/
  app.py            Flask routes
  config.py         Which SharePoint file to use (see below)
  graph_client.py   Thin Microsoft Graph API wrapper
  logic.py          Pure business logic (column detection, totals, roster)
  templates/        Jinja templates
  static/style.css  The handful of styles Tailwind utilities can't express
  tests/            pytest suite (logic.py only — no Graph calls in tests)
  scripts/          One-off helper for resolving a SharePoint share link
                     into the Drive ID / Item ID that config.py needs
  requirements.txt
  Procfile          Railway/gunicorn entry point
  .env.example      Every environment variable this app reads
```

---

## Which Excel file it talks to

`webapp/config.py` holds two sets of Drive ID / Item ID, and `ACTIVE_FILE`
picks between them:

- `"DUMMY"` — a test workbook, safe to experiment against.
- `"MAIN"` — the real production file
  (`Strict Employee Performance Analysis.xlsx`).

**`ACTIVE_FILE` currently defaults to `"MAIN"`** — the app reads and writes
live production data out of the box. Adding, editing, or deleting an entry
through the running app changes the real sheet. Switch it to `"DUMMY"` in
`config.py` for local testing. If `ACTIVE_FILE` is `"MAIN"` but its Drive
ID/Item ID aren't set, the app refuses to start rather than silently falling
back to the dummy file.

---

## Local setup

**Prerequisites:** Python 3.x, and an Azure App Registration with
`Files.ReadWrite.All` (or equivalent) Graph API permissions for the target
SharePoint file.

```bash
cd webapp
pip install -r requirements.txt
```

Copy `webapp/.env.example` to `webapp/.env` and fill in:

| Variable | Required | Notes |
|---|---|---|
| `AZURE_CLIENT_ID` | Yes | Azure app registration |
| `AZURE_TENANT_ID` | Yes | Azure app registration |
| `AZURE_CLIENT_SECRET` | Yes | Azure app registration |
| `FLASK_SECRET_KEY` | Recommended | Signs the session cookie. Falls back to a hardcoded dev value if unset — fine locally, not for anything reachable over a network |
| `FLASK_DEBUG` | No | `1`/`true`/`yes`/`on` to enable Flask's debugger locally. Never set in production |
| `EMPLOYEES_DATA_DIR` | No | See [Roster storage](#roster-storage) below |

Run it:

```bash
python app.py
```

Starts on `http://localhost:5000` and prints which `ACTIVE_FILE` it's using.

Run the tests:

```bash
pytest webapp/tests -q
```

---

## Roster storage

The Add Entry dropdown's employee list is stored in `webapp/employees.json`,
seeded from the sheet's names on first run. `EMPLOYEES_DATA_DIR` points this
file at a different directory instead of next to `logic.py` — needed on any
host with an ephemeral filesystem (see Deployment below), where every
redeploy would otherwise wipe it and silently revert any employee added or
removed through the UI.

---

## Deployment (Railway)

The app ships with a `Procfile` and runs under gunicorn, not Flask's dev
server:

```
web: gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
```

To deploy:

1. Set the service's **Root Directory to `webapp`**, so Railway finds the
   Procfile and `requirements.txt`.
2. Add a **persistent volume** (e.g. mounted at `/data`) and set
   `EMPLOYEES_DATA_DIR=/data` — otherwise the roster resets on every deploy.
3. Set the required environment variables in the Railway dashboard:
   `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`,
   `FLASK_SECRET_KEY`, `EMPLOYEES_DATA_DIR`. Leave `FLASK_DEBUG` and `PORT`
   unset — Railway injects `PORT` itself.
4. `GET /healthz` returns `200 "ok"` for Railway's deploy health check. It
   deliberately doesn't call Graph, so a Microsoft outage shows up as an
   error banner in the UI rather than failing the health check and rolling
   back the deployment.
