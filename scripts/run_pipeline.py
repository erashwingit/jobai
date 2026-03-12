"""
scripts/run_pipeline.py — Full pipeline orchestrator.
Runs all 5 modules in sequence. Use this for manual/cron runs.

Usage:
    python scripts/run_pipeline.py                    # Full pipeline
    python scripts/run_pipeline.py --module discovery # Single module
    python scripts/run_pipeline.py --dry-run          # Test without applying
"""
import asyncio
import argparse
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

from shared.config_validator import validate_secrets, load_settings, load_profile
from shared.database import init_db
from shared.logger import get_logger

logger = get_logger("pipeline")


async def run_discovery_module() -> list[dict]:
    """Module 1: Scrape portals → deduplicate → analyze → queue."""
    logger.info("=" * 50)
    logger.info("MODULE 1: Job Discovery & Screening")
    logger.info("=" * 50)

    from modules.discovery.scraper import scrape_all_portals
    from modules.discovery.deduplicator import deduplicate_jobs, save_raw_jobs
    from modules.discovery.jd_analyzer import analyze_batch
    from modules.discovery.match_scorer import score_and_queue_jobs
    from shared.config_validator import load_profile

    profile = load_profile()

    # Step 1: Scrape portals
    raw_jobs = await scrape_all_portals()
    logger.info(f"Scraped: {len(raw_jobs)} raw jobs")

    # Step 2: Deduplicate
    new_jobs = deduplicate_jobs(raw_jobs)
    save_raw_jobs(new_jobs)

    # Step 3: Analyze with LLM
    analyzed = await analyze_batch(new_jobs, profile)

    # Step 4: Score and queue
    queued, skipped = score_and_queue_jobs(analyzed)
    logger.info(f"Discovery complete: {len(queued)} queued, {len(skipped)} skipped")

    return queued


def run_resume_module(queued_jobs: list[dict]) -> list[dict]:
    """Module 2: Tailor resumes → compile PDFs → ATS score."""
    logger.info("=" * 50)
    logger.info("MODULE 2: Resume Tailoring Engine")
    logger.info("=" * 50)

    import json
    from modules.resume.tailoring_engine import tailor_resume, save_tailored_resume
    from modules.resume.latex_compiler import compile_resume
    from modules.resume.ats_scorer import (
        extract_text_from_pdf, calculate_ats_score, meets_threshold
    )
    from modules.application.human_checkpoint import flag_for_human, REASON_RESUME_FAILED
    from shared.database import update_job_status, get_db

    ready_jobs = []
    settings = load_settings()
    max_retries = settings.get("resume", {}).get("max_retry_attempts", 1)

    for job in queued_jobs:
        job_id = job["job_id"]
        company = job["company"]
        role = job["role"]

        # Parse stored JD analysis
        jd_parsed = job.get("jd_parsed") or {}
        if isinstance(jd_parsed, str):
            try:
                jd_parsed = json.loads(jd_parsed)
            except json.JSONDecodeError:
                jd_parsed = {}

        if not jd_parsed:
            logger.warning(f"No JD analysis for job {job_id}, skipping resume tailoring")
            continue

        pdf_path = None
        for attempt in range(max_retries + 1):
            try:
                # Tailor resume
                tailored = tailor_resume(job, jd_parsed)
                yaml_path = save_tailored_resume(tailored, company, role)

                # Compile to PDF
                pdf_path = compile_resume(yaml_path, company, role)
                if not pdf_path:
                    continue

                # ATS Score check
                resume_text = extract_text_from_pdf(pdf_path)
                ats_result = calculate_ats_score(resume_text, jd_parsed)

                if meets_threshold(ats_result):
                    # Save PDF path to applications table
                    with get_db() as conn:
                        conn.execute(
                            "INSERT OR IGNORE INTO applications (app_id, job_id, pdf_path, ats_score, status) "
                            "VALUES (?, ?, ?, ?, 'READY')",
                            (__import__('uuid').uuid4().hex, job_id, str(pdf_path), ats_result["total_score"])
                        )

                    update_job_status(job_id, "RESUME_READY")
                    ready_jobs.append({**job, "pdf_path": str(pdf_path)})
                    logger.info(f"Resume ready: {company} | {role} | ATS={ats_result['total_score']}")
                    break
                else:
                    logger.warning(
                        f"ATS score {ats_result['total_score']} below threshold "
                        f"for {company}/{role} (attempt {attempt + 1})"
                    )

            except Exception as e:
                logger.error(f"Resume tailoring failed for {job_id}: {e}")

        if not ready_jobs or ready_jobs[-1]["job_id"] != job_id:
            flag_for_human(
                job_id, company, role, job["jd_url"],
                REASON_RESUME_FAILED
            )

    logger.info(f"Resume module complete: {len(ready_jobs)} resumes ready")
    return ready_jobs


