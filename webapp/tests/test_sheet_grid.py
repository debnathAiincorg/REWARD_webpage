import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sheet_grid import (
    Grid, address, apply_ops, col_letter, date_to_serial, month_number,
    op_write, serial_to_date,
)


def test_col_letter_and_address():
    assert col_letter(1) == "A"
    assert col_letter(26) == "Z"
    assert col_letter(27) == "AA"
    assert address(5, 1) == "A5"
    assert address(5, 1, 5, 7) == "A5:G5"


def test_serial_round_trip_matches_excel():
    # 46321 is what the sheet stores for the 26-Oct banner.
    assert serial_to_date(46321) == date(2026, 10, 26)
    assert date_to_serial(date(2026, 10, 26)) == 46321


def test_month_number_ignores_case_and_accepts_abbreviations():
    assert month_number("May") == 5
    assert month_number("AUGUST") == 8
    assert month_number("sept") == 9
    assert month_number("Smarch") is None
    assert month_number("") is None


def test_from_used_range_pads_offset_and_trims_trailing_blanks():
    grid = Grid.from_used_range({
        "rowIndex": 1, "columnIndex": 1,
        "values": [["x", "y"], ["", ""]],
        "numberFormat": [["General", "0%"], ["General", "General"]],
    })
    assert grid.n_rows == 2
    assert grid.cell(2, 2) == "x"
    assert grid.fmt(2, 3) == "0%"
    assert grid.cell(1, 1) == ""


def test_apply_ops_insert_write_delete():
    grid = Grid([["a"], ["b"], ["c"]])
    out = apply_ops(grid, [
        {"op": "insert_rows", "row": 2, "count": 1},
        op_write(2, 1, [["new"]]),
        {"op": "delete_rows", "row": 4, "count": 1},
    ])
    assert [r[0] for r in out.values] == ["a", "new", "b"]


def test_apply_ops_none_leaves_cell_alone():
    grid = Grid([["keep", "old"]])
    out = apply_ops(grid, [op_write(1, 1, [[None, "new"]])])
    assert out.values == [["keep", "new"]]
