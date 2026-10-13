# Pure logic for the "Monthly Performance Bonus" sheet — no Graph calls.
#
# The sheet is a stack of month blocks, with no gap between blocks:
#
#   [26-Oct]  <- banner: a real date in column A, merged A:F, yellow, centred
#   Index | Name | Performance Bonus | Status | Status Date | Notes | For The Month of
#         | Employee A | 1500 | Approved | 10/26/2026 | ... | SEPTEMBER
#         | Employee B |   |   |   | June |          <- pre-filled name, waiting
#   [26-Nov]
#   (blank row instead of a header — not every block repeats it)
#         | Employee A | ...
#
# A block is identified by its banner's date. Column H has no header but holds
# ad-hoc notes; it's shown read-only and never written.

from collections import Counter
from datetime import date

from sheet_grid import (
    MONTH_NAMES, clean_text, date_to_serial, fold, is_blank, is_number,
    month_number, op_write, serial_to_date,
)

COLUMNS = {
    "index": "index",
    "name": "name",
    "bonus": "performance bonus",
    "status": "status",
    "status_date": "status date",
    "notes": "notes",
    "for_month": "for the month of",
}

STATUS_CHOICES = ["Approved", "Missed", "Pending"]

# How the existing banners look: merged across Index..Notes (A:F), yellow, centred.
BANNER_LAST_COL = 6
BANNER_FILL = "#FFFF00"
DEFAULT_DATE_FORMAT = "m/d/yyyy"


def find_layout(grid):
    for r in range(1, grid.n_rows + 1):
        keys = [fold(v) for v in grid.row_values(r)]
        if all(k in keys for k in COLUMNS.values()):
            layout = {name: keys.index(k) + 1 for name, k in COLUMNS.items()}
            layout["header_row"] = r
            layout["width"] = max(layout[k] for k in COLUMNS)
            layout["extra"] = layout["width"] + 1
            return layout
    raise ValueError("Could not find a Monthly Performance Bonus header row "
                     "(Index, Name, Performance Bonus, Status, Status Date, Notes, For The Month of).")


def is_banner(grid, row, layout):
    first = grid.cell(row, 1)
    if not is_number(first):
        return False
    return all(is_blank(grid.cell(row, c)) for c in range(2, layout["width"] + 1))


def banner_text(d, number_format):
    """How Excel displays the banner: 'd-mmm' -> '26-Oct', 'mmm-yy' -> 'Apr-26'."""
    if "d" in number_format.lower():
        return f"{d.day}-{d:%b}"
    return f"{d:%b}-{d:%y}"


def parse_amount(value):
    """A bonus as a number, or None for blanks and text like '(2500)+500'."""
    if is_number(value):
        return value
    text = clean_text(value).replace(",", "")
    try:
        number = float(text)
    except ValueError:
        return None
    return int(number) if number == int(number) else number


def parse_blocks(grid):
    """Returns (layout, blocks, records)."""
    layout = find_layout(grid)
    last = grid.last_nonblank_row()
    banners = [r for r in range(1, last + 1) if is_banner(grid, r, layout)]
    blocks, records = [], []
    for i, banner_row in enumerate(banners):
        end = banners[i + 1] - 1 if i + 1 < len(banners) else last
        d = serial_to_date(grid.cell(banner_row, 1))
        fmt = grid.fmt(banner_row, 1)
        block = {
            "id": d.isoformat(),
            "date": d,
            "banner_row": banner_row,
            "number_format": fmt,
            "text": banner_text(d, fmt),
            "label": f"{banner_text(d, fmt)} ({d:%d %b %Y})",
            "header_row": None,
            "last_row": banner_row,
            "rows": [],
        }
        for r in range(banner_row + 1, end + 1):
            if grid.row_blank(r):
                continue
            block["last_row"] = r
            if fold(grid.cell(r, layout["name"])) == "name":
                block["header_row"] = r
                continue
            name = clean_text(grid.cell(r, layout["name"]))
            if not name:
                continue
            bonus = grid.cell(r, layout["bonus"])
            record = {
                "row": r,
                "block_id": block["id"],
                "block_text": block["text"],
                "block_date": d,
                "name": name,
                "bonus": "" if is_blank(bonus) else bonus,
                "amount": parse_amount(bonus),
                "status": clean_text(grid.cell(r, layout["status"])),
                "status_date": serial_to_date(grid.cell(r, layout["status_date"])),
                "notes": clean_text(grid.cell(r, layout["notes"])),
                "for_month": clean_text(grid.cell(r, layout["for_month"])),
                "extra": clean_text(grid.cell(r, layout["extra"])),
            }
            record["filled"] = any(not is_blank(record[k]) for k in ("bonus", "status", "for_month")) \
                or record["status_date"] is not None
            block["rows"].append(record)
            records.append(record)
        blocks.append(block)
    return layout, blocks, records


