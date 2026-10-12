import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import keyboard_logic as kl
from sheet_grid import Grid, apply_ops

HEADER = ["Index", "Year", "Month", "Employee Name", "Accuracy Score", "Speed", "Comments"]
BLANK = [""] * 7
GEN = ["General"] * 7


def fmt(acc="0%", speed="General"):
    return ["General", "General", "General", "General", acc, speed, "General"]


def make_grid():
    """Same shape as the real sheet: header, blank, May group, blank, June
    group (title-case months, gaps in Index), blank, AUGUST (upper case)."""
    values = [
        HEADER, BLANK,
        [1, 2026, "May", "Alice", 0.97, "18 WPM", ""],
        [2, 2026, "May", "Bob", 0.9925, "38.2 WPM", ""],
        [3, 2026, "May", "Chitra", 0, 0, ""],
        BLANK,
        [12, 2026, "June", "Alice", 0.98, "17WPM", ""],
        [13, 2026, "June", "Bob", 0.96, "21 WPM", ""],
        BLANK,
        [42, 2026, "AUGUST", "Alice", 0.98, "25 WPM", ""],
    ]
    formats = [GEN, GEN, fmt(), fmt("0.00%"), fmt("0%", "0%"), GEN, fmt(), fmt(), GEN, fmt()]
    return Grid(values, formats)


def names_by_row(grid):
    return [(grid.cell(r, 3), grid.cell(r, 4)) for r in range(1, grid.n_rows + 1)]


def entry(name, month, **kw):
    e = {"name": name, "year": 2026, "month_num": month, "absent": False,
         "accuracy_pct": 98, "speed_wpm": 20, "comments": ""}
    e.update(kw)
    return e


def test_parse_groups_and_values():
    records, groups = kl.parse_rows(make_grid())
    assert [(g["month_num"], g["first_row"], g["last_row"]) for g in groups] == [(5, 3, 5), (6, 7, 8), (8, 10, 10)]
    bob = kl.find_record(records, "bob", 2026, 5)
    assert bob["accuracy"] == 0.9925 and bob["speed"] == 38.2
    assert kl.find_record(records, "Alice", 2026, 6)["speed"] == 17.0
    assert kl.find_record(records, "Chitra", 2026, 5)["absent"]
    assert kl.find_record(records, "Alice", 2026, 8)["month_label"] == "AUGUST"


def test_parse_inherits_year_month_on_rows_that_leave_them_blank():
    grid = Grid([HEADER, BLANK, [1, 2026, "May", "Alice", 0.9, "1 WPM", ""], ["", "", "", "Bob", 0.9, "1 WPM", ""]])
    records, groups = kl.parse_rows(grid)
    assert len(groups) == 1 and records[1]["month_num"] == 5 and records[1]["year"] == 2026


def test_accuracy_format_and_speed_helpers():
    assert kl.accuracy_format(0.97) == "0%"
    assert kl.accuracy_format(0.9847) == "0.00%"
    assert kl.format_speed(38.2) == "38.2 WPM"
    assert kl.format_speed(18.0) == "18 WPM"
    assert kl.parse_speed("17WPM") == 17.0


def test_add_to_existing_month_goes_at_end_of_its_group_before_separator():
    grid = make_grid()
    ops, action = kl.plan_save(grid, entry("Dev", 5, accuracy_pct=98.47, speed_wpm=22.5))
    assert action == "added"
    assert ops[0] == {"op": "insert_rows", "row": 6, "count": 1}
    out = apply_ops(grid, ops)
    assert out.row_values(6) == [43, 2026, "May", "Dev", 0.9847, "22.5 WPM", ""]
    assert out.fmt(6, 5) == "0.00%"
    assert out.row_blank(7)                      # separator kept
    assert out.cell(8, 3) == "June"              # June group untouched, just shifted
    _, groups = kl.parse_rows(out)
    assert [len(g["rows"]) for g in groups] == [4, 2, 1]


def test_add_to_last_month_appends_without_insert():
    grid = make_grid()
    ops, _ = kl.plan_save(grid, entry("Bob", 8))
    assert [o["op"] for o in ops] == ["write"]
    assert ops[0]["row"] == 11
    assert apply_ops(grid, ops).cell(11, 3) == "AUGUST"   # group's own spelling


