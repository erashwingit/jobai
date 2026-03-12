"""
modules/interview_prep/star_generator.py — STAR story generator.
Generates structured behavioral interview stories from candidate experience.
"""
from shared.llm_client import get_llm_client, sanitize_input
from shared.config_validator import load_profile
from shared.logger import get_logger

logger = get_logger(__name__)


def generate_star_stories(role: str, target_themes: list[str] | None = None) -> list[dict]:
    """
    Generate STAR story templates for behavioral interviews.

    Args:
        role: Target role name
        target_themes: Optional list of themes to cover

    Returns:
        List of STAR story dicts
    """
    profile = load_profile()
    candidate = profile.get("candidate", {})
    llm = get_llm_client()

    themes = target_themes or [
        "technical problem solving",
        "leadership",
        "working under pressure",
        "cross-team collaboration",
        "learning a new technology",
    ]

    stories = []
    for theme in themes[:5]:
        story = _generate_single_story(
            theme=theme,
            role=role,
            skills=candidate.get("skills_primary", []),
            llm=llm,
        )
        if story:
            stories.append(story)

    return stories


def _generate_single_story(theme: str, role: str, skills: list, llm) -> dict | None:
    """Generate a single STAR story template."""
    skills_str = ", ".join(skills[:8])
    prompt = f"""Create a STAR story template for a {role} candidate.
Theme: {theme}
Available skills to use: {skills_str}

Provide a realistic, detailed template:
- Situation: specific workplace context
- Task: clear objective
- Action: 3 specific technical actions taken (use relevant skills)
- Result: quantified outcome (%, time saved, users impacted)

Keep it concise and specific. Output ONLY as JSON:
{{"theme": "{theme}", "situation": "...", "task": "...", "action": "...", "result": "..."}}"""

    try:
        response = llm.complete(prompt)
        from shared.llm_client import parse_json_response
        return parse_json_response(response)
    except Exception as e:
        logger.error(f"STAR story generation failed for theme '{theme}': {e}")
        return {
            "theme": theme,
            "situation": f"[Describe a real situation involving {theme}]",
            "task": "[What was required of you]",
            "action": f"[Specific actions using {', '.join(skills[:3])}]",
            "result": "[Quantified outcome: X% improvement, Y hours saved]",
        }
