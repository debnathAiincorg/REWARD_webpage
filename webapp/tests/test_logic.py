from datetime import date

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import logic
from logic import (
    detect_columns,
    parse_date_value,
    to_number,
    rows_to_records,
    find_existing_row,
    week_bounds,
    totals_by_employee,
    next_index,
    distinct_employees,
    entries_for_date,
    filter_records,
)

HEADERS = ["Index", "Date", "Name", "Punctuality", "L&D", "Extra Hours",
           "Fluency Compliance", "Innovation", "Extraordinary Performance"]


def make_rows():
    return [
        {"index": 0, "values": [1, "2026-07-01", "Alice", 1, 1, 0, 0, 0, 0]},
        {"index": 1, "values": [2, "2026-07-01", "Bob", 1, 0, 0.5, 1, 0, 2]},
        {"index": 2, "values": [3, "2026-07-02", "Alice", 0, 1, 0, 1, 1, 0]},
    ]


def test_detect_columns():
    cols = detect_columns(HEADERS)
    assert cols["date_idx"] == 1
    assert cols["name_idx"] == 2
    assert cols["index_idx"] == 0
    assert cols["category_names"] == [
        "Punctuality", "L&D", "Extra Hours", "Fluency Compliance",
        "Innovation", "Extraordinary Performance",
    ]


def test_detect_columns_picks_up_new_column():
    cols = detect_columns(HEADERS + ["Team Spirit"])
    assert "Team Spirit" in cols["category_names"]


def test_detect_columns_separates_notes_as_text():
    cols = detect_columns(HEADERS + ["Notes"])
    assert "Notes" in cols["text_names"]
    assert "Notes" not in cols["category_names"]


def test_totals_by_employee_ignores_text_fields():
    headers = HEADERS + ["Notes"]
    rows = [{"index": 0, "values": [1, "2026-07-01", "Alice", 1, 1, 0, 0, 0, 0, "late"]}]
    records = rows_to_records(headers, rows)
    cols = detect_columns(headers)
    totals = totals_by_employee(
        records, date(2026, 7, 1), date(2026, 7, 1), cols["category_names"]
    )
    assert totals["Alice"]["points"] == 2


def test_parse_date_value_iso_string():
    assert parse_date_value("2026-07-01") == date(2026, 7, 1)


def test_parse_date_value_excel_serial():
    # Serial 46204 -> 2026-07-01 in Excel's 1900 date system.
    assert parse_date_value(46204) == date(2026, 7, 1)


def test_parse_date_value_none():
    assert parse_date_value(None) is None
    assert parse_date_value("") is None


def test_to_number_truncates_floats():
    assert to_number(0.5) == 0
    assert to_number(1.9) == 1
    assert to_number(None) == 0
    assert to_number("") == 0
    assert to_number("3") == 3


def test_rows_to_records():
    records = rows_to_records(HEADERS, make_rows())
    assert len(records) == 3
    assert records[0]["Name"] == "Alice"
    assert records[0]["Date"] == date(2026, 7, 1)
    assert records[0]["Punctuality"] == 1
    assert records[0]["_row_index"] == 0


def test_find_existing_row_match():
    records = rows_to_records(HEADERS, make_rows())
    idx = find_existing_row(records, "Alice", date(2026, 7, 2))
    assert idx == 2


def test_find_existing_row_no_match():
    records = rows_to_records(HEADERS, make_rows())
    assert find_existing_row(records, "Carol", date(2026, 7, 1)) is None


def test_week_bounds():
    monday, today = week_bounds(date(2026, 7, 8))  # a Wednesday
    assert monday == date(2026, 7, 6)
    assert today == date(2026, 7, 8)


def test_totals_by_employee():
    records = rows_to_records(HEADERS, make_rows())
    cols = detect_columns(HEADERS)
    totals = totals_by_employee(
        records, date(2026, 7, 1), date(2026, 7, 2), cols["category_names"]
    )
    assert totals["Alice"]["points"] == 5  # (1+1+0+0+0+0) + (0+1+0+1+1+0)
    assert totals["Alice"]["amount"] == 50
    assert totals["Bob"]["points"] == 4  # 1+0+0(truncated 0.5)+1+0+2
    assert totals["Bob"]["amount"] == 40


def test_totals_by_employee_excludes_out_of_range():
    records = rows_to_records(HEADERS, make_rows())
    cols = detect_columns(HEADERS)
    totals = totals_by_employee(
        records, date(2026, 7, 2), date(2026, 7, 2), cols["category_names"]
    )
    assert "Bob" not in totals
    assert totals["Alice"]["points"] == 3