def find_block(blocks, block_id):
    return next((b for b in blocks if b["id"] == block_id), None)


def find_record(block, name):
    key = fold(name)
    return next((r for r in block["rows"] if fold(r["name"]) == key), None) if block else None


def next_block_date(blocks):
    """The banner date a new block would get: the month after the latest block,
    on the same day of the month (the 26th, in the current sheet)."""
    if not blocks:
        today = date.today()
        return date(today.year, today.month, 26)
    latest = max(blocks, key=lambda b: b["date"])["date"]
    year, month = (latest.year + 1, 1) if latest.month == 12 else (latest.year, latest.month + 1)
    for day in (latest.day, 28):
        try:
            return date(year, month, day)
        except ValueError:
            continue


def _date_format(grid, layout, records):
    fmts = Counter(grid.fmt(r["row"], layout["status_date"]) for r in records if r["status_date"])
    fmts.pop("General", None)
    return fmts.most_common(1)[0][0] if fmts else DEFAULT_DATE_FORMAT


def _month_spelling(records, month_num):
    """Reuse the spelling already in the sheet for this month (latest block
    first); otherwise UPPERCASE, as the most recent blocks write it."""
    for r in sorted(records, key=lambda r: r["block_date"], reverse=True):
        if month_number(r["for_month"]) == month_num:
            return r["for_month"]
    return MONTH_NAMES[month_num - 1].upper()


def parse_bonus_input(text):
    """'1500' -> 1500 (a number, like the sheet stores it); '(2500)+500' stays text."""
    text = clean_text(text)
    if not text:
        return ""
    amount = parse_amount(text)
    return amount if amount is not None else text


def plan_save(grid, block_id, entry, editing=False):
    """Plan filling in (or adding) one employee's row in one month block.

    block_id is a block's ISO banner date, or "new" for the next month's block.
    entry: {"name", "bonus": str, "status": str, "status_date": date|None,
            "notes": str, "for_month": int|None}
    Returns (ops, action) with action in {"filled", "updated", "added", "created"}.
    """
    layout, blocks, records = parse_blocks(grid)
    name = clean_text(entry["name"])
    if not name:
        raise ValueError("Select an employee.")
    status = clean_text(entry.get("status"))
    if status and fold(status) not in {fold(s) for s in STATUS_CHOICES}:
        raise ValueError(f"Status must be one of: {', '.join(STATUS_CHOICES)}.")

    date_fmt = _date_format(grid, layout, records)
    fields = {
        "bonus": parse_bonus_input(entry.get("bonus")),
        "status": status,
        "status_date": date_to_serial(entry["status_date"]) if entry.get("status_date") else "",
        # Blank Notes means "leave whatever is there" (None = don't touch the cell),
        # same rule the Daily section uses for its free-text column.
        "notes": clean_text(entry.get("notes")) or None,
        "for_month": _month_spelling(records, entry["for_month"]) if entry.get("for_month") else "",
    }
    field_cols = ["bonus", "status", "status_date", "notes", "for_month"]
    first_col = min(layout[k] for k in field_cols)
    last_col = max(layout[k] for k in field_cols)

    def field_write(row):
        values = [None] * (last_col - first_col + 1)
        formats = [None] * len(values)
        for k in field_cols:
            values[layout[k] - first_col] = fields[k]
        if fields["status_date"] != "":
            formats[layout["status_date"] - first_col] = date_fmt
        return op_write(row, first_col, [values], [formats])

    def full_row(row_name, with_fields):
        values = [""] * layout["width"]
        formats = ["General"] * layout["width"]
        values[layout["name"] - 1] = row_name
        if with_fields:
            for k in field_cols:
                values[layout[k] - 1] = "" if fields[k] is None else fields[k]
            if fields["status_date"] != "":
                formats[layout["status_date"] - 1] = date_fmt
        return values, formats

    if block_id == "new":
        if editing:
            raise ValueError("Pick an existing month block to edit.")
        new_date = next_block_date(blocks)
        latest = max(blocks, key=lambda b: b["date"]) if blocks else None
        start = grid.last_nonblank_row() + 1  # blocks sit back to back, no gap
        banner_fmt = latest["number_format"] if latest else "d-mmm"
        ops = [
            op_write(start, 1, [[date_to_serial(new_date)]], [[banner_fmt]]),
            {"op": "merge", "row": start, "col": 1, "to_col": BANNER_LAST_COL},
            {"op": "fill", "row": start, "col": 1, "to_col": BANNER_LAST_COL, "color": BANNER_FILL},
            {"op": "align", "row": start, "col": 1, "to_col": BANNER_LAST_COL, "horizontal": "Center"},
        ]
        header = grid.row_values(layout["header_row"], layout["width"])
        roster = [r["name"] for r in latest["rows"]] if latest else []
        if fold(name) not in {fold(n) for n in roster}:
            roster.append(name)
        rows, fmts = [header], [["General"] * layout["width"]]
        for n in roster:
            v, f = full_row(n, fold(n) == fold(name))
            rows.append(v)
            fmts.append(f)
        ops.append(op_write(start + 1, 1, rows, fmts))
        return ops, "created"

    block = find_block(blocks, block_id)
    if block is None:
        raise ValueError("That month block no longer exists in the sheet.")
    existing = find_record(block, name)
    if editing and existing is None:
        raise ValueError("That entry no longer exists in the sheet — it may have been changed or deleted.")
    if existing:
        return [field_write(existing["row"])], ("updated" if existing["filled"] else "filled")

    # Not pre-filled: a new row at the end of the block, before the next banner.
    row = block["last_row"] + 1
    ops = []
    if row <= grid.last_nonblank_row():
        ops.append({"op": "insert_rows", "row": row, "count": 1})
        if block["last_row"] == block["banner_row"]:
            # An inserted row takes its format from the row above; never let it
            # inherit the banner's yellow.
            ops.append({"op": "fill", "row": row, "col": 1, "to_col": layout["extra"], "color": None})
    values, formats = full_row(name, True)
    ops.append(op_write(row, 1, [values], [formats]))
    return ops, "added"


