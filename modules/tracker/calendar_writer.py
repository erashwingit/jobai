"""
modules/tracker/calendar_writer.py — Google Calendar interview event creation.
Creates interview events with all available details from email parsing.
"""
import os
from datetime import datetime, timedelta, timezone

from shared.google_auth import build_service
from shared.logger import get_logger

logger = get_logger(__name__)


def create_interview_event(
    company: str,
    role: str,
    interview_date: str,
    interview_time: str | None = None,
    interview_format: str | None = None,
    meeting_link: str | None = None,
    interviewer: str | None = None,
    prep_doc_url: str | None = None,
) -> str | None:
    """
    Create a Google Calendar event for an interview.

    Args:
        company: Company name
        role: Job role
        interview_date: Date string (YYYY-MM-DD)
        interview_time: Time string (HH:MM) or None
        interview_format: video|phone|onsite or None
        meeting_link: Video call link or None
        interviewer: Interviewer name or None
        prep_doc_url: Google Docs prep sheet URL or None

    Returns:
        Calendar event ID if created, None on failure
    """
    try:
        calendar_id = os.getenv("CALENDAR_ID", "primary")
        service = build_service("calendar", "v3")

        # Parse date/time
        start_dt, end_dt = _build_event_times(interview_date, interview_time)

        # Build description
        description = _build_description(
            company, role, interview_format, meeting_link, interviewer, prep_doc_url
        )

        # Format: colorId 9 = blueberry (interviews)
        event_body = {
            "summary": f"Interview: {role} @ {company}",
            "description": description,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "Asia/Kolkata",
            },
            "colorId": "9",
            "reminders": {
                "useDefault": False,
                "overrides": [
                    {"method": "popup", "minutes": 60},   # 1 hour before
                    {"method": "popup", "minutes": 1440}, # 1 day before
                ],
            },
        }

        # Add meeting link as conferencing if available
        if meeting_link:
            event_body["location"] = meeting_link

        result = service.events().insert(
            calendarId=calendar_id,
            body=event_body,
            sendNotifications=True
        ).execute()

        event_id = result.get("id")
        event_link = result.get("htmlLink")
        logger.info(f"Calendar event created for {company}/{role}: {event_link}")
        return event_id

    except Exception as e:
        logger.error(f"Failed to create calendar event: {e}")
        return None


def _build_event_times(
    date_str: str,
    time_str: str | None,
) -> tuple[datetime, datetime]:
    """
    Parse date/time strings into start/end datetime objects.
    Defaults to 10:00 AM IST with 1-hour duration if time unknown.
    """
    try:
        if time_str:
            # Combine date and time
            dt_str = f"{date_str} {time_str}"
            formats = ["%Y-%m-%d %H:%M", "%Y-%m-%d %I:%M %p", "%Y-%m-%d %I:%M%p"]
            start_dt = None
            for fmt in formats:
                try:
                    start_dt = datetime.strptime(dt_str, fmt)
                    break
                except ValueError:
                    continue
            if start_dt is None:
                raise ValueError(f"Could not parse: {dt_str}")
        else:
            # Default to 10 AM if time unknown
            start_dt = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=10, minute=0)

    except Exception:
        # Fallback: use tomorrow at 10 AM
        tomorrow = datetime.now(timezone.utc) + timedelta(days=1)
        start_dt = tomorrow.replace(hour=10, minute=0, second=0, microsecond=0)
        logger.warning(f"Could not parse interview date/time, defaulting to tomorrow 10 AM")

    end_dt = start_dt + timedelta(hours=1)
    return start_dt, end_dt


def _build_description(
    company: str,
    role: str,
    interview_format: str | None,
    meeting_link: str | None,
    interviewer: str | None,
    prep_doc_url: str | None,
) -> str:
    """Build a rich event description."""
    lines = [
        f"🏢 Company: {company}",
        f"💼 Role: {role}",
    ]

    if interview_format:
        lines.append(f"📋 Format: {interview_format.title()}")
    if interviewer:
        lines.append(f"👤 Interviewer: {interviewer}")
    if meeting_link:
        lines.append(f"🔗 Meeting Link: {meeting_link}")
    if prep_doc_url:
        lines.append(f"📚 Prep Sheet: {prep_doc_url}")

    lines.append("\n🤖 Created automatically by Ashvani Job Bot")
    return "\n".join(lines)
