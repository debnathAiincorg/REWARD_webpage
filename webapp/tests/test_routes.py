# End-to-end route tests with Graph replaced by an in-memory workbook: every
# page renders, and every Add / Edit / Delete lands in the fake sheet with the
# layout the logic modules promise. No network calls.

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import config
import logic
import sheet_grid
from sheet_grid import Grid, date_to_serial

HDR_KB = ["Index", "Year", "Month", "Employee Name", "Accuracy Score", "Speed", "Comments"]
HDR_MB = ["Index", "Name", "Performance Bonus", "Status", "Status Date", "Notes", "For The Month of", ""]
OCT = date_to_serial(date(2026, 10, 26))


def fresh_sheets():
    return {
        config.WHATSAPP_SHEET: Grid([
            ["First_Name", "Last_Name", "Mobile_1"],
            ["Alice", "Arora", 9000000001],
            ["Bob", "Bose", ""],
        ]),
        config.KEYBOARD_SHEET: Grid(
            [HDR_KB, [""] * 7, [1, 2026, "AUGUST", "Alice", 0.97, "20 WPM", ""],
             [2, 2026, "AUGUST", "Bob", 0, 0, ""]],
            [["General"] * 7, ["General"] * 7,
             ["General"] * 4 + ["0%", "General", "General"], ["General"] * 4 + ["0%", "0%", "General"]],
        ),
        config.MONTHLY_SHEET: Grid(
            [[OCT] + [""] * 7, HDR_MB,
             ["", "Alice", 1500, "Approved", OCT, "", "SEPTEMBER", ""],
             ["", "Bob", "", "", "", "June", "", ""]],
            [["d-mmm"] + ["General"] * 7, ["General"] * 8,
             ["General"] * 4 + ["m/d/yyyy"] + ["General"] * 3, ["General"] * 8],
        ),
    }


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(logic, "EMPLOYEES_PATH", tmp_path / "employees.json")
    logic.save_employee_list(["Alice", "Bob", "Chitra"])

    sheets = fresh_sheets()

    def fake_get(name):
        return sheets[name]

    def fake_apply(name, ops):
        sheets[name] = sheet_grid.apply_ops(sheets[name], ops)

    from sections import common, keyboard, monthly, whatsapp, daily
    for mod in (common, keyboard, monthly, whatsapp):
        if hasattr(mod, "get_sheet_grid"):
            monkeypatch.setattr(mod, "get_sheet_grid", fake_get)
    monkeypatch.setattr(common, "apply_ops", fake_apply)

    table = {"headers": ["Index", "Date", "Name", "Punctuality", "Notes"],
             "rows": [{"index": 0, "values": [1, "2026-10-01", "Alice", 1, ""]}]}
    monkeypatch.setattr(daily, "get_table_columns", lambda: table["headers"])
    monkeypatch.setattr(daily, "get_table_rows", lambda: table["rows"])
    # The shared employee dropdown seeds the roster from Daily's sheet too.
    monkeypatch.setattr(common, "get_table_columns", lambda: table["headers"])
    monkeypatch.setattr(common, "get_table_rows", lambda: table["rows"])

    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        c.sheets = sheets
        yield c


@pytest.mark.parametrize("url", [
    "/", "/healthz",
    "/daily/dashboard", "/daily/add", "/daily/history",
    "/whatsapp/dashboard", "/whatsapp/add", "/whatsapp/history",
    "/keyboard/dashboard", "/keyboard/add", "/keyboard/history",
    "/monthly/dashboard", "/monthly/add", "/monthly/history",
    "/whatsapp/add?first=Alice&last=Arora",
    "/keyboard/add?name=Alice&period=2026-08",
    "/monthly/add?block=2026-10-26&name=Bob",
])
def test_every_page_renders(client, url):
    response = client.get(url)
    assert response.status_code == 200, response.data[:500]


def test_home_shows_four_sections(client):
    html = client.get("/").get_data(as_text=True)
    for title in ("Daily Performance Bonus", "Employee Whatsapp",
                  "Monthly Performance Bonus", "Keyboard Performance Status - M"):
        assert title in html


def test_section_name_and_nav_visible_inside_section(client):
    html = client.get("/keyboard/history").get_data(as_text=True)
    assert "Keyboard Performance Status - M" in html
    assert "/keyboard/dashboard" in html and "/keyboard/add" in html


