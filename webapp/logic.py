# Pure business logic for the performance table — no Graph API calls here.
# Category columns are never hardcoded: they're whatever detect_columns() finds
# in the sheet's current header row, so new columns are picked up automatically.

import json
import os
from datetime import date, datetime, timedelta
from pathlib import Path

RESERVED_HEADERS = {"date", "name", "index"}

# One performance point is worth this much, in rupees.
POINTS_TO_AMOUNT = 10

# The Add Entry dropdown's roster of selectable employees. Deliberately kept
# separate from the sheet: retiring a name here stops it appearing in the
# dropdown without touching a single one of that person's existing rows.
#
# EMPLOYEES_DATA_DIR points this at a persistent disk in production. Hosts with
# an ephemeral filesystem wipe the app directory on every redeploy, which would
# silently undo each add/remove and re-seed the roster from the sheet. Unset
# (local dev), it falls back to sitting next to this file as before.
EMPLOYEES_PATH = Path(
    os.environ.get("EMPLOYEES_DATA_DIR", Path(__file__).resolve().parent)
) / "employees.json"

# Known free-text columns (e.g. "Notes") — carried through as-is, never summed
# into points, never overwritten with a number input.
TEXT_FIELD_NAMES = {"notes", "comment", "comments", "remark", "remarks"}


def detect_columns(headers):
    """Classify header names into date/name/index/text positions plus category columns.

    Returns {"date_idx", "name_idx", "index_idx", "category_names", "text_names"}.
    Indices are 0-based positions into a row's values list; category_names and
    text_names preserve sheet order.
    """
    date_idx = name_idx = index_idx = None
    category_names = []
    text_names = []
    for i, h in enumerate(headers):
        if h is None or str(h).strip() == "":
            continue
        clean = str(h).strip()
        hl = clean.lower()
        if hl == "date":
            date_idx = i
        elif hl == "name":
            name_idx = i
        elif hl == "index":
            index_idx = i
        elif hl in TEXT_FIELD_NAMES:
            text_names.append(clean)
        else:
            category_names.append(clean)
    return {
        "date_idx": date_idx,
        "text_names": text_names,
        "name_idx": name_idx,
        "index_idx": index_idx,
        "category_names": category_names,
    }


def parse_date_value(value):
    """Convert a raw Graph cell value (ISO string or Excel serial number) to a date."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Excel serial date: days since 1899-12-30 (Excel's epoch, incl. the 1900 leap bug).
        return (datetime(1899, 12, 30) + timedelta(days=value)).date()
    text = str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def to_number(value):
    """Best-effort numeric coercion, truncating floats like the existing script does."""
    if value is None or value == "":
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        pass
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def rows_to_records(headers, rows):
    """Turn raw Graph rows into dicts keyed by header name, with Date parsed and
    Name normalized. Each record also carries '_row_index' for update_table_row().
    """
    cols = detect_columns(headers)
    records = []
    for row in rows:
        values = row["values"]
        record = {"_row_index": row["index"]}
        for i, h in enumerate(headers):
            if h is None or str(h).strip() == "":
                continue
            record[str(h).strip()] = values[i] if i < len(values) else None
        if cols["date_idx"] is not None and cols["date_idx"] < len(values):
            record["Date"] = parse_date_value(values[cols["date_idx"]])
        if cols["name_idx"] is not None and cols["name_idx"] < len(values):
            raw_name = values[cols["name_idx"]]
            record["Name"] = str(raw_name).strip() if raw_name is not None else None
        records.append(record)
    return records


def find_existing_row(records, name, target_date):
    """Return the table row index of a matching (Name, Date) pair, or None."""
    name = str(name).strip()
    for r in records:
        if r.get("Name") == name and r.get("Date") == target_date:
            return r["_row_index"]
    return None


def week_bounds(today):
    """Return (monday, today) for the current week-to-date range."""
    monday = today - timedelta(days=today.weekday())
    return monday, today


def previous_week_bounds(today):
    """Return (monday, sunday) for the complete calendar week just before
    this one — a fixed 7-day window, not a rolling one, so it doesn't shift
    as the current week progresses."""
    this_monday = today - timedelta(days=today.weekday())
    monday = this_monday - timedelta(days=7)
    sunday = this_monday - timedelta(days=1)
    return monday, sunday


def totals_by_employee(records, start, end, category_names):
    """Sum points (and amount = points * 10) per employee within [start, end]."""
    totals = {}
    for r in records:
        name = r.get("Name")
        row_date = r.get("Date")
        if not name or not row_date:
            continue
        if not (start <= row_date <= end):
            continue
        points = sum(to_number(r.get(cat)) for cat in category_names)
        bucket = totals.setdefault(name, {"points": 0, "amount": 0})
        bucket["points"] += points
    for bucket in totals.values():
        bucket["amount"] = bucket["points"] * POINTS_TO_AMOUNT
    return totals


def next_index(records):
    """Next sequential Index value for a new row: max existing Index + 1 (or 1)."""
    max_idx = 0
    for r in records:
        idx = to_number(r.get("Index"))
        max_idx = max(max_idx, idx)
    return max_idx + 1


def distinct_employees(records):
    """Sorted unique employee names present in the sheet — never hardcoded."""
    return sorted({r["Name"] for r in records if r.get("Name")})


def entries_for_date(records, target_date):
    """Records whose Date matches target_date, for the dashboard's 'today' list."""
    return [r for r in records if r.get("Date") == target_date]


