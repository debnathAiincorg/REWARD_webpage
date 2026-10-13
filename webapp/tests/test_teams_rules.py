# The Daily dashboard must show exactly what the Teams weekly report showed
# (weekly_report_send_teams.py, get_cumulative_data — removed from this repo in
# commit 06f7eda; transcribed below as `teams_report`). "Today" is fixed to a
# Monday, Tuesday, Wednesday and Sunday. Made-up data only — no Graph.
#
# Two deliberate differences, chosen by the user:
#  1. The script listed every name in the sheet in the Weekly Performance
#     Report (0s for people with nothing in the week); the dashboard lists only
#     names with a row inside the range. Totals are the same either way.
#  2. "Previous Day" always means yesterday. The script used Saturday for the
#     weekly table on Mondays; the dashboard uses Sunday (0 / Rs 0 when the
#     sheet has no Sunday rows).

import re
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import logic
from test_routes import client  # noqa: F401  (pytest fixture)

HEADERS = ["Index", "Date", "Name", "Punctuality", "L&D", "Extra Hours",
           "Fluency Compliance", "Innovation", "Extraordinary Performance"]
CATEGORIES = HEADERS[3:]

# Oct 2026: Mon 5, Sat 10, Sun 11, Mon 12, Tue 13, Wed 14, Sat 17, Sun 18.
ROWS = [
    ("2026-09-28", "Farah",  [1, 1, 0, 0, 0, 0]),    # only in an older week
    ("2026-10-05", "Alice",  [1, 1, 0.5, 1, 0, 0]),  # 0.5 Extra Hours counts as 0
    ("2026-10-05", "Bob",    [1, 0, 0, 1, 1, 2]),
    ("2026-10-10", "Alice",  [1, 1, 1, 0, 0, 0]),    # Saturday
    ("2026-10-10", "Chitra", [0, 1, 0, 0, 0, 1]),    # Saturday
    ("2026-10-11", "Bob",    [1, 0, 0, 0, 0, 0]),    # Sunday
    ("2026-10-12", "Alice",  [1, 1, 0, 1, 1, 0]),
    ("2026-10-12", "Bob",    [0, 1, 0, 0, 0, 0]),
    ("2026-10-13", "Alice",  [1, 0, 0, 0, 0, 0]),    # superseded by the duplicate below
    ("2026-10-13", "Chitra", [1, 1, 0, 1, 0, 3]),
    ("2026-10-13", "Alice",  [1, 1, 0, 1, 1, 1]),    # duplicate Name + Date: this one wins
    ("2026-10-14", "Bob",    [1, 1, 0, 0, 0, 0]),
    ("2026-10-17", "Dev",    [1, 1, 0, 0, 0, 0]),    # Saturday
    ("2026-10-18", "Alice",  [1, 0, 0, 0, 0, 0]),    # Sunday
]

MONDAY, TUESDAY, WEDNESDAY, SUNDAY = date(2026, 10, 12), date(2026, 10, 13), date(2026, 10, 14), date(2026, 10, 18)


def graph_rows():
    return [{"index": i, "values": [i + 1, d, n] + list(v)} for i, (d, n, v) in enumerate(ROWS)]


def records():
    return logic.rows_to_records(HEADERS, graph_rows())


# --- The Teams script, transcribed (same algorithm, in-memory rows) ----------

