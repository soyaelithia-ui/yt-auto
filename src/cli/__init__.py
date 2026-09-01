"""Modular CLI package for YouTube Automation System."""
from src.cli.handlers.queue import list_queue, print_queue
from src.cli.handlers.status import (
    _is_daemon_running,
    cli_errors,
    cli_status,
    print_errors,
    print_status,
)
from src.cli.parser import build_parser, dispatch_cli, translate_legacy_args

__all__ = [
    "build_parser",
    "dispatch_cli",
    "translate_legacy_args",
    "cli_status",
    "list_queue",
    "print_status",
    "print_queue",
    "cli_errors",
    "print_errors",
    "_is_daemon_running",
]