async def run_application_module(ready_jobs: list[dict], dry_run: bool = False) -> dict:
    """Module 3: Auto-apply to jobs via portal bots."""
    logger.info("=" * 50)
    logger.info("MODULE 3: Auto-Application Bot")
    logger.info("=" * 50)

    if dry_run:
        logger.info("DRY RUN: Skipping actual applications")
        return {"applied": 0, "skipped": len(ready_jobs), "flagged": 0, "dry_run": True}

    from modules.application.bot_orchestrator import run_applications
    stats = await run_applications(ready_jobs)
    return stats


def run_email_monitor() -> dict:
    """Module 4: Check Gmail for interview invites/rejections."""
    logger.info("=" * 50)
    logger.info("MODULE 4: Email Monitor & Tracker Update")
    logger.info("=" * 50)

    from modules.tracker.email_parser import run_email_monitor
    stats = run_email_monitor()
    return stats


def run_interview_prep(job_id: str | None = None) -> None:
    """Module 5: Generate interview prep sheets for INTERVIEW_SCHEDULED jobs."""
    logger.info("=" * 50)
    logger.info("MODULE 5: Interview Prep AI")
    logger.info("=" * 50)

    from shared.database import get_jobs_by_status
    from modules.interview_prep.prep_generator import generate_prep_sheet
    from modules.interview_prep.glassdoor_scraper import scrape_glassdoor_interviews
    from modules.interview_prep.docs_writer import create_prep_doc

    if job_id:
        from shared.database import get_db
        with get_db() as conn:
            row = conn.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        jobs = [dict(row)] if row else []
    else:
        jobs = get_jobs_by_status("INTERVIEW_SCHEDULED")

    for job in jobs:
        try:
            # Supplement with Glassdoor data
            glassdoor_data = scrape_glassdoor_interviews(job["company"])

            # Generate prep sheet
            prep_data = generate_prep_sheet(job)

            # Add Glassdoor interview Q&A if available
            if glassdoor_data.get("interview_questions"):
                prep_data["sections"]["glassdoor_insights"] = glassdoor_data

            # Write to Google Docs
            doc_url = create_prep_doc(job, prep_data)
            if doc_url:
                logger.info(f"Prep sheet ready: {doc_url}")

        except Exception as e:
            logger.error(f"Prep generation failed for job {job.get('job_id')}: {e}")


async def main(args: argparse.Namespace) -> None:
    """Main pipeline entry point."""
    logger.info("Ashvani Job Bot — Pipeline Starting")

    # Startup validations
    validate_secrets(strict=not args.dry_run)
    init_db()

    module = args.module

    if module in ("all", "discovery"):
        queued_jobs = await run_discovery_module()
    else:
        from shared.database import get_jobs_by_status
        queued_jobs = get_jobs_by_status("QUEUED")

    if module in ("all", "resume") and queued_jobs:
        ready_jobs = run_resume_module(queued_jobs)
    else:
        from shared.database import get_jobs_by_status
        ready_jobs = get_jobs_by_status("RESUME_READY")

    if module in ("all", "application") and ready_jobs:
        app_stats = await run_application_module(ready_jobs, dry_run=args.dry_run)
        logger.info(f"Application stats: {app_stats}")

    if module in ("all", "email"):
        email_stats = run_email_monitor()
        logger.info(f"Email stats: {email_stats}")

    if module in ("all", "prep"):
        run_interview_prep()

    # Daily summary notification
    if module == "all":
        from modules.discovery.match_scorer import get_daily_stats
        from shared.telegram_notifier import notify_daily_summary
        stats = get_daily_stats()
        notify_daily_summary(
            stats.get("applied", 0),
            stats.get("interview_scheduled", 0),
            stats.get("rejected", 0),
            stats.get("needs_human", 0),
        )

    logger.info("Pipeline run complete")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ashvani Job Application Bot")
    parser.add_argument(
        "--module",
        choices=["all", "discovery", "resume", "application", "email", "prep"],
        default="all",
        help="Run a specific module (default: all)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run pipeline without submitting applications"
    )

    args = parser.parse_args()
    asyncio.run(main(args))
