# ADIRI — Performance Tracking

An internal Flask webapp for tracking employee performance. It reads and writes
four sheets of one SharePoint workbook (`Strict Employee Performance
Analysis.xlsx`) via the Microsoft Graph API — there's no local database.

---

## Sections

The home page (`/`) shows one card per sheet. Inside a section, the header
shows the section's name (click it to switch section) and that section's own
**Dashboard**, **Add Entry** and **History** tabs. URLs are section-prefixed:
`/daily/...`, `/whatsapp/...`, `/monthly/...`, `/keyboard/...`. The old
`/dashboard`, `/add` and `/history` URLs redirect to `/daily/...`.

Every section works the same way: Add Entry updates an existing entry instead
of duplicating it, History lists every row with filters plus Edit (opens Add
Entry pre-filled) and Delete (with a confirmation), and a Graph failure shows
an error banner or toast instead of crashing the page.

### Daily Performance Bonus (`/daily/...`)

`Table1` in the "Daily Performance Bonus" sheet, via the Graph **table** API.

- **Dashboard** — KPI row (total employees, weekly points and amount,
  employees with zero points this week, previous week's points), **Previous
  Day Performance**, and the **Weekly Performance Report** with a TOTAL row.
- **Add Entry** — de-duplicates on Name + Date. Searchable employee dropdown
  backed by its own roster (`employees.json`), kept separate from the sheet —
  add or retire a name without touching that person's past entries.
- **History** — filter by employee and/or date range.

Columns are never hardcoded: headers are auto-detected
(`webapp/logic.py: detect_columns`) into Date, Name, an optional Index,
free-text columns (e.g. `Notes`), and numeric category columns.
`KNOWN_WIDGETS` in `webapp/sections/daily.py` gives a few known categories a
nicer input widget (a 0/1 toggle, a decimal field) — an unlisted category
still works as a plain number input.

### Employee Whatsapp (`/whatsapp/...`)

A flat list: `First_Name | Last_Name | Mobile_1`, one contact per row.

- **Dashboard** — total contacts, contacts with a missing/invalid number,
  roster employees with no contact, and a searchable list with a WhatsApp
  button (`https://wa.me/91<number>`) per contact.
- **Add Entry** — de-duplicates on First + Last name. The number must be a
  10-digit Indian mobile (`+91` / a leading `0` are stripped) and is written as
  a plain number, exactly like the existing ones. New contacts go under the
  last one. Editing can fix a name's spelling in place.
- **Delete** — removes the contact's row.

### Monthly Performance Bonus (`/monthly/...`)

Not a table but a stack of **month blocks**. Each starts with a yellow banner
(a real date such as 26 Oct 2026, displayed `26-Oct`, merged across A:F),
usually followed by a header row (`Index | Name | Performance Bonus | Status |
Status Date | Notes | For The Month of`), then one row per employee — often
pre-filled with just the name. Blocks sit back to back with no gap. Column H
has no header; it's shown read-only and never written.

- **Dashboard** — pick a block: total bonus, approved count and amount,
  missed, pending/empty, and the per-employee table. Text amounts such as
  `(2500)+500` are listed but not added to the totals.
- **Add Entry** — de-duplicates on Name + block. Fills the employee's
  pre-filled row if the block has one, otherwise adds a row at the end of the
  block (before the next banner). "New block" creates next month's block the
  way the existing ones look: banner on the same day of the month with the same
  number format, merge, fill and alignment, then the header row and every name
  from the latest block. Status is Approved / Missed / Pending (or blank). A
  blank Notes field keeps the row's existing note.
- **Delete** — clears Bonus, Status, Status Date and For The Month of but keeps
  the Name and Notes, so the block's pre-filled roster stays intact.

### Keyboard Performance Status - M (`/keyboard/...`)

`Index | Year | Month | Employee Name | Accuracy Score | Speed | Comments`: a
header, one blank row, then one group per month, separated by exactly one
blank row. Accuracy is a number with a `0%` / `0.00%` format; Speed is text
like `18 WPM`, except on an absent employee's row (0 and 0, both formatted
`0%`).

- **Dashboard** — pick a month: average accuracy and speed (both leave out 0%
  rows), top performer, employees at 0%, and a month-by-month table.
- **Add Entry** — de-duplicates on Employee + Year + Month. A new row goes at
  the end of its month's group; a new month starts a new group after one blank
  row, spelled in upper case like the latest groups. Index is max + 1 and
  existing rows are never renumbered. A month earlier than the latest one can't
  be started from the app.
- **Delete** — removes the row; removing a month's last row also removes one
  separator, so the gaps stay single.

### How the non-table sheets are written

Whatsapp, Monthly and Keyboard go through the Graph **worksheet range** API
(`get_sheet_grid` / `apply_ops` in `webapp/graph_client.py`). Before every
write the sheet is re-read and the target row is found by its key — never by a
row number cached from an earlier page load. The per-sheet modules
(`whatsapp_logic.py`, `monthly_logic.py`, `keyboard_logic.py`) are pure: they
turn the sheet into records and *plan* each write as a list of operations
(insert rows, write values and number formats, merge, fill). `sheet_grid.py`
applies the same operations to an in-memory grid, which is how the tests check
the exact layout each write leaves behind.

