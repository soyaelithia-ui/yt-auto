import logging
import os
from pathlib import Path

from src.observability.context import get_run_context

_logging_initialized = False

LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUP_COUNT = 9


class RunContextFilter(logging.Filter):
    """Inject run-correlation fields into every record.

    Missing fields render as ``-`` so the plain format stays readable when
    no pipeline turn is active (CLI, pollers, tests).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        context = get_run_context()
        record.run_id = getattr(record, "run_id", None) or context.run_id or "-"
        record.component = (
            getattr(record, "component", None)
            or context.component
            or record.name.split(".")[-1]
        )
        record.stage = getattr(record, "stage", None) or context.stage or "-"
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
