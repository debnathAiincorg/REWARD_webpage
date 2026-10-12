# Thin wrapper around the Microsoft Graph Excel workbook API: the Table1
# endpoints for Daily Performance Bonus, and the worksheet range endpoints for
# the sheets that aren't Excel Tables. All identity (which file) comes from
# config.py — nothing here hardcodes a Drive ID or Item ID.

import os
from pathlib import Path
from urllib.parse import quote

import requests
from dotenv import load_dotenv
from msal import ConfidentialClientApplication

from config import DRIVE_ID, ITEM_ID, TABLE_NAME
from sheet_grid import Grid, address

# Load webapp/.env (local development only — on Railway the variables come from
# the service settings), regardless of the process's working directory.
load_dotenv(Path(__file__).resolve().parent / ".env")

AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
WORKBOOK_BASE = f"{GRAPH_BASE}/drives/{DRIVE_ID}/items/{ITEM_ID}/workbook"
TABLE_BASE = f"{WORKBOOK_BASE}/tables/{TABLE_NAME}"


class GraphError(Exception):
    """Raised for any Azure auth failure or Graph API HTTP error."""


def get_access_token():
    try:
        authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
        app = ConfidentialClientApplication(
            AZURE_CLIENT_ID,
            client_credential=AZURE_CLIENT_SECRET,
            authority=authority,
        )
        result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    except Exception as e:
        raise GraphError(f"Could not authenticate with Azure: {e}") from e

    if "access_token" in result:
        return result["access_token"]
    raise GraphError(
        "Azure authentication failed: "
        + result.get("error_description", result.get("error", "unknown error"))
    )


def _headers():
    return {
        "Authorization": f"Bearer {get_access_token()}",
        "Content-Type": "application/json",
    }


def _request(method, url, json_body=None):
    try:
        response = requests.request(method, url, headers=_headers(), json=json_body, timeout=30)
    except requests.RequestException as e:
        raise GraphError(f"Could not reach Microsoft Graph: {e}") from e

    if response.status_code >= 400:
        raise GraphError(
            f"Graph API returned {response.status_code} for {method} {url}: {response.text[:300]}"
        )
    return response.json() if response.text else None


def get_table_columns():
    """Return the table's column headers in order, e.g. ['Index', 'Date', 'Name', ...]."""
    data = _request("GET", f"{TABLE_BASE}/columns")
    columns = sorted(data["value"], key=lambda c: c["index"])
    return [c["name"] for c in columns]


def get_table_rows():
    """Return [{'index': int, 'values': [...]}], one entry per data row (header excluded)."""
    data = _request("GET", f"{TABLE_BASE}/rows")
    return [{"index": row["index"], "values": row["values"][0]} for row in data["value"]]


def add_table_row(values_by_column: dict):
    """Append a new row. Builds the value order fresh from get_table_columns() every call."""
    headers = get_table_columns()
    row_values = [values_by_column.get(h) for h in headers]
    _request("POST", f"{TABLE_BASE}/rows/add", json_body={"values": [row_values]})


def update_table_row(row_index: int, values_by_column: dict):
    """Overwrite an existing row's values in place (identified by its table row index)."""
    headers = get_table_columns()
    row_values = [values_by_column.get(h) for h in headers]
    _request(
        "PATCH",
        f"{TABLE_BASE}/rows/itemAt(index={row_index})",
        json_body={"values": [row_values]},
    )


def delete_table_row(row_index: int):
    """Delete a row from the table (identified by its table row index)."""
    _request("DELETE", f"{TABLE_BASE}/rows/itemAt(index={row_index})")


# ---------------------------------------------------------------------------
# Worksheet range API — for the sheets that aren't Excel Tables.
# ---------------------------------------------------------------------------


def _sheet_url(sheet_name):
    return f"{WORKBOOK_BASE}/worksheets/{quote(sheet_name, safe='')}"


def _range_url(sheet_name, addr):
    return f"{_sheet_url(sheet_name)}/range(address='{addr}')"


def get_sheet_grid(sheet_name):
    """Read a worksheet's used range (values + number formats) as a Grid.

    Called fresh before every write, so a row is always located by its key in
    the sheet as it is now — never by a row number from an earlier page load.
    """
    data = _request(
        "GET",
        f"{_sheet_url(sheet_name)}/usedRange?$select=address,values,numberFormat,rowIndex,columnIndex",
    )
    return Grid.from_used_range(data or {})


def apply_ops(sheet_name, ops):
    """Send a plan from sheet_grid's operation vocabulary to Graph, in order."""
    for op in ops:
        kind = op["op"]
        if kind in ("insert_rows", "delete_rows"):
            # Whole rows, so merged banners and everything else below move with them.
            rows = f"{op['row']}:{op['row'] + op['count'] - 1}"
            action = "insert" if kind == "insert_rows" else "delete"
            shift = "Down" if kind == "insert_rows" else "Up"
            _request("POST", f"{_range_url(sheet_name, rows)}/{action}", json_body={"shift": shift})
        elif kind == "write":
            vals = op["values"]
            addr = address(op["row"], op["col"], op["row"] + len(vals) - 1, op["col"] + len(vals[0]) - 1)
            body = {"values": vals}
            if op.get("formats"):
                body["numberFormat"] = op["formats"]
            _request("PATCH", _range_url(sheet_name, addr), json_body=body)
        elif kind == "merge":
            addr = address(op["row"], op["col"], op["row"], op["to_col"])
            _request("POST", f"{_range_url(sheet_name, addr)}/merge", json_body={"across": False})
        elif kind == "fill":
            addr = address(op["row"], op["col"], op["row"], op["to_col"])
            if op.get("color"):
                _request("PATCH", f"{_range_url(sheet_name, addr)}/format/fill", json_body={"color": op["color"]})
            else:
                _request("POST", f"{_range_url(sheet_name, addr)}/format/fill/clear")
        elif kind == "align":
            addr = address(op["row"], op["col"], op["row"], op["to_col"])
            _request(
                "PATCH", f"{_range_url(sheet_name, addr)}/format",
                json_body={"horizontalAlignment": op["horizontal"]},
            )
        else:
            raise GraphError(f"Unknown sheet operation: {kind!r}")