def test_next_index():
    records = rows_to_records(HEADERS, make_rows())
    assert next_index(records) == 4


def test_next_index_empty_sheet():
    assert next_index([]) == 1


def test_distinct_employees():
    records = rows_to_records(HEADERS, make_rows())
    assert distinct_employees(records) == ["Alice", "Bob"]


def test_entries_for_date():
    records = rows_to_records(HEADERS, make_rows())
    todays = entries_for_date(records, date(2026, 7, 1))
    assert {r["Name"] for r in todays} == {"Alice", "Bob"}


def test_filter_records_by_employee():
    records = rows_to_records(HEADERS, make_rows())
    filtered = filter_records(records, employee="Alice")
    assert len(filtered) == 2
    assert all(r["Name"] == "Alice" for r in filtered)


def test_filter_records_by_date_range():
    records = rows_to_records(HEADERS, make_rows())
    filtered = filter_records(records, date_from=date(2026, 7, 2), date_to=date(2026, 7, 2))
    assert len(filtered) == 1
    assert filtered[0]["Name"] == "Alice"


# ---------------------------------------------------------------------------
# Employee master list (webapp/employees.json) — the Add Entry dropdown's
# source of truth. Deliberately independent of what's in the sheet, so a name
# can be retired from the dropdown without disturbing that person's past rows.
# ---------------------------------------------------------------------------

def _use_temp_employees(tmp_path, monkeypatch):
    """Point the employee list at a throwaway file so tests never touch the real one."""
    path = tmp_path / "employees.json"
    monkeypatch.setattr(logic, "EMPLOYEES_PATH", path)
    return path


