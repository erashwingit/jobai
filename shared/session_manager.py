"""
shared/session_manager.py — Encrypted cookie-based session management.
Security: NEVER stores passwords. Reads AES-256-GCM encrypted cookies only.
"""
import os
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

from shared.logger import get_logger

logger = get_logger(__name__)

COOKIE_FILE = Path(os.path.expanduser("~/.config/ashvani-job-bot/cookies.enc"))
COOKIE_SECRET = os.getenv("COOKIE_SECRET", "")


class CookieExpiredError(Exception):
    """Raised when session cookies are missing or expired."""
    pass


def _decrypt_cookies() -> dict:
    """
    Decrypt the AES-256-GCM encrypted cookie file.
    Encryption is handled by tools/export-cookies.js.

    Returns:
        Dict mapping portal name → list of cookie dicts

    Raises:
        CookieExpiredError: If file missing, secret missing, or decryption fails
    """
    if not COOKIE_FILE.exists():
        raise CookieExpiredError(
            f"Cookie file not found: {COOKIE_FILE}\n"
            "Run: node tools/export-cookies.js"
        )

    if not COOKIE_SECRET:
        raise CookieExpiredError(
            "COOKIE_SECRET environment variable not set. "
            "Add COOKIE_SECRET to your .env file."
        )

    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        from cryptography.hazmat.backends import default_backend

        payload = json.loads(COOKIE_FILE.read_text())

        # Derive key using same scrypt params as Node.js
        salt = bytes.fromhex(payload["salt"])
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1, backend=default_backend())
        key = kdf.derive(COOKIE_SECRET.encode())

        # Decrypt AES-256-GCM
        iv = bytes.fromhex(payload["iv"])
        tag = bytes.fromhex(payload["tag"])
        ciphertext = bytes.fromhex(payload["data"])

        aesgcm = AESGCM(key)
        # GCM: ciphertext || tag
        plaintext = aesgcm.decrypt(iv, ciphertext + tag, None)
        return json.loads(plaintext)

    except ImportError:
        raise CookieExpiredError(
            "cryptography package not installed. Run: pip install cryptography"
        )
    except Exception as e:
        raise CookieExpiredError(
            f"Failed to decrypt cookies: {type(e).__name__}. "
            "Re-run: node tools/export-cookies.js"
        ) from e


def get_cookies(portal: str) -> list[dict]:
    """
    Get decrypted session cookies for a portal.

    Args:
        portal: Portal name (e.g., 'linkedin', 'naukri')

    Returns:
        List of cookie dicts for Playwright's context.add_cookies()

    Raises:
        CookieExpiredError: If cookies missing or expired
    """
    all_cookies = _decrypt_cookies()
    cookies = all_cookies.get(portal, [])

    if not cookies:
        raise CookieExpiredError(
            f"No cookies found for portal: {portal}\n"
            "Run: node tools/export-cookies.js"
        )

    # Check for expired cookies
    now = datetime.now(timezone.utc).timestamp()
    expired = [c for c in cookies if c.get("expires", -1) > 0 and c["expires"] < now]

    if expired:
        raise CookieExpiredError(
            f"{len(expired)} cookie(s) expired for {portal}.\n"
            "Run: node tools/export-cookies.js to refresh."
        )

    logger.info(f"Loaded {len(cookies)} session cookies for {portal}")
    return cookies


async def inject_cookies(context, portal: str) -> None:
    """
    Inject session cookies into a Playwright browser context.
    This replaces all password-based login flows.

    Args:
        context: Playwright BrowserContext
        portal: Portal name

    Raises:
        CookieExpiredError: If cookies are missing or expired
    """
    cookies = get_cookies(portal)
    await context.add_cookies(cookies)
    logger.info(f"Injected {len(cookies)} session cookies for {portal}")


def check_cookie_health(portal: str) -> dict:
    """
    Check cookie health without raising exceptions.

    Returns:
        Dict with: valid (bool), cookie_count, expires_at, message
    """
    try:
        cookies = get_cookies(portal)
        # Find the soonest-expiring session cookie
        expiry_timestamps = [
            c["expires"] for c in cookies
            if c.get("expires", -1) > 0
        ]
        soonest = min(expiry_timestamps) if expiry_timestamps else None
        expires_str = (
            datetime.fromtimestamp(soonest, tz=timezone.utc).isoformat()
            if soonest else "session (no expiry)"
        )
        return {
            "valid": True,
            "cookie_count": len(cookies),
            "expires_at": expires_str,
            "message": f"Cookies valid for {portal}",
        }
    except CookieExpiredError as e:
        return {
            "valid": False,
            "cookie_count": 0,
            "expires_at": None,
            "message": str(e),
        }
