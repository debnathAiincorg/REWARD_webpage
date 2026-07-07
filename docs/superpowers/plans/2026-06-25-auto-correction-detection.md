# Auto-Correction Detection for Weekly Performance Report — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Detect when yesterday's already-reported Excel data changes and re-send a corrected Teams report, while staying silent for normal daily data-entry activity.

**Architecture:** A new `TRIGGER_SOURCE` env-var distinguishes a normal scheduled run from a watcher-triggered run. On the watcher path, the script compares a JSON snapshot of yesterday's data (committed to the repo by the workflow) against freshly read Excel data; it sends a "🔧 Corrected Report" only when they differ, then updates the snapshot. The scheduled path is unchanged in output but gains a `save_snapshot()` call at the end.

**Tech Stack:** Python 3.11, openpyxl, pytest (new dev dep), GitHub Actions, Power Automate `repository_dispatch`.

## Global Constraints

- Category column names must be exactly: `Punctuality`, `L&D`, `Fluency Compliance`, `Innovation`, `Extraordinary Performance`
- `get_real_yesterday_data()` uses `datetime.now().date() - timedelta(days=1)` unconditionally — never the weekday-adjusted `prev_day_start`/`prev_day_end` from `get_cumulative_data()`
- Snapshot I/O errors must never block the scheduled report: catch, log `[WARNING]`, continue
- Snapshot file committed to repo root as `last_known_yesterday.json`
- `[skip ci]` suffix on snapshot commit messages

---

## File Map

| File | Status | Responsibility |
|------|--------|---------------|
| `weekly_report_send_teams.py` | **Modify** | Add `_detect_columns()`, `get_real_yesterday_data()`, `load_snapshot()`, `save_snapshot()`, `has_yesterday_data_changed()`; add `title_prefix` param to format functions; restructure `__main__` |
| `.github/workflows/weekly_report.yml` | **Modify** | Add `permissions: contents: write`, `TRIGGER_SOURCE` env var, post-run snapshot commit step |
| `last_known_yesterday.json` | **Created at runtime** | Snapshot written by the workflow; not pre-created |
| `tests/test_corrections.py` | **Create** | Unit tests for `_detect_columns`, `get_real_yesterday_data`, snapshot functions, change detection |
| `requirements.txt` | **Modify** | Add `pytest>=7.0.0` |

---

## Task 1: Extract `_detect_columns()` helper and wire it into `get_cumulative_data()`

**Files:**
- Modify: `weekly_report_send_teams.py:149-165` (inline column detection → extracted function)

**Interfaces:**
- Produces: `_detect_columns(ws) -> (date_col: int|None, name_col: int|None, category_cols: dict[str,int], point_cols: list[int])` — all column indices are 1-based

- [ ] **Step 1: Add `pytest` to `requirements.txt`**

Open `requirements.txt` and append:
```
pytest>=7.0.0
```

- [ ] **Step 2: Create `tests/test_corrections.py` with the helper + `_detect_columns` test**

Create file `tests/test_corrections.py`:

```python
import json
import os
import sys
from datetime import date, datetime, timedelta
from unittest.mock import patch

import pytest
from openpyxl import Workbook

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import weekly_report_send_teams as module

CATEGORIES = [
    "Punctuality", "L&D", "Fluency Compliance",
    "Innovation", "Extraordinary Performance",
]


def make_test_workbook(rows):
    """Build an in-memory openpyxl Workbook with the expected sheet structure.

    rows: list of dicts with keys: date (datetime), name (str),
          and optionally each category name (int, default 0).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Daily Performance Bonus"
    headers = ["Index", "Date", "Name"] + CATEGORIES
    for col, h in enumerate(headers, 1):
        ws.cell(row=1, column=col, value=h)
    for r, row in enumerate(rows, 2):
        ws.cell(row=r, column=1, value=r - 1)
        ws.cell(row=r, column=2, value=row["date"])
        ws.cell(row=r, column=3, value=row["name"])
        for col, cat in enumerate(CATEGORIES, 4):
            ws.cell(row=r, column=col, value=row.get(cat, 0))
    return wb


# ── _detect_columns ──────────────────────────────────────────────────────────

def test_detect_columns_identifies_all_columns():
    wb = make_test_workbook([])
    ws = wb["Daily Performance Bonus"]
    date_col, name_col, category_cols, point_cols = module._detect_columns(ws)
    assert date_col == 2
    assert name_col == 3
    assert category_cols == {
        "Punctuality": 4, "L&D": 5, "Fluency Compliance": 6,
        "Innovation": 7, "Extraordinary Performance": 8,
    }
    assert sorted(point_cols) == [4, 5, 6, 7, 8]


def test_detect_columns_returns_none_for_missing_columns():
    wb = Workbook()
    ws = wb.active
    ws.cell(row=1, column=1, value="Index")
    date_col, name_col, category_cols, point_cols = module._detect_columns(ws)
    assert date_col is None
    assert name_col is None
```

