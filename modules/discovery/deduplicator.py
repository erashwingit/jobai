"""
modules/discovery/deduplicator.py — SQLite-based job deduplication.
Filters out already-seen jobs and fetches full JD text for new ones.
"""
from shared.database import get_db, job_exists
from shared.logger import get_logger

logger = get_logger(__name__)


def deduplicate_jobs(raw_jobs: list[dict]) -> list[dict]:
    """
    Filter out jobs already in the database.

    Args:
        raw_jobs: List of raw job dicts from scrapers

    Returns:
        List of new jobs not seen before
    """
    new_jobs = []
    duplicate_count = 0

    for job in raw_jobs:
        if job_exists(job["job_id"]):
            duplicate_count += 1
        else:
            new_jobs.append(job)

    logger.info(
        f"Deduplication: {len(raw_jobs)} total, "
        f"{len(new_jobs)} new, {duplicate_count} duplicates"
    )
    return new_jobs


def save_raw_jobs(jobs: list[dict]) -> int:
    """
    Persist new raw jobs to the database with status=SCRAPED.

    Args:
        jobs: List of new job dicts

    Returns:
        Number of jobs saved
    """
    if not jobs:
        return 0

    query = """
        INSERT OR IGNORE INTO jobs
            (job_id, portal, company, role, location, jd_url, jd_raw, status, scraped_at, posted_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'SCRAPED', CURRENT_TIMESTAMP, ?)
    """

    saved = 0
    with get_db() as conn:
        for job in jobs:
            try:
                conn.execute(query, (
                    job["job_id"],
                    job["portal"],
                    job["company"],
                    job["role"],
                    job.get("location", ""),
                    job["jd_url"],
                    job.get("jd_raw", ""),
                    job.get("posted_at"),
                ))
                saved += 1
            except Exception as e:
                logger.error(f"Failed to save job {job.get('job_id')}: {e}")

    logger.info(f"Saved {saved}/{len(jobs)} new jobs to database")
    return saved
