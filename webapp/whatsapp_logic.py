# Pure logic for the "Employee Whatsapp" sheet — no Graph calls here.
#
# Layout: a header row (First_Name | Last_Name | Mobile_1), then one contact per
# row with no gaps. Mobile_1 is stored as a plain whole number (General format),
# so it's written back as a JSON number — never as text, never as a float that
# Excel could show in scientific notation.

import re

from sheet_grid import clean_text, fold, is_blank, is_number, op_write

HEADER_KEYS = {"first": "first_name", "last": "last_name", "mobile": "mobile_1"}


def _header_key(value):
    return fold(value).replace(" ", "_")


def find_layout(grid):
    """Locate the header row and the three columns. Raises ValueError if missing."""
    for r in range(1, min(grid.n_rows, 10) + 1):
        keys = [_header_key(v) for v in grid.row_values(r)]
        if all(k in keys for k in HEADER_KEYS.values()):
            cols = {name: keys.index(k) + 1 for name, k in HEADER_KEYS.items()}
            return {"header_row": r, **cols}
    raise ValueError("Could not find the First_Name / Last_Name / Mobile_1 header row.")


def normalize_mobile(value):
    """A 10-digit Indian mobile as a string, or None if it isn't one.

    Accepts what people type ('+91 98765 43210', '098765-43210') and what the
    sheet stores (the int 9876543210, or a float 9876543210.0).
    """
    if is_blank(value):
        return None
    if is_number(value):
        if float(value) != int(value):
            return None
        digits = str(int(value))
    else:
        digits = re.sub(r"\D", "", str(value))
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10 and digits[0] in "6789":
        return digits
    return None


def contact_key(first, last):
    return (fold(first), fold(last))


def parse_contacts(grid):
    layout = find_layout(grid)
    contacts = []
    for r in range(layout["header_row"] + 1, grid.n_rows + 1):
        first = clean_text(grid.cell(r, layout["first"]))
        last = clean_text(grid.cell(r, layout["last"]))
        raw_mobile = grid.cell(r, layout["mobile"])
        if not first and not last and is_blank(raw_mobile):
            continue
        mobile = normalize_mobile(raw_mobile)
        contacts.append({
            "row": r,
            "first_name": first,
            "last_name": last,
            "full_name": f"{first} {last}".strip(),
            "mobile_raw": "" if is_blank(raw_mobile) else (
                str(int(raw_mobile)) if is_number(raw_mobile) and float(raw_mobile) == int(raw_mobile)
                else clean_text(raw_mobile)
            ),
            "mobile": mobile,
            "status": "ok" if mobile else ("missing" if is_blank(raw_mobile) else "invalid"),
            "wa_link": f"https://wa.me/91{mobile}" if mobile else None,
        })
    return contacts


def find_contact(contacts, first, last):
    key = contact_key(first, last)
    return next((c for c in contacts if contact_key(c["first_name"], c["last_name"]) == key), None)


def _row_payload(layout, first, last, mobile):
    width = max(layout["first"], layout["last"], layout["mobile"])
    values = [None] * width  # None = "leave this cell alone" in a Graph PATCH
    values[layout["first"] - 1] = first
    values[layout["last"] - 1] = last
    values[layout["mobile"] - 1] = int(mobile)
    return values


def plan_save(grid, first, last, mobile, original=None):
    """Plan an add or an in-place edit. Returns (ops, action) with action in
    {"added", "updated"}. Raises ValueError for a clash with another contact.

    `original` is the (first, last) the edit started from, so a typo in a name
    can be fixed in place. Without it, an existing First+Last is updated
    instead of duplicated.
    """
    layout = find_layout(grid)
    contacts = parse_contacts(grid)
    first, last = clean_text(first), clean_text(last)
    mobile = normalize_mobile(mobile)
    if not first:
        raise ValueError("Enter a first name.")
    if not mobile:
        raise ValueError("Enter a valid 10-digit mobile number.")

    target = find_contact(contacts, *original) if original else None
    if original and target is None:
        raise ValueError("That contact no longer exists in the sheet — it may have been changed or deleted.")
    same_key = find_contact(contacts, first, last)
    if target and same_key and same_key["row"] != target["row"]:
        raise ValueError(f"{first} {last} already exists as another contact.")
    target = target or same_key

    values = _row_payload(layout, first, last, mobile)
    if target:
        return [op_write(target["row"], 1, [values])], "updated"

    # Append directly under the last contact (a row with only stray spaces
    # counts as empty), copying that row's number formats.
    last_row = max((c["row"] for c in contacts), default=layout["header_row"])
    new_row = last_row + 1
    formats = None
    if contacts:
        formats = [[grid.fmt(last_row, c) for c in range(1, len(values) + 1)]]
    # A stray-space cell is replaced, so write "" rather than "leave alone".
    values = ["" if v is None else v for v in values]
    return [op_write(new_row, 1, [values], formats)], "added"


def plan_delete(grid, first, last):
    contact = find_contact(parse_contacts(grid), first, last)
    if contact is None:
        raise ValueError("That contact no longer exists in the sheet.")
    return [{"op": "delete_rows", "row": contact["row"], "count": 1}]


def dashboard_summary(contacts, roster):
    """Contact figures from the sheet, plus roster-based figures by Daily's rule
    (headcount from the shared roster; matching ignores case)."""
    names = {fold(c["full_name"]) for c in contacts}
    return {
        "total_employees": len(roster),
        "total": len(contacts),
        "valid": sum(1 for c in contacts if c["status"] == "ok"),
        "problem": sum(1 for c in contacts if c["status"] != "ok"),
        "roster_missing": sorted(n for n in roster if fold(n) not in names),
    }