def test_load_employee_list_missing_file_returns_empty(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    assert logic.load_employee_list() == []


def test_save_and_load_employee_list_round_trip(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Bob", "Alice"])
    assert logic.load_employee_list() == ["Alice", "Bob"]


def test_save_employee_list_sorts_and_dedupes(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Carol", "Alice", "Carol"])
    assert logic.load_employee_list() == ["Alice", "Carol"]


def test_load_employee_list_corrupt_file_returns_empty(tmp_path, monkeypatch):
    path = _use_temp_employees(tmp_path, monkeypatch)
    path.write_text("{not json", encoding="utf-8")
    assert logic.load_employee_list() == []


def test_add_employee_name_adds_and_sorts(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Bob"])
    assert logic.add_employee_name("Alice") == ("Alice", True)
    assert logic.load_employee_list() == ["Alice", "Bob"]


def test_add_employee_name_trims_whitespace(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    name, _ = logic.add_employee_name("  Alice Sharma  ")
    assert name == "Alice Sharma"
    assert logic.load_employee_list() == ["Alice Sharma"]


def test_add_employee_name_rejects_blank(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    assert logic.add_employee_name("   ") == (None, False)
    assert logic.load_employee_list() == []


def test_add_employee_name_duplicate_is_case_insensitive(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Alice Sharma"])
    # Returns the spelling already on file, so the route can just select it.
    assert logic.add_employee_name("alice sharma") == ("Alice Sharma", False)
    assert logic.load_employee_list() == ["Alice Sharma"]


def test_remove_employee_name(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Alice", "Bob"])
    logic.remove_employee_name("Alice")
    assert logic.load_employee_list() == ["Bob"]


def test_remove_employee_name_is_case_insensitive(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Alice"])
    logic.remove_employee_name("ALICE")
    assert logic.load_employee_list() == []


def test_remove_employee_name_unknown_is_noop(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Alice"])
    logic.remove_employee_name("Carol")
    assert logic.load_employee_list() == ["Alice"]


def test_seed_employee_list_seeds_when_file_missing(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.seed_employee_list_if_missing(rows_to_records(HEADERS, make_rows()))
    assert logic.load_employee_list() == ["Alice", "Bob"]


def test_seed_employee_list_does_not_reseed_emptied_list(tmp_path, monkeypatch):
    # The whole point of the x button: an emptied list is a deliberate state,
    # not a missing file. Re-seeding here would silently undo every removal.
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list([])
    logic.seed_employee_list_if_missing(rows_to_records(HEADERS, make_rows()))
    assert logic.load_employee_list() == []


def test_seed_employee_list_keeps_existing_file_untouched(tmp_path, monkeypatch):
    _use_temp_employees(tmp_path, monkeypatch)
    logic.save_employee_list(["Zoe"])
    logic.seed_employee_list_if_missing(rows_to_records(HEADERS, make_rows()))
    assert logic.load_employee_list() == ["Zoe"]


# ---------------------------------------------------------------------------
# Roster storage location. On a host with an ephemeral filesystem the roster
# has to live on a mounted volume, or every redeploy silently reverts each
# add/remove. EMPLOYEES_DATA_DIR is read once at import — the same moment it
# would be read on a real boot — so these tests reload the module to exercise
# it, then reload once more to leave the module as they found it.
# ---------------------------------------------------------------------------

def test_employees_path_honours_data_dir_env_var(tmp_path, monkeypatch):
    volume = tmp_path / "data"
    monkeypatch.setenv("EMPLOYEES_DATA_DIR", str(volume))
    try:
        importlib.reload(logic)
        assert logic.EMPLOYEES_PATH == volume / "employees.json"
    finally:
        monkeypatch.undo()
        importlib.reload(logic)


def test_save_and_load_employee_list_use_data_dir_env_var(tmp_path, monkeypatch):
    volume = tmp_path / "data"
    monkeypatch.setenv("EMPLOYEES_DATA_DIR", str(volume))
    try:
        importlib.reload(logic)
        logic.save_employee_list(["Bob", "Alice"])
        # Written to the volume, not next to logic.py — that's the whole point.
        assert (volume / "employees.json").exists()
        assert logic.load_employee_list() == ["Alice", "Bob"]
    finally:
        monkeypatch.undo()
        importlib.reload(logic)


def test_employees_path_defaults_beside_logic_when_env_var_unset(monkeypatch):
    monkeypatch.delenv("EMPLOYEES_DATA_DIR", raising=False)
    try:
        importlib.reload(logic)
        expected = Path(logic.__file__).resolve().parent / "employees.json"
        assert logic.EMPLOYEES_PATH == expected
    finally:
        monkeypatch.undo()
        importlib.reload(logic)


def test_save_employee_list_creates_missing_directory(tmp_path, monkeypatch):
    # A freshly mounted volume is an empty path that may not exist on first boot.
    target = tmp_path / "mnt" / "data" / "employees.json"
    monkeypatch.setattr(logic, "EMPLOYEES_PATH", target)
    logic.save_employee_list(["Alice"])
    assert target.exists()
    assert logic.load_employee_list() == ["Alice"]


# ---------------------------------------------------------------------------
# Dashboard KPIs. These take the roster as an argument rather than reading
# employees.json, so they stay pure and testable without touching disk.
# ---------------------------------------------------------------------------

MONDAY = date(2026, 7, 6)
WEDNESDAY = date(2026, 7, 8)   # "today"

CATEGORIES = ["Punctuality", "L&D", "Extra Hours", "Fluency Compliance",
              "Innovation", "Extraordinary Performance"]

DASH_ROSTER = ["Alice", "Bob", "Carol"]


def dash_records():
    """Alice works two days, Bob one, Carol is on the roster but never appears."""
    return rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-07", "Alice", 1, 1, 0, 0, 0, 0]},
        {"index": 1, "values": [2, "2026-07-08", "Alice", 0, 1, 0, 1, 1, 0]},
        {"index": 2, "values": [3, "2026-07-07", "Bob", 1, 0, 0.5, 1, 0, 2]},
    ])


def test_points_to_amount_constant():
    assert logic.POINTS_TO_AMOUNT == 10


def test_dashboard_kpis_counts_the_whole_roster():
    k = logic.dashboard_kpis(dash_records(), DASH_ROSTER, MONDAY, WEDNESDAY, CATEGORIES)
    assert k["total_employees"] == 3


def test_dashboard_kpis_weekly_points_and_amount():
    k = logic.dashboard_kpis(dash_records(), DASH_ROSTER, MONDAY, WEDNESDAY, CATEGORIES)
    assert k["weekly_points"] == 9   # Alice 2+3, Bob 4 (0.5 truncates to 0)
    assert k["weekly_amount"] == 90


def test_dashboard_kpis_zero_points_includes_employees_with_no_entries():
    k = logic.dashboard_kpis(dash_records(), DASH_ROSTER, MONDAY, WEDNESDAY, CATEGORIES)
    assert k["zero_point_employees"] == 1   # Carol never appears in the sheet at all


def test_dashboard_kpis_zero_points_includes_entries_totalling_zero():
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-07", "Alice", 0, 0, 0, 0, 0, 0]},
    ])
    k = logic.dashboard_kpis(records, ["Alice"], MONDAY, WEDNESDAY, CATEGORIES)
    assert k["zero_point_employees"] == 1


def test_dashboard_kpis_matches_roster_names_case_insensitively():
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-07", "alice", 1, 1, 0, 0, 0, 0]},
    ])
    k = logic.dashboard_kpis(records, ["Alice"], MONDAY, WEDNESDAY, CATEGORIES)
    assert k["zero_point_employees"] == 0
    assert k["weekly_points"] == 2


# ---------------------------------------------------------------------------
# Weekly Performance Report rows: previous-day and week-to-date figures side
# by side. Inclusion follows the week-to-date range only, matching what the
# Dashboard totals table already did before the extra columns were added.
# ---------------------------------------------------------------------------

PREV_DAY = date(2026, 7, 7)   # the Tuesday before WEDNESDAY


def test_weekly_report_rows_figures():
    rows = logic.weekly_report_rows(dash_records(), MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    alice = next(r for r in rows if r["name"] == "Alice")
    assert alice["prev_points"] == 2
    assert alice["prev_amount"] == 20
    assert alice["week_points"] == 5
    assert alice["week_amount"] == 50


def test_weekly_report_rows_sorted_by_previous_day_amount_desc():
    rows = logic.weekly_report_rows(dash_records(), MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert [r["name"] for r in rows] == ["Bob", "Alice"]


def test_weekly_report_rows_ties_break_on_name():
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-07", "Zoe", 1, 0, 0, 0, 0, 0]},
        {"index": 1, "values": [2, "2026-07-07", "Adam", 1, 0, 0, 0, 0, 0]},
    ])
    rows = logic.weekly_report_rows(records, MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert [r["name"] for r in rows] == ["Adam", "Zoe"]


def test_weekly_report_rows_includes_week_activity_with_no_previous_day_entry():
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-08", "Carol", 1, 1, 1, 0, 0, 0]},
    ])
    rows = logic.weekly_report_rows(records, MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert [r["name"] for r in rows] == ["Carol"]
    assert rows[0]["prev_points"] == 0
    assert rows[0]["prev_amount"] == 0
    assert rows[0]["week_points"] == 3


def test_weekly_report_rows_excludes_activity_outside_the_week():
    # A Sunday entry with a Monday-only window: outside week-to-date, so the
    # employee does not appear even though it is the previous day. This is the
    # existing inclusion rule, kept deliberately.
    sunday, monday = date(2026, 7, 5), date(2026, 7, 6)
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-05", "Alice", 1, 1, 0, 0, 0, 0]},
    ])
    rows = logic.weekly_report_rows(records, monday, monday, sunday, CATEGORIES)
    assert rows == []


def test_weekly_report_rows_excludes_employee_with_only_previous_week_entries():
    # Dave's only entry is from the week before [MONDAY, WEDNESDAY] — he must
    # not appear in this week's report at all, not even with zero totals.
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-01", "Dave", 1, 1, 0, 0, 0, 0]},
    ])
    rows = logic.weekly_report_rows(records, MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert rows == []
    assert "Dave" not in [r["name"] for r in rows]


def test_weekly_report_rows_keeps_employee_with_no_activity_since_early_in_week():
    # Eve's only entry is Monday; nothing since. She must still appear for the
    # rest of the week, with totals frozen at Monday's figures rather than
    # disappearing or resetting to zero on a quiet day.
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-06", "Eve", 1, 1, 0, 0, 0, 0]},
    ])
    rows = logic.weekly_report_rows(records, MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert [r["name"] for r in rows] == ["Eve"]
    assert rows[0]["week_points"] == 2
    assert rows[0]["week_amount"] == 20
    assert rows[0]["prev_points"] == 0   # nothing on Tuesday (PREV_DAY)


def test_weekly_report_rows_includes_employee_who_joins_mid_week():
    # Frank's first-ever entry is today (Wednesday) — he must appear starting
    # from that first entry, included in this week's report immediately.
    records = rows_to_records(HEADERS, [
        {"index": 0, "values": [1, "2026-07-08", "Frank", 1, 0, 0, 0, 0, 0]},
    ])
    rows = logic.weekly_report_rows(records, MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert [r["name"] for r in rows] == ["Frank"]
    assert rows[0]["week_points"] == 1
    assert rows[0]["week_amount"] == 10
    assert rows[0]["prev_points"] == 0   # nothing on Tuesday (PREV_DAY) either


def test_weekly_report_rows_amounts_are_points_times_constant():
    rows = logic.weekly_report_rows(dash_records(), MONDAY, WEDNESDAY, PREV_DAY, CATEGORIES)
    assert rows
    for r in rows:
        assert r["prev_amount"] == r["prev_points"] * logic.POINTS_TO_AMOUNT
        assert r["week_amount"] == r["week_points"] * logic.POINTS_TO_AMOUNT