Built with Flask + Jinja (one blueprint per section), styled with Tailwind CSS
(via CDN, no build step) and Lucide icons.

---

## Project layout

The application lives entirely under `webapp/`:

```
webapp/
  app.py              App setup, home page, roster routes, legacy redirects
  sections/           One Flask blueprint per section (daily, whatsapp,
                      monthly, keyboard), plus the section list for the nav
  config.py           The SharePoint file's IDs and the sheet names
  graph_client.py     Thin Microsoft Graph wrapper (table API + range API)
  logic.py            Daily: column detection, totals, roster
  sheet_grid.py       Grid and write-operation helpers for the range sheets
  whatsapp_logic.py   Per-sheet parsing and write planning (pure, no Graph)
  monthly_logic.py
  keyboard_logic.py
  templates/          Jinja templates (a folder per newer section)
  static/style.css    The handful of styles Tailwind utilities can't express
  tests/              pytest suite — no live Graph calls
  requirements.txt
  Procfile            Railway/gunicorn entry point
  .env.example        Every environment variable this app reads
```

---

## Which Excel file it talks to

Only the live production workbook, `Strict Employee Performance
Analysis.xlsx` (SharePoint site `StrictEmployeePerformance`). Its Drive ID and
Item ID live in `webapp/config.py` and nowhere else; if either is missing, the
app refuses to start.

**Every Add, Edit and Delete in the running app changes the real sheets** —
locally as well as on Railway.

---

## Local setup

**Prerequisites:** Python 3.10+, and an Azure App Registration with
`Files.ReadWrite.All` (or equivalent) Microsoft Graph application permission
for the workbook.

```bash
cd webapp
pip install -r requirements.txt
```

Copy `webapp/.env.example` to `webapp/.env` (git-ignored) and fill it in —
see [Environment variables](#environment-variables). `graph_client.py` loads
that file for local runs; on Railway the variables come from the service
settings instead.

Run it:

```bash
python app.py
```

Starts on `http://localhost:5000`.

Run the tests:

```bash
pytest webapp/tests -q
```

Local copies of the workbook (`*.xlsx`) are git-ignored: they contain real
employee data and this repository is public. Never commit one, and keep test
fixtures to made-up names and numbers.

---

## Environment variables

| Variable | Required | Notes |
|---|---|---|
| `AZURE_CLIENT_ID` | Yes | Azure app registration |
| `AZURE_TENANT_ID` | Yes | Azure app registration |
| `AZURE_CLIENT_SECRET` | Yes | Azure app registration |
| `FLASK_SECRET_KEY` | Yes in production | Signs the session cookie (flash messages). Falls back to a value that is public in this repo — fine locally, never in production |
| `EMPLOYEES_DATA_DIR` | Yes on Railway | Directory holding `employees.json`; point it at a persistent volume. See [Roster storage](#roster-storage) |
| `FLASK_DEBUG` | No | `1`/`true`/`yes`/`on` enables Flask's debugger locally. Never set in production |
| `PORT` | — | Injected by Railway; don't set it yourself |

The four sections all use these same variables — the sheet names and file IDs
are in `config.py`, not in the environment.

---

## Roster storage

The Add Entry dropdown's employee list is stored in `employees.json`, seeded
from the Daily sheet's names on first run. `EMPLOYEES_DATA_DIR` points this
file at a different directory instead of next to `logic.py` — needed on any
host with an ephemeral filesystem, where every redeploy would otherwise wipe it
and silently revert any employee added or removed through the UI.

The same roster also feeds the employee pickers on the Keyboard and Monthly
Add Entry pages (merged with any names already in those sheets).

---

## Deployment (Railway)

The app runs under gunicorn, not Flask's dev server (`webapp/Procfile`):

```
web: gunicorn app:app --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120
```

One-time setup in the Railway service:

1. **Settings → Source:** connect this GitHub repo and branch `main`, and set
   **Root Directory** to `webapp`, so Railway finds the Procfile and
   `requirements.txt`.
2. **Volume:** attach a persistent volume mounted at `/data`.
3. **Variables:** set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`,
   `AZURE_CLIENT_SECRET`, `FLASK_SECRET_KEY` (a long random string, e.g.
   `python -c "import secrets; print(secrets.token_hex(32))"`) and
   `EMPLOYEES_DATA_DIR=/data`. Leave `FLASK_DEBUG` and `PORT` unset.
4. **Settings → Deploy → Healthcheck Path:** `/healthz`. It returns
   `200 "ok"` and deliberately doesn't call Graph, so a Microsoft outage shows
   up as an error banner in the UI rather than failing the health check and
   rolling back the deployment.

Every push to `main` then triggers a deploy. After one, open the public URL
and check that the home page shows the four sections and that each section's
Dashboard and History load without a red "Could not load data" banner.