def teams_report(today):
    weekday = today.weekday()
    this_monday = today - timedelta(days=weekday)
    if weekday == 0:
        start, end = today - timedelta(days=7), today - timedelta(days=1)
        week_number = start.isocalendar()[1]
        week_label = f"Week #{week_number} - {start.strftime('%b %d')} to {end.strftime('%b %d')} (Complete Week)"
        # The script used today - 2 (Saturday) here. Deliberately changed: the
        # weekly table's "previous day" is yesterday (Sunday) on Mondays too.
        prev_day_start = prev_day_end = today - timedelta(days=1)
        breakdown_start = breakdown_end = today - timedelta(days=1)
    elif weekday == 6:
        start, end = this_monday, today - timedelta(days=1)
        week_number = start.isocalendar()[1]
        week_label = f"Week #{week_number} - {start.strftime('%b %d')} to {end.strftime('%b %d')} (Complete Week)"
        prev_day_start = prev_day_end = end
        breakdown_start, breakdown_end = prev_day_start, prev_day_end
    else:
        start, end = this_monday, today - timedelta(days=1)
        week_number = start.isocalendar()[1]
        if start == end:
            week_label = f"Week #{week_number} - {start.strftime('%b %d')}"
        else:
            week_label = f"Week #{week_number} - {start.strftime('%b %d')} to {end.strftime('%b %d')}"
        prev_day_start = prev_day_end = today - timedelta(days=1)
        breakdown_start, breakdown_end = prev_day_start, prev_day_end

    all_names, seen = [], set()
    for _, n, _ in ROWS:
        if n not in seen:
            seen.add(n)
            all_names.append(n)
    totals, prev_day_totals = defaultdict(int), defaultdict(int)
    for n in all_names:
        totals[n] = prev_day_totals[n] = 0
    row_data, breakdown = {}, {}
    for d, n, values in ROWS:
        row_date = date.fromisoformat(d)
        key = (n, row_date)
        row_data[key] = sum(int(v or 0) for v in values)
        if breakdown_start <= row_date <= breakdown_end:
            breakdown[key] = {c: int(v or 0) for c, v in zip(CATEGORIES, values)}
    for (n, row_date), pts in row_data.items():
        if start <= row_date <= end:
            totals[n] += pts
        if prev_day_start <= row_date <= prev_day_end:
            prev_day_totals[n] += pts
    employees = sorted(
        [{"name": n, "points": p, "amount": p * 10, "prev_day_points": prev_day_totals.get(n, 0),
          "prev_day_amount": prev_day_totals.get(n, 0) * 10} for n, p in totals.items()],
        key=lambda x: (-x["prev_day_amount"], x["name"]),
    )
    prev_day_employees = [{"name": n, **cats} for (n, _), cats in breakdown.items()]
    if weekday == 0:
        present = {e["name"] for e in prev_day_employees}
        prev_day_employees += [{"name": n, **{c: 0 for c in CATEGORIES}} for n in all_names if n not in present]
    prev_day_employees.sort(key=lambda x: x["name"])
    in_range = {n for (n, d) in row_data if start <= d <= end}
    return {
        "start": start, "end": end, "week_label": week_label,
        "prev_day": prev_day_start, "breakdown_day": breakdown_start,
        # The dashboard's chosen rule: only names with a row inside the range.
        "employees": [e for e in employees if e["name"] in in_range],
        "all_sheet_employees": employees,
        "breakdown": prev_day_employees,
    }


def dashboard(today):
    """What the Daily dashboard computes, via the same calls the route makes."""
    period = logic.report_period(today)
    recs = records()
    unique = logic.unique_by_name_date(recs)
    weekly = logic.weekly_report_rows(unique, period["start"], period["end"], period["prev_day"], CATEGORIES)
    breakdown = logic.previous_day_breakdown(unique, logic.distinct_employees(recs), period["breakdown_day"],
                                             period["fill_breakdown"], CATEGORIES, [])
    return period, weekly, breakdown


# --- Same output as the script, every weekday ---------------------------------

@pytest.mark.parametrize("today", [MONDAY, TUESDAY, WEDNESDAY, SUNDAY])
def test_dashboard_matches_teams_script(today):
    period, weekly, breakdown = dashboard(today)
    teams = teams_report(today)
    for key in ("start", "end", "week_label", "prev_day", "breakdown_day"):
        assert period[key] == teams[key], key
    assert [(r["name"], r["prev_points"], r["prev_amount"], r["week_points"], r["week_amount"]) for r in weekly] == \
           [(e["name"], e["prev_day_points"], e["prev_day_amount"], e["points"], e["amount"]) for e in teams["employees"]]
    # Totals equal the script's TOTAL row (which also summed its 0 rows).
    assert sum(r["week_points"] for r in weekly) == sum(e["points"] for e in teams["all_sheet_employees"])
    assert sum(r["prev_points"] for r in weekly) == sum(e["prev_day_points"] for e in teams["all_sheet_employees"])
    assert [{"name": r["Name"], **{c: r[c] for c in CATEGORIES}} for r in breakdown] == teams["breakdown"]


