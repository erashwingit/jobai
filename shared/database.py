"""
shared/database.py — SQLite connection manager with schema initialization.
Uses standard sqlite3 (SQLCipher optional via DB_ENCRYPTION_KEY env var).
"""
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from typing import Generator

from shared.logger import get_logger

logger = get_logger(__name__)

# Default DB path — stored outside project dir for security
_DEFAULT_DB_PATH = os.path.expanduser("~/.config/ashvani-job-bot/job_tracker.db")
DB_PATH = os.getenv("DB_PATH", _DEFAULT_DB_PATH)
DB_KEY = os.getenv("DB_ENCRYPTION_KEY")  # Optional: enables SQLCipher encryption


def _get_connection() -> sqlite3.Connection:
    """
    Create a SQLite connection. Uses SQLCipher if DB_ENCRYPTION_KEY is set.
    Falls back to standard sqlite3 if sqlcipher3 is not installed.
    """
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    if DB_KEY:
        try:
            from sqlcipher3 import dbapi2 as sqlcipher  # type: ignore
            conn = sqlcipher.connect(DB_PATH)
            conn.execute(f"PRAGMA key='{DB_KEY}'")
            conn.execute("PRAGMA cipher_page_size = 4096")
            conn.execute("PRAGMA kdf_iter = 64000")
            conn.execute("PRAGMA cipher_hmac_algorithm = HMAC_SHA512")
            logger.info("Connected to encrypted SQLite database")
            return conn
        except ImportError:
            logger.warning(
                "sqlcipher3 not installed — falling back to unencrypted SQLite. "
                "Run: pip install sqlcipher3 for encryption."
            )

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Access columns by name
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
    Initialize all database tables. Safe to call multiple times (IF NOT EXISTS).
    Run once during setup.
    """
    schema = """
    -- ============================================================
    -- Jobs: discovered from portals (Module 1)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS jobs (
        job_id       TEXT PRIMARY KEY,
        portal       TEXT NOT NULL,
        company      TEXT NOT NULL,
        role         TEXT NOT NULL,
        location     TEXT,
        jd_url       TEXT NOT NULL,
        jd_raw       TEXT,
        jd_parsed    TEXT,           -- JSON: {skills, experience_years, keywords}
        match_score  REAL DEFAULT 0,
        status       TEXT DEFAULT 'SCRAPED',
        scraped_at   DATETIME DEFAULT CURRENT_TIMESTAMP,
        posted_at    DATETIME,
        notes        TEXT,
        CONSTRAINT valid_status CHECK (
            status IN (
                'SCRAPED', 'QUEUED', 'SKIPPED', 'RESUME_READY',
                'RESUME_FAILED', 'APPLIED', 'NEEDS_HUMAN',
                'INTERVIEW_SCHEDULED', 'PREP_READY',
                'REJECTED', 'GHOSTED'
            )
        )
    );

    -- ============================================================
    -- Applications: submission records (Module 3)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS applications (
        app_id       TEXT PRIMARY KEY,
        job_id       TEXT NOT NULL REFERENCES jobs(job_id),
        pdf_path     TEXT,
        ats_score    REAL,
        status       TEXT DEFAULT 'PENDING',
        applied_at   DATETIME,
        sheets_row   TEXT,           -- Google Sheets row ID / range
        error_log    TEXT
    );

    -- ============================================================
    -- Emails: parsed Gmail responses (Module 4)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS emails (
        email_id         TEXT PRIMARY KEY,
        job_id           TEXT REFERENCES jobs(job_id),
        gmail_message_id TEXT UNIQUE NOT NULL,
        email_type       TEXT,       -- interview_invite | rejection | other
        parsed_data      TEXT,       -- JSON: {date, time, interviewer, location}
        confidence       REAL,
        received_at      DATETIME,
        processed        INTEGER DEFAULT 0
    );

    -- ============================================================
    -- Prep sheets: interview prep documents (Module 5)
    -- ============================================================
    CREATE TABLE IF NOT EXISTS prep_sheets (
        prep_id      TEXT PRIMARY KEY,
        job_id       TEXT NOT NULL REFERENCES jobs(job_id),
        doc_id       TEXT,           -- Google Docs document ID
        doc_url      TEXT,
        generated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        status       TEXT DEFAULT 'PENDING'
    );

    -- ============================================================
    -- Human queue: items requiring manual intervention
    -- ============================================================
    CREATE TABLE IF NOT EXISTS human_queue (
        queue_id   TEXT PRIMARY KEY,
        job_id     TEXT NOT NULL REFERENCES jobs(job_id),
        reason     TEXT NOT NULL,
        url        TEXT,
        context    TEXT,             -- JSON: additional context
        flagged_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        resolved   INTEGER DEFAULT 0
    );

    -- ============================================================
    -- Indexes for common query patterns
    -- ============================================================
    CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status);
    CREATE INDEX IF NOT EXISTS idx_jobs_portal ON jobs(portal);
    CREATE INDEX IF NOT EXISTS idx_jobs_scraped_at ON jobs(scraped_at);
    CREATE INDEX IF NOT EXISTS idx_applications_job_id ON applications(job_id);
    CREATE INDEX IF NOT EXISTS idx_emails_processed ON emails(processed);
    CREATE INDEX IF NOT EXISTS idx_human_queue_resolved ON human_queue(resolved);
    """

    with get_db() as conn:
        conn.executescript(schema)
    logger.info("Database schema initialized successfully")


def get_jobs_by_status(status: str) -> list[dict]:
    """Fetch all jobs with a given status."""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY scraped_at DESC",
            (status,)
        ).fetchall()
    return [dict(row) for row in rows]


def update_job_status(job_id: str, status: str, **extra_fields) -> None:
    """Update job status and any extra fields atomically."""
    set_clauses = ["status = ?"]
    values = [status]

    for field, value in extra_fields.items():
        set_clauses.append(f"{field} = ?")
        values.append(value)

    values.append(job_id)
    query = f"UPDATE jobs SET {', '.join(set_clauses)} WHERE job_id = ?"

    with get_db() as conn:
        conn.execute(query, values)
    logger.info(f"Job {job_id} status updated to {status}")


def job_exists(job_id: str) -> bool:
    """Check if a job already exists in the database (deduplication)."""
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM jobs WHERE job_id = ?", (job_id,)
        ).fetchone()[0]
    return count > 0
