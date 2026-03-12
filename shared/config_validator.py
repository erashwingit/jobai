"""
shared/config_validator.py — Startup validation of required secrets and config.
Security: Validates presence (not values) of required env vars at startup.
"""
import os
import sys
import yaml
from pathlib import Path
from shared.logger import get_logger

logger = get_logger(__name__)

REQUIRED_SECRETS = [
    "GEMINI_API_KEY",
    "GROQ_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_CHAT_ID",
    "SHEETS_ID",
]

OPTIONAL_SECRETS = [
    "GOOGLE_CREDENTIALS_JSON",
    "APIFY_API_TOKEN",
    "DB_ENCRYPTION_KEY",
]


def validate_secrets(strict: bool = True) -> bool:
    """
    Validate that required environment variables are set.
    Security: Never logs the actual values, only key names.

    Args:
        strict: If True, exit process on missing secrets

    Returns:
        True if all required secrets are present
    """
    missing = [k for k in REQUIRED_SECRETS if not os.getenv(k)]
    optional_missing = [k for k in OPTIONAL_SECRETS if not os.getenv(k)]

    if optional_missing:
        logger.warning(f"Optional secrets not configured: {optional_missing}")

    if missing:
        logger.error(f"Missing required secrets: {missing}")
        if strict:
            print(
                f"\n[FATAL] Missing required environment variables: {missing}\n"
                f"Copy .env.example to .env and fill in the values.\n",
                file=sys.stderr
            )
            sys.exit(1)
        return False

    # Validate format (not value) of critical keys
    _validate_key_formats()

    logger.info("All required secrets validated successfully")
    return True


def _validate_key_formats() -> None:
    """Validate key formats without logging values."""
    gemini_key = os.getenv("GEMINI_API_KEY", "")
    if gemini_key and not gemini_key.startswith("AIza"):
        logger.warning("GEMINI_API_KEY format unexpected (should start with 'AIza')")

    chat_id = os.getenv("TELEGRAM_CHAT_ID", "")
    if chat_id and not (chat_id.lstrip("-").isdigit()):
        logger.warning("TELEGRAM_CHAT_ID should be a numeric value")


def load_settings() -> dict:
    """Load and return settings.yaml as a dictionary."""
    settings_path = Path("config/settings.yaml")
    if not settings_path.exists():
        logger.error(f"Settings file not found: {settings_path}")
        return {}

    with open(settings_path) as f:
        return yaml.safe_load(f) or {}


def load_profile() -> dict:
    """Load and return profile.yaml as a dictionary."""
    profile_path = Path("config/profile.yaml")
    if not profile_path.exists():
        logger.error(f"Profile file not found: {profile_path}")
        return {}

    with open(profile_path) as f:
        return yaml.safe_load(f) or {}
