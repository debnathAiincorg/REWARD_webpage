# What each dashboard shows (period + strip text) on given dates, with made-up
# sheets that have the same STRUCTURE as the real workbook: Keyboard months
# May-September 2026; Monthly blocks Apr-26, May-26, 26-Jun ... 26-Dec, each
# "for" the month before its banner. Names and numbers are made up. No Graph.

import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import config
import logic
from sheet_grid import Grid, date_to_serial
from test_routes import client  # noqa: F401  (pytest fixture)

KB_HEADER = ["Index", "Year", "Month", "Employee Name", "Accuracy Score", "Speed", "Comments"]
MB_HEADER = ["Index", "Name", "Performance Bonus", "Status", "Status Date", "Notes", "For The Month of", ""]


def keyboard_sheet():
    """May-September 2026, one blank row between months, like the real sheet."""
    values, formats, index = [KB_HEADER, [""] * 7], [["General"] * 7] * 2, 1
    months = [("May", 0.95, "20 WPM"), ("June", 0.96, "21 WPM"), ("July", 0.97, "22 WPM"),
              ("AUGUST", 0.98, "24 WPM"), ("SEPTEMBER", 0.99, "26 WPM")]
    for i, (month, acc, speed) in enumerate(months):
        if i:
            values.append([""] * 7)
            formats.append(["General"] * 7)
        for name in ("Alice", "Bob"):
            values.append([index, 2026, month, name, acc, speed, ""])
            formats.append(["General"] * 4 + ["0%", "General", "General"])
            index += 1
    return Grid(values, formats)


# (banner date, banner format, "For The Month of", bonus per filled row)
BLOCKS = [
    (date(2026, 4, 1), "mmm-yy", "March", 1000), (date(2026, 5, 1), "mmm-yy", "April", 1000),
    (date(2026, 6, 26), "d-mmm", "May", 1000), (date(2026, 7, 26), "d-mmm", "June", 1500),
    (date(2026, 8, 26), "d-mmm", "July", 2000), (date(2026, 9, 26), "d-mmm", "August", 2500),
    (date(2026, 10, 26), "d-mmm", "SEPTEMBER", 3000),
    (date(2026, 11, 26), "d-mmm", "", 0),                    # pre-created: names only
    (date(2026, 12, 26), "d-mmm", None, 0),                  # banner only
]


def monthly_sheet():
    values, formats = [], []
    for d, fmt, for_month, bonus in BLOCKS:
        values.append([date_to_serial(d)] + [""] * 7)
        formats.append([fmt] + ["General"] * 7)
        if for_month is None:
            continue
        values.append(MB_HEADER)
        formats.append(["General"] * 8)
        for name in ("Alice", "Bob"):
            if for_month:
                values.append(["", name, bonus, "Approved", date_to_serial(d), "", for_month, ""])
            else:
                values.append(["", name, "", "", "", "", "", ""])
            formats.append(["General"] * 8)
    return Grid(values, formats)


def strip_text(html):
    m = re.search(r"<div[^>]*data-period-strip>(.*?)</div>", html, re.S)
    assert m, "no period strip"
    text = re.sub(r"<[^>]+>", " ", m.group(1))
    return " · ".join(part.strip() for part in re.split(r"\s{2,}", text) if part.strip())


@pytest.fixture
def at(client, monkeypatch):
    """at(today) -> {dashboard: strip text} with "today" fixed for all four."""
    from sections import daily, keyboard, monthly, whatsapp
    client.sheets[config.KEYBOARD_SHEET] = keyboard_sheet()
    client.sheets[config.MONTHLY_SHEET] = monthly_sheet()

    def run(today):
        for module in (daily, keyboard, monthly, whatsapp):
            monkeypatch.setattr(module, "_today", lambda today=today: today)
        return {slug: strip_text(client.get(f"/{slug}/dashboard").get_data(as_text=True))
                for slug in ("daily", "keyboard", "monthly", "whatsapp")}
    return run