# --- Hand-worked expectations, for readability --------------------------------

def test_monday_previous_complete_week():
    period, weekly, breakdown = dashboard(MONDAY)
    assert (period["start"], period["end"]) == (date(2026, 10, 5), date(2026, 10, 11))
    assert period["week_label"] == "Week #41 - Oct 05 to Oct 11 (Complete Week)"
    # "Previous day" is yesterday (Sunday) for BOTH tables, even on a Monday.
    assert period["prev_day"] == period["breakdown_day"] == date(2026, 10, 11)
    # Week: Alice 3 (0.5 -> 0) + 3, Bob 5 + 1, Chitra 2. Previous day = Sunday,
    # which only has Bob's 1 point, so Bob sorts first, then Alice, then Chitra.
    assert [(r["name"], r["prev_points"], r["prev_amount"], r["week_points"]) for r in weekly] == \
           [("Bob", 1, 10, 6), ("Alice", 0, 0, 6), ("Chitra", 0, 0, 2)]
    # Saturday's rows are in the week's totals but no longer in "previous day".
    assert sum(r["prev_points"] for r in weekly) == 1
    # Sunday table: Bob's row, plus every other name in the sheet with 0s.
    assert [r["Name"] for r in breakdown] == ["Alice", "Bob", "Chitra", "Dev", "Farah"]
    assert breakdown[1]["Punctuality"] == 1 and all(breakdown[0][c] == 0 for c in CATEGORIES)


def test_monday_without_sunday_rows_shows_zero_previous_day():
    # The sheet has no rows dated Sunday: every "previous day" cell is 0 / Rs 0,
    # while the previous complete week's totals are untouched.
    recs = [r for r in records() if r["Date"] != date(2026, 10, 11)]
    unique = logic.unique_by_name_date(recs)
    period = logic.report_period(MONDAY)
    weekly = logic.weekly_report_rows(unique, period["start"], period["end"], period["prev_day"], CATEGORIES)
    assert period["prev_day"] == date(2026, 10, 11)
    # All previous-day amounts are 0, so rows fall back to name order.
    assert [(r["name"], r["prev_points"], r["prev_amount"]) for r in weekly] == \
           [("Alice", 0, 0), ("Bob", 0, 0), ("Chitra", 0, 0)]
    assert [(r["name"], r["week_points"], r["week_amount"]) for r in weekly] == \
           [("Alice", 6, 60), ("Bob", 5, 50), ("Chitra", 2, 20)]
    breakdown = logic.previous_day_breakdown(unique, logic.distinct_employees(recs), period["breakdown_day"],
                                             period["fill_breakdown"], CATEGORIES, [])
    assert all(r[c] == 0 for r in breakdown for c in CATEGORIES)   # every name listed, all 0s


def test_every_weekday_previous_day_is_yesterday():
    for offset in range(7):                                   # Mon 12 .. Sun 18 Oct
        today = MONDAY + timedelta(days=offset)
        period = logic.report_period(today)
        assert period["prev_day"] == today - timedelta(days=1), today.strftime("%A")
        assert period["breakdown_day"] == period["prev_day"], today.strftime("%A")
        assert period["end"] < today                          # today's rows are never included


def test_tuesday_single_day_label():
    period, weekly, _ = dashboard(TUESDAY)
    assert (period["start"], period["end"]) == (MONDAY, MONDAY)
    assert period["week_label"] == "Week #42 - Oct 12"
    assert [(r["name"], r["prev_points"], r["week_points"]) for r in weekly] == [("Alice", 4, 4), ("Bob", 1, 1)]


