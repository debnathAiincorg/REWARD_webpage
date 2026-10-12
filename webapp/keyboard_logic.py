# Pure logic for the "Keyboard Performance Status - M" sheet — no Graph calls.
#
# Layout: header row, one blank row, then one group of rows per month
# (Year + Month on every row), with exactly one blank row between groups:
#
#   Index | Year | Month | Employee Name | Accuracy Score | Speed | Comments
#   (blank)
#   1     | 2026 | May   | ...           | 0.97 (0%)      | 18 WPM |
#   ...
#   (blank)
#   12    | 2026 | June  | ...
#
# Accuracy is a real number with a percent format: "0%" for whole percents,
# "0.00%" otherwise. Speed is text ("18 WPM") — except for an absent employee,
# whose row has Accuracy 0 and Speed the *number* 0, both formatted "0%".
# Index has gaps and is never renumbered; a new row gets max(Index) + 1.

import re

from sheet_grid import MONTH_NAMES, clean_text, fold, is_number, month_number, op_write

COLUMNS = {
    "index": "index",
    "year": "year",
    "month": "month",
    "name": "employee name",
    "accuracy": "accuracy score",
    "speed": "speed",
    "comments": "comments",
}


def find_layout(grid):
    for r in range(1, min(grid.n_rows, 10) + 1):
        keys = [fold(v) for v in grid.row_values(r)]
        if all(k in keys for k in COLUMNS.values()):
            return {"header_row": r, "width": len(COLUMNS),
                    **{name: keys.index(k) + 1 for name, k in COLUMNS.items()}}
    raise ValueError("Could not find the Keyboard sheet's header row "
                     "(Index, Year, Month, Employee Name, Accuracy Score, Speed, Comments).")


def parse_speed(value):
    """'18 WPM', '17WPM', '38.2 wpm' -> 18.0 / 17.0 / 38.2; the number 0 -> 0.0."""
    if is_number(value):
        return float(value)
    match = re.search(r"\d+(?:\.\d+)?", clean_text(value))
    return float(match.group()) if match else None


def format_speed(wpm):
    """38.2 -> '38.2 WPM', 18.0 -> '18 WPM' — the spelling most rows use."""
    return f"{wpm:g} WPM"


def accuracy_format(fraction):
    """'0%' when the percent is whole (97%), '0.00%' otherwise (98.47%)."""
    return "0%" if round(fraction * 100, 2) == round(fraction * 100) else "0.00%"


def parse_rows(grid):
    """Every data row, plus the month groups they form. Returns (records, groups)."""
    layout = find_layout(grid)
    records, groups = [], []
    current = None
    for r in range(layout["header_row"] + 1, grid.n_rows + 1):
        if grid.row_blank(r):
            current = None
            continue
        raw_year = grid.cell(r, layout["year"])
        raw_month = grid.cell(r, layout["month"])
        # Rows typed without Year/Month inherit them from the row above in
        # the same group (older copies of the sheet did that).
        year = int(raw_year) if is_number(raw_year) else (
            int(clean_text(raw_year)) if clean_text(raw_year).isdigit() else (current or {}).get("year"))
        month_num = month_number(raw_month) or (current or {}).get("month_num")
        month_label = clean_text(raw_month) or (current or {}).get("month_label", "")

        if current is None or (current["year"], current["month_num"]) != (year, month_num):
            current = {"year": year, "month_num": month_num, "month_label": month_label,
                       "first_row": r, "last_row": r, "rows": []}
            groups.append(current)
        current["last_row"] = r

        raw_acc = grid.cell(r, layout["accuracy"])
        raw_speed = grid.cell(r, layout["speed"])
        raw_index = grid.cell(r, layout["index"])
        record = {
            "row": r,
            "index": int(raw_index) if is_number(raw_index) else None,
            "year": year,
            "month_num": month_num,
            "month_label": month_label,
            "name": clean_text(grid.cell(r, layout["name"])),
            "accuracy": float(raw_acc) if is_number(raw_acc) else None,
            "speed_raw": raw_speed,
            "speed": parse_speed(raw_speed),
            "comments": clean_text(grid.cell(r, layout["comments"])),
        }
        record["absent"] = record["accuracy"] == 0
        current["rows"].append(record)
        records.append(record)
    return records, groups


def period_key(year, month_num):
    return f"{year}-{month_num:02d}"


def period_label(year, month_num):
    return f"{MONTH_NAMES[month_num - 1]} {year}"


def find_record(records, name, year, month_num):
    key = fold(name)
    return next((r for r in records
                 if fold(r["name"]) == key and r["year"] == year and r["month_num"] == month_num), None)


def next_index(records):
    return max((r["index"] for r in records if r["index"] is not None), default=0) + 1


def _row_values(layout, index, year, month_label, name, accuracy, speed_value, comments):
    values = [""] * layout["width"]
    values[layout["index"] - 1] = index
    values[layout["year"] - 1] = year
    values[layout["month"] - 1] = month_label
    values[layout["name"] - 1] = name
    values[layout["accuracy"] - 1] = accuracy
    values[layout["speed"] - 1] = speed_value
    values[layout["comments"] - 1] = comments
    return values