- [ ] **Step 3: Run the test — expect FAIL because `_detect_columns` does not exist yet**

```
cd d:\REWARDS
python -m pytest tests/test_corrections.py::test_detect_columns_identifies_all_columns -v
```

Expected: `AttributeError: module 'weekly_report_send_teams' has no attribute '_detect_columns'`

- [ ] **Step 4: Add `_detect_columns()` to `weekly_report_send_teams.py` (before `get_cumulative_data`)**

Insert this function at line 103 (just before `def get_cumulative_data()`):

```python
def _detect_columns(ws):
    """Return (date_col, name_col, category_cols, point_cols) from header row.

    All indices are 1-based. date_col and name_col are None if not found.
    category_cols maps category name → column index for the five bonus categories.
    point_cols lists every non-date, non-name, non-index scoring column.
    """
    headers = [ws.cell(row=1, column=c).value for c in range(1, ws.max_column + 1)]
    date_col = name_col = None
    point_cols = []
    category_cols = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        hl = str(h).strip().lower()
        if hl == "date":
            date_col = i + 1
        elif hl == "name":
            name_col = i + 1
        elif hl != "index":
            point_cols.append(i + 1)
            h_clean = str(h).strip()
            if h_clean in [
                "Punctuality", "L&D", "Fluency Compliance",
                "Innovation", "Extraordinary Performance",
            ]:
                category_cols[h_clean] = i + 1
    return date_col, name_col, category_cols, point_cols
```

- [ ] **Step 5: Replace inline column detection inside `get_cumulative_data()` with the helper call**

In `get_cumulative_data()`, replace lines 149–165 (the `headers = …` block through the end of the `for i, h` loop) with:

```python
    # Detect columns from row 1
    date_col, name_col, category_cols, point_cols = _detect_columns(ws)
```

- [ ] **Step 6: Run the two `_detect_columns` tests — expect PASS**

```
python -m pytest tests/test_corrections.py::test_detect_columns_identifies_all_columns tests/test_corrections.py::test_detect_columns_returns_none_for_missing_columns -v
```

Expected: `2 passed`

- [ ] **Step 7: Commit**

```bash
git add requirements.txt weekly_report_send_teams.py tests/test_corrections.py
git commit -m "refactor: extract _detect_columns helper, add test scaffold"
```

---

## Task 2: Add `get_real_yesterday_data()`

**Files:**
- Modify: `weekly_report_send_teams.py` (new function after `_detect_columns`)
- Modify: `tests/test_corrections.py` (new tests)

**Interfaces:**
- Consumes: `_detect_columns(ws)` from Task 1; global `TEMP_FILE` path
- Produces: `get_real_yesterday_data() -> dict[str, dict[str, int]]` — e.g. `{"Alice": {"Punctuality": 1, "L&D": 0, ...}}`

- [ ] **Step 1: Add failing tests for `get_real_yesterday_data`**

Append to `tests/test_corrections.py`:

