# Helpers shared by the worksheet-range sections (Whatsapp, Monthly, Keyboard).

import logic
from graph_client import GraphError, apply_ops, get_sheet_grid, get_table_columns, get_table_rows
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


def load_roster():
    """The shared employee roster (employees.json) that every section's
    dropdown and roster-based dashboard figures use, exactly like Daily's.

    First run only, it is seeded from the Daily sheet's names — the same seed
    Daily uses — so every section starts from the same list whichever page is
    opened first.
    """
    if not logic.EMPLOYEES_PATH.exists():
        try:
            records = logic.rows_to_records(get_table_columns(), get_table_rows())
            logic.seed_employee_list_if_missing(records)
        except GraphError:
            pass  # no seed this time; the roster is just empty until it works
    return logic.load_employee_list()


def roster_choices(selected=None):
    """Names for the shared employee dropdown: the roster, plus a name being
    edited that has since been removed from it — added for this render only
    (never written back), so that entry stays editable.
    """
    employees = load_roster()
    if selected and fold(selected) not in {fold(n) for n in employees}:
        employees = sorted(employees + [selected], key=fold)
    return employees
