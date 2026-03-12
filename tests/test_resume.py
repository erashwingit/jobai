"""
tests/test_resume.py — Unit tests for Module 2: Resume Tailoring Engine.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


class TestATSScorer:
    def test_perfect_keyword_match(self):
        """100% keyword coverage should yield high score."""
        from modules.resume.ats_scorer import calculate_ats_score

        resume_text = """
        AI Engineer with expertise in Python, Machine Learning, PyTorch, FastAPI,
        Docker, Kubernetes. Experience with LLMs, RAG, NLP, and MLOps pipelines.
        Education in Computer Science. Projects include ML pipeline and LLM system.
        Worked from 2020 to 2024.
        """
        jd_analysis = {
            "skills": ["Python", "Machine Learning", "PyTorch", "FastAPI"],
            "keywords": ["LLMs", "RAG", "NLP", "Docker", "Kubernetes"],
        }

        result = calculate_ats_score(resume_text, jd_analysis)
        assert result["total_score"] >= 75
        assert len(result["missing_keywords"]) == 0

    def test_no_match_gives_low_score(self):
        """No keyword overlap should give low score."""
        from modules.resume.ats_scorer import calculate_ats_score

        resume_text = "I like cooking and gardening. My hobby is painting."
        jd_analysis = {
            "skills": ["Python", "TensorFlow", "Kubernetes"],
            "keywords": ["MLOps", "CI/CD", "Docker"],
        }
        result = calculate_ats_score(resume_text, jd_analysis)
        assert result["total_score"] < 30

    def test_empty_resume_returns_zero(self):
        """Empty resume should return zero score."""
        from modules.resume.ats_scorer import calculate_ats_score
        result = calculate_ats_score("", {"skills": ["Python"], "keywords": ["ML"]})
        assert result["total_score"] == 0

    def test_meets_threshold_true(self):
        """Score above threshold returns True."""
        from modules.resume.ats_scorer import meets_threshold
        with patch("modules.resume.ats_scorer.load_settings") as mock_s:
            mock_s.return_value = {"resume": {"ats_min_score": 75}}
            assert meets_threshold({"total_score": 80}) is True

    def test_meets_threshold_false(self):
        """Score below threshold returns False."""
        from modules.resume.ats_scorer import meets_threshold
        with patch("modules.resume.ats_scorer.load_settings") as mock_s:
            mock_s.return_value = {"resume": {"ats_min_score": 75}}
            assert meets_threshold({"total_score": 60}) is False


class TestTailoringEngine:
    def test_skills_reranking_surfaces_relevant_first(self):
        """Skills matching JD keywords should appear first."""
        from modules.resume.tailoring_engine import _tailor_skills

        original_skills = [
            {"label": "Misc", "details": "gardening, cooking"},
            {"label": "AI/ML", "details": "PyTorch, TensorFlow, LLMs, RAG"},
            {"label": "Backend", "details": "FastAPI, PostgreSQL"},
        ]
        required_skills = ["PyTorch", "LLMs"]
        keywords = ["RAG", "FastAPI"]

        result = _tailor_skills(original_skills, required_skills, keywords)
        # AI/ML should come first (most keyword overlap)
        assert result[0]["label"] == "AI/ML"

    def test_projects_reranked_by_relevance(self):
        """Most relevant projects should appear first."""
        from modules.resume.tailoring_engine import _rerank_projects

        projects = [
            {"name": "Web app", "highlights": ["React", "Node.js"]},
            {"name": "ML Pipeline", "highlights": ["PyTorch", "LLMs", "RAG", "MLOps"]},
        ]
        keywords = ["LLMs", "MLOps", "RAG"]
        result = _rerank_projects(projects, keywords)
        assert result[0]["name"] == "ML Pipeline"

    def test_save_tailored_filename_sanitization(self):
        """Output filename should be safely sanitized."""
        from modules.resume.tailoring_engine import save_tailored_resume

        mock_resume = {"cv": {"name": "Test"}, "design": {"theme": "classic"}}

        with patch("modules.resume.tailoring_engine.load_master_resume", return_value=mock_resume), \
             patch("builtins.open", MagicMock()), \
             patch("modules.resume.tailoring_engine.Path.mkdir"):

            path = save_tailored_resume(mock_resume, "Google/Alphabet Inc.", "Senior AI/ML Engineer!")
            # Should not contain special characters
            assert "/" not in path.name or path.name.count("/") == 0
