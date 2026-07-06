# Thin wrapper around the Microsoft Graph Excel workbook API for Table1.
# All identity (which file) comes from config.py — nothing here hardcodes a
# Drive ID or Item ID.

import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from msal import ConfidentialClientApplication

from config import DRIVE_ID, ITEM_ID, TABLE_NAME

# Reuse the same repo-root .env as weekly_report_send_teams.py — single source
# of truth for Azure credentials, regardless of the process's working directory.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
TABLE_BASE = f"{GRAPH_BASE}/drives/{DRIVE_ID}/items/{ITEM_ID}/workbook/tables/{TABLE_NAME}"


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
