import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import monthly_logic as ml
from sheet_grid import Grid, apply_ops, date_to_serial

HEADER = ["Index", "Name", "Performance Bonus", "Status", "Status Date", "Notes", "For The Month of", ""]
BLANK = [""] * 8
GEN = ["General"] * 8
DATE_FMT = ["General"] * 4 + ["m/d/yyyy"] + ["General"] * 3

SEP = date_to_serial(date(2026, 9, 26))
OCT = date_to_serial(date(2026, 10, 26))
NOV = date_to_serial(date(2026, 11, 26))


def banner(serial):
    return [serial] + [""] * 7


def banner_fmt():
    return ["d-mmm"] + ["General"] * 7


def make_grid():
    """Made-up names in the real sheet's shape: back-to-back blocks, a header
    in the first two, a blank row instead of a header in the third, and the
    unlabeled column H holding an ad-hoc note."""
    values = [
        banner(SEP), HEADER,
        ["", "Alice", "(2500)+500", "Approved", SEP, "carried over", "August", ""],
        ["", "Bob", 1500, "Missed", "", "", "August", "500 Missed"],
        ["", "Chitra", "", "", "", "June", "", ""],
        banner(OCT), HEADER,
        ["", "Alice", "", "", "", "carried over", "SEPTEMBER", ""],
        ["", "Bob", 1500, "Approved", OCT, "", "SEPTEMBER", ""],
        ["", "Chitra", "", "", "", "June", "", ""],
        banner(NOV), BLANK,
        ["", "Alice", "", "", "", "", "", ""],
        ["", "Bob", "", "", "", "", "", ""],
    ]
    formats = [banner_fmt(), GEN, DATE_FMT, GEN, GEN,
               banner_fmt(), GEN, GEN, DATE_FMT, GEN,
               banner_fmt(), GEN, GEN, GEN]
    return Grid(values, formats)


def entry(name, **kw):
    e = {"name": name, "bonus": "1500", "status": "Approved",
         "status_date": date(2026, 11, 26), "notes": "", "for_month": 10}
    e.update(kw)
    return e


def test_parse_blocks():
    layout, blocks, records = ml.parse_blocks(make_grid())
    assert layout["extra"] == 8
    assert [b["id"] for b in blocks] == ["2026-09-26", "2026-10-26", "2026-11-26"]
    assert [b["text"] for b in blocks] == ["26-Sep", "26-Oct", "26-Nov"]
    assert [b["header_row"] for b in blocks] == [2, 7, None]
    assert [len(b["rows"]) for b in blocks] == [3, 3, 2]
    bob = ml.find_record(blocks[0], "bob")
    assert bob["amount"] == 1500 and bob["extra"] == "500 Missed"
    alice = ml.find_record(blocks[0], "Alice")
    assert alice["amount"] is None and alice["bonus"] == "(2500)+500"
    assert alice["status_date"] == date(2026, 9, 26)
    assert not ml.find_record(blocks[2], "Alice")["filled"]


def test_banner_text_follows_number_format():
    assert ml.banner_text(date(2026, 4, 1), "mmm-yy") == "Apr-26"
    assert ml.banner_text(date(2026, 10, 26), "d-mmm") == "26-Oct"


def test_fill_prefilled_row_writes_only_c_to_g_and_keeps_notes():
    grid = make_grid()
    ops, action = ml.plan_save(grid, "2026-11-26", entry("Alice"))
    assert action == "filled"
    assert len(ops) == 1 and ops[0]["row"] == 13 and ops[0]["col"] == 3
    out = apply_ops(grid, ops)
    assert out.row_values(13) == ["", "Alice", 1500, "Approved", date_to_serial(date(2026, 11, 26)),
                                  "", "OCTOBER", ""]
    assert out.fmt(13, 5) == "m/d/yyyy"
    assert out.n_rows == grid.n_rows


def test_blank_notes_keep_existing_notes():
    grid = make_grid()
    out = apply_ops(grid, ml.plan_save(grid, "2026-10-26", entry("Chitra"))[0])
    assert out.cell(10, 6) == "June"


def test_for_month_reuses_existing_spelling():
    grid = make_grid()
    out = apply_ops(grid, ml.plan_save(grid, "2026-11-26", entry("Bob", for_month=9))[0])
    assert out.cell(14, 7) == "SEPTEMBER"
    out = apply_ops(grid, ml.plan_save(grid, "2026-11-26", entry("Bob", for_month=8))[0])
    assert out.cell(14, 7) == "August"


