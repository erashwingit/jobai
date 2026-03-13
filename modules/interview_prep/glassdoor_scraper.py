"""
modules/interview_prep/glassdoor_scraper.py — Direct Glassdoor scraping via Playwright.
No Apify dependency. Uses stealth browser with cookie session injection.

Security: Cookie-based sessions ONLY — no passwords stored.
"""
import re
import asyncio
from shared.logger import get_logger

logger = get_logger(__name__)


def scrape_glassdoor_interviews(company: str, max_reviews: int = 10) -> dict:
    """
    Scrape Glassdoor interview questions for a company using direct Playwright.

    Args:
        company: Company name to search
        max_reviews: Maximum interview reviews to fetch (capped at 10)

    Returns:
        Dict with interview_questions and company_ratings
    """
    try:
        return asyncio.run(_async_scrape(company, min(max_reviews, 10)))
    except Exception as e:
        logger.error(f"Glassdoor scraping failed for {company}: {e}")
        return {"interview_questions": [], "company_ratings": {}}


async def _async_scrape(company: str, max_reviews: int) -> dict:
    """Async Playwright scrape of Glassdoor interview section."""
    from playwright.async_api import async_playwright

    safe_company = re.sub(r"[^a-zA-Z0-9 ]", "", company).strip().replace(" ", "-").lower()
    search_url = (
        f"https://www.glassdoor.com/Interview/{safe_company}-interview-questions-SRCH_KE0,"
        f"{len(safe_company)}.htm"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="America/New_York",
        )

        page = await context.new_page()

        # Mask automation signals
        await page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        try:
            await page.goto(search_url, wait_until="domcontentloaded", timeout=30_000)
            await page.wait_for_timeout(2000)

            interview_questions = await _extract_interview_questions(page, max_reviews)
            company_ratings = await _extract_ratings(page)

        except Exception as e:
            logger.warning(f"Glassdoor page load error for {company}: {e}")
            interview_questions = []
            company_ratings = {}
        finally:
            await browser.close()

    logger.info(
        f"Glassdoor scraped {len(interview_questions)} interview reviews for {company}"
    )
    return {
        "interview_questions": interview_questions,
        "company_ratings": company_ratings,
    }


async def _extract_interview_questions(page, max_reviews: int) -> list[dict]:
    """Extract interview question blocks from the Glassdoor interview page."""
    questions = []

    # Glassdoor interview review selectors (subject to HTML changes)
    review_selectors = [
        "[data-test='InterviewReview']",
        ".interview-review",
        "[class*='interview'][class*='review']",
        "li[class*='empReview']",
    ]

    reviews_el = None
    for sel in review_selectors:
        try:
            reviews_el = await page.query_selector_all(sel)
            if reviews_el:
                break
        except Exception:
            continue

    if not reviews_el:
        logger.debug("No interview review elements found — Glassdoor may have changed layout")
        return []

    for review in reviews_el[:max_reviews]:
        try:
            # Extract text from review block
            text = await review.inner_text()
            if len(text) < 20:
                continue

            # Attempt to extract structured fields from text blocks
            lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

            title_line = lines[0] if lines else "Unknown Role"
            body = " ".join(lines[1:])

            # Heuristic: detect difficulty
            difficulty = "Unknown"
            if re.search(r"\bhard\b|\bdifficult\b", body, re.I):
                difficulty = "Hard"
            elif re.search(r"\beasy\b|\bstraightforward\b", body, re.I):
                difficulty = "Easy"
            elif re.search(r"\bmoderate\b|\bmedium\b|\baverage\b", body, re.I):
                difficulty = "Medium"

            # Heuristic: detect experience sentiment
            experience = "Neutral"
            if re.search(r"\bpositive\b|\bgreat\b|\bwonderful\b", body, re.I):
                experience = "Positive"
            elif re.search(r"\bnegative\b|\bawful\b|\bbad\b|\btough\b", body, re.I):
                experience = "Negative"

            questions.append({
                "role": title_line[:120],
                "difficulty": difficulty,
                "experience": experience,
                "questions": body[:600],
                "outcome": _detect_outcome(body),
            })

        except Exception as e:
            logger.debug(f"Error parsing review element: {e}")
            continue

    return questions


async def _extract_ratings(page) -> dict:
    """Extract overall company ratings if visible on the page."""
    try:
        # Overall rating often present in sidebar
        rating_el = await page.query_selector("[data-test='rating-info-component']")
        if not rating_el:
            rating_el = await page.query_selector("[class*='ratingNumber']")

        if rating_el:
            text = await rating_el.inner_text()
            match = re.search(r"(\d+\.\d+|\d+)", text)
            if match:
                return {"overall": float(match.group(1))}
    except Exception:
        pass
    return {}


def _detect_outcome(text: str) -> str:
    """Detect interview outcome from review text."""
    t = text.lower()
    if re.search(r"\boffered\b|\bgot the job\b|\bhired\b", t):
        return "Accepted"
    if re.search(r"\brejected\b|\bno offer\b|\bdeclined\b", t):
        return "Rejected"
    return "Unknown"
