"""
modules/interview_prep/prep_generator.py — Full interview prep sheet generation.
Generates comprehensive Q&A, STAR stories, and company research using LLM.
"""
import json
from shared.llm_client import get_llm_client, sanitize_input
from shared.config_validator import load_profile
from shared.logger import get_logger

logger = get_logger(__name__)


def generate_prep_sheet(job: dict) -> dict:
    """
    Generate a complete interview prep sheet for a job.

    Args:
        job: Job dict with company, role, jd_raw, jd_parsed

    Returns:
        Prep sheet dict with all sections
    """
    company = job.get("company", "Unknown")
    role = job.get("role", "Unknown")
    jd_text = job.get("jd_raw", "")
    jd_parsed = job.get("jd_parsed") or {}

    if isinstance(jd_parsed, str):
        try:
            jd_parsed = json.loads(jd_parsed)
        except json.JSONDecodeError:
            jd_parsed = {}

    profile = load_profile()
    candidate = profile.get("candidate", {})
    llm = get_llm_client()

    logger.info(f"Generating prep sheet for {company} | {role}")

    prep = {
        "company": company,
        "role": role,
        "generated_at": __import__('datetime').datetime.utcnow().isoformat(),
        "sections": {}
    }

    # --- Section 1: Company Overview ---
    prep["sections"]["company_overview"] = _generate_company_overview(company, role, llm)

    # --- Section 2: Role Analysis ---
    prep["sections"]["role_analysis"] = _generate_role_analysis(role, jd_text, jd_parsed, llm)

    # --- Section 3: Behavioral Questions (HR Round) ---
    prep["sections"]["behavioral_questions"] = _generate_behavioral_questions(
        company, role, llm
    )

    # --- Section 4: Technical Questions ---
    prep["sections"]["technical_questions"] = _generate_technical_questions(
        role, jd_text, jd_parsed, llm
    )

    # --- Section 5: STAR Stories ---
    prep["sections"]["star_stories"] = _generate_star_stories(candidate, role, llm)

    # --- Section 6: Questions to Ask ---
    prep["sections"]["questions_to_ask"] = _generate_questions_to_ask(company, role, llm)

    # --- Section 7: Managerial Questions ---
    prep["sections"]["managerial_questions"] = _generate_managerial_questions(role, llm)

    logger.info(f"Prep sheet generated: {len(prep['sections'])} sections")
    return prep


def _generate_company_overview(company: str, role: str, llm) -> str:
    """Research and summarize the company."""
    prompt = f"""Provide a concise interview preparation summary for a candidate interviewing at {company} for a {role} position.

Include:
1. What the company does (2-3 sentences)
2. Company size, founded year, business model
3. Recent news or developments (mention if unknown)
4. Company culture and values (based on public information)
5. Key products/services relevant to this role
6. Main competitors

Format as bullet points. Be factual; state "information not available" if unsure."""

    try:
        return llm.complete(prompt)
    except Exception as e:
        logger.error(f"Company overview generation failed: {e}")
        return f"Research {company} on LinkedIn, Glassdoor, and their official website."


def _generate_role_analysis(role: str, jd_text: str, jd_parsed: dict, llm) -> str:
    """Analyze the role and key responsibilities."""
    safe_jd = sanitize_input(jd_text, max_length=3000)
    skills = jd_parsed.get("skills", [])

    prompt = f"""Analyze this {role} position for interview preparation.

Job Description:
{safe_jd}

Key required skills: {', '.join(skills[:15])}

Provide:
1. Core responsibilities summary (3-4 bullets)
2. Key technical skills to demonstrate
3. What success looks like in this role (first 90 days)
4. Red flags or challenges in this role
5. How to position your experience for this role

Format as clear bullet points."""

    try:
        return llm.complete(prompt)
    except Exception as e:
        logger.error(f"Role analysis failed: {e}")
        return f"Review the job description for {role} carefully before the interview."


def _generate_behavioral_questions(company: str, role: str, llm) -> list[dict]:
    """Generate HR/behavioral interview questions with answer frameworks."""
    prompt = f"""Generate 8 behavioral interview questions for a {role} position at {company}.

For each question provide:
1. The question
2. What the interviewer is assessing
3. Answer framework (STAR method tips)

Format as JSON array:
[
  {{
    "question": "Tell me about yourself",
    "assessing": "communication, background relevance",
    "framework": "2-min pitch: current role → key achievements → why this role"
  }}
]

Return ONLY the JSON array, no other text."""

    try:
        response = llm.complete(prompt)
        import re
        array_match = re.search(r'\[.*\]', response, re.DOTALL)
        if array_match:
            return json.loads(array_match.group())
    except Exception as e:
        logger.error(f"Behavioral questions failed: {e}")

    return [
        {"question": "Tell me about yourself.", "assessing": "Communication", "framework": "Present → Past → Future"},
        {"question": "Why do you want to work at this company?", "assessing": "Motivation", "framework": "Research → Alignment → Contribution"},
        {"question": "Describe a challenging project.", "assessing": "Problem-solving", "framework": "Situation → Challenge → Action → Result"},
    ]