def plan_save(grid, entry, editing=False):
    """Plan an add or in-place edit for one employee/month. Returns (ops, action).

    entry: {"name", "year", "month_num", "absent": bool,
            "accuracy_pct": float|None, "speed_wpm": float|None, "comments": str}
    """
    layout = find_layout(grid)
    records, groups = parse_rows(grid)
    name = clean_text(entry["name"])
    year, month_num = entry["year"], entry["month_num"]
    if not name:
        raise ValueError("Select an employee.")
    if not year or not month_num:
        raise ValueError("Select a year and month.")

    if entry.get("absent"):
        accuracy, speed_value = 0, 0
        acc_fmt = speed_fmt = "0%"
    else:
        if entry.get("accuracy_pct") is None:
            raise ValueError("Enter an accuracy score (or mark the employee absent).")
        pct = float(entry["accuracy_pct"])
        if not 0 <= pct <= 100:
            raise ValueError("Accuracy must be between 0 and 100%.")
        accuracy = round(pct / 100, 4)
        acc_fmt = accuracy_format(accuracy)
        speed = entry.get("speed_wpm")
        speed_value = format_speed(float(speed)) if speed is not None else ""
        speed_fmt = "General"
    comments = clean_text(entry.get("comments"))

    existing = find_record(records, name, year, month_num)
    if editing and existing is None:
        raise ValueError("That entry no longer exists in the sheet — it may have been changed or deleted.")

    def formats_like(ref_row):
        fmts = [grid.fmt(ref_row, c) if ref_row else "General" for c in range(1, layout["width"] + 1)]
        fmts[layout["accuracy"] - 1] = acc_fmt
        fmts[layout["speed"] - 1] = speed_fmt
        return [fmts]

    if existing:
        values = _row_values(layout, existing["index"] if existing["index"] is not None else "",
                             existing["year"], existing["month_label"], existing["name"],
                             accuracy, speed_value, comments)
        return [op_write(existing["row"], 1, [values], formats_like(existing["row"]))], "updated"

    index = next_index(records)
    group = next((g for g in groups if (g["year"], g["month_num"]) == (year, month_num)), None)
    if group:
        # End of that month's group, just above its blank separator.
        row = group["last_row"] + 1
        values = _row_values(layout, index, year, group["month_label"], name,
                             accuracy, speed_value, comments)
        ops = []
        if row <= grid.last_nonblank_row():
            ops.append({"op": "insert_rows", "row": row, "count": 1})
        ops.append(op_write(row, 1, [values], formats_like(group["last_row"])))
        return ops, "added"

    latest = max(groups, key=lambda g: (g["year"], g["month_num"]), default=None)
    if latest and (year, month_num) < (latest["year"], latest["month_num"]):
        raise ValueError(
            f"{period_label(year, month_num)} is earlier than the latest month in the sheet "
            f"({period_label(latest['year'], latest['month_num'])}). New months can only be added after it."
        )
    # A new month starts a new group: one blank row, then its rows. The same
    # holds for the very first group, whose "blank row" sits under the header.
    last_row = grid.last_nonblank_row() or layout["header_row"]
    row = last_row + 2
    month_label = MONTH_NAMES[month_num - 1].upper()
    values = _row_values(layout, index, year, month_label, name, accuracy, speed_value, comments)
    ref = latest["last_row"] if latest else None
    return [op_write(row, 1, [values], formats_like(ref))], "added"


def plan_delete(grid, name, year, month_num):
    """Delete one row. If it was the only row of its month, also drop one of
    the blank separators around it, so the gaps between groups stay single."""
    records, groups = parse_rows(grid)
    record = find_record(records, name, year, month_num)
    if record is None:
        raise ValueError("That entry no longer exists in the sheet.")
    pos = next(i for i, g in enumerate(groups) if record in g["rows"])
    group = groups[pos]
    if len(group["rows"]) > 1:
        return [{"op": "delete_rows", "row": record["row"], "count": 1}]
    if pos + 1 < len(groups):
        # Drop the row and the separator after it: header/blank/next group stays.
        return [{"op": "delete_rows", "row": record["row"], "count": 2}]
    if pos > 0:
        # Last group: drop the separator before it along with the row.
        return [{"op": "delete_rows", "row": record["row"] - 1, "count": 2}]
    return [{"op": "delete_rows", "row": record["row"], "count": 1}]


def periods(groups):
    """Distinct (year, month_num) in chronological order."""
    return sorted({(g["year"], g["month_num"]) for g in groups if g["year"] and g["month_num"]})


def month_summary(records, year, month_num):
    rows = [r for r in records if (r["year"], r["month_num"]) == (year, month_num)]
    rows = sorted(rows, key=lambda r: (-(r["accuracy"] or 0), -(r["speed"] or 0), fold(r["name"])))
    present = [r for r in rows if r["accuracy"]]
    speeds = [r["speed"] for r in present if r["speed"]]
    top = max(present, key=lambda r: (r["accuracy"], r["speed"] or 0), default=None)
    return {
        "rows": rows,
        "count": len(rows),
        "avg_accuracy": sum(r["accuracy"] for r in present) / len(present) if present else None,
        "avg_speed": sum(speeds) / len(speeds) if speeds else None,
        "top": top,
        "zero": [r for r in rows if r["accuracy"] == 0],
    }


def comparison_table(records, period_list):
    """{name: {period: record}} plus the sorted name list, for the month-by-month table."""
    table = {}
    for r in records:
        if not r["name"]:
            continue
        table.setdefault(r["name"], {})[(r["year"], r["month_num"])] = r
    return sorted(table, key=fold), table


def roster_kpis(records, roster, year, month_num):
    """Roster-based figures for one month, by Daily's rule: headcounts come from
    the shared roster (employees.json), never from the sheet. A name added to
    the roster counts as "not tested" until it has a row for that month; a
    removed name drops out of these figures, while its sheet rows still show in
    the tables and History. Matching ignores case.
    """
    tested = {fold(r["name"]) for r in records if (r["year"], r["month_num"]) == (year, month_num)}
    return {
        "total_employees": len(roster),
        "not_tested": [n for n in roster if fold(n) not in tested],
    }
