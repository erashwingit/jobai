"""
modules/discovery/scraper.py — Multi-portal job scraper.
Scrapes LinkedIn, Naukri, Indeed, Glassdoor, Instahiring using Playwright.

Note: Run browser automation LOCALLY (not GitHub Actions) to avoid IP bans.
"""
import asyncio
import hashlib
from datetime import datetime
from typing import AsyncGenerator

from playwright.async_api import async_playwright, Page, Browser

from shared.logger import get_logger
from shared.config_validator import load_settings, load_profile

logger = get_logger(__name__)


def _make_job_id(portal: str, url: str) -> str:
    """Create a stable, unique job ID from portal + URL hash."""
    return hashlib.md5(f"{portal}:{url}".encode()).hexdigest()


# ============================================================
# Base scraper interface
# ============================================================

class BaseScraper:
    """Abstract base class for portal-specific scrapers."""

    portal_name: str = "base"

    def __init__(self, page: Page, profile: dict, settings: dict):
        self.page = page
        self.profile = profile
        self.settings = settings

    async def search(self) -> AsyncGenerator[dict, None]:
        """
        Yield raw job dicts from the portal.
        Each dict: {job_id, portal, company, role, location, jd_url, jd_raw, posted_at}
        """
        raise NotImplementedError


# ============================================================
# LinkedIn scraper
# ============================================================

class LinkedInScraper(BaseScraper):
    portal_name = "linkedin"
    BASE_URL = "https://www.linkedin.com/jobs/search/"

    async def search(self) -> AsyncGenerator[dict, None]:
        profile = self.profile.get("candidate", {})
        roles = profile.get("target_roles", ["AI Engineer"])
        locations = profile.get("target_locations", ["Remote"])
        max_age_hours = self.settings.get("job_discovery", {}).get("max_age_hours", 48)

        for role in roles[:3]:  # Limit roles to avoid rate limits
            for location in locations[:2]:
                search_url = (
                    f"{self.BASE_URL}?keywords={role.replace(' ', '%20')}"
                    f"&location={location.replace(' ', '%20')}"
                    f"&f_TPR=r{max_age_hours * 3600}"  # Time filter in seconds
                    f"&f_AL=true"  # Easy Apply filter
                )

                logger.info(f"Scraping LinkedIn: {role} in {location}")

                try:
                    await self.page.goto(search_url, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)

                    # Extract job cards
                    job_cards = await self.page.query_selector_all(
                        ".jobs-search__results-list li"
                    )

                    for card in job_cards[:20]:  # Max 20 per search
                        try:
                            job = await self._extract_card(card)
                            if job:
                                yield job
                        except Exception as e:
                            logger.debug(f"Failed to extract LinkedIn job card: {e}")

                except Exception as e:
                    logger.warning(f"LinkedIn search failed for {role}/{location}: {e}")

    async def _extract_card(self, card) -> dict | None:
        """Extract job data from a LinkedIn job card element."""
        title_el = await card.query_selector(".base-search-card__title")
        company_el = await card.query_selector(".base-search-card__subtitle")
        location_el = await card.query_selector(".job-search-card__location")
        link_el = await card.query_selector("a.base-card__full-link")

        if not all([title_el, company_el, link_el]):
            return None

        title = (await title_el.inner_text()).strip()
        company = (await company_el.inner_text()).strip()
        location = (await location_el.inner_text()).strip() if location_el else ""
        url = await link_el.get_attribute("href")

        if not url:
            return None

        # Clean URL (remove tracking params)
        url = url.split("?")[0]
        job_id = _make_job_id("linkedin", url)

        return {
            "job_id": job_id,
            "portal": "linkedin",
            "company": company,
            "role": title,
            "location": location,
            "jd_url": url,
            "jd_raw": "",  # Fetched by deduplicator
            "posted_at": datetime.utcnow().isoformat(),
        }


# ============================================================
# Naukri scraper
# ============================================================

