# Pure helpers for the worksheet-range sections (Whatsapp, Monthly, Keyboard).
#
# Those sheets aren't Excel Tables, so they're handled as a plain grid of cells.
# Each section's logic module reads a Grid and *plans* a write as a list of
# operations (insert rows, write cells, merge, fill...). graph_client.apply_ops()
# sends those operations to Graph; apply_ops() below performs the same
# operations on an in-memory Grid, which is how the tests check the exact
# layout a write leaves behind without any Graph call.
#
# Rows and columns are 1-based throughout, like Excel.

from datetime import date, datetime, timedelta

EXCEL_EPOCH = date(1899, 12, 30)

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]


def col_letter(col):
    """1 -> 'A', 27 -> 'AA'."""
    letters = ""
    while col > 0:
        col, rem = divmod(col - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def address(row, col, to_row=None, to_col=None):
    """A1-style address for a single cell or a rectangle."""
    start = f"{col_letter(col)}{row}"
    if to_row is None and to_col is None:
        return start
    return f"{start}:{col_letter(to_col or col)}{to_row or row}"


def is_blank(value):
    return value is None or (isinstance(value, str) and value.strip() == "")


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def clean_text(value):
    return "" if value is None else str(value).strip()


def fold(value):
    """Comparison key for names and month spellings ('AUGUST' == 'August')."""
    return " ".join(clean_text(value).lower().split())


def serial_to_date(value):
    if is_number(value):
        return EXCEL_EPOCH + timedelta(days=int(value))
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def date_to_serial(d):
    return (d - EXCEL_EPOCH).days


def month_number(value):
    """'May', 'AUGUST', 'sep' -> 5, 8, 9. None if it isn't a month name."""
    text = fold(value)
    if len(text) < 3:
        return None
    for i, name in enumerate(MONTH_NAMES, start=1):
        if name.lower().startswith(text):
            return i
    return None


class Grid:
    """A worksheet's values and number formats, padded to a rectangle starting at A1."""

    def __init__(self, values, formats=None):
        width = max((len(r) for r in values), default=0)
        self.values = [list(r) + [""] * (width - len(r)) for r in values]
        if formats is None:
            formats = [["General"] * width for _ in values]
        self.formats = [list(r) + ["General"] * (width - len(r)) for r in formats]

    @classmethod
    def from_used_range(cls, data):
        """Build from a Graph usedRange response (which may not start at A1)."""
        top, left = data.get("rowIndex", 0), data.get("columnIndex", 0)
        values = [[""] * left + list(r) for r in data.get("values", [])]
        formats = [["General"] * left + list(r) for r in data.get("numberFormat", [])]
        values = [[] for _ in range(top)] + values
        formats = [[] for _ in range(top)] + formats
        grid = cls(values, formats)
        while grid.values and all(is_blank(v) for v in grid.values[-1]):
            grid.values.pop()
            grid.formats.pop()
        return grid

    @property
    def n_rows(self):
        return len(self.values)

    @property
    def n_cols(self):
        return len(self.values[0]) if self.values else 0

    def cell(self, row, col):
        if 1 <= row <= self.n_rows and 1 <= col <= len(self.values[row - 1]):
            return self.values[row - 1][col - 1]
        return ""

    def fmt(self, row, col):
        if 1 <= row <= self.n_rows and 1 <= col <= len(self.formats[row - 1]):
            return self.formats[row - 1][col - 1]
        return "General"

    def row_values(self, row, to_col=None):
        to_col = to_col or self.n_cols
        return [self.cell(row, c) for c in range(1, to_col + 1)]

    def row_formats(self, row, to_col=None):
        to_col = to_col or self.n_cols
        return [self.fmt(row, c) for c in range(1, to_col + 1)]

    def row_blank(self, row):
        return all(is_blank(v) for v in self.row_values(row))

    def last_nonblank_row(self):
        for r in range(self.n_rows, 0, -1):
            if not self.row_blank(r):
                return r
        return 0


# ---------------------------------------------------------------------------
# Write operations. Each is a plain dict, so a plan is easy to read in a test
# failure and easy to send to Graph:
#   {"op": "insert_rows", "row": r, "count": n}        whole rows, shift down
#   {"op": "delete_rows", "row": r, "count": n}        whole rows, shift up
#   {"op": "write", "row": r, "col": c, "values": [[...]], "formats": [[...]] | None}
#   {"op": "merge", "row": r, "col": c, "to_col": c2}
#   {"op": "fill", "row": r, "col": c, "to_col": c2, "color": "#FFFF00" | None}
#   {"op": "align", "row": r, "col": c, "to_col": c2, "horizontal": "Center"}
# Operations apply in order; every row number refers to the sheet as it is
# after the operations before it.
# ---------------------------------------------------------------------------


def op_write(row, col, values, formats=None):
    return {"op": "write", "row": row, "col": col, "values": values, "formats": formats}


def apply_ops(grid, ops):
    """Return a new Grid with ops applied. Mirrors what Graph does to the sheet
    (minus styling, which a Grid doesn't model — merges/fills are recorded in
    grid.styles so tests can still assert on them)."""
    values = [list(r) for r in grid.values]
    formats = [list(r) for r in grid.formats]
    styles = list(getattr(grid, "styles", []))
    width = grid.n_cols

    def ensure(row, col):
        nonlocal width
        width = max(width, col)
        while len(values) < row:
            values.append([])
            formats.append([])
        for r in range(len(values)):
            values[r] += [""] * (width - len(values[r]))
            formats[r] += ["General"] * (width - len(formats[r]))

    for op in ops:
        kind = op["op"]
        if kind == "insert_rows":
            ensure(op["row"] - 1, 1)
            for _ in range(op["count"]):
                values.insert(op["row"] - 1, [""] * width)
                formats.insert(op["row"] - 1, ["General"] * width)
        elif kind == "delete_rows":
            del values[op["row"] - 1: op["row"] - 1 + op["count"]]
            del formats[op["row"] - 1: op["row"] - 1 + op["count"]]
        elif kind == "write":
            rows = op["values"]
            ensure(op["row"] + len(rows) - 1, op["col"] + max(len(r) for r in rows) - 1)
            for i, row_vals in enumerate(rows):
                for j, v in enumerate(row_vals):
                    # None = "leave this cell alone", exactly as in a Graph PATCH.
                    if v is not None:
                        values[op["row"] - 1 + i][op["col"] - 1 + j] = v
                    if op.get("formats") and op["formats"][i][j] is not None:
                        formats[op["row"] - 1 + i][op["col"] - 1 + j] = op["formats"][i][j]
        else:
            styles.append(dict(op))

    result = Grid(values, formats)
    result.styles = styles
    return result
