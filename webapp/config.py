# Single source of truth for which SharePoint Excel file this app talks to.
# No other file in this project should hardcode a Drive ID or Item ID.
#
# This is the live production workbook: every Add, Edit and Delete in the
# running app changes the real sheets.

# Production file: "Strict Employee Performance Analysis.xlsx"
# (sites/StrictEmployeePerformance).
MAIN_DRIVE_ID = "b!_Oj5AOOCqUa-6fnpgxmwM4Tmz3IIfOZIhM-bF3vfV8Q7o8oZ3WyrQ4ILTnuUDgHw"
MAIN_ITEM_ID = "01EUH7IGAHNG3EYW2JJ5C37HVRDHKNUFDB"

TABLE_NAME = "Table1"
SHEET_NAME = "Daily Performance Bonus"

# The other three sections are plain worksheets (no Excel Table), read and
# written through the worksheet range API. Names must match the tabs exactly.
WHATSAPP_SHEET = "Employee Whatsapp"
MONTHLY_SHEET = "Monthly Performance Bonus"
KEYBOARD_SHEET = "Keyboard Performance Status - M"

if not MAIN_DRIVE_ID or not MAIN_ITEM_ID:
    raise RuntimeError("MAIN_DRIVE_ID/MAIN_ITEM_ID are not set. Refusing to start.")

DRIVE_ID, ITEM_ID = MAIN_DRIVE_ID, MAIN_ITEM_ID