```python
# ── get_real_yesterday_data ───────────────────────────────────────────────────

def test_get_real_yesterday_data_returns_only_yesterday(tmp_path):
    yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())
    today_dt = datetime.combine(date.today(), datetime.min.time())

    wb = make_test_workbook([
        {"date": yesterday, "name": "Alice",
         "Punctuality": 1, "L&D": 1, "Fluency Compliance": 0,
         "Innovation": 0, "Extraordinary Performance": 0},
        {"date": today_dt, "name": "Alice",
         "Punctuality": 1, "L&D": 1, "Fluency Compliance": 1,
         "Innovation": 1, "Extraordinary Performance": 1},
    ])
    test_file = str(tmp_path / "source.xlsx")
    wb.save(test_file)

    with patch.object(module, "TEMP_FILE", test_file):
        result = module.get_real_yesterday_data()

    assert list(result.keys()) == ["Alice"]
    assert result["Alice"] == {
        "Punctuality": 1, "L&D": 1, "Fluency Compliance": 0,
        "Innovation": 0, "Extraordinary Performance": 0,
    }


def test_get_real_yesterday_data_deduplicates_keeps_last(tmp_path):
    yesterday = datetime.combine(date.today() - timedelta(days=1), datetime.min.time())

    wb = make_test_workbook([
        {"date": yesterday, "name": "Bob", "Punctuality": 0, "L&D": 0,
         "Fluency Compliance": 0, "Innovation": 0, "Extraordinary Performance": 0},
        {"date": yesterday, "name": "Bob", "Punctuality": 1, "L&D": 1,
         "Fluency Compliance": 1, "Innovation": 1, "Extraordinary Performance": 1},
    ])
    test_file = str(tmp_path / "source.xlsx")
    wb.save(test_file)

    with patch.object(module, "TEMP_FILE", test_file):
        result = module.get_real_yesterday_data()

    assert result["Bob"]["Punctuality"] == 1


def test_get_real_yesterday_data_empty_when_no_rows(tmp_path):
    wb = make_test_workbook([])
    test_file = str(tmp_path / "source.xlsx")
    wb.save(test_file)

    with patch.object(module, "TEMP_FILE", test_file):
        result = module.get_real_yesterday_data()

    assert result == {}
```

- [ ] **Step 2: Run new tests — expect FAIL**

```
python -m pytest tests/test_corrections.py -k "get_real_yesterday" -v
```

Expected: `AttributeError: module 'weekly_report_send_teams' has no attribute 'get_real_yesterday_data'`

- [ ] **Step 3: Add `get_real_yesterday_data()` to `weekly_report_send_teams.py`**

Insert after `_detect_columns()` (before `get_cumulative_data()`):

```python
def get_real_yesterday_data():
    """Read per-employee category data for actual calendar yesterday.

    Always uses today - 1 day (never weekday-adjusted).
    Returns {employee_name: {category: int}} for rows matching yesterday's date.
    Last occurrence wins when duplicate (name, date) rows exist.
    """
    yesterday_date = datetime.now().date() - timedelta(days=1)
    wb = load_workbook(TEMP_FILE)
    if "Daily Performance Bonus" in wb.sheetnames:
        ws = wb["Daily Performance Bonus"]
    else:
        ws = max(wb.worksheets, key=lambda s: s.max_row or 0)

    date_col, name_col, category_cols, _ = _detect_columns(ws)
    if not name_col or not date_col:
        return {}

    result = {}
    for row in range(2, ws.max_row + 1):
        name_val = ws.cell(row=row, column=name_col).value
        date_val = ws.cell(row=row, column=date_col).value
        if not name_val or not date_val:
            continue
        row_date = date_val.date() if hasattr(date_val, "date") else None
        if not row_date or row_date != yesterday_date:
            continue
        name = str(name_val).strip()
        result[name] = {
            cat_name: int(ws.cell(row=row, column=col_num).value or 0)
            for cat_name, col_num in category_cols.items()
        }
    return result
```

- [ ] **Step 4: Run all three `get_real_yesterday_data` tests — expect PASS**

```
python -m pytest tests/test_corrections.py -k "get_real_yesterday" -v
```

Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add weekly_report_send_teams.py tests/test_corrections.py
git commit -m "feat: add get_real_yesterday_data() for snapshot comparison"
```

---

## Task 3: Add snapshot functions and change-detection logic

**Files:**
- Modify: `weekly_report_send_teams.py` (add `import json`, `SNAPSHOT_FILE`, three new functions)
- Modify: `tests/test_corrections.py` (new tests)

**Interfaces:**
- Produces:
  - `SNAPSHOT_FILE: str` — module-level constant `"last_known_yesterday.json"`
  - `load_snapshot() -> dict | None`
  - `save_snapshot(date_str: str, employees_dict: dict) -> None`
  - `has_yesterday_data_changed(yesterday_date_str: str, fresh_data: dict) -> bool`

- [ ] **Step 1: Add failing tests**

Append to `tests/test_corrections.py`:

```python
# ── Snapshot functions ────────────────────────────────────────────────────────

