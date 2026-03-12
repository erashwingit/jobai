"""
modules/interview_prep/docs_writer.py — Google Docs prep sheet writer.
Creates and formats interview prep documents in Google Docs.
"""
import json
import os
from datetime import datetime

from shared.google_auth import build_service
from shared.database import get_db, update_job_status
from shared.telegram_notifier import notify_prep_ready
from shared.logger import get_logger

logger = get_logger(__name__)


def create_prep_doc(job: dict, prep_data: dict) -> str | None:
    """
    Create a formatted Google Docs prep sheet for an interview.

    Args:
        job: Job dict with company, role, job_id
        prep_data: Generated prep sheet dict from prep_generator

    Returns:
        Google Docs URL, or None on failure
    """
    try:
        docs_service = build_service("docs", "v1")
        drive_service = build_service("drive", "v3")

        company = job.get("company", "Unknown")
        role = job.get("role", "Unknown")
        date_str = datetime.utcnow().strftime("%Y-%m-%d")

        # Create the document
        doc_title = f"Interview Prep: {role} @ {company} [{date_str}]"
        doc = docs_service.documents().create(
            body={"title": doc_title}
        ).execute()

        doc_id = doc["documentId"]
        doc_url = f"https://docs.google.com/document/d/{doc_id}/edit"

        # Build the document content
        requests = _build_document_requests(prep_data, company, role)

        # Apply all formatting in one batch
        docs_service.documents().batchUpdate(
            documentId=doc_id,
            body={"requests": requests}
        ).execute()

        # Move to prep sheets folder if configured
        folder_id = os.getenv("DRIVE_FOLDER_ID")
        if folder_id:
            drive_service.files().update(
                fileId=doc_id,
                addParents=folder_id,
                removeParents="root",
                fields="id, parents"
            ).execute()

        # Update database
        _save_prep_sheet(job["job_id"], doc_id, doc_url)
        update_job_status(job["job_id"], "PREP_READY")

        # Notify via Telegram
        notify_prep_ready(company, role, doc_url)

        logger.info(f"Prep sheet created: {doc_url}")
        return doc_url

    except Exception as e:
        logger.error(f"Failed to create prep doc for {job.get('company')}: {e}")
        return None


def _build_document_requests(prep_data: dict, company: str, role: str) -> list[dict]:
    """Build Google Docs API requests to populate the prep sheet."""
    requests = []
    insert_index = 1  # Google Docs text index (1-based)

    def append_text(text: str, style: str = "NORMAL_TEXT") -> None:
        nonlocal insert_index
        requests.append({
            "insertText": {
                "location": {"index": insert_index},
                "text": text
            }
        })
        # Apply paragraph style
        requests.append({
            "updateParagraphStyle": {
                "range": {
                    "startIndex": insert_index,
                    "endIndex": insert_index + len(text)
                },
                "paragraphStyle": {"namedStyleType": style},
                "fields": "namedStyleType"
            }
        })
        insert_index += len(text)

    sections = prep_data.get("sections", {})

    # Title
    append_text(f"Interview Prep: {role} @ {company}\n", "TITLE")
    append_text(f"Generated: {prep_data.get('generated_at', '')[:10]}\n\n", "NORMAL_TEXT")

    # Company Overview
    append_text("Company Overview\n", "HEADING_1")
    append_text(sections.get("company_overview", "") + "\n\n", "NORMAL_TEXT")

    # Role Analysis
    append_text("Role Analysis\n", "HEADING_1")
    append_text(sections.get("role_analysis", "") + "\n\n", "NORMAL_TEXT")

    # Behavioral Questions
    append_text("HR / Behavioral Questions\n", "HEADING_1")
    for q in sections.get("behavioral_questions", []):
        if isinstance(q, dict):
            append_text(f"Q: {q.get('question', '')}\n", "HEADING_3")
            append_text(f"Assessing: {q.get('assessing', '')}\n", "NORMAL_TEXT")
            append_text(f"Framework: {q.get('framework', '')}\n\n", "NORMAL_TEXT")

    # Technical Questions
    append_text("Technical Questions\n", "HEADING_1")
    for q in sections.get("technical_questions", []):
        if isinstance(q, dict):
            difficulty = q.get('difficulty', '')
            append_text(f"Q [{difficulty.upper()}]: {q.get('question', '')}\n", "HEADING_3")
            key_points = q.get('key_points', [])
            if key_points:
                append_text(f"Key points: {', '.join(key_points)}\n\n", "NORMAL_TEXT")

    # STAR Stories
    append_text("STAR Stories\n", "HEADING_1")
    for story in sections.get("star_stories", []):
        if isinstance(story, dict):
            append_text(f"Theme: {story.get('theme', '')}\n", "HEADING_3")
            for key in ["situation", "task", "action", "result"]:
                append_text(f"  {key.upper()}: {story.get(key, '')}\n", "NORMAL_TEXT")
            append_text("\n", "NORMAL_TEXT")

    # Managerial Questions
    append_text("Managerial Questions\n", "HEADING_1")
    for q in sections.get("managerial_questions", []):
        if isinstance(q, dict):
            append_text(f"Q: {q.get('question', '')}\n", "HEADING_3")
            append_text(f"Tip: {q.get('tip', '')}\n\n", "NORMAL_TEXT")

    # Questions to Ask
    append_text("Questions to Ask Interviewer\n", "HEADING_1")
    for q in sections.get("questions_to_ask", []):
        append_text(f"• {q}\n", "NORMAL_TEXT")

    return requests


def _save_prep_sheet(job_id: str, doc_id: str, doc_url: str) -> None:
    """Persist prep sheet record to database."""
    import uuid
    prep_id = str(uuid.uuid4())

    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO prep_sheets
                (prep_id, job_id, doc_id, doc_url, generated_at, status)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, 'READY')
            """,
            (prep_id, job_id, doc_id, doc_url)
        )
