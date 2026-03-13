"""
modules/application/naukri_bot.py — Naukri Quick Apply via submitter microservice.
Security: Cookie-based sessions ONLY — NO password authentication.
"""
import os
from pathlib import Path

import httpx

from modules.application.human_checkpoint import flag_for_human
from shared.session_manager import check_cookie_health
from shared.database import update_job_status
from shared.telegram_notifier import notify_applied
from shared.logger import get_logger

logger = get_logger(__name__)

SUBMITTER_URL = os.getenv("SUBMITTER_SERVICE_URL", "http://localhost:3002")


class NaukriBot:
    """
    Naukri Quick Apply bot — delegates to the Node.js submitter microservice.
    Pre-flight checks cookie health before making service calls.
    """

    def __init__(self, *args, **kwargs):
        pass

    def preflight_check(self) -> bool:
        """Verify Naukri cookies are valid before attempting applications."""
        health = check_cookie_health("naukri")
        if not health["valid"]:
            logger.error(f"Naukri cookie check failed: {health['message']}")
            return False
        logger.info(f"Naukri cookies OK — expires: {health['expires_at']}")
        return True

    async def apply_to_job(self, job: dict, pdf_path: Path) -> bool:
        """Apply to a Naukri job via the submitter microservice."""
        job_id = job["job_id"]
        company = job["company"]
        role = job["role"]
        url = job["jd_url"]

        if not self.preflight_check():
            flag_for_human(
                job_id, company, role, url,
                "Naukri session cookies expired. Run: node tools/export-cookies.js"
            )
            return False

        try:
            response = httpx.post(
                f"{SUBMITTER_URL}/submit",
                json={
                    "portal": "naukri",
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
            logger.error(f"Submitter service unreachable at {SUBMITTER_URL}")
            flag_for_human(job_id, company, role, url, "Submitter service not running")
            return False
        except httpx.TimeoutException:
            flag_for_human(job_id, company, role, url, "Submitter service timeout")
            return False

        if result.get("error") == "CookieExpiredError":
            flag_for_human(
                job_id, company, role, url,
                "Naukri session expired. Run: node tools/export-cookies.js"
            )
            return False

        if result.get("success"):
            update_job_status(job_id, "APPLIED", notes="Naukri Quick Apply via submitter")
            notify_applied(company, role, "naukri")
            logger.info(f"Naukri: Applied to {company} | {role}")
            return True

        flag_for_human(job_id, company, role, url, result.get("message", "Unknown failure"))
        return False
