"""
shared/credential_manager.py — Secure portal credential retrieval.
Security: Uses OS keychain (macOS/Linux/Windows) with .env fallback.
"""
import os
from shared.logger import get_logger

logger = get_logger(__name__)

SERVICE_NAME = "ashvani-job-bot"


def get_credential(portal: str, field: str) -> str:
    """
    Retrieve portal credential from OS keychain (preferred) or env var (fallback).

    Setup for local dev:
        python -c "import keyring; keyring.set_password('ashvani-job-bot', 'linkedin_email', 'your@email.com')"
        python -c "import keyring; keyring.set_password('ashvani-job-bot', 'linkedin_password', 'yourpassword')"

    Args:
        portal: Portal name (e.g., 'linkedin', 'naukri')
        field: Credential field (e.g., 'email', 'password')

    Returns:
        Credential value

    Raises:
        ValueError: If credential is not found in keychain or env
    """
    key = f"{portal}_{field}"

    # Try OS keychain first (most secure option)
    try:
        import keyring
        value = keyring.get_password(SERVICE_NAME, key)
        if value:
            logger.info(f"Loaded credential from keychain: {portal}/{field}")
            return value
    except Exception as e:
        logger.debug(f"Keychain unavailable: {type(e).__name__}, trying env var")

    # Fallback to environment variable
    env_key = f"{portal.upper()}_{field.upper()}"
    value = os.getenv(env_key)
    if value:
        logger.info(f"Loaded credential from env var: {env_key}")
        return value

    raise ValueError(
        f"Credential not found for {portal}/{field}.\n"
        f"Option 1 (keychain): python -c \"import keyring; "
        f"keyring.set_password('{SERVICE_NAME}', '{key}', 'your_value')\"\n"
        f"Option 2 (.env): Set {env_key}=your_value in .env file"
    )


def set_credential(portal: str, field: str, value: str) -> None:
    """
    Store a credential in the OS keychain.

    Args:
        portal: Portal name (e.g., 'linkedin')
        field: Credential field (e.g., 'email', 'password')
        value: The credential value to store
    """
    try:
        import keyring
        key = f"{portal}_{field}"
        keyring.set_password(SERVICE_NAME, key, value)
        logger.info(f"Credential stored in keychain: {portal}/{field}")
    except Exception as e:
        logger.error(f"Failed to store credential in keychain: {e}")
        raise


def has_credential(portal: str, field: str) -> bool:
    """Check if a credential is available without raising an error."""
    try:
        get_credential(portal, field)
        return True
    except ValueError:
        return False
