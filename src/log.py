import logging
import os
from pathlib import Path

from src.observability.context import get_run_context

_logging_initialized = False

LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUP_COUNT = 9


import re

_REDACTION_PATTERNS = [
    # Telegram Bot Token format: 123456789:ABCdef-ghij_klmn12345
    (re.compile(r"\b(\d{8,12}:)[A-Za-z0-9_-]{30,40}\b"), r"\1***REDACTED***"),
    # Google / OAuth Refresh and Access Tokens
    (re.compile(r"(?i)(refresh_token|client_secret|api_key|access_token|secret)([\"']?\s*[:=]\s*[\"']?)([\w\-\.]{15,})"), r"\1\2***REDACTED***"),
    # Bearer Tokens
    (re.compile(r"(?i)bearer\s+([A-Za-z0-9_\-\.]{20,})"), r"Bearer ***REDACTED***"),
]


def redact_secrets(text: str) -> str:
    """Sanitizes text by replacing credential tokens with redacted masks."""
    if not isinstance(text, str):
        text = str(text)
    for pattern, repl in _REDACTION_PATTERNS:
        text = pattern.sub(repl, text)
    return text


class RunContextFilter(logging.Filter):
    """Inject run-correlation fields and redact sensitive secrets."""

    def filter(self, record: logging.LogRecord) -> bool:
        context = get_run_context()
        record.run_id = getattr(record, "run_id", None) or context.run_id or "-"
        record.component = (
            getattr(record, "component", None)
            or context.component
            or record.name.split(".")[-1]
        )
        record.stage = getattr(record, "stage", None) or context.stage or "-"

        # Redact secrets in message
        if isinstance(record.msg, str):
            record.msg = redact_secrets(record.msg)
        if record.args:
            if isinstance(record.args, dict):
                record.args = {k: redact_secrets(v) if isinstance(v, str) else v for k, v in record.args.items()}
            elif isinstance(record.args, tuple):
                record.args = tuple(redact_secrets(v) if isinstance(v, str) else v for v in record.args)
        return True


def setup_logging(log_level=logging.INFO):
    """Configura logging centralizado para el sistema YouTube Automation."""
    global _logging_initialized
    if _logging_initialized:
        return logging.getLogger("yt_auto")

    base_dir = Path(__file__).resolve().parent.parent
    log_dir = Path(os.environ.get("YT_LOG_DIR") or (base_dir / "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        '%(asctime)s [%(levelname)s] %(name)s [run=%(run_id)s stage=%(stage)s]: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    root_logger = logging.getLogger("yt_auto")
    root_logger.setLevel(log_level)

    # Prevenir handlers duplicados si se llama múltiples veces
    if not root_logger.handlers:
        # Rotación: evita crecimiento ilimitado del disco (guard de recursos).
        from logging.handlers import RotatingFileHandler

        file_handler = RotatingFileHandler(
            log_dir / "youtube_automation.log",
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        context_filter = RunContextFilter()
        for handler in (file_handler, console_handler):
            handler.addFilter(context_filter)
            root_logger.addHandler(handler)

    _logging_initialized = True
    return root_logger

def get_logger(module_name: str):
    """Devuelve un logger hijo de yt_auto."""
    setup_logging()
    return logging.getLogger(f"yt_auto.{module_name}")
