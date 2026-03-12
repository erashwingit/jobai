"""
modules/interview_prep/glassdoor_scraper.py — Glassdoor interview Q&A via Apify.
Uses Apify free tier to scrape Glassdoor reviews and interview questions.
"""
import os
import time
import requests

from shared.logger import get_logger

logger = get_logger(__name__)

APIFY_API_BASE = "https://api.apify.com/v2"
GLASSDOOR_ACTOR_ID = "voyager~glassdoor-scraper"  # Apify public actor


def scrape_glassdoor_interviews(company: str, max_reviews: int = 10) -> dict:
    """
    Scrape Glassdoor interview questions and reviews for a company.
    Uses Apify free tier (free runs per month).

    Args:
        company: Company name to search
        max_reviews: Max number of interview reviews to fetch

    Returns:
        Dict with interview_questions and company_ratings
    """
    apify_token = os.getenv("APIFY_API_TOKEN")

    if not apify_token:
        logger.warning("APIFY_API_TOKEN not set — skipping Glassdoor scraping")
        return {"interview_questions": [], "company_ratings": {}}

    try:
        # Start the actor run
        run_id = _start_actor_run(apify_token, company, max_reviews)
        if not run_id:
            return {"interview_questions": [], "company_ratings": {}}

        # Wait for completion (poll with timeout)
        results = _wait_for_results(apify_token, run_id, timeout_minutes=5)
        return _parse_results(results)

    except Exception as e:
        logger.error(f"Glassdoor scraping failed for {company}: {e}")
        return {"interview_questions": [], "company_ratings": {}}


def _start_actor_run(token: str, company: str, max_reviews: int) -> str | None:
    """Start an Apify actor run and return the run ID."""
    url = f"{APIFY_API_BASE}/acts/{GLASSDOOR_ACTOR_ID}/runs"

    payload = {
        "input": {
            "queries": [company],
            "maxReviewsPerPage": max_reviews,
            "reviewType": "INTERVIEW",
            "proxy": {"useApifyProxy": True, "apifyProxyGroups": ["RESIDENTIAL"]},
        }
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        run_id = response.json()["data"]["id"]
        logger.info(f"Apify run started: {run_id}")
        return run_id
    except Exception as e:
        logger.error(f"Failed to start Apify run: {e}")
        return None


def _wait_for_results(token: str, run_id: str, timeout_minutes: int = 5) -> list:
    """Poll Apify for run completion and fetch results."""
    status_url = f"{APIFY_API_BASE}/actor-runs/{run_id}"
    dataset_url = f"{APIFY_API_BASE}/actor-runs/{run_id}/dataset/items"
    headers = {"Authorization": f"Bearer {token}"}

    deadline = time.time() + (timeout_minutes * 60)

    while time.time() < deadline:
        try:
            status_resp = requests.get(status_url, headers=headers, timeout=10)
            status = status_resp.json()["data"]["status"]

            if status in ("SUCCEEDED", "FINISHED"):
                items_resp = requests.get(dataset_url, headers=headers, timeout=30)
                return items_resp.json()
            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                logger.warning(f"Apify run {run_id} ended with status: {status}")
                return []

            logger.debug(f"Apify run status: {status} — waiting...")
            time.sleep(15)

        except Exception as e:
            logger.error(f"Error polling Apify run: {e}")
            time.sleep(15)

    logger.warning(f"Apify run {run_id} timed out after {timeout_minutes}m")
    return []


def _parse_results(raw_results: list) -> dict:
    """Parse Apify results into structured interview data."""
    interview_questions = []
    ratings = {}

    for item in raw_results:
        # Extract interview questions from reviews
        if item.get("reviewType") == "INTERVIEW":
            text = item.get("pros", "") + " " + item.get("cons", "")
            interview_text = item.get("interviewText", text)

            if interview_text:
                interview_questions.append({
                    "company": item.get("employerName", ""),
                    "role": item.get("jobTitle", ""),
                    "experience": item.get("interviewExperience", ""),
                    "difficulty": item.get("interviewDifficulty", ""),
                    "questions": interview_text[:500],
                    "outcome": item.get("interviewOutcome", ""),
                })

        # Collect ratings
        if "overallRating" in item:
            ratings = {
                "overall": item.get("overallRating"),
                "culture": item.get("cultureRating"),
                "work_life": item.get("workLifeBalanceRating"),
                "senior_mgmt": item.get("seniorManagementRating"),
                "comp_benefits": item.get("compensationBenefitsRating"),
                "career_growth": item.get("careerOpportunitiesRating"),
            }

    logger.info(f"Glassdoor parsed: {len(interview_questions)} interview reviews")
    return {
        "interview_questions": interview_questions[:10],
        "company_ratings": ratings,
    }
