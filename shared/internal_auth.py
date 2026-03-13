"""
shared/internal_auth.py — HMAC-SHA256 inter-service request signing.

Used for Python→Node.js calls to the submitter microservice.
Every request to /submit must carry a timestamped HMAC signature to prevent
unauthorised callers from invoking the service even on localhost.

Security design:
  - Token = HMAC-SHA256(key=INTERNAL_TOKEN, msg=<timestamp_minute>:<portal>:<job_id>)
  - Timestamp is truncated to the current minute — Node.js validates ±1 minute window
  - Shared secret is INTERNAL_TOKEN env var (min 32 chars enforced)
  - This is NOT a substitute for network-level isolation; it is a defence-in-depth layer
"""
import hashlib
import hmac
import os
import time

from shared.logger import get_logger

logger = get_logger(__name__)

_INTERNAL_TOKEN_KEY = "INTERNAL_TOKEN"
_MIN_TOKEN_LENGTH = 32


def _get_token() -> bytes:
    """Read and validate the INTERNAL_TOKEN secret from env."""
    token = os.getenv(_INTERNAL_TOKEN_KEY, "")
    if len(token) < _MIN_TOKEN_LENGTH:
        raise ValueError(
            f"INTERNAL_TOKEN must be at least {_MIN_TOKEN_LENGTH} characters. "
            f"Generate with: python -c \"import secrets; print(secrets.token_hex(32))\""
        )
    return token.encode()


def sign_request(portal: str, job_id: str) -> dict[str, str]:
    """
    Generate HMAC-SHA256 auth headers for a submitter service request.

    Args:
        portal:  Portal name (e.g. 'linkedin')
        job_id:  Job identifier for the request

    Returns:
        Dict of headers to merge into the httpx request:
        {
            'X-Internal-Token': '<hex_signature>',
            'X-Timestamp':      '<unix_minute>',
        }

    Raises:
        ValueError: If INTERNAL_TOKEN is not set or too short
    """
    key = _get_token()
    # Truncate to the current minute for ±1 min replay window
    timestamp_minute = str(int(time.time()) // 60)
    message = f"{timestamp_minute}:{portal}:{job_id}".encode()
    signature = hmac.new(key, message, hashlib.sha256).hexdigest()

    return {
        "X-Internal-Token": signature,
        "X-Timestamp": timestamp_minute,
    }


def verify_signature(portal: str, job_id: str, signature: str, timestamp_str: str) -> bool:
    """
    Verify an incoming HMAC signature (Python-side helper for tests).

    Args:
        portal:        Portal name
        job_id:        Job identifier
        signature:     Hex signature from X-Internal-Token header
        timestamp_str: Minute timestamp from X-Timestamp header

    Returns:
        True if signature is valid within ±1 minute window
    """
    try:
        key = _get_token()
        request_minute = int(timestamp_str)
        current_minute = int(time.time()) // 60

        # Allow ±1 minute clock drift
        if abs(current_minute - request_minute) > 1:
            logger.warning("HMAC timestamp outside ±1 minute window — replay attack?")
            return False

        message = f"{timestamp_str}:{portal}:{job_id}".encode()
        expected = hmac.new(key, message, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)

    except Exception as e:
        logger.error(f"Signature verification error: {e}")
        return False
