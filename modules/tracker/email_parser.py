"""
modules/tracker/email_parser.py — LLM-powered email classification and data extraction.
Identifies interview invites and rejections; extracts interview details.
"""
import uuid
import json
from datetime import datetime

from shared.llm_client import get_llm_client
from shared.database import get_db, update_job_status
from shared.telegram_notifier import notify_interview_scheduled, notify_rejected
from shared.config_validator import load_settings
from shared.logger import get_logger

logger = get_logger(__name__)


def match_email_to_job(email: dict) -> str | None:
    """
    Try to match an email to a known job application using company name / domain.

    Args:
        email: Email dict with subject, sender, body

    Returns:
        job_id if matched, None otherwise
    """
    sender = email.get("sender", "").lower()
    subject = email.get("subject", "").lower()
    body = email.get("body", "").lower()

    # Extract sender domain
    domain_match = __import__('re').search(r'@([\w.-]+)', sender)
    sender_domain = domain_match.group(1) if domain_match else ""

    # Try to find matching application by company name in email
    with get_db() as conn:
        rows = conn.execute(
            "SELECT job_id, company FROM jobs WHERE status IN ('APPLIED', 'INTERVIEW_SCHEDULED')"
        ).fetchall()

    for row in rows:
        company = row["company"].lower()
        company_domain = company.replace(" ", "").replace(",", "").replace(".", "")

        # Match by company name in email text
        if (company in subject or company in body[:500] or
                company_domain in sender_domain or
                sender_domain in company):
            logger.info(f"Email matched to job: {row['job_id']} ({row['company']})")
            return row["job_id"]

    logger.debug(f"No job match found for email from: {sender}")
    return None


def process_email(email: dict) -> dict | None:
    """
    Process a single email: classify it and update job status accordingly.

    Args:
        email: Email dict {gmail_id, subject, sender, body, received_at}

    Returns:
        Processing result dict, or None if skipped
    """
    settings = load_settings()
    threshold = settings.get("email_monitor", {}).get("parse_confidence_threshold", 0.80)

    llm = get_llm_client()

    try:
        # Classify email using LLM
        parsed = llm.parse_email(
            email_subject=email.get("subject", ""),
            email_body=email.get("body", ""),
        )

        email_type = parsed.get("email_type", "other")
        confidence = parsed.get("confidence", 0)

        logger.info(
            f"Email classified: type={email_type}, confidence={confidence:.2f}"
        )

        # Skip low-confidence classifications
        if confidence < threshold and email_type != "other":
            logger.info(f"Low confidence ({confidence:.2f}) — skipping email processing")
            return None

        # Match to a job
        job_id = match_email_to_job(email)
        company = parsed.get("company_name", "Unknown Company")

        # Save email to database
        email_db_id = _save_email(email, job_id, email_type, parsed, confidence)

        # Handle by type
        if email_type == "interview_invite" and job_id:
            _handle_interview_invite(job_id, parsed, company)
        elif email_type == "rejection" and job_id:
            _handle_rejection(job_id, parsed, company)

        return {
            "email_id": email_db_id,
            "job_id": job_id,
            "email_type": email_type,
            "confidence": confidence,
            "parsed": parsed,
        }

    except Exception as e:
        logger.error(f"Email processing failed: {e}")
        return None


def _handle_interview_invite(job_id: str, parsed: dict, company: str) -> None:
    """Update job status and trigger calendar/prep sheet creation."""
    update_job_status(job_id, "INTERVIEW_SCHEDULED")

    interview_date = parsed.get("interview_date", "TBD")
    interview_format = parsed.get("interview_format", "TBD")

    # Get role for notification
    with get_db() as conn:
        row = conn.execute("SELECT role FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    role = row["role"] if row else "Unknown Role"

    notify_interview_scheduled(company, role, interview_date, interview_format)
    logger.info(f"Interview invite processed for job {job_id}: {interview_date}")


def _handle_rejection(job_id: str, parsed: dict, company: str) -> None:
    """Update job status to REJECTED."""
    update_job_status(job_id, "REJECTED")

    with get_db() as conn:
        row = conn.execute("SELECT role FROM jobs WHERE job_id=?", (job_id,)).fetchone()
    role = row["role"] if row else "Unknown Role"

    notify_rejected(company, role)
    logger.info(f"Rejection processed for job {job_id}")


def _save_email(
    email: dict,
    job_id: str | None,
    email_type: str,
    parsed: dict,
    confidence: float,
) -> str:
    """Persist processed email to database."""
    email_id = str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO emails
                (email_id, job_id, gmail_message_id, email_type, parsed_data, confidence, received_at, processed)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                email_id,
                job_id,
                email.get("gmail_id"),
                email_type,
                json.dumps(parsed),
                confidence,
                email.get("received_at"),
            )
        )

    return email_id


def run_email_monitor() -> dict:
    """
    Full email monitor pipeline: fetch → classify → update.
    Returns summary stats.
    """
    from modules.tracker.gmail_monitor import fetch_unread_job_emails, mark_email_processed

    emails = fetch_unread_job_emails()
    stats = {"processed": 0, "interviews": 0, "rejections": 0, "unmatched": 0}

    for email in emails:
        result = process_email(email)
        if result:
            stats["processed"] += 1
            if result["email_type"] == "interview_invite":
                stats["interviews"] += 1
            elif result["email_type"] == "rejection":
                stats["rejections"] += 1
            if not result["job_id"]:
                stats["unmatched"] += 1

            # Mark as processed only after successful handling
            mark_email_processed(email["gmail_id"])

    logger.info(f"Email monitor run complete: {stats}")
    return stats