def plan_clear(grid, block_id, name):
    """Delete = clear Bonus, Status, Status Date and For The Month of, keeping
    the Name (and Notes) so the block's pre-filled roster stays intact."""
    layout, blocks, _ = parse_blocks(grid)
    record = find_record(find_block(blocks, block_id), name)
    if record is None:
        raise ValueError("That entry no longer exists in the sheet.")
    cols = ["bonus", "status", "status_date", "for_month"]
    first_col = min(layout[k] for k in cols)
    last_col = max(layout[k] for k in cols)
    values = [None] * (last_col - first_col + 1)
    for k in cols:
        values[layout[k] - first_col] = ""
    return [op_write(record["row"], first_col, [values])]


def block_summary(block):
    rows = block["rows"] if block else []
    numeric = [r["amount"] for r in rows if r["amount"] is not None]
    approved = [r for r in rows if fold(r["status"]) == "approved"]
    return {
        "rows": rows,
        "employees": len(rows),
        "total_amount": sum(numeric),
        "approved_amount": sum(r["amount"] for r in approved if r["amount"] is not None),
        "non_numeric": [r for r in rows if r["amount"] is None and not is_blank(r["bonus"])],
        "approved": len(approved),
        "missed": sum(1 for r in rows if fold(r["status"]) == "missed"),
        "pending": sum(1 for r in rows if fold(r["status"]) not in ("approved", "missed")),
    }


def report_block(blocks, today):
    """The block the dashboard opens on: the latest block whose banner date has
    already passed (before today), so pre-created future blocks (26-Nov,
    26-Dec) aren't the default. If no block's date has passed yet, fall back
    to default_block()."""
    passed = [b for b in blocks if b["date"] < today]
    if passed:
        return max(passed, key=lambda b: b["date"])
    return default_block(blocks)


def report_reason(block, today):
    """Why the dashboard opened on `block` (see report_block), for the strip."""
    if block["date"] < today:
        return "latest block up to yesterday"
    return "latest block with entries · no block date has passed yet"


def bonus_month(block):
    """The month a block's bonuses are for: the most common "For The Month of"
    value in the block, else the month before the banner (26-Sep -> August),
    which is how every existing block is filled in."""
    counts = Counter(month_number(r["for_month"]) for r in block["rows"] if month_number(r["for_month"]))
    if counts:
        return MONTH_NAMES[counts.most_common(1)[0][0] - 1]
    d = block["date"]
    return MONTH_NAMES[(d.month - 2) % 12]


def previous_block(blocks, block):
    """The block just before `block` (by banner date), or None."""
    earlier = [b for b in blocks if b["date"] < block["date"]]
    return max(earlier, key=lambda b: b["date"]) if earlier else None


def default_block(blocks):
    """Latest block with anything filled in; otherwise the latest block."""
    filled = [b for b in blocks if any(r["filled"] for r in b["rows"])]
    pool = filled or blocks
    return max(pool, key=lambda b: b["date"]) if pool else None


def roster_kpis(block, roster):
    """Roster-based figures for one month block, by Daily's rule: headcounts
    come from the shared roster (employees.json), never from the sheet. A roster
    name has "no bonus entry" if the block has no row for it, or its row is
    still empty (only the pre-filled name). Removed names drop out of these
    figures; their sheet rows still show in the tables and History. Matching
    ignores case.
    """
    filled = {fold(r["name"]) for r in (block["rows"] if block else []) if r["filled"]}
    return {
        "total_employees": len(roster),
        "no_entry": [n for n in roster if fold(n) not in filled],
    }
