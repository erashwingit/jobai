"""
modules/application/indeed_bot.py — Indeed Easy Apply automation.
TODO: Implement IndeedBot following the same pattern as LinkedInBot.
"""
from pathlib import Path
from playwright.async_api import Page

from modules.application.human_checkpoint import flag_for_human
from shared.logger import get_logger

logger = get_logger(__name__)


class IndeedBot:
    """Automates Indeed Easy Apply job applications. (Stub — implement Week 2)"""

    def __init__(self, page: Page, context):
        self.page = page
        self.context = context
        self.is_logged_in = False

    async def login(self) -> bool:
        """TODO: Implement Indeed login."""
        logger.warning("IndeedBot.login() not yet implemented")
        return False

    async def apply_to_job(self, job: dict, pdf_path: Path) -> bool:
        """TODO: Implement Indeed Easy Apply."""
        flag_for_human(
            job["job_id"], job["company"], job["role"], job["jd_url"],
            "IndeedBot not yet implemented — manual application required"
        )
        return False