# Exactly what each dashboard's strip says, per date (the table shown to the user).
CALENDAR = {
    date(2026, 10, 12): (  # Monday
        "Week #41 - Oct 05 to Oct 11 (Complete Week) · Previous day: · Sun, 11 Oct 2026 · data up to yesterday",
        "September 2026 · last completed month",
        "26-Sep block · Bonuses for: · August · latest block up to yesterday",
        "Contact list as of today · Mon, 12 Oct 2026 · live from the sheet"),
    date(2026, 10, 13): (  # Tuesday
        "Week #42 - Oct 12 · Previous day: · Mon, 12 Oct 2026 · data up to yesterday",
        "September 2026 · last completed month",
        "26-Sep block · Bonuses for: · August · latest block up to yesterday",
        "Contact list as of today · Tue, 13 Oct 2026 · live from the sheet"),
    date(2026, 10, 25): (  # Sunday
        "Week #43 - Oct 19 to Oct 24 (Complete Week) · Previous day: · Sat, 24 Oct 2026 · data up to yesterday",
        "September 2026 · last completed month",
        "26-Sep block · Bonuses for: · August · latest block up to yesterday",
        "Contact list as of today · Sun, 25 Oct 2026 · live from the sheet"),
    date(2026, 10, 26): (  # Monday — the 26-Oct banner's own day: not yet "passed"
        "Week #43 - Oct 19 to Oct 25 (Complete Week) · Previous day: · Sun, 25 Oct 2026 · data up to yesterday",
        "September 2026 · last completed month",
        "26-Sep block · Bonuses for: · August · latest block up to yesterday",
        "Contact list as of today · Mon, 26 Oct 2026 · live from the sheet"),
    date(2026, 10, 27): (  # Tuesday
        "Week #44 - Oct 26 · Previous day: · Mon, 26 Oct 2026 · data up to yesterday",
        "September 2026 · last completed month",
        "26-Oct block · Bonuses for: · September · latest block up to yesterday",
        "Contact list as of today · Tue, 27 Oct 2026 · live from the sheet"),
    date(2026, 10, 31): (  # Saturday
        "Week #44 - Oct 26 to Oct 30 · Previous day: · Fri, 30 Oct 2026 · data up to yesterday",
        "September 2026 · last completed month",
        "26-Oct block · Bonuses for: · September · latest block up to yesterday",
        "Contact list as of today · Sat, 31 Oct 2026 · live from the sheet"),
    date(2026, 11, 1): (   # Sunday — October has ended but has no Keyboard rows yet
        "Week #44 - Oct 26 to Oct 31 (Complete Week) · Previous day: · Sat, 31 Oct 2026 · data up to yesterday",
        "September 2026 · latest completed month in the sheet · no rows for October 2026 yet",
        "26-Oct block · Bonuses for: · September · latest block up to yesterday",
        "Contact list as of today · Sun, 01 Nov 2026 · live from the sheet"),
}


@pytest.mark.parametrize("today", list(CALENDAR))
def test_calendar(at, today):
    got = at(today)
    daily, keyboard, monthly, whatsapp = CALENDAR[today]
    assert got["daily"] == daily
    assert got["keyboard"] == keyboard
    assert got["monthly"] == monthly
    assert got["whatsapp"] == whatsapp


@pytest.mark.parametrize("today", list(CALENDAR))
def test_daily_period_ends_yesterday(today):
    period = logic.report_period(today)
    assert period["end"] < today and period["prev_day"] == period["breakdown_day"]


def test_previous_period_figures(client, monkeypatch):
    from sections import keyboard, monthly
    client.sheets[config.KEYBOARD_SHEET] = keyboard_sheet()
    client.sheets[config.MONTHLY_SHEET] = monthly_sheet()
    monkeypatch.setattr(keyboard, "_today", lambda: date(2026, 10, 13))
    monkeypatch.setattr(monthly, "_today", lambda: date(2026, 10, 13))
    html = client.get("/keyboard/dashboard").get_data(as_text=True)
    assert "99.00%" in html and "August 2026: 98.00%" in html          # September vs August
    assert "26.0 WPM" in html and "August 2026: 24.0 WPM" in html
    html = client.get("/monthly/dashboard").get_data(as_text=True)
    assert "₹5,000" in html and "26-Aug block: ₹4,000" in html          # 26-Sep vs 26-Aug
    html = client.get("/monthly/dashboard?block=2026-04-01").get_data(as_text=True)
    assert "No earlier block" in html


def test_manual_choice_says_so_and_links_back(client, monkeypatch):
    from sections import keyboard, monthly
    client.sheets[config.KEYBOARD_SHEET] = keyboard_sheet()
    client.sheets[config.MONTHLY_SHEET] = monthly_sheet()
    monkeypatch.setattr(keyboard, "_today", lambda: date(2026, 10, 13))
    monkeypatch.setattr(monthly, "_today", lambda: date(2026, 10, 13))
    kb = strip_text(client.get("/keyboard/dashboard?period=2026-06").get_data(as_text=True))
    assert kb == "June 2026 · Chosen manually · Back to last completed month (September 2026)"
    mb = strip_text(client.get("/monthly/dashboard?block=2026-11-26").get_data(as_text=True))
    assert mb == "26-Nov block · Bonuses for: · October · Chosen manually · Back to latest block up to yesterday (26-Sep)"
    # The link goes back to the default view (no ?period= / ?block=).
    html = client.get("/keyboard/dashboard?period=2026-06").get_data(as_text=True)
    assert re.search(r'<a href="/keyboard/dashboard" class="[^"]*">\s*<i data-lucide="rotate-ccw"', html)