class NaukriScraper(BaseScraper):
    portal_name = "naukri"
    BASE_URL = "https://www.naukri.com"

    async def search(self) -> AsyncGenerator[dict, None]:
        profile = self.profile.get("candidate", {})
        roles = profile.get("target_roles", ["AI Engineer"])

        for role in roles[:3]:
            search_url = f"{self.BASE_URL}/{role.lower().replace(' ', '-')}-jobs"
            logger.info(f"Scraping Naukri: {role}")

            try:
                await self.page.goto(search_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)

                job_cards = await self.page.query_selector_all(".jobTuple")

                for card in job_cards[:20]:
                    try:
                        job = await self._extract_card(card)
                        if job:
                            yield job
                    except Exception as e:
                        logger.debug(f"Failed to extract Naukri card: {e}")

            except Exception as e:
                logger.warning(f"Naukri search failed for {role}: {e}")

    async def _extract_card(self, card) -> dict | None:
        title_el = await card.query_selector(".title")
        company_el = await card.query_selector(".companyInfo .subTitle")
        location_el = await card.query_selector(".location")
        link_el = await card.query_selector("a.title")

        if not all([title_el, link_el]):
            return None

        title = (await title_el.inner_text()).strip()
        company = (await company_el.inner_text()).strip() if company_el else "Unknown"
        location = (await location_el.inner_text()).strip() if location_el else ""
        url = await link_el.get_attribute("href") or ""

        job_id = _make_job_id("naukri", url)
        return {
            "job_id": job_id,
            "portal": "naukri",
            "company": company,
            "role": title,
            "location": location,
            "jd_url": url,
            "jd_raw": "",
            "posted_at": datetime.utcnow().isoformat(),
        }


# ============================================================
# Indeed scraper
# ============================================================

class IndeedScraper(BaseScraper):
    portal_name = "indeed"
    BASE_URL = "https://in.indeed.com/jobs"

    async def search(self) -> AsyncGenerator[dict, None]:
        profile = self.profile.get("candidate", {})
        roles = profile.get("target_roles", ["AI Engineer"])
        locations = profile.get("target_locations", ["Remote"])

        for role in roles[:3]:
            for location in locations[:2]:
                search_url = (
                    f"{self.BASE_URL}?q={role.replace(' ', '+')}"
                    f"&l={location.replace(' ', '+')}"
                    f"&fromage=2"  # Jobs from last 2 days
                )
                logger.info(f"Scraping Indeed: {role} in {location}")

                try:
                    await self.page.goto(search_url, wait_until="networkidle", timeout=30000)
                    await asyncio.sleep(2)

                    job_cards = await self.page.query_selector_all(".job_seen_beacon")

                    for card in job_cards[:20]:
                        try:
                            job = await self._extract_card(card)
                            if job:
                                yield job
                        except Exception as e:
                            logger.debug(f"Failed to extract Indeed card: {e}")

                except Exception as e:
                    logger.warning(f"Indeed search failed: {e}")

    async def _extract_card(self, card) -> dict | None:
        title_el = await card.query_selector(".jobTitle a")
        company_el = await card.query_selector("[data-testid='company-name']")
        location_el = await card.query_selector("[data-testid='text-location']")

        if not title_el:
            return None

        title = (await title_el.inner_text()).strip()
        company = (await company_el.inner_text()).strip() if company_el else "Unknown"
        location = (await location_el.inner_text()).strip() if location_el else ""
        href = await title_el.get_attribute("href") or ""
        url = f"https://in.indeed.com{href}" if href.startswith("/") else href

        job_id = _make_job_id("indeed", url)
        return {
            "job_id": job_id,
            "portal": "indeed",
            "company": company,
            "role": title,
            "location": location,
            "jd_url": url,
            "jd_raw": "",
            "posted_at": datetime.utcnow().isoformat(),
        }


# ============================================================
# Main scraper orchestrator
# ============================================================

SCRAPER_MAP = {
    "linkedin": LinkedInScraper,
    "naukri": NaukriScraper,
    "indeed": IndeedScraper,
    # glassdoor + instahiring: add similar pattern
}


async def scrape_all_portals() -> list[dict]:
    """
    Scrape all configured portals and return raw job listings.
    Uses a single browser instance with stealth config.
    """
    from modules.application.browser_config import get_stealth_browser

    settings = load_settings()
    profile = load_profile()
    portals = settings.get("job_discovery", {}).get("portals", list(SCRAPER_MAP.keys()))

    all_jobs: list[dict] = []

    async with async_playwright() as pw:
        browser, context = await get_stealth_browser(pw)
        page = await context.new_page()

        try:
            for portal in portals:
                scraper_cls = SCRAPER_MAP.get(portal)
                if not scraper_cls:
                    logger.warning(f"No scraper implemented for portal: {portal}")
                    continue

                scraper = scraper_cls(page, profile, settings)
                portal_jobs = []

                async for job in scraper.search():
                    portal_jobs.append(job)

                logger.info(f"Scraped {len(portal_jobs)} jobs from {portal}")
                all_jobs.extend(portal_jobs)

                # Respectful delay between portals
                await asyncio.sleep(5)

        finally:
            await browser.close()

    logger.info(f"Total scraped: {len(all_jobs)} jobs across {len(portals)} portals")
    return all_jobs
