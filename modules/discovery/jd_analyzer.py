"""
modules/discovery/jd_analyzer.py — AI-powered JD analysis using LLM.
Fetches full JD text and extracts structured data for match scoring.
"""
import asyncio
import httpx
from bs4 import BeautifulSoup

from shared.llm_client import get_llm_client
from shared.database import get_db
from shared.logger import get_logger

logger = get_logger(__name__)


async def fetch_jd_text(url: str) -> str:
    """
    Fetch and clean job description text from a URL.

    Args:
        url: Job posting URL

    Returns:
        Cleaned JD text (HTML stripped)
    """
    try:
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=15.0,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/121.0.0.0 Safari/537.36"
                )
            }
        ) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, "lxml")

        # Remove script/style elements
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        # Try to find job description container
        jd_selectors = [
            ".jobs-description__content",  # LinkedIn
            ".job-description",
            "[data-testid='jobsearch-JobComponent-description']",  # Indeed
            ".job-desc",  # Naukri
            "article",
            "main",
        ]

        text = ""
        for selector in jd_selectors:
            element = soup.select_one(selector)
            if element:
                text = element.get_text(separator="\n", strip=True)
                break

        # Fallback to full body text
        if not text:
            text = soup.get_text(separator="\n", strip=True)

        # Truncate to reasonable length
        return text[:8000].strip()

    except Exception as e:
        logger.warning(f"Failed to fetch JD from {url}: {type(e).__name__}")
        return ""


def analyze_jd(job_id: str, jd_text: str, profile: dict) -> dict | None:
    """
    Analyze a JD using LLM and return structured data.

    Args:
        job_id: Job ID for logging
        jd_text: Raw JD text
        profile: Candidate profile dict

    Returns:
        Parsed JD dict with skills, match_score, keywords, etc.
    """
    if not jd_text or len(jd_text.strip()) < 100:
        logger.warning(f"JD text too short for job {job_id} — skipping LLM analysis")
        return None

    try:
        llm = get_llm_client()
        candidate_info = profile.get("candidate", {})

        profile_summary = {
            "skills": candidate_info.get("skills_primary", []) + candidate_info.get("skills_secondary", []),
            "experience_years": candidate_info.get("experience_years", 3),
            "target_roles": candidate_info.get("target_roles", []),
            "summary": candidate_info.get("professional_summary", ""),
        }

        result = llm.analyze_jd(jd_text, profile_summary)
        logger.info(
            f"JD analyzed for job {job_id}: match_score={result.get('match_score', 0)}"
        )
        return result

    except Exception as e:
        logger.error(f"LLM JD analysis failed for job {job_id}: {e}")
        return None


def update_job_with_analysis(job_id: str, jd_raw: str, analysis: dict) -> None:
    """
    Persist JD text and LLM analysis results to the database.
    """
    import json

    with get_db() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET jd_raw = ?,
                jd_parsed = ?,
                match_score = ?
            WHERE job_id = ?
            """,
            (
                jd_raw,
                json.dumps(analysis),
                analysis.get("match_score", 0),
                job_id,
            )
        )
    logger.info(f"Job {job_id} updated with analysis (score={analysis.get('match_score')})")


async def analyze_batch(jobs: list[dict], profile: dict) -> list[dict]:
    """
    Fetch JDs and run LLM analysis for a batch of new jobs.
    Processes concurrently with a limit to avoid rate limits.

    Args:
        jobs: List of raw job dicts (status=SCRAPED)
        profile: Candidate profile

    Returns:
        List of analyzed jobs with match_score populated
    """
    semaphore = asyncio.Semaphore(3)  # Max 3 concurrent JD fetches
    analyzed = []

    async def process_single(job: dict) -> dict | None:
        async with semaphore:
            jd_text = await fetch_jd_text(job["jd_url"])
            if not jd_text:
                jd_text = job.get("jd_raw", "")

            analysis = analyze_jd(job["job_id"], jd_text, profile)
            if analysis:
                update_job_with_analysis(job["job_id"], jd_text, analysis)
                return {**job, "match_score": analysis.get("match_score", 0), "analysis": analysis}
            return None

    tasks = [process_single(job) for job in jobs]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    for result in results:
        if isinstance(result, dict):
            analyzed.append(result)
        elif isinstance(result, Exception):
            logger.error(f"JD analysis task failed: {result}")

    logger.info(f"Analyzed {len(analyzed)}/{len(jobs)} jobs successfully")
    return analyzed
