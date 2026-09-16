# Weekly Performance Report — Teams Bot

A Python script that reads employee performance data from a SharePoint Excel file and sends **two separate Adaptive Cards** to Microsoft Teams via a Power Automate webhook:

1. **Previous Day Performance Breakdown** — Category-level scores (Punctuality, L&D, Fluency Compliance, Innovation, Extraordinary Performance) for the previous working day
2. **Weekly Performance Report** — Weekly totals with previous-day aggregates and TOTAL row

---

## How It Works

### 1. Download the Excel file from SharePoint

- Tries the public SharePoint link first.
- If the public link redirects to an HTML login page, falls back to **Microsoft Graph API** using Azure credentials from `.env`.
- Graph API download retries up to **3 times**, with a 30-second wait between attempts.
- Saves the file temporarily to `TEMP_FILE` (default: `D:\sharepoint\temp_source.xlsx`).

### 2. Read the "Daily Performance Bonus" sheet

- Auto-detects the `Date`, `Name`, and category columns from row 1 — no column positions are hardcoded.
- Identifies category columns: `Punctuality`, `L&D`, `Fluency Compliance`, `Innovation`, `Extraordinary Performance`
- Collects all unique employee names from the sheet automatically.
- New employees added to the Excel file appear in reports with no code changes.
- Deduplicates rows by (name, date) to prevent double-counting.

### 3. Calculate date range based on today's weekday

| Day of Run | Weekly Range | Previous Day (Weekly Card) | Breakdown Card Date |
|---|---|---|---|
| **Monday** | Previous Monday → Previous Sunday | Previous Saturday (with real data) | Previous Sunday (all 0s) |
| **Tuesday** | This Monday only | Yesterday (Monday) | Yesterday (Monday) |
| **Wednesday–Saturday** | This Monday → Yesterday | Yesterday | Yesterday |
| **Sunday** | This Monday → Yesterday (Saturday) | Yesterday (Saturday) | Yesterday (Saturday) |

**Monday Special Handling:**
- Weekly Report shows previous Saturday's actual performance data
- Breakdown card shows all employees with 0s dated Sunday (non-working day)
- Both cards are always sent on Monday, even though breakdown is all zeros

### 4. Aggregate points and calculate payout

- **Weekly Card:**
  - Sums all point columns per employee within the weekly date range
  - Also aggregates the **previous day** separately (for "Previous Day Point/Amount" columns)
  - **Amount = Points × ₹10**
  - Employees sorted by **previous day amount (descending), name (ascending) as tiebreaker**

- **Breakdown Card:**
  - Shows category-level scores from the "Daily Performance Bonus" sheet
  - One row per employee with actual values: Punctuality, L&D, Fluency Compliance, Innovation, Extraordinary Performance
  - On Monday: All employees shown with 0s (since Sunday is non-working)
  - On other days: Only employees with data for that previous day are shown; if no data exists, breakdown card is skipped

### 5. Send two separate Adaptive Cards to Teams

**Card 1: Previous Day Performance Breakdown** (sent first, if data exists)
```
Title: "Previous Day Performance Breakdown"
Date Label: (e.g., "Jun 21" for Monday's Sunday, or "Jun 22" for other days)

Columns: Name | Punctuality | L&D | Fluency Compliance | Innovation | Extraordinary Performance
```

**Card 2: Weekly Performance Report** (always sent)
```
Title: "Weekly Performance Report"
Week Label: (e.g., "Week #25 - Jun 15 to Jun 21 (Complete Week)")

Columns: Name | Previous Day Point | Previous Day Amount | Weekly Total Point | Weekly Total Amount
TOTAL Row: Aggregated sums
```

Both cards sent via Power Automate webhook URL using HTTP POST.

### 6. Cleanup

Deletes the temporary Excel file after both reports are sent.

---

## Prerequisites

- Python 3.x
- Required packages:
  - `requests`
  - `openpyxl`
  - `msal`
  - `python-dotenv`

---

## Installation

```bash
pip install requests openpyxl msal python-dotenv
```

---

## Setup

### 1. Create a `.env` file

```env
AZURE_CLIENT_ID=your-client-id
AZURE_TENANT_ID=your-tenant-id
AZURE_CLIENT_SECRET=your-client-secret
```

These credentials are only used if the public SharePoint link requires authentication.

---

## Excel File Format

- **Sheet name:** `Daily Performance Bonus`
- **Required columns:** `Date`, `Name`, `Punctuality`, `L&D`, `Fluency Compliance`, `Innovation`, `Extraordinary Performance`
- Additional columns (like `Index`) are recognized and skipped
- Any unknown numeric column is treated as a point column (summed in weekly total)
- New employees (rows) are picked up automatically on the next run

### Example Sheet Structure

| Index | Date | Name | Punctuality | L&D | Fluency Compliance | Innovation | Extraordinary Performance |
|---|---|---|---|---|---|---|---|
| 1 | 2026-06-22 | Employee1 | 1 | 1 | 0 | 0 | 0 |
| 2 | 2026-06-22 | Employee2 | 1 | 1 | 0 | 0 | 0 |
| 3 | 2026-06-22 | Employee3 | 0 | 0 | 0 | 0 | 0 |

---

## Key Features

✓ **Automatic column detection** — No hardcoded column positions  
✓ **Automatic employee discovery** — New rows/names picked up dynamically  
✓ **Deduplication** — Prevents double-counting on duplicate (name, date) rows  
✓ **Two-card split** — Breakdown card sent independently from weekly summary  
✓ **Monday special case** — Previous day breakdown shows all employees with 0s for Sunday  
✓ **Fallback authentication** — Public link → Graph API with retries  
✓ **Idempotent** — Safe to run multiple times (uses temp file only)

---

## Notes

- No hardcoded dates or employee names — everything derived from Excel data and current date.
- **Monday** sends breakdown card with all employees + 0s (Sunday is non-working), then weekly card with Saturday's real data.
- **Tuesday** single-day report (Monday only) since start == end.
- **Sorting:** Employees ordered by previous-day amount (highest first), name (A–Z) as tiebreaker.
- **Rows with no date or name columns are skipped** — handles sparse or malformed Excel data gracefully.