def test_bonus_stays_number_or_text():
    assert ml.parse_bonus_input("1,500") == 1500
    assert ml.parse_bonus_input("(2500)+500") == "(2500)+500"
    assert ml.parse_bonus_input("") == ""


def test_new_employee_in_middle_block_is_inserted_before_next_banner():
    grid = make_grid()
    ops, action = ml.plan_save(grid, "2026-10-26", entry("Dev"))
    assert action == "added"
    assert ops[0] == {"op": "insert_rows", "row": 11, "count": 1}
    out = apply_ops(grid, ops)
    assert out.cell(11, 2) == "Dev"
    assert out.cell(12, 1) == NOV                 # Nov banner moved down intact
    _, blocks, _ = ml.parse_blocks(out)
    assert [len(b["rows"]) for b in blocks] == [3, 4, 2]


def test_new_employee_in_last_block_appends_without_insert():
    grid = make_grid()
    ops, _ = ml.plan_save(grid, "2026-11-26", entry("Dev"))
    assert [o["op"] for o in ops] == ["write"] and ops[0]["row"] == 15


def test_entry_in_banner_only_block_goes_right_under_banner():
    grid = apply_ops(make_grid(), [{"op": "write", "row": 15, "col": 1,
                                    "values": [[date_to_serial(date(2026, 12, 26))]], "formats": [["d-mmm"]]}])
    ops, _ = ml.plan_save(grid, "2026-12-26", entry("Alice"))
    out = apply_ops(grid, ops)
    assert out.cell(16, 2) == "Alice" and out.cell(15, 1) == date_to_serial(date(2026, 12, 26))


def test_new_block_copies_banner_header_and_roster_and_fills_the_entry():
    grid = make_grid()
    ops, action = ml.plan_save(grid, "new", entry("Bob", status_date=date(2026, 12, 26), for_month=11))
    assert action == "created"
    out = apply_ops(grid, ops)
    dec = date_to_serial(date(2026, 12, 26))
    assert out.row_values(15)[0] == dec and out.fmt(15, 1) == "d-mmm"
    assert {"op": "merge", "row": 15, "col": 1, "to_col": 6} in out.styles
    assert {"op": "fill", "row": 15, "col": 1, "to_col": 6, "color": "#FFFF00"} in out.styles
    assert out.row_values(16) == HEADER
    assert [out.cell(r, 2) for r in (17, 18)] == ["Alice", "Bob"]
    assert out.row_values(17)[2:] == ["", "", "", "", "", ""]          # names only
    assert out.row_values(18)[2:7] == [1500, "Approved", dec, "", "NOVEMBER"]
    _, blocks, _ = ml.parse_blocks(out)
    assert blocks[-1]["id"] == "2026-12-26" and blocks[-1]["header_row"] == 16


def test_new_block_adds_employee_not_in_previous_roster():
    grid = make_grid()
    out = apply_ops(grid, ml.plan_save(grid, "new", entry("Dev"))[0])
    assert [out.cell(r, 2) for r in (17, 18, 19)] == ["Alice", "Bob", "Dev"]


def test_next_block_date_handles_year_end():
    _, blocks, _ = ml.parse_blocks(make_grid())
    assert ml.next_block_date(blocks) == date(2026, 12, 26)
    assert ml.next_block_date([{"date": date(2026, 12, 26)}]) == date(2027, 1, 26)


def test_invalid_status_refused():
    with pytest.raises(ValueError):
        ml.plan_save(make_grid(), "2026-10-26", entry("Alice", status="Maybe"))


def test_edit_of_vanished_entry_refused():
    with pytest.raises(ValueError):
        ml.plan_save(make_grid(), "2026-10-26", entry("Nobody"), editing=True)


def test_clear_keeps_name_notes_and_extra_column():
    grid = make_grid()
    out = apply_ops(grid, ml.plan_clear(grid, "2026-09-26", "Bob"))
    assert out.row_values(4) == ["", "Bob", "", "", "", "", "", "500 Missed"]
    assert out.n_rows == grid.n_rows
    out = apply_ops(grid, ml.plan_clear(grid, "2026-09-26", "Alice"))
    assert out.cell(3, 6) == "carried over"


def test_block_summary():
    _, blocks, _ = ml.parse_blocks(make_grid())
    s = ml.block_summary(blocks[0])
    assert s["total_amount"] == 1500
    assert [r["name"] for r in s["non_numeric"]] == ["Alice"]
    assert (s["approved"], s["missed"], s["pending"]) == (1, 1, 1)


def test_default_block_is_latest_with_data():
    _, blocks, _ = ml.parse_blocks(make_grid())
    assert ml.default_block(blocks)["id"] == "2026-10-26"
