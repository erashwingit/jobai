"""
modules/tracker/sheets_writer.py — Google Sheets tracker CRUD operations.
Maintains the canonical job application tracker spreadsheet.
"""
import os
from datetime import datetime
from typing import Any

from shared.google_auth import build_service
from shared.logger import get_logger

logger = get_logger(__name__)

# Column mapping for the tracker sheet
# Row 1 = headers, data starts at Row 2
COLUMNS = [
    "Job ID",          # A
    "Company",         # B
    "Role",            # C
    "Portal",          # D
    "Applied Date",    # E
    "Status",          # F
    "Interview Date",  # G
    "Interviewer",     # H
    "Prep Sheet Link", # I
    "Notes",           # J
]

SHEET_NAME = "Applications"


def get_or_create_sheet() -> str:
    """
    Get the spreadsheet ID from environment. Create header row if sheet is empty.

    Returns:
        Spreadsheet ID
    """
    sheet_id = os.getenv("SHEETS_ID")
    if not sheet_id:
        raise ValueError("SHEETS_ID environment variable not set")

    service = build_service("sheets", "v4")

    # Check if header row exists
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{SHEET_NAME}!A1:J1"
    ).execute()

    if not result.get("values"):
        # Initialize with header row
        service.spreadsheets().values().update(
            spreadsheetId=sheet_id,
            range=f"{SHEET_NAME}!A1:J1",
            valueInputOption="RAW",
            body={"values": [COLUMNS]}
        ).execute()
        logger.info("Initialized Google Sheets tracker with header row")

    return sheet_id


def append_application(job: dict) -> str | None:
    """
    Append a new job application row to the tracker.

    Args:
        job: Job dict with company, role, portal, etc.

    Returns:
        Updated range string (e.g., "Applications!A5:J5"), or None on failure
    """
    try:
        sheet_id = get_or_create_sheet()
        service = build_service("sheets", "v4")

        row = [
            job.get("job_id", ""),
            job.get("company", ""),
            job.get("role", ""),
            job.get("portal", ""),
            datetime.utcnow().strftime("%Y-%m-%d"),
            "Applied",
            "",  # Interview Date
            "",  # Interviewer
            "",  # Prep Sheet Link
            job.get("notes", ""),
        ]

        result = service.spreadsheets().values().append(
            spreadsheetId=sheet_id,
            range=f"{SHEET_NAME}!A:J",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": [row]}
        ).execute()

        updated_range = result.get("updates", {}).get("updatedRange", "")
        logger.info(f"Added job to tracker: {job.get('company')} | {job.get('role')}")
        return updated_range

    except Exception as e:
        logger.error(f"Failed to append to Sheets: {e}")
        _save_to_retry_queue("append", job)
        return None


def update_application_status(
    job_id: str,
    status: str,
    interview_date: str | None = None,
    prep_link: str | None = None,
) -> bool:
    """
    Update an existing row's status (e.g., from Applied → Interview Scheduled).

    Args:
        job_id: Job ID to find the row
        status: New status string
        interview_date: Optional interview date string
        prep_link: Optional Google Docs prep sheet URL

    Returns:
        True if updated successfully
    """
    try:
        sheet_id = get_or_create_sheet()
        service = build_service("sheets", "v4")

        # Find the row with this job_id
        row_idx = _find_row_by_job_id(service, sheet_id, job_id)
        if row_idx is None:
            logger.warning(f"Job {job_id} not found in Sheets tracker")
            return False

        # Build updates (only non-None values)
        updates = []

        # Status (Column F = index 5)
        updates.append({
            "range": f"{SHEET_NAME}!F{row_idx}",
            "values": [[status]]
        })

        if interview_date:
            updates.append({
                "range": f"{SHEET_NAME}!G{row_idx}",
                "values": [[interview_date]]
            })

        if prep_link:
            updates.append({
                "range": f"{SHEET_NAME}!I{row_idx}",
                "values": [[prep_link]]
            })

        service.spreadsheets().values().batchUpdate(
            spreadsheetId=sheet_id,
            body={"valueInputOption": "RAW", "data": updates}
        ).execute()

        logger.info(f"Updated Sheets row for job {job_id}: status={status}")
        return True

    except Exception as e:
        logger.error(f"Failed to update Sheets for job {job_id}: {e}")
        return False


def _find_row_by_job_id(service, sheet_id: str, job_id: str) -> int | None:
    """Find the row number (1-indexed) for a given job_id."""
    result = service.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"{SHEET_NAME}!A:A"
    ).execute()

    values = result.get("values", [])
    for idx, row in enumerate(values, start=1):
        if row and row[0] == job_id:
            return idx

    return None


def _save_to_retry_queue(operation: str, data: dict) -> None:
    """Save failed Sheets operations to a local retry queue."""
    import json
    from pathlib import Path

    queue_path = Path("data/retry_queue.json")
    queue_path.parent.mkdir(exist_ok=True)

    queue = []
    if queue_path.exists():
        with open(queue_path) as f:
            try:
                queue = json.load(f)
            except json.JSONDecodeError:
                queue = []

    queue.append({
        "operation": operation,
        "data": data,
        "timestamp": datetime.utcnow().isoformat(),
    })

    with open(queue_path, "w") as f:
        json.dump(queue, f, indent=2)

    logger.info(f"Saved failed Sheets operation to retry queue")


def update_status(job_id: str, status: str) -> bool:
    """
    Convenience alias: update only the status column for a job.
    Called by shared.database.update_job_status() to keep Sheets in sync.

    Args:
        job_id: Job ID to locate in the tracker
        status: New status string (e.g., 'APPLIED', 'INTERVIEW_SCHEDULED')

    Returns:
        True if updated successfully
    """
    return update_application_status(job_id, status)
