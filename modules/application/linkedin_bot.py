"""
modules/application/linkedin_bot.py — LinkedIn Easy Apply via submitter microservice.
Security: Cookie-based sessions ONLY — NO password authentication.

Delegates all browser automation to the Node.js submitter service (port 3002).
"""
import os
from pathlib import Path

import httpx

from modules.application.human_checkpoint import (
    flag_for_human, REASON_CAPTCHA, REASON_COMPLEX_FORM
)
from shared.session_manager import CookieExpiredError, check_cookie_health
from shared.database import update_job_status
from shared.telegram_notifier import notify_applied
from shared.logger import get_logger

logger = get_logger(__name__)

SUBMITTER_URL = os.getenv("SUBMITTER_SERVICE_URL", "http://localhost:3002")


class LinkedInBot:
    """
    LinkedIn Easy Apply bot — delegates to the Node.js submitter microservice.
    Pre-flight checks cookie health before making service calls.
    """

    def __init__(self, *args, **kwargs):
        # No Playwright browser needed — submitter service handles it
        pass

    def preflight_check(self) -> bool:
        """Verify LinkedIn cookies are valid before attempting applications."""
        health = check_cookie_health("linkedin")
        if not health["valid"]:
            logger.error(f"LinkedIn cookie check failed: {health['message']}")
            return False
        logger.info(f"LinkedIn cookies OK — expires: {health['expires_at']}")
        return True

    async def apply_to_job(self, job: dict, pdf_path: Path) -> bool:
        """
        Apply to a LinkedIn job via the submitter microservice.

        Args:
            job: Job dict with job_id, company, role, jd_url
            pdf_path: Path to tailored resume PDF

        Returns:
            True if application submitted successfully
        """
        job_id = job["job_id"]
        company = job["company"]
        role = job["role"]
        url = job["jd_url"]

        # Pre-flight: verify cookies before starting browser
        if not self.preflight_check():
            flag_for_human(
                job_id, company, role, url,
                "LinkedIn session cookies expired. Run: node tools/export-cookies.js"
            )
            return False

        try:
            response = httpx.post(
                f"{SUBMITTER_URL}/submit",
                json={
                    "portal": "linkedin",
                    "job_url": url,
                    "job_id": job_id,
                    "company": company,
                    "role": role,
                    "resume_path": str(pdf_path.resolve()),
                },
                timeout=120.0,
            )
            result = response.json()

        except httpx.ConnectError:
            logger.error(
                f"Submitter service unreachable at {SUBMITTER_URL}. "
                "Start with: cd services/submitter && node index.js"
            )
            flag_for_human(job_id, company, role, url, "Submitter service not running")
            return False
        except httpx.TimeoutException:
            logger.error(f"Submitter timed out for {job_id}")
            flag_for_human(job_id, company, role, url, "Submitter service timeout")
            return False

        if result.get("error") == "CookieExpiredError":
            flag_for_human(
                job_id, company, role, url,
                "LinkedIn session expired. Run: node tools/export-cookies.js"
            )
            return False

        if result.get("success"):
            update_job_status(job_id, "APPLIED", notes="LinkedIn Easy Apply via submitter")
            notify_applied(company, role, "linkedin")
            logger.info(f"LinkedIn: Applied to {company} | {role}")
            return True

        # Application failed — flag for human review
        message = result.get("message", "Unknown failure")
        if "CAPTCHA" in message:
            flag_for_human(job_id, company, role, url, REASON_CAPTCHA)
        elif "complex" in message.lower():
            flag_for_human(job_id, company, role, url, REASON_COMPLEX_FORM)
        else:
            flag_for_human(job_id, company, role, url, message)

        return False
