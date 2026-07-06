# Single source of truth for which SharePoint Excel file this app talks to.
# No other file in this project should hardcode a Drive ID or Item ID.

ACTIVE_FILE = "DUMMY"  # "DUMMY" or "MAIN"

# Fill these in with your dummy/test file's IDs before running the app.
DUMMY_DRIVE_ID = "b!ncIFrojL106h53P8D_qyinjcKBnN9CFGrFJ26Ac7DPP-kaV-qe0HS73NEabHbqpx"
DUMMY_ITEM_ID = "01ZAECLIXEJYLGEVLWOZB2FQXRBJRJEBV7"

# Leave these as None until dummy-file testing is complete and you explicitly
# provide the production file's IDs for cutover.
MAIN_DRIVE_ID = None
MAIN_ITEM_ID = None

TABLE_NAME = "Table1"
SHEET_NAME = "Daily Performance Bonus"

if ACTIVE_FILE == "DUMMY":
    DRIVE_ID, ITEM_ID = DUMMY_DRIVE_ID, DUMMY_ITEM_ID
elif ACTIVE_FILE == "MAIN":
    if not MAIN_DRIVE_ID or not MAIN_ITEM_ID:
        raise RuntimeError(
            "ACTIVE_FILE is 'MAIN' but MAIN_DRIVE_ID/MAIN_ITEM_ID are not set. "
            "Refusing to start."
        )
    DRIVE_ID, ITEM_ID = MAIN_DRIVE_ID, MAIN_ITEM_ID
else:
    raise RuntimeError(f"Unknown ACTIVE_FILE: {ACTIVE_FILE!r}")
