# Roster-based dashboard figures on Keyboard, Monthly and Employee Whatsapp,
# following Daily's rule: headcounts come from the shared roster
# (employees.json); adding a name counts them as "missing" until they have an
# entry; removing a name drops them from those figures while their sheet rows
# still show in the tables and History. Fake data only — no Graph.

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import keyboard_logic as kl
import logic
import monthly_logic as ml
import whatsapp_logic as wl
from test_keyboard_logic import make_grid as keyboard_grid
from test_monthly_logic import make_grid as monthly_grid
from test_routes import client  # noqa: F401  (pytest fixture)
from test_whatsapp_logic import make_grid as whatsapp_grid


def kpi(html, label):
    """The value shown in the KPI tile with this label."""
    m = re.search(re.escape(label) + r'</span>\s*</div>\s*<div class="kpi-value[^"]*" data-countup>([^<]*)</div>', html)
    assert m, f"KPI {label!r} not found"
    return m.group(1).strip()


def chips(html, title):
    """Names listed in the amber name-list card with this title."""
    m = re.search(re.escape(title) + r".*?<ul[^>]*>(.*?)</ul>", html, re.S)
    return re.findall(r"<li[^>]*>([^<]+)</li>", m.group(1)) if m else []


# --- Pure logic ---------------------------------------------------------------

def test_keyboard_roster_kpis_count_roster_not_sheet_and_ignore_case():
    records, _ = kl.parse_rows(keyboard_grid())
    # August has only Alice. Roster spellings differ in case.
    figures = kl.roster_kpis(records, ["ALICE", "bob", "Dev"], 2026, 8)
    assert figures["total_employees"] == 3
    assert figures["not_tested"] == ["bob", "Dev"]


def test_keyboard_absent_row_counts_as_tested():
    records, _ = kl.parse_rows(keyboard_grid())
    # Chitra has a 0% (absent) row in May: that's a row, so not "not tested".
    assert "Chitra" not in kl.roster_kpis(records, ["Chitra"], 2026, 5)["not_tested"]


def test_monthly_no_entry_includes_missing_and_empty_rows():
    _, blocks, _ = ml.parse_blocks(monthly_grid())
    oct_block = blocks[1]   # Alice filled, Bob filled, Chitra pre-filled only
    figures = ml.roster_kpis(oct_block, ["alice", "Chitra", "Dev"])
    assert figures["total_employees"] == 3
    assert figures["no_entry"] == ["Chitra", "Dev"]


def test_whatsapp_total_employees_from_roster():
    summary = wl.dashboard_summary(wl.parse_contacts(whatsapp_grid()), ["alice arora", "Farah Khan"])
    assert summary["total_employees"] == 2
    assert summary["total"] == 4                       # contacts still from the sheet
    assert summary["roster_missing"] == ["Farah Khan"]


# --- Through the app: add a name, then remove it -----------------------------
# The test_routes fixture roster is Alice, Bob, Chitra.

def test_keyboard_dashboard_add_then_remove(client):
    url = "/keyboard/dashboard?period=2026-08"         # August: Alice tested, Bob absent (0%)
    html = client.get(url).get_data(as_text=True)
    assert kpi(html, "Total employees") == "3"
    assert kpi(html, "Not tested this month") == "1"
    assert chips(html, "Not tested in August 2026") == ["Chitra"]

    client.post("/employees/add", data={"name": "Dev", "next": "keyboard"})
    html = client.get(url).get_data(as_text=True)
    assert kpi(html, "Total employees") == "4"
    assert kpi(html, "Not tested this month") == "2"
    assert chips(html, "Not tested in August 2026") == ["Chitra", "Dev"]

    client.post("/employees/delete", data={"name": "Bob", "next": "keyboard"})
    html = client.get(url).get_data(as_text=True)
    assert kpi(html, "Total employees") == "3"
    assert kpi(html, "Employees at 0%") == "1"          # sheet figure: Bob's row still counts
    assert ">Bob<" in html                               # and still shows in the table
    assert ">Bob<" in client.get("/keyboard/history").get_data(as_text=True)


def test_monthly_dashboard_add_then_remove(client):
    url = "/monthly/dashboard?block=2026-10-26"         # Alice filled, Bob pre-filled only
    html = client.get(url).get_data(as_text=True)
    assert kpi(html, "Total employees") == "3"
    assert chips(html, "No bonus entry in block 26-Oct") == ["Bob", "Chitra"]

    client.post("/employees/add", data={"name": "Dev", "next": "monthly"})
    html = client.get(url).get_data(as_text=True)
    assert kpi(html, "Total employees") == "4"
    assert kpi(html, "No bonus entry in this block") == "3"
    assert chips(html, "No bonus entry in block 26-Oct") == ["Bob", "Chitra", "Dev"]

    client.post("/employees/delete", data={"name": "Bob", "next": "monthly"})
    html = client.get(url).get_data(as_text=True)
    assert kpi(html, "Total employees") == "3"
    assert chips(html, "No bonus entry in block 26-Oct") == ["Chitra", "Dev"]
    assert ">Bob<" in html or "Bob\n" in html            # his row is still in the block table
    assert "Bob" in client.get("/monthly/history").get_data(as_text=True)
    assert client.sheets[config.MONTHLY_SHEET].cell(4, 2) == "Bob"   # sheet untouched


def test_whatsapp_dashboard_add_then_remove(client):
    logic.save_employee_list(["Alice Arora", "Bob Bose"])
    html = client.get("/whatsapp/dashboard").get_data(as_text=True)
    assert kpi(html, "Total employees") == "2"
    assert kpi(html, "Employees without a contact") == "0"

    client.post("/employees/add", data={"name": "Farah Khan", "next": "whatsapp"})
    html = client.get("/whatsapp/dashboard").get_data(as_text=True)
    assert kpi(html, "Total employees") == "3"
    assert kpi(html, "Employees without a contact") == "1"
    assert "Farah Khan" in html

    client.post("/employees/delete", data={"name": "Bob Bose", "next": "whatsapp"})
    html = client.get("/whatsapp/dashboard").get_data(as_text=True)
    assert kpi(html, "Total employees") == "2"
    assert kpi(html, "Total contacts") == "2"            # sheet figure unchanged
    assert "Bob Bose" in html                             # still in the contact list
    assert client.sheets[config.WHATSAPP_SHEET].cell(3, 1) == "Bob"


def test_roster_changes_never_touch_a_sheet(client):
    before = {n: [list(r) for r in client.sheets[n].values]
              for n in (config.WHATSAPP_SHEET, config.MONTHLY_SHEET, config.KEYBOARD_SHEET)}
    for slug in ("keyboard", "monthly", "whatsapp"):
        client.post("/employees/add", data={"name": "Zed Zee", "next": slug})
        client.post("/employees/delete", data={"name": "Zed Zee", "next": slug})
    after = {n: [list(r) for r in client.sheets[n].values] for n in before}
    assert after == before
