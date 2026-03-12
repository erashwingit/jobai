"""
modules/interview_prep/company_researcher.py — Company research via LLM + web.
"""
from shared.llm_client import get_llm_client
from shared.logger import get_logger

logger = get_logger(__name__)


def research_company(company: str, role: str) -> str:
    """
    Research a company using LLM knowledge for interview prep.

    Returns:
        Research summary string
    """
    llm = get_llm_client()
    prompt = f"""Provide interview prep research for {company} ({role} position).
Include: company overview, products/services, culture, recent news, competitors.
Format as concise bullet points. State 'not publicly known' where uncertain."""

    try:
        return llm.complete(prompt)
    except Exception as e:
        logger.error(f"Company research failed for {company}: {e}")
        return f"Research {company} on LinkedIn, Glassdoor, and their official website before the interview."
