# The shared employee dropdown on every section's Add Entry page: one roster
# (employees.json) behind all of them, the /employees/add and /employees/delete
# routes returning to the section they were used from, and roster changes never
# touching a sheet. Uses the fake in-memory workbook from test_routes — no Graph.

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import logic
from test_routes import client  # noqa: F401  (pytest fixture)

SECTIONS = ["daily", "whatsapp", "monthly", "keyboard"]
SHEETS = [config.WHATSAPP_SHEET, config.MONTHLY_SHEET, config.KEYBOARD_SHEET]


def options(html):
    return re.findall(r'<li class="combo-option[^"]*"\s+data-name="([^"]+)"', html)


def hidden_name(html):
    return re.search(r'<input type="hidden" id="name"[^>]*value="([^"]*)"', html).group(1)


def snapshot(client):
    return {name: [list(r) for r in client.sheets[name].values] for name in SHEETS}


@pytest.mark.parametrize("slug", SECTIONS)
def test_every_add_page_has_the_same_dropdown(client, slug):
    html = client.get(f"/{slug}/add").get_data(as_text=True)
    assert 'id="nameCombo"' in html and 'id="nameSearch"' in html
    assert options(html) == ["Alice", "Bob", "Chitra"]          # the shared roster
    assert html.count('class="combo-remove') == 3                 # × per name
    assert 'id="newEmployee"' in html and 'id="addEmployeeBtn"' in html
    assert re.search(r'id="empAddForm"[^>]*action="/employees/add"', html)
    assert html.count(f'<input type="hidden" name="next" value="{slug}">') == 2
    assert "js/employee-combo.js" in html


@pytest.mark.parametrize("slug", ["monthly", "keyboard"])
def test_dropdown_lists_only_the_roster_not_sheet_names(client, slug):
    logic.save_employee_list(["Alice"])
    html = client.get(f"/{slug}/add").get_data(as_text=True)
    # Bob is in both sheets, but removed from the roster, so he isn't offered.
    assert options(html) == ["Alice"]


def test_name_field_posts_as_before(client):
    for slug in ("monthly", "keyboard"):
        html = client.get(f"/{slug}/add").get_data(as_text=True)
        assert re.search(r'<input type="hidden" id="name" name="name" value="">', html)
    # Employee Whatsapp's picker posts nothing: the form still posts first/last/mobile.
    html = client.get("/whatsapp/add").get_data(as_text=True)
    assert re.search(r'<input type="hidden" id="name"\s+value="">', html)
    assert 'name="first"' in html and 'name="last"' in html and 'name="mobile"' in html


@pytest.mark.parametrize("slug", SECTIONS)
def test_adding_a_name_returns_to_the_same_section_with_it_selected(client, slug):
    before = snapshot(client)
    response = client.post("/employees/add", data={"name": "Dev Das", "next": slug})
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/{slug}/add?name=Dev+Das")
    assert "Dev Das" in logic.load_employee_list()

    html = client.get(f"/{slug}/add?name=Dev+Das").get_data(as_text=True)
    assert "Dev Das" in options(html)
    assert hidden_name(html) == "Dev Das"
    # Preselecting a name is not an edit: no row is locked or targeted.
    assert 'name="editing" value="1"' not in html
    assert 'id="nameLocked"' not in html
    if slug == "whatsapp":
        assert 'name="orig_first" value=""' in html
    assert snapshot(client) == before                              # no sheet touched


def test_whatsapp_pick_after_add_fills_first_and_last_name(client):
    client.post("/employees/add", data={"name": "Esha Rani Iyer", "next": "whatsapp"})
    html = client.get("/whatsapp/add?name=Esha+Rani+Iyer").get_data(as_text=True)
    assert re.search(r'id="first" name="first" value="Esha"', html)
    assert re.search(r'id="last" name="last" value="Rani Iyer"', html)
    # Both stay ordinary editable fields.
    assert not re.search(r'id="first"[^>]*disabled', html)
    assert not re.search(r'id="last"[^>]*disabled', html)


@pytest.mark.parametrize("slug", SECTIONS)
def test_removing_a_name_updates_every_section_and_no_sheet(client, slug):
    before = snapshot(client)
    response = client.post("/employees/delete", data={"name": "Bob", "next": slug})
    assert response.headers["Location"].endswith(f"/{slug}/add")
    for other in SECTIONS:
        assert "Bob" not in options(client.get(f"/{other}/add").get_data(as_text=True))
    assert snapshot(client) == before


def test_unknown_next_falls_back_to_daily(client):
    response = client.post("/employees/add", data={"name": "Zed", "next": "https://evil.example"})
    assert response.headers["Location"].endswith("/daily/add?name=Zed")


def test_whatsapp_edit_keeps_a_removed_name_for_that_edit(client):
    logic.remove_employee_name("Alice")
    logic.save_employee_list(["Bob", "Chitra"])
    html = client.get("/whatsapp/add?first=Alice&last=Arora").get_data(as_text=True)
    assert "Alice Arora" in options(html)                        # shown for this edit
    assert hidden_name(html) == "Alice Arora"
    assert "Alice Arora" not in logic.load_employee_list()       # never written back


@pytest.mark.parametrize("url, expected", [
    ("/keyboard/add?name=Alice&period=2026-08", "Alice"),
    ("/monthly/add?block=2026-10-26&name=Bob", "Bob"),
])
def test_editing_a_removed_name_still_shows_it(client, url, expected):
    logic.save_employee_list(["Chitra"])
    html = client.get(url).get_data(as_text=True)
    assert re.search(r'id="nameLocked" value="%s" disabled' % expected, html)
    assert re.search(r'<input type="hidden" id="name" name="name" value="%s">' % expected, html)


def test_whatsapp_save_still_writes_the_same_row(client):
    client.post("/whatsapp/add", data={"first": "Chitra", "last": "Chand", "mobile": "7000000003"})
    assert client.sheets[config.WHATSAPP_SHEET].row_values(4) == ["Chitra", "Chand", 7000000003]


def test_roster_is_seeded_from_daily_when_missing(client):
    logic.EMPLOYEES_PATH.unlink()
    html = client.get("/keyboard/add").get_data(as_text=True)
    # The fake Daily Table1 has one row, for Alice.
    assert options(html) == ["Alice"]
    assert logic.load_employee_list() == ["Alice"]
