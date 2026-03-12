"""
tests/test_tracker.py — Unit tests for Module 4: Tracker & Email Monitor.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestEmailParser:
    def test_match_email_to_job_by_company_name(self):
        """Email from company should match that company's job application."""
        from modules.tracker.email_parser import match_email_to_job

        email = {
            "sender": "hr@google.com",
            "subject": "Interview invitation for Software Engineer",
            "body": "Dear candidate, Google would like to invite you for an interview.",
        }

        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: {"job_id": "job-123", "company": "Google"}[key]

        with patch("modules.tracker.email_parser.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchall.return_value = [mock_row]
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            result = match_email_to_job(email)
            # Should match google.com domain to Google company
            assert result is not None

    def test_run_email_monitor_returns_stats(self):
        """Email monitor should return processing statistics."""
        from modules.tracker.email_parser import run_email_monitor

        with patch("modules.tracker.email_parser.fetch_unread_job_emails", return_value=[]), \
             patch("modules.tracker.email_parser.mark_email_processed"):

            stats = run_email_monitor()
            assert "processed" in stats
            assert "interviews" in stats
            assert "rejections" in stats


class TestGmailMonitor:
    def test_gmail_query_contains_interview_keywords(self):
        """Gmail query should include configured interview keywords."""
        from modules.tracker.gmail_monitor import build_gmail_query

        settings = {
            "email_monitor": {
                "interview_keywords": ["interview", "schedule"],
                "rejection_keywords": ["regret"],
            }
        }
        query = build_gmail_query(settings)
        assert "interview" in query
        assert "schedule" in query
        assert "regret" in query

    def test_already_processed_check(self):
        """Emails already in DB should be skipped."""
        from modules.tracker.gmail_monitor import _is_already_processed

        with patch("modules.tracker.gmail_monitor.get_db") as mock_db:
            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = [1]
            mock_db.return_value.__enter__ = MagicMock(return_value=mock_conn)
            mock_db.return_value.__exit__ = MagicMock(return_value=False)

            assert _is_already_processed("gmail-id-123") is True


class TestSheetsWriter:
    def test_append_application_saves_to_retry_on_failure(self):
        """Failed Sheets operations should be saved to retry queue."""
        from modules.tracker.sheets_writer import append_application

        with patch("modules.tracker.sheets_writer.build_service") as mock_service, \
             patch("modules.tracker.sheets_writer._save_to_retry_queue") as mock_retry:

            mock_service.side_effect = Exception("API Error")

            job = {"job_id": "j1", "company": "Test", "role": "Dev", "portal": "linkedin"}
            result = append_application(job)

            assert result is None
            mock_retry.assert_called_once()