def test_save_and_load_roundtrip(tmp_path):
    data = {"Alice": {"Punctuality": 1, "L&D": 0, "Fluency Compliance": 1,
                      "Innovation": 0, "Extraordinary Performance": 0}}
    snap_file = str(tmp_path / "snap.json")
    with patch.object(module, "SNAPSHOT_FILE", snap_file):
        module.save_snapshot("2026-06-24", data)
        result = module.load_snapshot()
    assert result == {"date": "2026-06-24", "employees": data}


def test_load_snapshot_returns_none_when_file_missing(tmp_path):
    with patch.object(module, "SNAPSHOT_FILE", str(tmp_path / "missing.json")):
        assert module.load_snapshot() is None


def test_save_snapshot_silent_on_bad_path():
    with patch.object(module, "SNAPSHOT_FILE", "/nonexistent_dir/snap.json"):
        module.save_snapshot("2026-06-24", {})  # must not raise


# ── has_yesterday_data_changed ────────────────────────────────────────────────

def test_no_change_when_data_identical(tmp_path):
    data = {"Alice": {"Punctuality": 1, "L&D": 0, "Fluency Compliance": 1,
                      "Innovation": 0, "Extraordinary Performance": 0}}
    snap_file = str(tmp_path / "snap.json")
    with open(snap_file, "w") as f:
        json.dump({"date": "2026-06-24", "employees": data}, f)
    with patch.object(module, "SNAPSHOT_FILE", snap_file):
        assert not module.has_yesterday_data_changed("2026-06-24", data)


def test_change_detected_when_value_differs(tmp_path):
    old = {"Alice": {"Punctuality": 0, "L&D": 0, "Fluency Compliance": 0,
                     "Innovation": 0, "Extraordinary Performance": 0}}
    new = {"Alice": {"Punctuality": 1, "L&D": 0, "Fluency Compliance": 0,
                     "Innovation": 0, "Extraordinary Performance": 0}}
    snap_file = str(tmp_path / "snap.json")
    with open(snap_file, "w") as f:
        json.dump({"date": "2026-06-24", "employees": old}, f)
    with patch.object(module, "SNAPSHOT_FILE", snap_file):
        assert module.has_yesterday_data_changed("2026-06-24", new)


def test_no_change_when_snapshot_date_differs(tmp_path):
    snapshot_data = {"Alice": {"Punctuality": 1, "L&D": 0, "Fluency Compliance": 0,
                               "Innovation": 0, "Extraordinary Performance": 0}}
    fresh_data = {"Alice": {"Punctuality": 0, "L&D": 0, "Fluency Compliance": 0,
                            "Innovation": 0, "Extraordinary Performance": 0}}
    snap_file = str(tmp_path / "snap.json")
    with open(snap_file, "w") as f:
        json.dump({"date": "2026-06-23", "employees": snapshot_data}, f)
    with patch.object(module, "SNAPSHOT_FILE", snap_file):
        # Different date means watcher fired on a new day — not a correction
        assert not module.has_yesterday_data_changed("2026-06-24", fresh_data)


def test_no_change_when_no_snapshot(tmp_path):
    with patch.object(module, "SNAPSHOT_FILE", str(tmp_path / "missing.json")):
        assert not module.has_yesterday_data_changed("2026-06-24", {"Alice": {}})
```

- [ ] **Step 2: Run new tests — expect FAIL**

```
python -m pytest tests/test_corrections.py -k "snapshot or change" -v
```

Expected: `AttributeError: module 'weekly_report_send_teams' has no attribute 'load_snapshot'`

- [ ] **Step 3: Add `import json` to imports at top of `weekly_report_send_teams.py`**

In the imports block (around line 3), add:
```python
import json
```

- [ ] **Step 4: Add `SNAPSHOT_FILE` constant and three functions to `weekly_report_send_teams.py`**

After `SHAREPOINT_ITEM_ID = ...` (around line 27) and before the function definitions, add:

```python
SNAPSHOT_FILE = "last_known_yesterday.json"
```

Then, after `cleanup_temp_file()` and before the `# MAIN EXECUTION` comment, add the three functions:

```python
def load_snapshot():
    """Load the last-known yesterday snapshot from disk. Returns None if absent."""
    try:
        with open(SNAPSHOT_FILE, "r") as f:
            return json.load(f)
    except FileNotFoundError:
        return None
    except Exception as e:
        print(f"[WARNING] Could not read snapshot: {e}")
        return None


def save_snapshot(date_str, employees_dict):
    """Persist yesterday's per-employee category data as the new baseline."""
    try:
        with open(SNAPSHOT_FILE, "w") as f:
            json.dump({"date": date_str, "employees": employees_dict}, f, indent=2)
        print(f"[OK] Snapshot saved for {date_str}")
    except Exception as e:
        print(f"[WARNING] Could not save snapshot: {e}")


def has_yesterday_data_changed(yesterday_date_str, fresh_data):
    """Return True only when yesterday's snapshot exists, date matches, and data differs."""
    snapshot = load_snapshot()
    if snapshot is None or snapshot.get("date") != yesterday_date_str:
        return False
    return snapshot["employees"] != fresh_data
```

- [ ] **Step 5: Run all snapshot/change-detection tests — expect PASS**

```
python -m pytest tests/test_corrections.py -k "snapshot or change" -v
```

Expected: `7 passed`

- [ ] **Step 6: Run the full test suite to confirm no regressions**

```
python -m pytest tests/test_corrections.py -v
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add weekly_report_send_teams.py tests/test_corrections.py
git commit -m "feat: add snapshot load/save and has_yesterday_data_changed"
```

---

## Task 4: Add `title_prefix` param to format functions + restructure `__main__`

**Files:**
- Modify: `weekly_report_send_teams.py` — `format_prev_day_card`, `format_teams_message`, `__main__` block

**Interfaces:**
- Consumes (from Tasks 1–3): `get_real_yesterday_data()`, `has_yesterday_data_changed()`, `save_snapshot()`, `load_snapshot()`
- `format_prev_day_card(prev_day_breakdown, title_prefix="")` — unchanged return type
- `format_teams_message(week_label, employees, title_prefix="")` — unchanged return type

- [ ] **Step 1: Add `title_prefix=""` param to `format_prev_day_card()`**

Change the function signature from:
```python
def format_prev_day_card(prev_day_breakdown):
```
to:
```python
def format_prev_day_card(prev_day_breakdown, title_prefix=""):
```

Then change the title TextBlock value from:
```python
"text": "Previous Day Performance Breakdown",
```
to:
```python
"text": f"{title_prefix}Previous Day Performance Breakdown",
```

- [ ] **Step 2: Add `title_prefix=""` param to `format_teams_message()`**

Change the function signature from:
```python
def format_teams_message(week_label, employees):
```
to:
```python
def format_teams_message(week_label, employees, title_prefix=""):
```

Then change the title TextBlock value from:
```python
"text": "Weekly Performance Report",
```
to:
```python
"text": f"{title_prefix}Weekly Performance Report",
```

- [ ] **Step 3: Replace the `if __name__ == "__main__":` block with the dual-mode version**

Replace everything from `# MAIN EXECUTION` to end of file with:

