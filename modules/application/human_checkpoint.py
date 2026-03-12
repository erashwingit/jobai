"""
modules/application/human_checkpoint.py — Flag jobs requiring manual intervention.
Handles CAPTCHAs, complex forms, and other cases the bot can't handle.
"""
import uuid
import json
from datetime import datetime

from shared.database import get_db, update_job_status
from shared.telegram_notifier import notify_needs_human
from shared.logger import get_logger

logger = get_logger(__name__)

# Reasons that trigger human checkpoint
REASON_CAPTCHA = "CAPTCHA detected — manual solving required"
REASON_COMPLEX_FORM = "Complex form with subjective questions"
REASON_LOGIN_REQUIRED = "Login failed or session expired"
REASON_RATE_LIMIT = "Portal rate limit or temporary block detected"
REASON_UNKNOWN_FORM = "Unknown form structure — unable to auto-fill"
REASON_RESUME_FAILED = "Resume ATS score below threshold after retry"


def flag_for_human(
    job_id: str,
    company: str,
    role: str,
    url: str,
    reason: str,
    context: dict | None = None,
) -> str:
    """
    Flag a job for manual human intervention.
    Updates job status to NEEDS_HUMAN and sends Telegram notification.

    Args:
        job_id: Job ID
        company: Company name
        role: Role name
        url: Application URL
        reason: Why human input is needed
        context: Additional context dict (form state, error details, etc.)

    Returns:
        Queue ID for tracking
    """
    queue_id = str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO human_queue (queue_id, job_id, reason, url, context, flagged_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                queue_id,
                job_id,
                reason,
                url,
                json.dumps(context or {}),
                datetime.utcnow().isoformat(),
            )
        )

    update_job_status(job_id, "NEEDS_HUMAN")
    notify_needs_human(company, role, url, reason)

    logger.info(f"Job {job_id} flagged for human review: {reason}")
    return queue_id


def resolve_human_item(queue_id: str, job_id: str) -> None:
    """Mark a human queue item as resolved after manual action."""
    with get_db() as conn:
        conn.execute(
            "UPDATE human_queue SET resolved=1 WHERE queue_id=?",
            (queue_id,)
        )

    update_job_status(job_id, "APPLIED")
    logger.info(f"Human queue item {queue_id} resolved for job {job_id}")


def get_pending_human_items() -> list[dict]:
    """Get all unresolved human queue items."""
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT hq.*, j.company, j.role, j.portal
            FROM human_queue hq
            JOIN jobs j ON hq.job_id = j.job_id
            WHERE hq.resolved = 0
            ORDER BY hq.flagged_at DESC
            """
        ).fetchall()

    return [dict(row) for row in rows]
