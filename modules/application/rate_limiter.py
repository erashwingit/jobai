"""
modules/application/rate_limiter.py — Daily application rate limiting per portal.
Prevents account bans by enforcing configurable daily caps.
"""
from datetime import date
from shared.database import get_db
from shared.config_validator import load_settings
from shared.logger import get_logger

logger = get_logger(__name__)

# Default daily limits if not set in settings.yaml
DEFAULT_LIMITS = {
    "linkedin": 25,
    "naukri": 30,
    "indeed": 20,
    "angellist": 15,
    "glassdoor": 15,
    "instahiring": 20,
}


def _get_limits() -> dict[str, int]:
    settings = load_settings()
    limit = settings.get("application", {}).get("daily_limit_per_portal", 25)
    return {portal: limit for portal in DEFAULT_LIMITS}


def can_apply(portal: str) -> bool:
    """Check if we can apply on this portal today (under daily limit)."""
    today = date.today().isoformat()
    limits = _get_limits()
    daily_limit = limits.get(portal, 20)

    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM applications a "
            "JOIN jobs j ON a.job_id = j.job_id "
            "WHERE j.portal=? AND DATE(a.applied_at)=? AND a.status='APPLIED'",
            (portal, today)
        ).fetchone()[0]

    remaining = daily_limit - count
    if remaining <= 0:
        logger.warning(f"Daily limit reached for {portal}: {count}/{daily_limit}")
        return False

    logger.debug(f"Rate limit check {portal}: {count}/{daily_limit} used, {remaining} remaining")
    return True


def get_remaining(portal: str) -> int:
    """Get remaining applications allowed today for a portal."""
    today = date.today().isoformat()
    limits = _get_limits()
    daily_limit = limits.get(portal, 20)

    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM applications a "
            "JOIN jobs j ON a.job_id = j.job_id "
            "WHERE j.portal=? AND DATE(a.applied_at)=?",
            (portal, today)
        ).fetchone()[0]

    return max(0, daily_limit - count)
