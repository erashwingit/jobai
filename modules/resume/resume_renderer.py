"""
modules/resume/resume_renderer.py — PDF generation via Jinja2 + Puppeteer microservice.
Replaces the old RenderCV / LaTeX pipeline entirely.

Pipeline: YAML dict → Jinja2 HTML → POST /generate-pdf → PDF bytes → file
"""
import os
import re
import stat
from pathlib import Path
from datetime import datetime

import httpx

from shared.logger import get_logger

logger = get_logger(__name__)

RESUMES_DIR = Path("resumes")
PDF_SERVICE_URL = os.getenv("PDF_SERVICE_URL", "http://localhost:3001")


def compile_resume(resume_data: dict, company: str, role: str) -> Path | None:
    """
    Send resume data to the PDF microservice and save the returned PDF.

    Args:
        resume_data: Tailored resume dict (cv + design sections)
        company: Company name (used for filename)
        role: Role name (used for filename)

    Returns:
        Path to saved PDF, or None if service call fails
    """
    RESUMES_DIR.mkdir(exist_ok=True)

    safe_company = re.sub(r'[^a-zA-Z0-9-]', '-', company.lower())[:40]
    safe_role = re.sub(r'[^a-zA-Z0-9-]', '-', role.lower())[:40]
    pdf_path = RESUMES_DIR / f"{safe_company}-{safe_role}.pdf"

    payload = {
        "cv": resume_data.get("cv", {}),
        "design": resume_data.get("design", {"color": "#004f90"}),
        "generated_date": datetime.utcnow().strftime("%Y-%m-%d"),
    }

    try:
        logger.info(f"Calling PDF service for {company} | {role}")
        response = httpx.post(
            f"{PDF_SERVICE_URL}/generate-pdf",
            json=payload,
            timeout=60.0,  # PDF generation can take a few seconds
        )
        response.raise_for_status()

        if response.headers.get("content-type", "") != "application/pdf":
            logger.error(f"PDF service returned unexpected content-type: {response.headers.get('content-type')}")
            return None

        pdf_path.write_bytes(response.content)
        # chmod 600 — owner read/write only
        os.chmod(pdf_path, stat.S_IRUSR | stat.S_IWUSR)

        gen_time = response.headers.get("x-generation-time-ms", "?")
        logger.info(f"PDF saved: {pdf_path} ({len(response.content):,} bytes, {gen_time}ms)")
        return pdf_path

    except httpx.ConnectError:
        logger.error(
            f"PDF service unreachable at {PDF_SERVICE_URL}. "
            "Start it with: cd services/pdf-service && node index.js"
        )
        return None
    except httpx.TimeoutException:
        logger.error("PDF service timed out after 60s")
        return None
    except httpx.HTTPStatusError as e:
        logger.error(f"PDF service error {e.response.status_code}: {e.response.text[:200]}")
        return None
    except Exception as e:
        logger.error(f"Unexpected PDF generation error: {type(e).__name__}: {e}")
        return None


def is_pdf_service_healthy() -> bool:
    """Check if the PDF microservice is running and healthy."""
    try:
        response = httpx.get(f"{PDF_SERVICE_URL}/health", timeout=5.0)
        return response.status_code == 200
    except Exception:
        return False


def get_pdf_path(company: str, role: str) -> Path:
    """Get the expected PDF path for a given company/role."""
    safe_company = re.sub(r'[^a-zA-Z0-9-]', '-', company.lower())[:40]
    safe_role = re.sub(r'[^a-zA-Z0-9-]', '-', role.lower())[:40]
    return RESUMES_DIR / f"{safe_company}-{safe_role}.pdf"
