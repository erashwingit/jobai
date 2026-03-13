"""
shared/database.py — SQLite deduplication cache only.
Google Sheets is the PRIMARY application tracker.
SQLite stores only job_id hashes to prevent re-scraping/re-applying the same jobs.
"""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from shared.logger import get_logger

logger = get_logger(__name__)

# SQLite is a local dedup cache only — NOT the primary tracker
_DEFAULT_DB_PATH = os.path.expanduser("~/.config/ashvani-job-bot/dedup_cache.db")
DB_PATH = os.getenv("DB_PATH", _DEFAULT_DB_PATH)


def _get_connection() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager for database connections with auto-commit/rollback."""
    conn = _get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    """
    Initialize dedup cache schema.
    SQLite tracks job_id hashes and human_queue only.
    All application status lives in Google Sheets.
    """
    schema = """
    -- Deduplication cache: tracks seen job IDs to avoid re-processing
    CREATE TABLE IF NOT EXISTS seen_jobs (
        job_id      TEXT PRIMARY KEY,
        portal      TEXT NOT NULL,
        company     TEXT NOT NULL,
        role        TEXT NOT NULL,
        jd_url      TEXT,
        jd_raw      TEXT,
        jd_parsed   TEXT,   -- JSON: LLM analysis result
        match_score REAL DEFAULT 0,
        status      TEXT DEFAULT 'SCRAPED',
        scraped_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
        posted_at   DATETIME,
        notes       TEXT,
        CONSTRAINT valid_status CHECK (
            status IN (
                'SCRAPED', 'QUEUED', 'SKIPPED', 'RESUME_READY',
                'RESUME_FAILED', 'APPLIED', 'NEEDS_HUMAN',
                'INTERVIEW_SCHEDULED', 'PREP_READY',
                'REJECTED', 'GHOSTED'
            )
        )
    );

    -- Human intervention queue (local, not in Sheets)
    CREATE TABLE IF NOT EXISTS human_queue (
        queue_id   TEXT PRIMARY KEY,
        job_id     TEXT NOT NULL REFERENCES seen_jobs(job_id),
        reason     TEXT NOT NULL,
        url        TEXT,
        context    TEXT,
        flagged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved   INTEGER DEFAULT 0
    );

    -- Application PDF paths (local reference only)
    CREATE TABLE IF NOT EXISTS applications (
        app_id     TEXT PRIMARY KEY,
        job_id     TEXT NOT NULL REFERENCES seen_jobs(job_id),
        pdf_path   TEXT,
        ats_score  REAL,
        status     TEXT DEFAULT 'PENDING',
        applied_at DATETIME,
        error_log  TEXT
    );

    CREATE INDEX IF NOT EXISTS idx_seen_jobs_status ON seen_jobs(status);
    CREATE INDEX IF NOT EXISTS idx_seen_jobs_portal ON seen_jobs(portal);
    CREATE INDEX IF NOT EXISTS idx_human_queue_resolved ON human_queue(resolved);
    """
    with get_db() as conn:
        conn.executescript(schema)
    logger.info("Dedup cache schema initialized")


def job_exists(job_id: str) -> bool:
    """Check if a job was already processed (dedup check)."""
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM seen_jobs WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
    return count > 0


def update_job_status(job_id: str, status: str, **extra_fields) -> None:
    """Update local dedup cache status. Google Sheets is the source of truth for tracking."""
    set_clauses = ["status = ?"]
    values = [status]
    for field, value in extra_fields.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)
    values.append(job_id)
    query = f"UPDATE seen_jobs SET {', '.join(set_clauses)} WHERE job_id = ?"
    with get_db() as conn:
        conn.execute(query, values)
    logger.debug(f"Dedup cache: job {job_id} → {status}")


def get_jobs_by_status(status: str) -> list[dict]:
    """Fetch jobs from dedup cache by status."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM seen_jobs WHERE status = ? ORDER BY scraped_at DESC",
            (status,)
        ).fetchall()
    return [dict(row) for row in rows]
