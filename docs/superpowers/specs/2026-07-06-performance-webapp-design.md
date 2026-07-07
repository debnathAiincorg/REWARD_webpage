# Performance Data Entry Web App — Design

## Purpose

Replace manual Excel data entry for the "Daily Performance Bonus" table with a local
Flask web app. The app reads and writes the same SharePoint-hosted Excel table
(`Table1` in the "Daily Performance Bonus" sheet) that `weekly_report_send_teams.py`
already reports from, but via the Microsoft Graph Excel workbook API directly
(no download/upload cycle).

This is a new, separate project. `weekly_report_send_teams.py` and its tests are not
modified.

## Non-goals

- No deployment, scheduling, or automation — run manually via `python app.py` on the
  user's PC.
- No login/auth beyond the existing Azure app registration — single-user internal tool.
- No mocked Graph API tests — see Testing section.

## Project layout

```
d:\REWARDS\
  weekly_report_send_teams.py   (untouched)
  .env                          (shared — AZURE_CLIENT_ID/TENANT_ID/SECRET)
  webapp\
    app.py                      Flask app + routes
    config.py                   ACTIVE_FILE switch + startup guard
    graph_client.py             all Graph API calls
    logic.py                    dynamic column detection, totals, dedupe lookup
    requirements.txt            flask, msal, requests, python-dotenv
    templates\
      base.html                 header, nav, footer-with-banner (all pages extend this)
      dashboard.html
      add_entry.html
      history.html
    static\
      style.css                 ledger theme lifted from form.html, extended app-wide
```

`webapp/app.py` loads `.env` from the repo root (`d:\REWARDS\.env`), one directory up
from `webapp/`, via an explicit path passed to `load_dotenv()` — same 3 variable names
(`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_CLIENT_SECRET`) as the existing project,
no duplication.

`config.py` is committed to git normally (not gitignored) — Drive/Item IDs are not
credentials and are useless without the Azure app secret in `.env`.

## Safety mechanism (config.py)

```python
ACTIVE_FILE = "DUMMY"

DUMMY_DRIVE_ID = "PUT_DUMMY_DRIVE_ID_HERE"
DUMMY_ITEM_ID = "PUT_DUMMY_ITEM_ID_HERE"

MAIN_DRIVE_ID = None
MAIN_ITEM_ID = None

if ACTIVE_FILE == "DUMMY":
    DRIVE_ID, ITEM_ID = DUMMY_DRIVE_ID, DUMMY_ITEM_ID
elif ACTIVE_FILE == "MAIN":
    if not MAIN_DRIVE_ID or not MAIN_ITEM_ID:
        raise RuntimeError(
            "ACTIVE_FILE is 'MAIN' but MAIN_DRIVE_ID/MAIN_ITEM_ID are not set. "
            "Refusing to start."
        )
    DRIVE_ID, ITEM_ID = MAIN_DRIVE_ID, MAIN_ITEM_ID
else:
    raise RuntimeError(f"Unknown ACTIVE_FILE: {ACTIVE_FILE!r}")
```

Rules:
- Every other module imports `DRIVE_ID` / `ITEM_ID` / `ACTIVE_FILE` from `config.py` —
  no other file ever hardcodes a Drive ID or Item ID, and nothing else branches on
  file identity.
- Never look up the file by name. Only the Drive ID + Item ID pair from config is used.
- `app.py` imports `config` at module load time, so a bad `MAIN` configuration crashes
  the process immediately, before Flask binds to a port — it never silently falls back.
- `DUMMY_DRIVE_ID` / `DUMMY_ITEM_ID` are left as placeholders in this repo. The user
  supplies the real values by editing `config.py` directly before first run.
- `MAIN_DRIVE_ID` / `MAIN_ITEM_ID` stay `None` until the user explicitly provides them
  after dummy-file testing is complete (build order step 7). Not done preemptively.

## Visible connection indicator

Every page's `base.html` footer renders a banner sourced directly from
`config.ACTIVE_FILE`:

- `ACTIVE_FILE == "DUMMY"` → orange/yellow banner: `Connected to: DUMMY file — safe for testing`
- `ACTIVE_FILE == "MAIN"` → a differently-colored (e.g. red) banner:
  `Connected to: MAIN file — LIVE DATA`

## graph_client.py

Mirrors `get_access_token()` from `weekly_report_send_teams.py` exactly (same MSAL
`ConfidentialClientApplication` pattern), plus:

- `get_table_columns()` → `GET /drives/{DRIVE_ID}/items/{ITEM_ID}/workbook/tables/Table1/columns`
  → ordered list of header names.
- `get_table_rows()` → `GET .../tables/Table1/rows` → list of `{index, values}`.
- `add_table_row(values_by_column: dict)` → builds a values array in the *exact* header
  order from a fresh `get_table_columns()` call, `POST .../tables/Table1/rows/add`.
