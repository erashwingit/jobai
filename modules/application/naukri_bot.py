"""
modules/application/naukri_bot.py — Naukri Quick Apply automation.
Targets the Quick Apply button on Naukri job listings.
"""
from pathlib import Path
from playwright.async_api import Page

from modules.application.browser_config import human_delay, human_type
from modules.application.human_checkpoint import flag_for_human, REASON_CAPTCHA
from modules.application.session_manager import save_session
from shared.credential_manager import get_credential
from shared.database import update_job_status
from shared.telegram_notifier import notify_applied
from shared.logger import get_logger

logger = get_logger(__name__)

NAUKRI_LOGIN_URL = "https://www.naukri.com/nlogin/login"


class NaukriBot:
    """Automates Naukri Quick Apply job applications."""

    def __init__(self, page: Page, context):
        self.page = page
        self.context = context
        self.is_logged_in = False

    async def login(self) -> bool:
        """Log into Naukri."""
        try:
            await self.page.goto(NAUKRI_LOGIN_URL, wait_until="networkidle", timeout=30000)
            await human_delay(1, 2)

            # Check if already logged in
            profile_icon = await self.page.query_selector(".nI-gNb-user-info__picture")
            if profile_icon:
                self.is_logged_in = True
                return True

            email = get_credential("naukri", "email")
            password = get_credential("naukri", "password")

            await human_type(self.page, "#usernameField", email)
            await human_delay(0.5, 1)
            await human_type(self.page, "#passwordField", password)
            await human_delay(0.5, 1)

            await self.page.click(".loginButton")
            await self.page.wait_for_load_state("networkidle", timeout=15000)
            await human_delay(2, 3)

            # Verify login
            profile_icon = await self.page.query_selector(".nI-gNb-user-info__picture")
            if profile_icon:
                self.is_logged_in = True
                await save_session(self.context, "naukri")
                logger.info("Naukri: Login successful")
                return True

            logger.warning("Naukri: Login verification failed")
            return False

        except Exception as e:
            logger.error(f"Naukri login failed: {e}")
            return False

    async def apply_to_job(self, job: dict, pdf_path: Path) -> bool:
        """Apply to a Naukri job using Quick Apply."""
        job_id = job["job_id"]
        company = job["company"]
        role = job["role"]
        url = job["jd_url"]

        if not self.is_logged_in:
            if not await self.login():
                flag_for_human(job_id, company, role, url, "Naukri login failed")
                return False

        try:
            await self.page.goto(url, wait_until="networkidle", timeout=30000)
            await human_delay(2, 4)

            # Check for CAPTCHA
            captcha = await self.page.query_selector(".g-recaptcha")
            if captcha:
                flag_for_human(job_id, company, role, url, REASON_CAPTCHA)
                return False

            # Look for Apply / Quick Apply button
            apply_btn = await self.page.query_selector(
                "button.apply-button, #apply-button, .apply-btn"
            )

            if not apply_btn:
                flag_for_human(job_id, company, role, url, "No apply button found")
                return False

            await apply_btn.click()
            await human_delay(2, 3)

            # Handle modal if it appears
            modal = await self.page.query_selector(".apply-modal, #apply-widget")
            if modal:
                # Try to upload resume
                upload = await self.page.query_selector("input[type='file']")
                if upload:
                    await upload.set_input_files(str(pdf_path))
                    await human_delay(1, 2)

                # Submit
                submit_btn = await self.page.query_selector(
                    "button[type='submit'], .submit-btn"
                )
                if submit_btn:
                    await submit_btn.click()
                    await human_delay(2, 3)

            # Verify success
            success_el = await self.page.query_selector(
                ".success-message, .applied-tag, [class*='success']"
            )
            if success_el:
                update_job_status(job_id, "APPLIED")
                notify_applied(company, role, "naukri")
                logger.info(f"Naukri: Applied to {company} | {role}")
                return True

            # Uncertain — flag for human verification
            flag_for_human(job_id, company, role, url, "Application outcome uncertain")
            return False

        except Exception as e:
            logger.error(f"Naukri apply failed for {job_id}: {e}")
            flag_for_human(job_id, company, role, url, f"Error: {type(e).__name__}")
            return False
