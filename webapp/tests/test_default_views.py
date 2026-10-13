# Which month / block the Keyboard and Monthly dashboards open on:
#   Keyboard: the last COMPLETED month (before the current calendar month).
#   Monthly:  the latest block whose banner date is TODAY OR EARLIER.
# Any month / block can still be picked, and an explicit ?period= / ?block=
# always wins. Fake data only — no Graph.

import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import keyboard_logic as kl
import monthly_logic as ml
from test_keyboard_logic import make_grid as keyboard_grid     # May, June, AUGUST 2026
from test_monthly_logic import make_grid as monthly_grid       # 26-Sep, 26-Oct, 26-Nov 2026
from test_routes import client  # noqa: F401  (pytest fixture)


# --- Keyboard: last completed month -------------------------------------------

PERIODS = [(2026, 5), (2026, 6), (2026, 8)]


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 13), (2026, 8)),    # September isn't in the sheet: latest completed month present
    (date(2026, 9, 3), (2026, 8)),      # August just completed
    (date(2026, 8, 20), (2026, 6)),     # August is still in progress -> not "completed"
    (date(2026, 8, 1), (2026, 6)),
    (date(2026, 7, 15), (2026, 6)),
    (date(2026, 5, 10), (2026, 8)),     # nothing completed yet -> fall back to the latest month
])
def test_keyboard_default_period(today, expected):
    assert kl.default_period(PERIODS, today) == expected


def test_keyboard_default_prefers_the_previous_month_when_present():
    assert kl.default_period([(2026, 5), (2026, 6), (2026, 9)], date(2026, 10, 13)) == (2026, 9)


def test_keyboard_default_across_the_year_boundary():
    assert kl.default_period([(2025, 11), (2025, 12), (2026, 1)], date(2026, 1, 5)) == (2025, 12)


def test_keyboard_default_with_no_months():
    assert kl.default_period([], date(2026, 10, 13)) is None


def test_keyboard_dashboard_opens_on_last_completed_month(client, monkeypatch):
    from sections import keyboard
    client.sheets[config.KEYBOARD_SHEET] = keyboard_grid()
    monkeypatch.setattr(keyboard, "_today", lambda: date(2026, 8, 20))     # mid-August
    html = client.get("/keyboard/dashboard").get_data(as_text=True)
    assert '<option value="2026-06" selected>' in html
    # The period strip names the month and why (the note it replaced said
    # "Opens on the last completed month").
    # The fake sheet has no July, so the strip says so instead of claiming June
    # is the last completed month.
    assert "latest completed month in the sheet · no rows for July 2026 yet" in html
    assert "Chosen manually" not in html
    assert "June 2026" in html


def test_keyboard_explicit_period_wins_and_hides_the_note(client, monkeypatch):
    from sections import keyboard
    client.sheets[config.KEYBOARD_SHEET] = keyboard_grid()
    monkeypatch.setattr(keyboard, "_today", lambda: date(2026, 8, 20))
    html = client.get("/keyboard/dashboard?period=2026-08").get_data(as_text=True)
    assert '<option value="2026-08" selected>' in html
    assert "Chosen manually" in html
    assert "Back to last completed month (June 2026)" in html


def test_keyboard_unknown_period_falls_back_to_the_default(client, monkeypatch):
    from sections import keyboard
    client.sheets[config.KEYBOARD_SHEET] = keyboard_grid()
    monkeypatch.setattr(keyboard, "_today", lambda: date(2026, 10, 13))
    html = client.get("/keyboard/dashboard?period=1999-01").get_data(as_text=True)
    assert '<option value="2026-08" selected>' in html


# --- Monthly: latest block dated today or earlier ---------------------------------

def _blocks():
    return ml.parse_blocks(monthly_grid())[1]


@pytest.mark.parametrize("today, expected", [
    (date(2026, 10, 13), "2026-09-26"),   # 26-Oct hasn't happened yet
    (date(2026, 10, 25), "2026-09-26"),   # the day before the 26-Oct banner
    (date(2026, 10, 26), "2026-10-26"),   # switches on the banner day itself
    (date(2026, 10, 27), "2026-10-26"),
    (date(2026, 11, 25), "2026-10-26"),   # 26-Nov is pre-created but still ahead
    (date(2026, 12, 1), "2026-11-26"),
])
def test_monthly_report_block(today, expected):
    assert ml.report_block(_blocks(), today)["id"] == expected


def test_monthly_report_block_falls_back_when_no_date_has_passed():
    blocks = _blocks()
    chosen = ml.report_block(blocks, date(2026, 9, 1))
    assert chosen["id"] == ml.default_block(blocks)["id"] == "2026-10-26"


def test_monthly_report_block_with_no_blocks():
    assert ml.report_block([], date(2026, 10, 13)) is None


def test_monthly_dashboard_opens_on_latest_passed_block(client, monkeypatch):
    from sections import monthly
    client.sheets[config.MONTHLY_SHEET] = monthly_grid()
    monkeypatch.setattr(monthly, "_today", lambda: date(2026, 10, 13))
    html = client.get("/monthly/dashboard").get_data(as_text=True)
    assert '<option value="2026-09-26" selected>' in html
    assert "Block 26-Sep" in html
    assert "latest block up to today" in html and "Chosen manually" not in html


def test_monthly_explicit_block_wins_and_hides_the_note(client, monkeypatch):
    from sections import monthly
    client.sheets[config.MONTHLY_SHEET] = monthly_grid()
    monkeypatch.setattr(monthly, "_today", lambda: date(2026, 10, 13))
    html = client.get("/monthly/dashboard?block=2026-11-26").get_data(as_text=True)
    assert '<option value="2026-11-26" selected>' in html
    assert "Chosen manually" in html
    assert "Back to latest block up to today (26-Sep)" in html


# --- WhatsApp is deliberately unchanged ------------------------------------------

def test_whatsapp_dashboard_has_no_period_choice(client):
    html = client.get("/whatsapp/dashboard").get_data(as_text=True)
    assert "Contact list as of today" in html and "Chosen manually" not in html