@pytest.mark.parametrize("old, new", [
    ("/dashboard", "/daily/dashboard"),
    ("/add?date=2026-10-01&name=Alice", "/daily/add?date=2026-10-01&name=Alice"),
    ("/history?employee=Alice", "/daily/history?employee=Alice"),
])
def test_legacy_urls_redirect_to_daily(client, old, new):
    response = client.get(old)
    assert response.status_code == 302
    assert response.headers["Location"].endswith(new)


def test_legacy_delete_post_is_forwarded_with_307(client):
    response = client.post("/history/delete", data={"row_index": "0"})
    assert response.status_code == 307
    assert response.headers["Location"].endswith("/daily/history/delete")


def test_whatsapp_add_edit_delete(client):
    client.post("/whatsapp/add", data={"first": "Chitra", "last": "Chand", "mobile": "+91 70000 00003"})
    grid = client.sheets[config.WHATSAPP_SHEET]
    assert grid.row_values(4) == ["Chitra", "Chand", 7000000003]

    client.post("/whatsapp/add", data={"first": "Bob", "last": "Bose", "mobile": "8000000002",
                                       "orig_first": "Bob", "orig_last": "Bose"})
    assert client.sheets[config.WHATSAPP_SHEET].cell(3, 3) == 8000000002

    client.post("/whatsapp/history/delete", data={"first": "Alice", "last": "Arora"})
    grid = client.sheets[config.WHATSAPP_SHEET]
    assert [grid.cell(r, 1) for r in range(2, grid.n_rows + 1)] == ["Bob", "Chitra"]


def test_whatsapp_rejects_bad_number(client):
    response = client.post("/whatsapp/add", data={"first": "X", "last": "Y", "mobile": "123"},
                           follow_redirects=True)
    assert "valid 10-digit" in response.get_data(as_text=True)
    assert client.sheets[config.WHATSAPP_SHEET].n_rows == 3


def test_keyboard_add_new_month_then_delete(client):
    client.post("/keyboard/add", data={"name": "Chitra", "year": "2026", "month": "9",
                                       "accuracy": "98.5", "speed": "22"})
    grid = client.sheets[config.KEYBOARD_SHEET]
    assert grid.row_blank(5)
    assert grid.row_values(6) == [3, 2026, "SEPTEMBER", "Chitra", 0.985, "22 WPM", ""]
    assert grid.fmt(6, 5) == "0.00%"

    client.post("/keyboard/history/delete", data={"name": "Chitra", "entry_period": "2026-09"})
    assert client.sheets[config.KEYBOARD_SHEET].last_nonblank_row() == 4


def test_keyboard_edit_absent(client):
    client.post("/keyboard/add", data={"name": "Alice", "year": "2026", "month": "8",
                                       "absent": "1", "editing": "1"})
    grid = client.sheets[config.KEYBOARD_SHEET]
    assert grid.row_values(3)[4:6] == [0, 0] and grid.fmt(3, 6) == "0%"


def test_monthly_fill_prefilled_row_then_clear(client):
    client.post("/monthly/add", data={"block": "2026-10-26", "name": "Bob", "bonus": "1500",
                                      "status": "Pending", "status_date": "2026-10-26", "for_month": "9"})
    grid = client.sheets[config.MONTHLY_SHEET]
    assert grid.row_values(4) == ["", "Bob", 1500, "Pending", OCT, "June", "SEPTEMBER", ""]
    assert grid.n_rows == 4

    client.post("/monthly/history/delete", data={"name": "Bob", "entry_block": "2026-10-26"})
    assert client.sheets[config.MONTHLY_SHEET].row_values(4) == ["", "Bob", "", "", "", "June", "", ""]


def test_monthly_new_block(client):
    client.post("/monthly/add", data={"block": "new", "name": "Alice", "bonus": "1500",
                                      "status": "Approved", "status_date": "2026-11-26", "for_month": "10"})
    grid = client.sheets[config.MONTHLY_SHEET]
    assert grid.cell(5, 1) == date_to_serial(date(2026, 11, 26))
    assert grid.row_values(6) == HDR_MB
    assert [grid.cell(r, 2) for r in (7, 8)] == ["Alice", "Bob"]
    assert grid.cell(7, 7) == "OCTOBER" and grid.cell(8, 3) == ""
