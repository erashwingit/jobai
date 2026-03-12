"""
modules/application/session_manager.py — Browser session persistence.
Saves/loads portal login sessions to minimize repeated logins.
"""
import os
import json
import stat
from pathlib import Path

from shared.logger import get_logger

logger = get_logger(__name__)

SESSION_DIR = Path(os.path.expanduser("~/.config/ashvani-job-bot/sessions"))


async def save_session(context, portal: str) -> None:
    """Save browser storage state (cookies + localStorage) for a portal."""
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    session_path = SESSION_DIR / f"{portal}_session.json"

    try:
        storage = await context.storage_state()
        with open(session_path, "w") as f:
            json.dump(storage, f)
        # Security: chmod 600 — owner read/write only
        os.chmod(session_path, stat.S_IRUSR | stat.S_IWUSR)
        logger.info(f"Session saved for portal: {portal}")
    except Exception as e:
        logger.error(f"Failed to save session for {portal}: {e}")


async def load_session(context_options: dict, portal: str) -> dict:
    """Load saved session state into browser context options."""
    session_path = SESSION_DIR / f"{portal}_session.json"

    if session_path.exists():
        # Verify file permissions before loading
        file_stat = session_path.stat()
        if file_stat.st_mode & 0o077:  # Group or other has permissions
            logger.warning(
                f"Session file {session_path} has insecure permissions — skipping"
            )
            return context_options

        context_options["storage_state"] = str(session_path)
        logger.info(f"Loaded saved session for portal: {portal}")
    else:
        logger.info(f"No saved session for {portal} — fresh login required")

    return context_options


def clear_session(portal: str) -> None:
    """Delete saved session (force re-login on next run)."""
    session_path = SESSION_DIR / f"{portal}_session.json"
    if session_path.exists():
        session_path.unlink()
        logger.info(f"Session cleared for portal: {portal}")
