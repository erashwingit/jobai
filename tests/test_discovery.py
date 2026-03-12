"""
tests/test_discovery.py — Unit tests for Module 1: Job Discovery & Screening.
"""
import pytest
import json
from unittest.mock import patch, MagicMock, AsyncMock


# ============================================================
# Test: Deduplication
# ============================================================

class TestDeduplication:
    def test_deduplicate_removes_existing_jobs(self):
        """Existing jobs should be filtered out."""
        from modules.discovery.deduplicator import deduplicate_jobs

        with patch("modules.discovery.deduplicator.job_exists") as mock_exists:
            mock_exists.side_effect = lambda jid: jid == "existing-123"

            raw_jobs = [
                {"job_id": "existing-123", "company": "OldCo", "role": "Dev"},
                {"job_id": "new-456", "company": "NewCo", "role": "Engineer"},
            ]

            new_jobs = deduplicate_jobs(raw_jobs)
            assert len(new_jobs) == 1
            assert new_jobs[0]["job_id"] == "new-456"

    def test_deduplicate_empty_input(self):
        """Empty input returns empty list."""
        from modules.discovery.deduplicator import deduplicate_jobs
        with patch("modules.discovery.deduplicator.job_exists", return_value=False):
            assert deduplicate_jobs([]) == []

    def test_job_id_generation_is_deterministic(self):
        """Same portal + URL always produces same job_id."""
        from modules.discovery.scraper import _make_job_id
        id1 = _make_job_id("linkedin", "https://example.com/job/123")
        id2 = _make_job_id("linkedin", "https://example.com/job/123")
        assert id1 == id2

    def test_different_urls_produce_different_ids(self):
        from modules.discovery.scraper import _make_job_id
        id1 = _make_job_id("linkedin", "https://example.com/job/123")
        id2 = _make_job_id("linkedin", "https://example.com/job/456")
        assert id1 != id2


# ============================================================
# Test: Match Scorer
# ============================================================

class TestMatchScorer:
    def test_score_above_threshold_queued(self):
        """Jobs with score >= threshold should be queued."""
        from modules.discovery.match_scorer import score_and_queue_jobs

        with patch("modules.discovery.match_scorer.load_settings") as mock_settings, \
             patch("modules.discovery.match_scorer.update_job_status") as mock_update, \
             patch("modules.discovery.match_scorer.notify_jobs_queued"), \
             patch("modules.discovery.match_scorer._is_excluded", return_value=False):

            mock_settings.return_value = {"job_discovery": {"min_match_score": 70}}

            jobs = [{"job_id": "j1", "company": "TechCo", "role": "AI Eng", "portal": "linkedin", "match_score": 85}]
            queued, skipped = score_and_queue_jobs(jobs)

            assert len(queued) == 1
            assert len(skipped) == 0
            mock_update.assert_called_with("j1", "QUEUED")

    def test_score_below_threshold_skipped(self):
        """Jobs with score < threshold should be skipped."""
        from modules.discovery.match_scorer import score_and_queue_jobs

        with patch("modules.discovery.match_scorer.load_settings") as mock_settings, \
             patch("modules.discovery.match_scorer.update_job_status") as mock_update, \
             patch("modules.discovery.match_scorer.notify_jobs_queued"), \
             patch("modules.discovery.match_scorer._is_excluded", return_value=False):

            mock_settings.return_value = {"job_discovery": {"min_match_score": 70}}

            jobs = [{"job_id": "j2", "company": "TechCo", "role": "AI Eng", "portal": "linkedin", "match_score": 45, "jd_raw": ""}]
            queued, skipped = score_and_queue_jobs(jobs)

            assert len(queued) == 0
            assert len(skipped) == 1

    def test_excluded_company_skipped(self):
        """Jobs from excluded companies should be skipped regardless of score."""
        from modules.discovery.match_scorer import _is_excluded
        job = {"company": "BlockedCorp", "role": "Engineer", "jd_raw": ""}
        profile = {"candidate": {"exclude_companies": ["BlockedCorp"], "exclude_keywords": []}}
        assert _is_excluded(job, profile) is True


# ============================================================
# Test: LLM JD Analyzer
# ============================================================

class TestJDAnalyzer:
    @pytest.mark.asyncio
    async def test_analyze_batch_handles_empty_input(self):
        """Empty batch returns empty list."""
        from modules.discovery.jd_analyzer import analyze_batch
        result = await analyze_batch([], profile={})
        assert result == []

    def test_update_job_with_analysis(self):
        """Analysis results are persisted correctly."""
        from modules.discovery.jd_analyzer import update_job_with_analysis

        with patch("modules.discovery.jd_analyzer.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            analysis = {"match_score": 80, "skills": ["Python"], "keywords": ["ML"]}
            update_job_with_analysis("job-123", "JD text", analysis)

            mock_conn.execute.assert_called_once()
