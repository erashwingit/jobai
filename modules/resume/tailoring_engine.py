"""
modules/resume/tailoring_engine.py — LLM-driven resume tailoring.
Customizes master resume YAML to emphasize keywords for each specific JD.
Pipeline: Master YAML → Tailored YAML → LaTeX → PDF
"""
import json
import copy
from pathlib import Path

import yaml

from shared.llm_client import get_llm_client, sanitize_input
from shared.logger import get_logger

logger = get_logger(__name__)

MASTER_RESUME_PATH = Path("config/master_resume.yaml")


def load_master_resume() -> dict:
    """Load the master resume YAML template."""
    if not MASTER_RESUME_PATH.exists():
        raise FileNotFoundError(
            f"Master resume not found at {MASTER_RESUME_PATH}. "
            "Copy config/master_resume.yaml and fill in your details."
        )

    with open(MASTER_RESUME_PATH) as f:
        return yaml.safe_load(f)


def tailor_resume(job: dict, jd_analysis: dict) -> dict:
    """
    Tailor the master resume for a specific job using LLM.

    Args:
        job: Job dict with company, role, jd_raw
        jd_analysis: LLM analysis result with skills, keywords

    Returns:
        Tailored resume as a dict (YAML structure)
    """
    master = load_master_resume()
    tailored = copy.deepcopy(master)

    keywords = jd_analysis.get("keywords", [])
    required_skills = jd_analysis.get("skills", [])
    jd_summary = jd_analysis.get("summary", "")

    logger.info(
        f"Tailoring resume for {job.get('company')} | {job.get('role')} | "
        f"keywords={len(keywords)}"
    )

    # --- Step 1: Tailor professional summary ---
    tailored_summary = _tailor_summary(
        original_summary=master.get("cv", {}).get("sections", {}).get("summary", [""])[0],
        role=job.get("role", ""),
        company=job.get("company", ""),
        keywords=keywords,
        jd_summary=jd_summary,
    )
    tailored["cv"]["sections"]["summary"] = [tailored_summary]

    # --- Step 2: Reorder skills to surface JD keywords first ---
    tailored["cv"]["sections"]["skills"] = _tailor_skills(
        original_skills=master.get("cv", {}).get("sections", {}).get("skills", []),
        required_skills=required_skills,
        keywords=keywords,
    )

    # --- Step 3: Highlight relevant projects first ---
    tailored["cv"]["sections"]["projects"] = _rerank_projects(
        original_projects=master.get("cv", {}).get("sections", {}).get("projects", []),
        keywords=keywords,
    )

    return tailored


def _tailor_summary(
    original_summary: str,
    role: str,
    company: str,
    keywords: list[str],
    jd_summary: str,
) -> str:
    """Use LLM to generate a tailored professional summary."""
    llm = get_llm_client()

    keywords_str = ", ".join(keywords[:15])
    safe_summary = sanitize_input(jd_summary, max_length=500)

    prompt = f"""Rewrite this professional summary to target the role of {role} at {company}.
Naturally incorporate these keywords: {keywords_str}
Role context: {safe_summary}

Original summary:
{original_summary}

Rules:
- Keep it to 2-3 sentences maximum
- Sound natural and human, not keyword-stuffed
- Preserve authentic experience claims
- Return ONLY the rewritten summary text, no quotes, no labels

Rewritten summary:"""

    try:
        result = llm.complete(prompt)
        # Clean up LLM response
        result = result.strip().strip('"').strip("'")
        if len(result) > 50:  # Sanity check
            return result
    except Exception as e:
        logger.warning(f"Summary tailoring failed: {e}, using original")

    return original_summary


def _tailor_skills(
    original_skills: list[dict],
    required_skills: list[str],
    keywords: list[str],
) -> list[dict]:
    """Reorder skill groups to surface JD-relevant skills first."""
    required_lower = {s.lower() for s in required_skills + keywords}
    scored_skills = []

    for skill_group in original_skills:
        details = skill_group.get("details", "")
        details_lower = details.lower()
        # Score by how many required skills appear in this group
        score = sum(1 for skill in required_lower if skill in details_lower)
        scored_skills.append((score, skill_group))

    # Sort by score descending (highest relevance first)
    scored_skills.sort(key=lambda x: x[0], reverse=True)
    return [s for _, s in scored_skills]


def _rerank_projects(
    original_projects: list[dict],
    keywords: list[str],
) -> list[dict]:
    """Move most relevant projects to top of list."""
    keywords_lower = {k.lower() for k in keywords}
    scored = []

    for project in original_projects:
        text = " ".join(project.get("highlights", [])).lower()
        text += " " + project.get("name", "").lower()
        score = sum(1 for k in keywords_lower if k in text)
        scored.append((score, project))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [p for _, p in scored]


def save_tailored_resume(tailored: dict, company: str, role: str) -> Path:
    """
    Save tailored resume YAML to a temp file for LaTeX compilation.

    Returns:
        Path to saved YAML file
    """
    import re
    safe_company = re.sub(r'[^a-zA-Z0-9-]', '-', company.lower())[:40]
    safe_role = re.sub(r'[^a-zA-Z0-9-]', '-', role.lower())[:40]

    output_dir = Path("resumes")
    output_dir.mkdir(exist_ok=True)

    yaml_path = output_dir / f"{safe_company}-{safe_role}.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(tailored, f, default_flow_style=False, allow_unicode=True)

    logger.info(f"Tailored resume YAML saved: {yaml_path}")
    return yaml_path
