"""
modules/tracker/gmail_monitor.py — Gmail API polling for job email responses.
Security: Uses gmail.readonly scope ONLY — no email modification or sending.
"""
import base64
import re
from datetime import datetime, timezone

from shared.google_auth import build_service
from shared.database import get_db
from shared.config_validator import load_settings
from shared.logger import get_logger

logger = get_logger(__name__)


def build_gmail_query(settings: dict) -> str:
    """
    Build Gmail search query to find interview/rejection emails.
    Only reads emails related to job applications.
    """
    interview_kw = settings.get("email_monitor", {}).get(
        "interview_keywords",
        ["interview", "schedule", "invitation", "shortlisted"]
    )
    rejection_kw = settings.get("email_monitor", {}).get(
        "rejection_keywords",
        ["regret", "unfortunately", "not moving forward"]
    )

    all_keywords = interview_kw + rejection_kw
    subject_filters = " OR ".join([f'subject:"{kw}"' for kw in all_keywords])

    # Only unread emails, in inbox, from last 7 days
    query = f"({subject_filters}) is:unread in:inbox newer_than:7d"
    return query


def fetch_unread_job_emails(max_results: int = 50) -> list[dict]:
    """
    Fetch unread job-related emails from Gmail.

    Returns:
        List of email dicts with {gmail_id, subject, sender, body, received_at}
    """
    settings = load_settings()
    service = build_service("gmail", "v1")
    query = build_gmail_query(settings)

    logger.info(f"Fetching Gmail with query: {query[:100]}")

    try:
        # List matching messages
        result = service.users().messages().list(
            userId="me",
            q=query,
            maxResults=max_results
        ).execute()

        messages = result.get("messages", [])
        logger.info(f"Found {len(messages)} matching emails")

        emails = []
        for msg_ref in messages:
            email = _fetch_email_detail(service, msg_ref["id"])
            if email:
                emails.append(email)

        return emails

    except Exception as e:
        logger.error(f"Gmail fetch failed: {type(e).__name__}: {str(e)[:200]}")
        return []


def _fetch_email_detail(service, message_id: str) -> dict | None:
    """Fetch full email content for a given message ID."""
    try:
        message = service.users().messages().get(
            userId="me",
            id=message_id,
            format="full"
        ).execute()

        headers = {h["name"]: h["value"] for h in message["payload"].get("headers", [])}
        subject = headers.get("Subject", "")
        sender = headers.get("From", "")
        date_str = headers.get("Date", "")

        body = _extract_body(message["payload"])
        received_at = _parse_date(date_str)

        # Skip if already processed
        if _is_already_processed(message_id):
            return None

        return {
            "gmail_id": message_id,
            "subject": subject,
            "sender": sender,
            "body": body,
            "received_at": received_at.isoformat() if received_at else None,
        }

    except Exception as e:
        logger.error(f"Failed to fetch email {message_id}: {e}")
        return None


def _extract_body(payload: dict) -> str:
    """Extract plain text body from email payload (handles nested parts)."""
    body = ""

    if payload.get("mimeType") == "text/plain":
        data = payload.get("body", {}).get("data", "")
        if data:
            body = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")

    elif payload.get("mimeType") == "text/html":
        data = payload.get("body", {}).get("data", "")
        if data:
            html = base64.urlsafe_b64decode(data + "==").decode("utf-8", errors="replace")
            # Strip HTML tags
            body = re.sub(r'<[^>]+>', ' ', html)
            body = re.sub(r'\s+', ' ', body).strip()

    # Recurse into parts
    for part in payload.get("parts", []):
        part_body = _extract_body(part)
        if part_body:
            body = part_body
            break

    return body[:5000]  # Truncate for LLM processing


def _parse_date(date_str: str) -> datetime | None:
    """Parse email date header string to datetime."""
    from email.utils import parsedate_to_datetime
    try:
        return parsedate_to_datetime(date_str).replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


def _is_already_processed(gmail_id: str) -> bool:
    """Check if we've already processed this email."""
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE gmail_message_id=?",
            (gmail_id,)
        ).fetchone()[0]
    return count > 0


def mark_email_processed(gmail_id: str) -> None:
    """Mark an email as processed in the database."""
    with get_db() as conn:
        conn.execute(
            "UPDATE emails SET processed=1 WHERE gmail_message_id=?",
            (gmail_id,)
        )
