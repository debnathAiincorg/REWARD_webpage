from datetime import date

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

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
