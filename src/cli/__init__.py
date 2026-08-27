"""Modular CLI package for YouTube Automation System."""
from src.cli.parser import build_parser, dispatch_cli, translate_legacy_args
from src.cli.legacy import (
    _is_daemon_running,
    cli_errors,
    cli_status,
    list_queue,
    print_errors,
    print_queue,
    print_status,
)

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
