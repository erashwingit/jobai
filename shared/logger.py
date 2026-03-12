"""
shared/logger.py — Structured JSON logger with PII sanitization.
Security: Automatically redacts emails, phone numbers, passwords, and API keys.
"""
import logging
import re
import os
import sys
from datetime import datetime
from pathlib import Path


class PIISanitizer(logging.Filter):
    """Remove PII from log records before writing (security control)."""

    PII_PATTERNS = [
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
        # Indian phone numbers
        (r'\b(\+91|0)?[6-9]\d{9}\b', '[PHONE]'),
        # Password fields in strings
        (r'(?i)(password|passwd|pwd)(["\s:=]+)[^\s,}"\']+', r'\1\2[REDACTED]'),
        # API keys / tokens / secrets
        (r'(?i)(api_key|token|secret|bearer|authorization)(["\s:=]+)[^\s,}"\']+',
         r'\1\2[REDACTED]'),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        message = str(record.getMessage())
        for pattern, replacement in self.PII_PATTERNS:
            message = re.sub(pattern, replacement, message, flags=re.IGNORECASE)
        record.msg = message
        record.args = ()
        return True


class JSONFormatter(logging.Formatter):
    """Output logs as structured JSON for easy parsing."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "module": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)
        # Use __import__ to avoid heavy json import at module level
        import json
        return json.dumps(log_entry)


def get_logger(name: str, level: str | None = None) -> logging.Logger:
    """
    Get a configured logger with PII sanitization and JSON output.

    Args:
        name: Logger name (usually __name__ of the calling module)
        level: Log level override; defaults to LOG_LEVEL env var or INFO

    Returns:
        Configured Logger instance
    """
    log_level_str = level or os.getenv("LOG_LEVEL", "INFO")
    log_level = getattr(logging, log_level_str.upper(), logging.INFO)

    logger = logging.getLogger(name)
    logger.setLevel(log_level)

    # Avoid adding duplicate handlers on re-import
    if logger.handlers:
        return logger

    # Add PII sanitizer filter
    logger.addFilter(PIISanitizer())

    # Console handler (stderr for errors, stdout for info)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(JSONFormatter())
    console_handler.setLevel(log_level)
    logger.addHandler(console_handler)

    # File handler — write to logs/ directory
    log_dir = Path(os.getenv("LOG_DIR", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"{name.replace('.', '_')}.log"

    file_handler = logging.FileHandler(log_file)
    file_handler.setFormatter(JSONFormatter())
    file_handler.setLevel(log_level)
    logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger
