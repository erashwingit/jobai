"""
modules/resume/ats_scorer.py — ATS (Applicant Tracking System) score calculator.
Scores resume PDF/text against JD keywords without requiring LLM.
"""
import re
from pathlib import Path

from shared.logger import get_logger
from shared.config_validator import load_settings

logger = get_logger(__name__)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """
    Extract plain text from a PDF file for ATS scoring.
    Uses pdfminer if available, falls back to basic extraction.
    """
    try:
        from pdfminer.high_level import extract_text
        text = extract_text(str(pdf_path))
        return text or ""
    except ImportError:
        logger.debug("pdfminer not installed, using pypdf fallback")

    try:
        import pypdf
        with open(pdf_path, "rb") as f:
            reader = pypdf.PdfReader(f)
            return "\n".join(page.extract_text() or "" for page in reader.pages)
    except ImportError:
        logger.warning("No PDF text extractor available (install pdfminer.six or pypdf)")
        return ""
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return ""


def calculate_ats_score(resume_text: str, jd_analysis: dict) -> dict:
    """
    Calculate ATS compatibility score between resume and JD.

    Scoring breakdown:
    - Keyword presence (60%): % of JD keywords found in resume
    - Skills match (30%): % of required skills found
    - Format score (10%): basic formatting checks

    Args:
        resume_text: Plain text extracted from resume PDF
        jd_analysis: LLM-analyzed JD dict with keywords, skills

    Returns:
        Dict with total_score (0-100) and breakdown
    """
    if not resume_text:
        logger.warning("Empty resume text — ATS scoring unavailable")
        return {"total_score": 0, "breakdown": {}, "missing_keywords": []}

    resume_lower = resume_text.lower()
    keywords = jd_analysis.get("keywords", [])
    required_skills = jd_analysis.get("skills", [])

    # --- Keyword score (60 points max) ---
    found_keywords = []
    missing_keywords = []

    for kw in keywords:
        # Word boundary match for accuracy
        pattern = r'\b' + re.escape(kw.lower()) + r'\b'
        if re.search(pattern, resume_lower):
            found_keywords.append(kw)
        else:
            missing_keywords.append(kw)

    keyword_score = (len(found_keywords) / len(keywords) * 60) if keywords else 60

    # --- Skills score (30 points max) ---
    found_skills = []
    missing_skills = []

    for skill in required_skills:
        pattern = r'\b' + re.escape(skill.lower()) + r'\b'
        if re.search(pattern, resume_lower):
            found_skills.append(skill)
        else:
            missing_skills.append(skill)

    skills_score = (len(found_skills) / len(required_skills) * 30) if required_skills else 30

    # --- Format score (10 points max) ---
    format_score = _check_format(resume_text)

    total_score = round(keyword_score + skills_score + format_score, 1)

    result = {
        "total_score": total_score,
        "breakdown": {
            "keyword_score": round(keyword_score, 1),
            "skills_score": round(skills_score, 1),
            "format_score": format_score,
        },
        "found_keywords": found_keywords,
        "missing_keywords": missing_keywords,
        "found_skills": found_skills,
        "missing_skills": missing_skills,
        "keyword_coverage": f"{len(found_keywords)}/{len(keywords)}" if keywords else "N/A",
    }

    logger.info(
        f"ATS Score: {total_score}/100 | "
        f"Keywords: {len(found_keywords)}/{len(keywords)} | "
        f"Skills: {len(found_skills)}/{len(required_skills)}"
    )
    return result


def _check_format(resume_text: str) -> float:
    """Check basic ATS-friendly formatting (10 points max)."""
    score = 10.0

    # Penalize if resume is too short (< 300 words)
    word_count = len(resume_text.split())
    if word_count < 300:
        score -= 3

    # Check for common section headers
    sections = ["experience", "education", "skills", "projects"]
    text_lower = resume_text.lower()
    found_sections = sum(1 for s in sections if s in text_lower)
    if found_sections < 3:
        score -= 2

    # Check for dates (ATS systems look for employment dates)
    date_pattern = r'\b(20\d{2}|19\d{2})\b'
    if not re.search(date_pattern, resume_text):
        score -= 2

    return max(0, score)


def meets_threshold(ats_result: dict) -> bool:
    """Check if ATS score meets the configured minimum threshold."""
    settings = load_settings()
    min_score = settings.get("resume", {}).get("ats_min_score", 75)
    return ats_result.get("total_score", 0) >= min_score
