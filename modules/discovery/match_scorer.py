"""
modules/discovery/match_scorer.py — Job match scoring and queue management.
Routes qualified jobs to resume tailoring; discards low-score jobs.
"""
from shared.database import get_db, update_job_status, get_jobs_by_status
from shared.telegram_notifier import notify_jobs_queued
from shared.config_validator import load_settings
from shared.logger import get_logger

logger = get_logger(__name__)


def score_and_queue_jobs(analyzed_jobs: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Route analyzed jobs based on match score.

    Args:
        analyzed_jobs: Jobs with match_score populated from LLM analysis

    Returns:
        Tuple of (queued_jobs, skipped_jobs)
    """
    settings = load_settings()
    min_score = settings.get("job_discovery", {}).get("min_match_score", 70)
    profile = load_settings()

    queued = []
    skipped = []

    for job in analyzed_jobs:
        score = job.get("match_score", 0)
        job_id = job["job_id"]

        # Additional filter: exclude blocked keywords/companies
        if _is_excluded(job, profile):
            update_job_status(job_id, "SKIPPED", notes="Excluded by profile filters")
            skipped.append(job)
            continue

        if score >= min_score:
            update_job_status(job_id, "QUEUED")
            queued.append(job)
            logger.info(
                f"Job QUEUED: {job.get('company')} | {job.get('role')} | "
                f"score={score} | portal={job.get('portal')}"
            )
        else:
            update_job_status(job_id, "SKIPPED", notes=f"match_score={score} < threshold={min_score}")
            skipped.append(job)
            logger.debug(f"Job SKIPPED: score {score} < {min_score}")

    # Send Telegram notification grouped by portal
    _notify_by_portal(queued)

    logger.info(
        f"Scoring complete: {len(queued)} queued, {len(skipped)} skipped"
    )
    return queued, skipped


def _is_excluded(job: dict, profile: dict) -> bool:
    """Check if job should be excluded based on profile filters."""
    candidate = profile.get("candidate", {})
    exclude_companies = [c.lower() for c in candidate.get("exclude_companies", [])]
    exclude_keywords = [k.lower() for k in candidate.get("exclude_keywords", [])]

    company_lower = job.get("company", "").lower()
    role_lower = job.get("role", "").lower()
    jd_lower = job.get("jd_raw", "").lower()

    if company_lower in exclude_companies:
        return True

    for keyword in exclude_keywords:
        if keyword in role_lower or keyword in jd_lower:
            return True

    return False


def _notify_by_portal(queued_jobs: list[dict]) -> None:
    """Send grouped Telegram notifications by portal."""
    portal_counts: dict[str, int] = {}
    for job in queued_jobs:
        portal = job.get("portal", "unknown")
        portal_counts[portal] = portal_counts.get(portal, 0) + 1

    for portal, count in portal_counts.items():
        notify_jobs_queued(count, portal)


def get_queued_jobs() -> list[dict]:
    """Fetch all jobs ready for resume tailoring."""
    return get_jobs_by_status("QUEUED")


def get_daily_stats() -> dict:
    """
    Get today's application statistics for the daily summary.
    """
    with get_db() as conn:
        stats = {}

        stats["applied"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='APPLIED' AND DATE(scraped_at)=DATE('now')"
        ).fetchone()[0]

        stats["interview_scheduled"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='INTERVIEW_SCHEDULED'"
        ).fetchone()[0]

        stats["rejected"] = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE status='REJECTED' AND DATE(scraped_at)=DATE('now')"
        ).fetchone()[0]

        stats["needs_human"] = conn.execute(
            "SELECT COUNT(*) FROM human_queue WHERE resolved=0"
        ).fetchone()[0]

    return stats
