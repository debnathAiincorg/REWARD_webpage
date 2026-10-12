import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import whatsapp_logic as wl
from sheet_grid import Grid, apply_ops

# Made-up contacts with the real sheet's shape: bold header, numbers stored as
# ints, and a trailing row holding a single stray space.
def make_grid():
    return Grid([
        ["First_Name", "Last_Name", "Mobile_1"],
        ["Alice", "Arora", 9000000001],
        ["Bob", "Bose", 8000000002],
        ["Chitra", "Chand", ""],
        ["Dev", "Das", 12345],
        [" ", "", ""],
    ])


def test_normalize_mobile():
    assert wl.normalize_mobile(9000000001) == "9000000001"
    assert wl.normalize_mobile(9000000001.0) == "9000000001"
    assert wl.normalize_mobile("+91 90000-00001") == "9000000001"
    assert wl.normalize_mobile("09000000001") == "9000000001"
    assert wl.normalize_mobile("919000000001") == "9000000001"
    assert wl.normalize_mobile("12345") is None
    assert wl.normalize_mobile("1234567890") is None  # Indian mobiles start 6-9
    assert wl.normalize_mobile("") is None


def test_parse_contacts_flags_missing_and_invalid_and_skips_stray_space_row():
    contacts = wl.parse_contacts(make_grid())
    assert [c["first_name"] for c in contacts] == ["Alice", "Bob", "Chitra", "Dev"]
    assert [c["status"] for c in contacts] == ["ok", "ok", "missing", "invalid"]
    assert contacts[0]["wa_link"] == "https://wa.me/919000000001"
    assert contacts[0]["mobile_raw"] == "9000000001"


def test_add_appends_after_last_contact_as_an_int():
    grid = make_grid()
    ops, action = wl.plan_save(grid, "Esha", "Iyer", "70000 00005")
    assert action == "added"
    out = apply_ops(grid, ops)
    # Row 6 held only a stray space; it becomes the new contact.
    assert out.row_values(6) == ["Esha", "Iyer", 7000000005]
    assert isinstance(out.cell(6, 3), int)
    assert out.n_rows == 6


def test_add_existing_name_updates_instead_of_duplicating():
    grid = make_grid()
    ops, action = wl.plan_save(grid, "alice", "ARORA", "9111111111")
    assert action == "updated"
    out = apply_ops(grid, ops)
    assert out.cell(2, 3) == 9111111111
    assert len(wl.parse_contacts(out)) == 4


def test_edit_can_fix_a_name_in_place():
    grid = make_grid()
    ops, action = wl.plan_save(grid, "Bobby", "Bose", "8000000002", original=("Bob", "Bose"))
    assert action == "updated"
    out = apply_ops(grid, ops)
    assert out.row_values(3) == ["Bobby", "Bose", 8000000002]


def test_edit_rename_into_another_contact_is_refused():
    with pytest.raises(ValueError):
        wl.plan_save(make_grid(), "Alice", "Arora", "8000000002", original=("Bob", "Bose"))


def test_invalid_mobile_is_refused():
    with pytest.raises(ValueError):
        wl.plan_save(make_grid(), "Esha", "Iyer", "12345")


def test_delete_removes_only_that_row():
    grid = make_grid()
    out = apply_ops(grid, wl.plan_delete(grid, "Bob", "Bose"))
    assert [c["first_name"] for c in wl.parse_contacts(out)] == ["Alice", "Chitra", "Dev"]


def test_delete_locates_by_key_not_cached_row():
    grid = make_grid()
    # Someone inserted a contact above Bob since the page loaded.
    grid = apply_ops(grid, [{"op": "insert_rows", "row": 2, "count": 1},
                            {"op": "write", "row": 2, "col": 1, "values": [["Zed", "Zee", 9999999999]], "formats": None}])
    out = apply_ops(grid, wl.plan_delete(grid, "Bob", "Bose"))
    names = [c["first_name"] for c in wl.parse_contacts(out)]
    assert "Bob" not in names and "Zed" in names and "Alice" in names


def test_dashboard_summary_lists_roster_names_without_contact():
    summary = wl.dashboard_summary(wl.parse_contacts(make_grid()), ["Alice Arora", "Farah Khan"])
    assert summary["total"] == 4
    assert summary["problem"] == 2
    assert summary["roster_missing"] == ["Farah Khan"]