def filter_records(records, employee=None, date_from=None, date_to=None):
    """Apply optional employee/date-range filters, for the History page."""
    result = records
    if employee:
        result = [r for r in result if r.get("Name") == employee]
    if date_from:
        result = [r for r in result if r.get("Date") and r["Date"] >= date_from]
    if date_to:
        result = [r for r in result if r.get("Date") and r["Date"] <= date_to]
    return result


# ---------------------------------------------------------------------------
# Employee master list — the Add Entry dropdown's roster, persisted in
# employees.json. This is the one part of this module that touches disk; it
# stays here because it's roster policy (trimming, dedupe, sort ordering),
# not transport.
# ---------------------------------------------------------------------------


def _normalize_names(names):
    """Trim, drop blanks, de-duplicate case-insensitively, and sort."""
    seen = {}
    for raw in names:
        if raw is None:
            continue
        clean = str(raw).strip()
        if not clean:
            continue
        # First spelling wins, so an existing entry keeps its original casing.
        seen.setdefault(clean.lower(), clean)
    return sorted(seen.values())


def load_employee_list():
    """The saved roster. Returns [] if the file is absent, unreadable or corrupt —
    a broken file should degrade to an empty dropdown, never crash the page."""
    try:
        with open(EMPLOYEES_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return _normalize_names(data)


def save_employee_list(names):
    """Write the roster back, always trimmed, de-duplicated and alphabetical."""
    clean = _normalize_names(names)
    # A freshly mounted volume is an empty directory that may not exist yet on
    # first boot; every roster write funnels through here, so this is the one
    # place that needs to guarantee it.
    os.makedirs(EMPLOYEES_PATH.parent, exist_ok=True)
    with open(EMPLOYEES_PATH, "w", encoding="utf-8") as f:
        json.dump(clean, f, indent=2, ensure_ascii=False)
    return clean


def add_employee_name(name):
    """Add a name to the roster, returning (stored_name, was_added).

    A blank name gives (None, False). A case-insensitive duplicate is not an
    error: it returns the spelling already on file, so the caller can simply
    select that one.
    """
    clean = str(name or "").strip()
    if not clean:
        return None, False
    current = load_employee_list()
    for existing in current:
        if existing.lower() == clean.lower():
            return existing, False
    save_employee_list(current + [clean])
    return clean, True


def remove_employee_name(name):
    """Retire a name from the dropdown. Returns True if it was there.

    This only ever rewrites employees.json — the person's rows in Table1 are
    left exactly as they are, and still show up in History.
    """
    clean = str(name or "").strip()
    if not clean:
        return False
    current = load_employee_list()
    remaining = [n for n in current if n.lower() != clean.lower()]
    if len(remaining) == len(current):
        return False
    save_employee_list(remaining)
    return True


def seed_employee_list_if_missing(records):
    """First run only: seed the roster from names already in the sheet.

    Keyed on the file not existing — never on it being empty. An empty roster is
    a deliberate state (every name removed via the dropdown's × button), and
    re-seeding it would silently undo those removals.
    """
    if EMPLOYEES_PATH.exists():
        return False
    save_employee_list(distinct_employees(records))
    return True


# ---------------------------------------------------------------------------
# Dashboard aggregates. These take the roster as an argument rather than
# reading employees.json themselves, which keeps them pure: no Graph calls and
# no disk access, so they unit-test directly.
# ---------------------------------------------------------------------------


def _fold(name):
    """Key a name for comparison — the sheet's spelling and the roster's may differ."""
    return str(name).strip().lower()


def dashboard_kpis(records, roster, start, end, category_names):
    """Headline figures for the Dashboard's KPI row.

    Counts come from the roster, not from the sheet, so an employee who has
    never submitted anything still counts — that's the whole point of the
    "zero points this week" figure.
    """
    totals = totals_by_employee(records, start, end, category_names)

    points_by_key = {}
    for name, bucket in totals.items():
        key = _fold(name)
        points_by_key[key] = points_by_key.get(key, 0) + bucket["points"]

    weekly_points = sum(bucket["points"] for bucket in totals.values())
    zero_count = sum(1 for n in roster if points_by_key.get(_fold(n), 0) == 0)

    # `end` is always "today" (the caller's week-to-date window), so the
    # previous complete week is derived from it directly rather than taking
    # a separate parameter.
    prev_monday, prev_sunday = previous_week_bounds(end)
    prev_week_totals = totals_by_employee(records, prev_monday, prev_sunday, category_names)
    previous_week_points = sum(bucket["points"] for bucket in prev_week_totals.values())

    return {
        "total_employees": len(roster),
        "weekly_points": weekly_points,
        "weekly_amount": weekly_points * POINTS_TO_AMOUNT,
        "zero_point_employees": zero_count,
        "previous_week_points": previous_week_points,
    }


def weekly_report_rows(records, start, end, prev_day, category_names):
    """Previous-day and week-to-date figures per employee, side by side.

    Only employees with activity inside [start, end] are listed — the same
    inclusion rule the week-to-date totals table has always used. An employee
    with week activity but nothing on prev_day simply shows zeros in the
    previous-day columns.
    """
    week_totals = totals_by_employee(records, start, end, category_names)
    prev_totals = totals_by_employee(records, prev_day, prev_day, category_names)

    rows = []
    for name, bucket in week_totals.items():
        prev_points = prev_totals.get(name, {}).get("points", 0)
        week_points = bucket["points"]
        rows.append({
            "name": name,
            "prev_points": prev_points,
            "prev_amount": prev_points * POINTS_TO_AMOUNT,
            "week_points": week_points,
            "week_amount": week_points * POINTS_TO_AMOUNT,
        })

    rows.sort(key=lambda r: (-r["prev_amount"], r["name"]))
    return rows
