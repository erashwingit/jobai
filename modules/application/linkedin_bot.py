"""
modules/application/linkedin_bot.py — LinkedIn Easy Apply automation.
Uses Playwright with stealth config. Run locally ONLY — not on GitHub Actions.
"""
import asyncio
from pathlib import Path

from playwright.async_api import Page

from modules.application.browser_config import human_delay, human_type, human_scroll
from modules.application.human_checkpoint import (
    flag_for_human, REASON_CAPTCHA, REASON_COMPLEX_FORM, REASON_UNKNOWN_FORM
)
from modules.application.session_manager import save_session
from shared.credential_manager import get_credential
from shared.database import update_job_status
from shared.telegram_notifier import notify_applied
from shared.logger import get_logger

logger = get_logger(__name__)

LINKEDIN_LOGIN_URL = "https://www.linkedin.com/login"


class LinkedInBot:
    """Automates LinkedIn Easy Apply job applications."""

    def __init__(self, page: Page, context):
        self.page = page
        self.context = context
        self.is_logged_in = False

    async def login(self) -> bool:
        """Log into LinkedIn with stored credentials."""
        try:
            await self.page.goto(LINKEDIN_LOGIN_URL, wait_until="networkidle", timeout=30000)
            await human_delay(1, 2)

            # Check if already logged in
            if "feed" in self.page.url:
                logger.info("LinkedIn: Already logged in via saved session")
                self.is_logged_in = True
                return True

            email = get_credential("linkedin", "email")
            password = get_credential("linkedin", "password")

            await human_type(self.page, "#username", email)
            await human_delay(0.5, 1)
            await human_type(self.page, "#password", password)
            await human_delay(0.5, 1)

            await self.page.click("[data-litms-control-urn='login-submit']")
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            await human_delay(2, 3)

            # Check for CAPTCHA or verification
            if "checkpoint" in self.page.url or "challenge" in self.page.url:
                logger.warning("LinkedIn: CAPTCHA/verification detected during login")
                return False

            if "feed" in self.page.url or "mynetwork" in self.page.url:
                self.is_logged_in = True
                await save_session(self.context, "linkedin")
                logger.info("LinkedIn: Login successful")
                return True

            logger.warning(f"LinkedIn: Unexpected page after login: {self.page.url}")
            return False

        except Exception as e:
            logger.error(f"LinkedIn login failed: {e}")
            return False

    async def apply_to_job(self, job: dict, pdf_path: Path) -> bool:
        """
        Apply to a single LinkedIn job using Easy Apply.

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

        if not self.is_logged_in:
            if not await self.login():
                flag_for_human(job_id, company, role, url, "LinkedIn login failed")
                return False

        try:
            logger.info(f"LinkedIn: Applying to {company} | {role}")
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            await human_delay(2, 4)

            # Look for Easy Apply button
            easy_apply_btn = await self.page.query_selector(
                ".jobs-apply-button--top-card button, "
                "[data-control-name='jobdetails_topcard_inapply']"
            )

            if not easy_apply_btn:
                flag_for_human(
                    job_id, company, role, url,
                    "No Easy Apply button found — external application required"
                )
                return False

            await easy_apply_btn.click()
            await human_delay(1, 2)

            # Handle multi-step application modal
            success = await self._handle_application_modal(job, pdf_path)

            if success:
                update_job_status(
                    job_id, "APPLIED",
                    notes="LinkedIn Easy Apply submitted"
                )
                notify_applied(company, role, "linkedin")
                logger.info(f"LinkedIn: Successfully applied to {company} | {role}")
                return True

            return False

        except Exception as e:
            logger.error(f"LinkedIn apply failed for {job_id}: {e}")
            flag_for_human(job_id, company, role, url, f"Application error: {type(e).__name__}")
            return False

    async def _handle_application_modal(self, job: dict, pdf_path: Path) -> bool:
        """
        Navigate through the Easy Apply multi-step modal.
        Handles common form patterns; flags complex forms for human review.
        """
        max_steps = 8
        current_step = 0

        while current_step < max_steps:
            await human_delay(1, 2)

            # Check for CAPTCHA
            captcha = await self.page.query_selector(
                ".captcha-internal, [class*='captcha']"
            )
            if captcha:
                flag_for_human(
                    job["job_id"], job["company"], job["role"], job["jd_url"],
                    REASON_CAPTCHA
                )
                return False

            # Check for resume upload prompt
            upload_input = await self.page.query_selector("input[type='file']")
            if upload_input:
                await upload_input.set_input_files(str(pdf_path))
                await human_delay(1, 2)

            # Fill contact info if empty
            await self._fill_contact_info()

            # Check for subjective/complex questions
            complex_fields = await self.page.query_selector_all(
                "textarea, [data-test-text-entity-list-form-component]"
            )
            if len(complex_fields) > 2:
                flag_for_human(
                    job["job_id"], job["company"], job["role"], job["jd_url"],
                    REASON_COMPLEX_FORM
                )
                return False

            # Try to proceed to next step or submit
            next_btn = await self.page.query_selector(
                "button[aria-label='Continue to next step'], "
                "button[aria-label='Review your application'], "
                ".artdeco-button--primary"
            )

            if not next_btn:
                break

            btn_text = await next_btn.inner_text()

            if "submit" in btn_text.lower():
                await next_btn.click()
                await human_delay(2, 3)
                logger.info("LinkedIn: Application submitted")
                return True

            await next_btn.click()
            current_step += 1

        # Fallback: flag for human if we couldn't complete
        flag_for_human(
            job["job_id"], job["company"], job["role"], job["jd_url"],
            REASON_UNKNOWN_FORM
        )
        return False

    async def _fill_contact_info(self) -> None:
        """Pre-fill common contact info fields if empty."""
        from shared.config_validator import load_profile

        profile = load_profile()
        candidate = profile.get("candidate", {})

        # Phone field
        phone_field = await self.page.query_selector(
            "input[id*='phoneNumber'], input[name*='phone']"
        )
        if phone_field:
            current_value = await phone_field.input_value()
            if not current_value:
                await human_type(self.page, phone_field, candidate.get("phone", ""))