def test_new_month_starts_new_group_after_one_blank_row_in_upper_case():
    grid = make_grid()
    ops, _ = kl.plan_save(grid, entry("Alice", 9))
    out = apply_ops(grid, ops)
    assert out.row_blank(11)
    assert out.row_values(12)[:4] == [43, 2026, "SEPTEMBER", "Alice"]
    _, groups = kl.parse_rows(out)
    assert [g["month_num"] for g in groups] == [5, 6, 8, 9]


def test_first_group_in_empty_sheet_leaves_blank_row_under_header():
    grid = Grid([HEADER])
    out = apply_ops(grid, kl.plan_save(grid, entry("Alice", 5))[0])
    assert out.row_blank(2)
    assert out.row_values(3)[:4] == [1, 2026, "MAY", "Alice"]


def test_earlier_missing_month_is_refused():
    with pytest.raises(ValueError):
        kl.plan_save(make_grid(), entry("Alice", 7))


def test_existing_entry_is_updated_in_place_keeping_index_and_spelling():
    grid = make_grid()
    ops, action = kl.plan_save(grid, entry("alice", 6, accuracy_pct=99.5, speed_wpm=30), editing=True)
    assert action == "updated"
    out = apply_ops(grid, ops)
    assert out.row_values(7) == [12, 2026, "June", "Alice", 0.995, "30 WPM", ""]
    assert out.fmt(7, 5) == "0.00%"
    assert out.n_rows == grid.n_rows


def test_absent_writes_zero_accuracy_and_numeric_zero_speed_like_the_sheet():
    grid = make_grid()
    out = apply_ops(grid, kl.plan_save(grid, entry("Bob", 6, absent=True), editing=True)[0])
    assert out.cell(8, 5) == 0 and out.cell(8, 6) == 0
    assert out.fmt(8, 5) == "0%" and out.fmt(8, 6) == "0%"


def test_new_index_is_max_plus_one_and_never_renumbers():
    grid = make_grid()
    out = apply_ops(grid, kl.plan_save(grid, entry("Dev", 6))[0])
    assert [out.cell(r, 1) for r in range(3, 13) if out.cell(r, 1) != ""] == [1, 2, 3, 12, 13, 43, 42]


def test_delete_row_inside_group():
    grid = make_grid()
    out = apply_ops(grid, kl.plan_delete(grid, "Bob", 2026, 5))
    _, groups = kl.parse_rows(out)
    assert [len(g["rows"]) for g in groups] == [2, 2, 1]
    assert out.row_blank(5)


def test_delete_last_row_of_last_group_also_drops_its_separator():
    grid = make_grid()
    out = apply_ops(grid, kl.plan_delete(grid, "Alice", 2026, 8))
    assert out.last_nonblank_row() == 8
    # Adding a new month afterwards still lands one blank row below June.
    out2 = apply_ops(out, kl.plan_save(out, entry("Alice", 9))[0])
    assert out2.row_blank(9) and out2.cell(10, 3) == "SEPTEMBER"


def test_delete_only_row_of_middle_group_keeps_single_gaps():
    grid = make_grid()
    grid = apply_ops(grid, kl.plan_delete(grid, "Bob", 2026, 6))
    out = apply_ops(grid, kl.plan_delete(grid, "Alice", 2026, 6))
    assert names_by_row(out)[4:7] == [("May", "Chitra"), ("", ""), ("AUGUST", "Alice")]
    blank_runs = [r for r in range(2, out.n_rows) if out.row_blank(r) and out.row_blank(r + 1)]
    assert blank_runs == []


def test_delete_missing_entry_raises():
    with pytest.raises(ValueError):
        kl.plan_delete(make_grid(), "Nobody", 2026, 5)


def test_month_summary_excludes_absent_from_averages():
    records, _ = kl.parse_rows(make_grid())
    s = kl.month_summary(records, 2026, 5)
    assert s["count"] == 3
    assert round(s["avg_accuracy"], 4) == round((0.97 + 0.9925) / 2, 4)
    assert s["avg_speed"] == pytest.approx((18 + 38.2) / 2)
    assert s["top"]["name"] == "Bob"
    assert [r["name"] for r in s["zero"]] == ["Chitra"]


def test_comparison_table():
    records, groups = kl.parse_rows(make_grid())
    names, table = kl.comparison_table(records, kl.periods(groups))
    assert names == ["Alice", "Bob", "Chitra"]
    assert set(table["Alice"]) == {(2026, 5), (2026, 6), (2026, 8)}
