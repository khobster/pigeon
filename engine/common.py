"""Shared config for Pigeon. Loads .env, exposes the subscriber list."""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

GMAIL_USER = os.getenv("GMAIL_USER")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")
PIGEON_SHEET_ID = os.getenv("PIGEON_SHEET_ID")
GOOGLE_CREDS_PATH = os.getenv("GOOGLE_CREDS_PATH", "./google-creds.json")
SI_API_KEY = os.getenv("SI_API_KEY")
HARVARD_API_KEY = os.getenv("HARVARD_API_KEY")


def require(name, value):
    if not value:
        sys.exit(f"Missing {name} in .env or environment.")
    return value


def subscribers():
    """Return the list of subscriber emails.

    With no sheet configured, returns just GMAIL_USER (test mode) so the
    pipeline can run end to end before a real list exists.
    """
    if not PIGEON_SHEET_ID:
        return [require("GMAIL_USER", GMAIL_USER)]

    import gspread
    from google.oauth2.service_account import Credentials

    creds_path = Path(GOOGLE_CREDS_PATH)
    if not creds_path.is_absolute():
        creds_path = PROJECT_ROOT / creds_path
    creds = Credentials.from_service_account_file(
        str(creds_path),
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    # Google's API throws transient 500s now and then (it cost us the
    # 2026-06-05 send). Retry with backoff before giving up.
    last = None
    for attempt in range(5):
        try:
            sheet = gspread.authorize(creds).open_by_key(PIGEON_SHEET_ID).sheet1
            rows = sheet.get_all_records()
            emails = [r["email"].strip() for r in rows if r.get("email", "").strip()]
            return emails or [require("GMAIL_USER", GMAIL_USER)]
        except Exception as e:  # noqa: BLE001
            last = e
            wait = 15 * (attempt + 1)
            print(f"  [retry] sheet read failed ({e}); waiting {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"subscriber sheet unreachable after retries: {last}")