- `update_table_row(row_index, values_by_column)` → same value-array building,
  `PATCH .../tables/Table1/rows/{row_index}`.

Never hardcode column order — always rebuild it from `get_table_columns()` so new
columns added to the sheet later are picked up automatically.

All Graph calls go through one `try/except` wrapper that catches auth failures and
HTTP errors and raises a single `GraphError` with a human-readable message. No
retries — this is a manual tool; a failed Graph call just shows an error banner and
the user reloads.

## logic.py (pure functions, no Graph calls)

- `detect_columns(headers)` → `(date_idx, name_idx, index_idx, category_names)` — same
  detection rules as `_detect_columns()` in the existing script (case-insensitive match
  on "date"/"name"/"index", everything else is a category), adapted to a plain header
  list instead of an openpyxl worksheet.
- `rows_to_records(headers, rows)` → list of dicts, e.g.
  `{"Date": date(...), "Name": "...", "Punctuality": 1, ...}`.
- `find_existing_row(records, name, date)` → row index of a matching (Name, Date) pair,
  or `None`. This is the duplicate check — one row per (Name, Date).
- `week_bounds(today)` → `(monday, today)` for week-to-date totals. Simpler than the
  existing script's Monday/weekend special-casing, because the dashboard only needs
  the *current* week-to-date, not a "previous complete week" report.
- `totals_by_employee(records, start, end)` → `{name: {"points": int, "amount": int}}`.
  Points = sum of every column that isn't Date/Name/Index. Amount = points × 10.
- `next_index(records)` → `max(existing Index values) + 1`, or `1` if the sheet is
  empty. Used to populate the Index column on new-row inserts (Index is otherwise
  unused by any report logic, same as today).
- `distinct_employees(records)` → sorted unique Names, for the Add Entry dropdown.
  Never hardcoded.

## Routes

- `GET /` — Home. Static landing page (large ADIRI brand treatment, one welcome line,
  three cards linking to Dashboard/Add Entry/History). No Graph API calls — nothing on
  this route can fail, so it has no error handling.
- `GET /dashboard` — Dashboard. Fetch columns + rows once, build today's submitted entries and
  `totals_by_employee()` for the current week, render.
- `GET /add` — Add Entry form. Populates the employee dropdown from
  `distinct_employees()`. Category inputs: the current 6 known categories
  (Punctuality, L&D, Extra Hours, Fluency Compliance, Innovation, Extraordinary
  Performance) keep the styled per-category widgets from `form.html` (0/1 toggle
  buttons, the Extraordinary Performance multi-choice row, a free number input for
  Extra Hours). Any column `detect_columns()` finds that isn't one of those 6 falls
  back to a plain number input — picked up automatically, no code change required.
- `POST /add` — Validate payload → `find_existing_row()` → if found,
  `update_table_row()`; otherwise `next_index()` + `add_table_row()`. Redirects back to
  `/add` with a flashed success/error message. Keeps `form.html`'s visual styling and
  toggle-button JS, but posts to a real Flask route instead of a JSON `/api/submit`
  fetch endpoint.
- `GET /history` — Fetch all rows, apply optional `?employee=` and `?from=&to=`
  query-string filters in Python (no Graph-side range filtering — dataset is small),
  render as a table.

## Error handling

`app.py` catches `GraphError` at the route level and renders a plain error banner on
the page (no stack traces shown to the user; the real exception is printed to the
console running `python app.py`).

## Testing

`logic.py`'s pure functions get real `pytest` unit tests using hand-built fake
header/row data — no live Graph calls, no dependency on the dummy file's current
state. `graph_client.py` and the Flask routes are exercised manually against the
dummy file, per the build order below, rather than mocked in automated tests (mocking
Graph responses would mostly test the mocks, not real behavior).

## Build order

1. Flask skeleton: header, nav, footer-with-banner, empty Dashboard and Add Entry page
   shells — no real data wiring yet.
2. Wire Add Entry form → Graph API → writes to `Table1` (dummy file only).
3. Wire Dashboard → Graph API → reads `Table1` → today's entries + week-to-date totals.
4. Add duplicate detection/update logic.
5. Add History page with filtering.
6. User tests everything against the dummy file.
7. Only after explicit user confirmation, MAIN file's IDs are provided for cutover —
   not done preemptively.

## Out of scope / explicitly excluded

- GitHub Actions, Windows Task Scheduler, or any automated scheduling.
- Deployment anywhere other than the user's local machine.
- Any modification to `weekly_report_send_teams.py` or `tests/test_corrections.py`.
- Guessing, hardcoding, or name-searching for the MAIN file's Drive/Item IDs.
