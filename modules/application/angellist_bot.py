"""
modules/application/angellist_bot.py — AngelList/Wellfound application bot.
TODO: Implement AngelListBot following the same pattern as LinkedInBot.
"""
from pathlib import Path
from playwright.async_api import Page

from modules.application.human_checkpoint import flag_for_human
from shared.logger import get_logger

logger = get_logger(__name__)


class AngelListBot:
    """Automates AngelList/Wellfound job applications. (Stub — implement Week 2)"""

    def __init__(self, page: Page, context):
        self.page = page
        self.context = context
        self.is_logged_in = False

    async def login(self) -> bool:
        """TODO: Implement AngelList login."""
        logger.warning("AngelListBot.login() not yet implemented")
        return False

    async def apply_to_job(self, job: dict, pdf_path: Path) -> bool:
        """TODO: Implement AngelList Quick Apply."""
        flag_for_human(
            job["job_id"], job["company"], job["role"], job["jd_url"],
            "AngelListBot not yet implemented — manual application required"
        )
        return False