```python
# MAIN EXECUTION
if __name__ == "__main__":
    print("=" * 60)
    print("WEEKLY PERFORMANCE REPORT - TEAMS SENDER")
    print("=" * 60)

    TRIGGER_SOURCE = os.environ.get("TRIGGER_SOURCE", "scheduled")
    print(f"[INFO] Trigger source: {TRIGGER_SOURCE}")

    if not download_source_file():
        exit(1)

    yesterday_date = datetime.now().date() - timedelta(days=1)
    yesterday_str = yesterday_date.isoformat()
    fresh_yesterday_data = get_real_yesterday_data()

    if TRIGGER_SOURCE == "watcher":
        if not has_yesterday_data_changed(yesterday_str, fresh_yesterday_data):
            print("[INFO] No change to yesterday's already-reported data. Exiting silently.")
            cleanup_temp_file()
            exit(0)

        print("[INFO] Yesterday's data changed — sending corrected report.")
        week_label, employee_data, _ = get_cumulative_data()
        if not week_label or not employee_data:
            print("[ERROR] No data to send.")
            cleanup_temp_file()
            exit(1)

        corrected_breakdown = {
            "date_label": yesterday_date.strftime("%b %d"),
            "employees": sorted(
                [{"name": name, **cats} for name, cats in fresh_yesterday_data.items()],
                key=lambda x: x["name"],
            ),
        }
        prefix = "🔧 Corrected Report - "
        cards_sent = 0

        if corrected_breakdown["employees"]:
            prev_day_card = format_prev_day_card(corrected_breakdown, title_prefix=prefix)
            if prev_day_card:
                print("Sending corrected Previous Day Performance Breakdown card to Teams...")
                if send_teams_webhook_message(WEBHOOK_URL, prev_day_card):
                    print("[OK] Corrected Previous Day card sent successfully!")
                    cards_sent += 1
                else:
                    print("[ERROR] Failed to send corrected Previous Day card to Teams")
                    cleanup_temp_file()
                    exit(1)

        weekly_card = format_teams_message(week_label, employee_data, title_prefix=prefix)
        print("Sending corrected Weekly Performance Report card to Teams...")
        if send_teams_webhook_message(WEBHOOK_URL, weekly_card):
            print("[OK] Corrected Weekly Report card sent successfully!")
            cards_sent += 1
        else:
            print("[ERROR] Failed to send corrected Weekly Report card to Teams")
            cleanup_temp_file()
            exit(1)

        save_snapshot(yesterday_str, fresh_yesterday_data)
        print(f"\n[OK] Total corrected cards sent: {cards_sent}")
        cleanup_temp_file()
        print("=" * 60)

    else:
        # Normal scheduled run — existing behavior unchanged
        print("Determining date range and reading Excel data...")
        week_label, employee_data, prev_day_breakdown = get_cumulative_data()

        if not week_label or not employee_data:
            print("[ERROR] No data to send.")
            cleanup_temp_file()
            exit(1)

        print(f"[OK] Report: {week_label}")
        print(f"[OK] Employees: {len(employee_data)}")
        if prev_day_breakdown and prev_day_breakdown["employees"]:
            print(f"[OK] Previous Day ({prev_day_breakdown['date_label']}): {len(prev_day_breakdown['employees'])} employees")
        print("\nVerification:")
        for emp in employee_data:
            print(f"  {emp['name']}: Prev Day {emp['prev_day_points']} pts (₹{emp['prev_day_amount']}) | Weekly {emp['points']} pts (₹{emp['amount']})")
        if prev_day_breakdown and prev_day_breakdown["employees"]:
            print(f"\nPrevious Day Breakdown ({prev_day_breakdown['date_label']}):")
            for emp in prev_day_breakdown["employees"]:
                print(
                    f"  {emp['name']}: Punctuality={emp.get('Punctuality', 0)}, "
                    f"L&D={emp.get('L&D', 0)}, Fluency Compliance={emp.get('Fluency Compliance', 0)}, "
                    f"Innovation={emp.get('Innovation', 0)}, "
                    f"Extraordinary Performance={emp.get('Extraordinary Performance', 0)}"
                )
        print()

        cards_sent = 0

        if prev_day_breakdown and prev_day_breakdown["employees"]:
            prev_day_card = format_prev_day_card(prev_day_breakdown)
            if prev_day_card:
                print("Sending Previous Day Performance Breakdown card to Teams...")
                if send_teams_webhook_message(WEBHOOK_URL, prev_day_card):
                    print("[OK] Previous Day card sent successfully!")
                    cards_sent += 1
                else:
                    print("ERROR: Failed to send Previous Day card to Teams")
                    cleanup_temp_file()
                    exit(1)

        weekly_card = format_teams_message(week_label, employee_data)
        print("Sending Weekly Performance Report card to Teams...")
        if send_teams_webhook_message(WEBHOOK_URL, weekly_card):
            print("[OK] Weekly Report card sent successfully!")
            cards_sent += 1
        else:
            print("ERROR: Failed to send Weekly Report card to Teams")
            cleanup_temp_file()
            exit(1)

        save_snapshot(yesterday_str, fresh_yesterday_data)
        print(f"\n[OK] Total cards sent: {cards_sent}")
        cleanup_temp_file()
        print("=" * 60)
```

