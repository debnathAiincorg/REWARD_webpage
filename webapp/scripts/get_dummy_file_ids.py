# One-off helper: resolve a SharePoint "Share" link into the (Drive ID, Item ID)
# pair that config.py needs. Run it, read the printed File name/Drive ID/Item ID,
# and only paste them into config.py once you've confirmed the file name is right.
#
# Reusable for the later MAIN cutover too — just swap SHARING_LINK to the
# production file's share link and re-run.

import base64
import os
from pathlib import Path

import requests
from dotenv import load_dotenv
from msal import ConfidentialClientApplication

# Paste the SharePoint "Share" link for the target file here.
SHARING_LINK = "https://cloudaiorg.sharepoint.com/:x:/s/Programmers/IQDkThZiVXZ2Q6LC8Qpikga_ATVld28aVM2HenYvpdR2ih4?e=bUsKXk"

# Same repo-root .env that webapp/ uses — no duplicated credentials.
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env")

AZURE_CLIENT_ID = os.environ.get("AZURE_CLIENT_ID")
AZURE_TENANT_ID = os.environ.get("AZURE_TENANT_ID")
AZURE_CLIENT_SECRET = os.environ.get("AZURE_CLIENT_SECRET")


def get_access_token():
    authority = f"https://login.microsoftonline.com/{AZURE_TENANT_ID}"
    app = ConfidentialClientApplication(
        AZURE_CLIENT_ID, client_credential=AZURE_CLIENT_SECRET, authority=authority
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise RuntimeError(
            "Azure authentication failed: "
            + result.get("error_description", result.get("error", "unknown error"))
        )
    return result["access_token"]


def encode_sharing_url(url: str) -> str:
    """Microsoft Graph's documented base64 encoding for the /shares/{id} endpoint."""
    b64 = base64.b64encode(url.encode("utf-8")).decode("utf-8")
    b64 = b64.rstrip("=").replace("/", "_").replace("+", "-")
    return "u!" + b64


def main():
    if not (AZURE_CLIENT_ID and AZURE_TENANT_ID and AZURE_CLIENT_SECRET):
        raise RuntimeError(
            "Missing AZURE_CLIENT_ID/AZURE_TENANT_ID/AZURE_CLIENT_SECRET — "
            "check that d:\\REWARDS\\.env exists and has all three."
        )
    if "PUT_SHARING_LINK_HERE" in SHARING_LINK:
        raise RuntimeError("Set SHARING_LINK to the actual SharePoint share link first.")

    token = get_access_token()
    encoded = encode_sharing_url(SHARING_LINK)
    url = f"https://graph.microsoft.com/v1.0/shares/{encoded}/driveItem?$select=id,name,parentReference"
    response = requests.get(url, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    response.raise_for_status()
    data = response.json()

    name = data.get("name")
    item_id = data.get("id")
    drive_id = data.get("parentReference", {}).get("driveId")

    print(f"File name: {name}")
    print(f"Drive ID:  {drive_id}")
    print(f"Item ID:   {item_id}")


if __name__ == "__main__":
    main()
