# Helpers shared by the worksheet-range sections (Whatsapp, Monthly, Keyboard).

import logic
from graph_client import apply_ops, get_sheet_grid
from sheet_grid import fold


def write_with_fresh_read(sheet_name, plan):
    """Re-read the sheet, plan the write against it, then apply it.

    `plan(grid)` returns ops or (ops, result). The plan is always made against
    the sheet as it is right now — never a row number from an earlier page
    load — so a concurrent edit can't redirect the write to the wrong row.
    Raises ValueError (plan refused) or GraphError (Graph failed).
    """
    grid = get_sheet_grid(sheet_name)
    planned = plan(grid)
    ops, result = planned if isinstance(planned, tuple) else (planned, None)
    apply_ops(sheet_name, ops)
    return result


def employee_choices(sheet_names):
    """Names for an employee picker: the shared roster plus any name already in
    this sheet, de-duplicated case-insensitively and sorted."""
    seen = {}
    for name in list(logic.load_employee_list()) + list(sheet_names):
        if name and fold(name) not in seen:
            seen[fold(name)] = name
    return sorted(seen.values(), key=fold)