- [ ] **Step 4: Run the full test suite to confirm no regressions**

```
python -m pytest tests/test_corrections.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Visually verify the `__main__` structure is correct**

Read through the new `__main__` and confirm:
- `TRIGGER_SOURCE` is read from env before any data work
- `fresh_yesterday_data = get_real_yesterday_data()` is called after `download_source_file()`, before the if/else
- Watcher path: compare → exit silently OR send corrected cards + save snapshot
- Scheduled path: same output as before + `save_snapshot()` at end
- `cleanup_temp_file()` is called on every exit path (both error exits and success)

- [ ] **Step 6: Commit**

```bash
git add weekly_report_send_teams.py
git commit -m "feat: add watcher mode with corrected-report send and snapshot update"
```

---

## Task 5: Update `weekly_report.yml`

**Files:**
- Modify: `.github/workflows/weekly_report.yml`

- [ ] **Step 1: Replace `.github/workflows/weekly_report.yml` with the updated version**

```yaml
name: Weekly Performance Report
on:
  workflow_dispatch:
  repository_dispatch:
    types: [weekly_report]

permissions:
  contents: write

jobs:
  send-weekly-report:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: pip install -r requirements.txt
      - name: Run weekly report
        env:
          AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
          TRIGGER_SOURCE: ${{ github.event.client_payload.source }}
        run: python weekly_report_send_teams.py
      - name: Commit updated snapshot
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add last_known_yesterday.json
          git diff --staged --quiet || git commit -m "Update yesterday snapshot [skip ci]"
          git push
```

- [ ] **Step 2: Verify the YAML is valid by reading it back and checking structure**

Confirm:
- `permissions: contents: write` is at the top level (not inside `jobs`)
- `TRIGGER_SOURCE: ${{ github.event.client_payload.source }}` is under the `Run weekly report` step's `env` block
- The `Commit updated snapshot` step comes **after** `Run weekly report`
- The commit step uses `git diff --staged --quiet ||` so it only commits when the file actually changed (no empty commits)
- `[skip ci]` is in the commit message

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/weekly_report.yml
git commit -m "ci: add permissions, TRIGGER_SOURCE, and snapshot commit step"
```

---

## Self-Review: Spec Coverage Check

| Spec Requirement | Covered By |
|-----------------|-----------|
| Scheduled run → send full report unchanged | Task 4 (`else` branch in `__main__`) |
| Scheduled run → save snapshot after send | Task 4 (`save_snapshot()` call in `else`) |
| Watcher run → recompute yesterday from Excel | Task 2 (`get_real_yesterday_data()`) |
| Watcher run → compare to snapshot | Task 3 (`has_yesterday_data_changed()`) |
| Watcher run → exit silently if identical | Task 4 (watcher `if not ...` branch) |
| Watcher run → send corrected report if changed | Task 4 (watcher `else` branch) |
| Watcher run → update snapshot after corrected send | Task 4 (`save_snapshot()` in watcher else) |
| Distinguish modes via `TRIGGER_SOURCE` env var | Task 4 (`os.environ.get("TRIGGER_SOURCE", "scheduled")`) |
| `last_known_yesterday.json` format `{date, employees}` | Task 3 (`save_snapshot`) |
| `get_real_yesterday_data()` uses actual `today - 1` | Task 2 (`yesterday_date = datetime.now().date() - timedelta(days=1)`) |
| `_detect_columns()` shared helper | Task 1 |
| Corrected cards prefixed with "🔧 Corrected Report - " | Task 4 (`prefix = "🔧 Corrected Report - "`) |
| Snapshot I/O errors → warn, do not crash | Task 3 (`load_snapshot`/`save_snapshot` try/except) |
| Date-mismatch in snapshot → treat as no correction | Task 3 (`has_yesterday_data_changed`: date check) |
| First-ever run (no snapshot) → no correction | Task 3 (`load_snapshot` returns None → False) |
| `permissions: contents: write` in workflow | Task 5 |
| `TRIGGER_SOURCE` env var in workflow | Task 5 |
| Snapshot commit step with `[skip ci]` | Task 5 |
| `git diff --staged --quiet` guard (no empty commits) | Task 5 |
