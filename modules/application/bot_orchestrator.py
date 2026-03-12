"""
modules/application/bot_orchestrator.py — Main bot controller.
Coordinates all portal bots, rate limiting, and human checkpoints.
"""
import asyncio
import uuid
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

from modules.application.browser_config import get_stealth_browser
from modules.application.rate_limiter import can_apply
from modules.application.human_checkpoint import flag_for_human, REASON_RESUME_FAILED
from shared.database import get_db, update_job_status, get_jobs_by_status
from shared.logger import get_logger

logger = get_logger(__name__)


async def run_applications(jobs: list[dict] | None = None) -> dict:
    """
    Run the full application pipeline for all RESUME_READY jobs.

    Args:
        jobs: Optional list of specific jobs; fetches RESUME_READY from DB if None

    Returns:
        Summary dict with applied, skipped, flagged counts
    """
    from modules.application.linkedin_bot import LinkedInBot
    from modules.application.naukri_bot import NaukriBot

    if jobs is None:
        jobs = get_jobs_by_status("RESUME_READY")

    if not jobs:
        logger.info("No jobs ready for application")
        return {"applied": 0, "skipped": 0, "flagged": 0}

    stats = {"applied": 0, "skipped": 0, "flagged": 0}

    # Group jobs by portal for efficient browser reuse
    jobs_by_portal: dict[str, list] = {}
    for job in jobs:
        portal = job.get("portal", "unknown")
        jobs_by_portal.setdefault(portal, []).append(job)

    async with async_playwright() as pw:
        for portal, portal_jobs in jobs_by_portal.items():
            if not can_apply(portal):
                logger.warning(f"Daily limit reached for {portal}, skipping {len(portal_jobs)} jobs")
                stats["skipped"] += len(portal_jobs)
                continue

            browser, context = await get_stealth_browser(pw, portal=portal)
            page = await context.new_page()

            try:
                # Instantiate the right bot for this portal
                bot = _get_bot(portal, page, context)
                if not bot:
                    logger.warning(f"No bot implementation for portal: {portal}")
                    stats["skipped"] += len(portal_jobs)
                    continue

                for job in portal_jobs:
                    if not can_apply(portal):
                        logger.info(f"Rate limit hit mid-batch for {portal}")
                        stats["skipped"] += 1
                        continue

                    # Get PDF path from application record
                    pdf_path = _get_pdf_path(job["job_id"])
                    if not pdf_path or not pdf_path.exists():
                        logger.warning(f"No PDF found for job {job['job_id']}")
                        stats["skipped"] += 1
                        continue

                    # Log application attempt
                    app_id = _create_application_record(job["job_id"], str(pdf_path))

                    success = await bot.apply_to_job(job, pdf_path)

                    if success:
                        stats["applied"] += 1
                        _update_application_record(app_id, "APPLIED")
                    else:
                        stats["flagged"] += 1
                        _update_application_record(app_id, "FAILED")

                    # Human-like delay between applications
                    await asyncio.sleep(5)

            except Exception as e:
                logger.error(f"Bot orchestrator error for {portal}: {e}")
            finally:
                await browser.close()

    logger.info(
        f"Application run complete: "
        f"applied={stats['applied']}, "
        f"skipped={stats['skipped']}, "
        f"flagged={stats['flagged']}"
    )
    return stats


def _get_bot(portal: str, page, context):
    """Instantiate the correct bot adapter for a portal."""
    from modules.application.linkedin_bot import LinkedInBot
    from modules.application.naukri_bot import NaukriBot

    bot_map = {
        "linkedin": LinkedInBot,
        "naukri": NaukriBot,
        # "indeed": IndeedBot,      # TODO: implement
        # "angellist": AngelListBot, # TODO: implement
    }

    cls = bot_map.get(portal)
    return cls(page, context) if cls else None


def _get_pdf_path(job_id: str) -> Path | None:
    """Get the resume PDF path for a job from the applications table."""
    with get_db() as conn:
        row = conn.execute(
            "SELECT pdf_path FROM applications WHERE job_id=? ORDER BY rowid DESC LIMIT 1",
            (job_id,)
        ).fetchone()

    if row and row["pdf_path"]:
        return Path(row["pdf_path"])
    return None


def _create_application_record(job_id: str, pdf_path: str) -> str:
    """Create an application record and return the app_id."""
    app_id = str(uuid.uuid4())
    with get_db() as conn:
        conn.execute(
            "INSERT INTO applications (app_id, job_id, pdf_path, status) VALUES (?, ?, ?, ?)",
            (app_id, job_id, pdf_path, "PENDING")
        )
    return app_id


def _update_application_record(app_id: str, status: str) -> None:
    """Update application record status after submission attempt."""
    applied_at = datetime.utcnow().isoformat() if status == "APPLIED" else None
    with get_db() as conn:
        conn.execute(
            "UPDATE applications SET status=?, applied_at=? WHERE app_id=?",
            (status, applied_at, app_id)
        )