def _generate_technical_questions(role: str, jd_text: str, jd_parsed: dict, llm) -> list[dict]:
    """Generate technical interview questions based on JD."""
    safe_jd = sanitize_input(jd_text, max_length=2000)
    skills = jd_parsed.get("skills", [])

    prompt = f"""Generate 10 technical interview questions for a {role} position.

Required skills: {', '.join(skills[:15])}
JD context: {safe_jd[:500]}

For each question:
- Include both conceptual and practical questions
- Range from fundamental to advanced
- Indicate difficulty level (basic/intermediate/advanced)

Format as JSON array:
[
  {{
    "question": "Explain the difference between supervised and unsupervised learning",
    "topic": "Machine Learning fundamentals",
    "difficulty": "basic",
    "key_points": ["definition", "examples", "use cases"]
  }}
]

Return ONLY the JSON array."""

    try:
        response = llm.complete(prompt)
        import re
        array_match = re.search(r'\[.*\]', response, re.DOTALL)
        if array_match:
            return json.loads(array_match.group())
    except Exception as e:
        logger.error(f"Technical questions failed: {e}")

    return [
        {"question": f"Walk me through your experience with {skills[0] if skills else 'your primary technology'}", "topic": "Core skills", "difficulty": "intermediate", "key_points": []},
    ]


def _generate_star_stories(candidate: dict, role: str, llm) -> list[dict]:
    """Generate STAR stories from candidate's experience."""
    skills = candidate.get("skills_primary", [])
    summary = candidate.get("professional_summary", "")

    prompt = f"""Create 5 STAR (Situation-Task-Action-Result) story templates for a {role} candidate.

Candidate background:
- Primary skills: {', '.join(skills[:10])}
- Summary: {sanitize_input(summary, max_length=300)}

For each story provide a template with placeholder sections:
- Situation: [context setup]
- Task: [what needed to be done]
- Action: [specific steps taken — use technical skills]
- Result: [quantified outcome]

Cover these themes:
1. Solving a complex technical problem
2. Leadership or mentoring
3. Delivering under pressure/deadline
4. Collaboration/cross-team work
5. Learning a new technology quickly

Format as JSON array with: theme, situation, task, action, result fields."""

    try:
        response = llm.complete(prompt)
        import re
        array_match = re.search(r'\[.*\]', response, re.DOTALL)
        if array_match:
            return json.loads(array_match.group())
    except Exception as e:
        logger.error(f"STAR stories generation failed: {e}")

    return [{"theme": "Technical Problem Solving", "situation": "[Describe context]", "task": "[What was required]", "action": "[Steps taken]", "result": "[Quantified outcome]"}]


def _generate_questions_to_ask(company: str, role: str, llm) -> list[str]:
    """Generate smart questions for the candidate to ask the interviewer."""
    prompt = f"""Generate 8 thoughtful questions a {role} candidate should ask during an interview at {company}.

Include questions about:
- Team structure and culture
- Technical stack and challenges
- Growth opportunities
- Success metrics for this role
- Company direction

These should show genuine interest and research. Format as a simple JSON array of strings.
Return ONLY the JSON array."""

    try:
        response = llm.complete(prompt)
        import re
        array_match = re.search(r'\[.*\]', response, re.DOTALL)
        if array_match:
            return json.loads(array_match.group())
    except Exception as e:
        logger.error(f"Questions to ask generation failed: {e}")

    return [
        f"What does success look like in the first 90 days for this {role} role?",
        "What are the biggest technical challenges the team is currently facing?",
        "How does the team approach knowledge sharing and mentorship?",
        "What does the on-call/incident rotation look like?",
        "How is performance measured for this role?",
    ]


def _generate_managerial_questions(role: str, llm) -> list[dict]:
    """Generate managerial round questions with answer tips."""
    prompt = f"""Generate 6 managerial interview questions for a {role} candidate.

Focus on: leadership potential, conflict resolution, prioritization, stakeholder management.

Format as JSON array:
[{{"question": "...", "tip": "answer approach"}}]

Return ONLY the JSON array."""

    try:
        response = llm.complete(prompt)
        import re
        array_match = re.search(r'\[.*\]', response, re.DOTALL)
        if array_match:
            return json.loads(array_match.group())
    except Exception as e:
        logger.error(f"Managerial questions failed: {e}")

    return [
        {"question": "How do you handle disagreements with your manager?", "tip": "Show maturity, process-first approach"},
        {"question": "How do you prioritize when everything is urgent?", "tip": "Describe a framework: impact vs effort matrix"},
    ]
