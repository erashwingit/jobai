"""
shared/google_auth.py — Google OAuth2 authentication with minimal scopes.
Security: Stores tokens outside project dir with chmod 600 permissions.
"""
import os
import stat
from pathlib import Path
from datetime import datetime, timezone

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

from shared.logger import get_logger

logger = get_logger(__name__)

# Store credentials outside the project directory (never in repo)
_CONFIG_DIR = Path(os.path.expanduser("~/.config/ashvani-job-bot"))
TOKEN_PATH = _CONFIG_DIR / "token.json"
CREDS_PATH = Path(
    os.getenv("GOOGLE_CREDENTIALS_JSON", str(_CONFIG_DIR / "credentials.json"))
)

# ============================================================
# Minimal OAuth scopes — Principle of Least Privilege
# NEVER request gmail.modify, gmail.compose, or drive (full)
# ============================================================
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",      # Read-only inbox
    "https://www.googleapis.com/auth/spreadsheets",        # Tracker read/write
    "https://www.googleapis.com/auth/calendar.events",     # Create interview events
    "https://www.googleapis.com/auth/documents",           # Create prep docs
    "https://www.googleapis.com/auth/drive.file",          # Access only files created by app
]


def get_credentials() -> Credentials:
    """
    Get valid Google OAuth2 credentials.
    Refreshes automatically if expired; triggers browser auth flow on first run.

    Returns:
        Valid Credentials object for Google API clients

    Raises:
        FileNotFoundError: If credentials.json is missing
        RuntimeError: If authentication flow fails
    """
    if not CREDS_PATH.exists():
        raise FileNotFoundError(
            f"Google credentials not found at: {CREDS_PATH}\n"
            f"Download from: https://console.cloud.google.com/apis/credentials\n"
            f"Then place at: {CREDS_PATH}"
        )

    creds: Credentials | None = None

    # Load existing token if available
    if TOKEN_PATH.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
            logger.info("Loaded existing Google OAuth token")
        except Exception as e:
            logger.warning(f"Failed to load token, re-authenticating: {e}")
            creds = None

    # Refresh or re-authenticate as needed
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                logger.info("Google OAuth token refreshed successfully")
            except Exception as e:
                logger.warning(f"Token refresh failed, re-authenticating: {e}")
                creds = _run_auth_flow()
        else:
            creds = _run_auth_flow()

        _save_token(creds)

    _check_token_health(creds)
    return creds


def _run_auth_flow() -> Credentials:
    """Run the OAuth2 browser-based authentication flow."""
    logger.info("Starting Google OAuth2 authentication flow...")
    flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_PATH), SCOPES)
    creds = flow.run_local_server(port=0)
    logger.info("Google OAuth2 authentication completed")
    return creds


def _save_token(creds: Credentials) -> None:
    """Save token with restricted file permissions (owner read/write only)."""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    with open(TOKEN_PATH, "w") as f:
        f.write(creds.to_json())

    # Security: chmod 600 — owner read/write only
    os.chmod(TOKEN_PATH, stat.S_IRUSR | stat.S_IWUSR)
    logger.info(f"Google OAuth token saved to {TOKEN_PATH} (permissions: 600)")


def _check_token_health(creds: Credentials) -> None:
    """Warn via Telegram if token is expiring soon."""
    if creds.expiry:
        time_to_expiry = creds.expiry.replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        if time_to_expiry.total_seconds() < 3600:  # Less than 1 hour
            logger.warning("Google OAuth token expiring within 1 hour")
            try:
                from shared.telegram_notifier import notify
                notify("⚠️ Google OAuth token expiring soon — will auto-refresh on next run")
            except Exception:
                pass  # Don't fail if telegram isn't configured


def build_service(service_name: str, version: str):
    """
    Build a Google API service client.

    Args:
        service_name: e.g., 'gmail', 'sheets', 'calendar', 'docs'
        version: e.g., 'v1', 'v4', 'v3'

    Returns:
        Google API service resource
    """
    from googleapiclient.discovery import build
    creds = get_credentials()
    return build(service_name, version, credentials=creds)
