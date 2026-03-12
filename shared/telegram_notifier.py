"""
shared/telegram_notifier.py — Telegram bot notifications.
Sends real-time alerts for job events, interview invites, and errors.
"""
import os
import requests
from shared.logger import get_logger

logger = get_logger(__name__)

_TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"


def notify(
    message: str,
    parse_mode: str = "HTML",
    silent: bool = False,
) -> bool:
    """
    Send a Telegram notification.

    Args:
        message: Message text (supports HTML formatting)
        parse_mode: "HTML" or "Markdown"
        silent: If True, send without sound notification

    Returns:
        True if sent successfully, False otherwise
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        logger.warning("Telegram credentials not configured — skipping notification")
        return False

    # Check if notifications are enabled in settings
    if os.getenv("TELEGRAM_ENABLED", "true").lower() == "false":
        return False

    url = _TELEGRAM_API.format(token=token)
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": parse_mode,
        "disable_notification": silent,
    }

    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Telegram notification sent successfully")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram notification: {type(e).__name__}")
        return False


# ============================================================
# Convenience notification builders
# ============================================================

def notify_jobs_queued(count: int, portal: str) -> None:
    notify(
        f"🔍 <b>Job Discovery</b>\n"
        f"Found <b>{count}</b> new jobs on <b>{portal}</b> matching your profile.\n"
        f"Pipeline started automatically."
    )


def notify_applied(company: str, role: str, portal: str) -> None:
    notify(
        f"✅ <b>Applied!</b>\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Role:</b> {role}\n"
        f"<b>Portal:</b> {portal}"
    )


def notify_needs_human(company: str, role: str, url: str, reason: str) -> None:
    notify(
        f"⚠️ <b>Manual Action Needed</b>\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Role:</b> {role}\n"
        f"<b>Reason:</b> {reason}\n"
        f"<b>URL:</b> {url}"
    )


def notify_interview_scheduled(company: str, role: str, date: str, format_: str) -> None:
    notify(
        f"🎉 <b>Interview Scheduled!</b>\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Role:</b> {role}\n"
        f"<b>Date:</b> {date}\n"
        f"<b>Format:</b> {format_}\n"
        f"Prep sheet being generated automatically..."
    )


def notify_rejected(company: str, role: str) -> None:
    notify(
        f"❌ <b>Rejection</b>\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Role:</b> {role}\n"
        f"Keep going! Next opportunity is closer.",
        silent=True,
    )


def notify_prep_ready(company: str, role: str, doc_url: str) -> None:
    notify(
        f"📚 <b>Prep Sheet Ready!</b>\n"
        f"<b>Company:</b> {company}\n"
        f"<b>Role:</b> {role}\n"
        f"<b>View:</b> {doc_url}"
    )


def notify_error(module: str, error_summary: str) -> None:
    notify(
        f"🚨 <b>Error in {module}</b>\n"
        f"{error_summary}\n"
        f"Check logs for details."
    )


def notify_daily_summary(
    total_applied: int,
    total_interviews: int,
    total_rejections: int,
    needs_human: int,
) -> None:
    notify(
        f"📊 <b>Daily Summary</b>\n"
        f"Applied: <b>{total_applied}</b>\n"
        f"Interviews: <b>{total_interviews}</b>\n"
        f"Rejections: {total_rejections}\n"
        f"Needs Review: <b>{needs_human}</b>"
    )