def test_wednesday_duplicate_last_row_wins_and_today_excluded():
    period, weekly, breakdown = dashboard(WEDNESDAY)
    assert period["week_label"] == "Week #42 - Oct 12 to Oct 13"
    # Alice on the 13th counts 5 (the later duplicate), not 1 + 5; Bob's row
    # for today (the 14th) is not included.
    assert [(r["name"], r["prev_points"], r["prev_amount"], r["week_points"], r["week_amount"]) for r in weekly] == \
           [("Chitra", 6, 60, 6, 60), ("Alice", 5, 50, 9, 90), ("Bob", 0, 0, 1, 10)]
    assert [r["Name"] for r in breakdown] == ["Alice", "Chitra"]
    assert breakdown[0]["Extraordinary Performance"] == 1     # values from the winning duplicate


def test_sunday_complete_week_to_saturday():
    period, weekly, _ = dashboard(SUNDAY)
    assert (period["start"], period["end"]) == (MONDAY, date(2026, 10, 17))
    assert period["week_label"] == "Week #42 - Oct 12 to Oct 17 (Complete Week)"
    assert period["prev_day"] == period["breakdown_day"] == date(2026, 10, 17)
    assert [(r["name"], r["prev_points"], r["week_points"]) for r in weekly] == \
           [("Dev", 2, 2), ("Alice", 0, 9), ("Bob", 0, 3), ("Chitra", 0, 6)]


def test_week_label_zero_pads_like_strftime():
    # "%b %d" zero-pads the day; the dashboard prints it the same way.
    assert logic.report_period(date(2026, 10, 7))["week_label"] == "Week #41 - Oct 05 to Oct 06"


def test_kpis_use_the_report_week_and_the_week_before_it():
    unique = logic.unique_by_name_date(records())
    roster = ["Alice", "Bob", "Chitra", "Dev", "Eve"]
    monday = logic.report_period(MONDAY)
    k = logic.dashboard_kpis(unique, roster, monday["start"], monday["end"], CATEGORIES)
    assert k["weekly_points"] == 14 and k["weekly_amount"] == 140          # Oct 5-11
    assert k["previous_week_points"] == 2                                   # Sep 28 - Oct 4
    assert k["zero_point_employees"] == 2                                   # Dev, Eve
    assert k["total_employees"] == 5

    wednesday = logic.report_period(WEDNESDAY)
    k = logic.dashboard_kpis(unique, roster, wednesday["start"], wednesday["end"], CATEGORIES)
    assert k["weekly_points"] == 16                                         # Oct 12-13, duplicate counted once
    assert k["previous_week_points"] == 14                                  # Oct 5-11


def test_free_text_columns_are_not_points():
    headers = HEADERS + ["Notes"]
    rows = [{"index": 0, "values": [1, "2026-10-12", "Alice", 1, 0, 0, 0, 0, 0, "Led the demo"]}]
    unique = logic.unique_by_name_date(logic.rows_to_records(headers, rows))
    cols = logic.detect_columns(headers)
    weekly = logic.weekly_report_rows(unique, MONDAY, MONDAY, MONDAY, cols["category_names"])
    assert weekly[0]["week_points"] == 1


# --- Through the app ----------------------------------------------------------

@pytest.mark.parametrize("today, label, prev_shown", [
    (MONDAY, "Week #41 - Oct 05 to Oct 11 (Complete Week)", "Sun, 11 Oct 2026"),
    (WEDNESDAY, "Week #42 - Oct 12 to Oct 13", "Tue, 13 Oct 2026"),
])
def test_dashboard_page(client, monkeypatch, today, label, prev_shown):
    from sections import daily
    monkeypatch.setattr(daily, "_today", lambda: today)
    monkeypatch.setattr(daily, "get_table_columns", lambda: HEADERS)
    monkeypatch.setattr(daily, "get_table_rows", graph_rows)
    html = client.get("/daily/dashboard").get_data(as_text=True)
    assert label in html and prev_shown in html
    teams = teams_report(today)
    names = re.findall(r'<td class="whitespace-nowrap font-medium text-navy-950">(\w+)', html.split("Weekly performance report")[1])
    assert names == [e["name"] for e in teams["employees"]]
    total = sum(e["amount"] for e in teams["employees"])
    assert f"₹{total}</td>" in html
