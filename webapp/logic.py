# Pure business logic for the performance table — no Graph API calls here.
# Category columns are never hardcoded: they're whatever detect_columns() finds
# in the sheet's current header row, so new columns are picked up automatically.

from datetime import date, datetime, timedelta

RESERVED_HEADERS = {"date", "name", "index"}


def detect_columns(headers):
    """Classify header names into date/name/index positions plus category columns.

    Returns {"date_idx", "name_idx", "index_idx", "category_names"}. Indices are
    0-based positions into a row's values list; category_names preserves sheet order.
    """
    date_idx = name_idx = index_idx = None
    category_names = []
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
        else:
            category_names.append(clean)
    return {
        "date_idx": date_idx,
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
        bucket["amount"] = bucket["points"] * 10
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
