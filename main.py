#!/usr/bin/env python3
"""Unified CLI entry point and canonical module re-exporter for YouTube Automation."""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Sequence

_project_dir = Path(__file__).resolve().parent
_projects_dir = str(_project_dir.parent)
if _projects_dir not in sys.path:
    sys.path.insert(0, _projects_dir)

_venv_dir = _project_dir / ".venv"
_venv_python = _venv_dir / "bin" / "python3"
if not _venv_python.is_file():
    _venv_python = _venv_dir / "bin" / "python"
if _venv_python.is_file() and Path(sys.prefix).resolve() != _venv_dir.resolve() and not os.environ.get("_YTAUTO_VENV_ACTIVE"):
    os.environ["_YTAUTO_VENV_ACTIVE"] = "1"
    os.execv(str(_venv_python), [str(_venv_python)] + sys.argv)


def _preparse_profile(argv: list[str]) -> None:
    """Apply --profile / -p before src.config is imported (env-driven defaults)."""
    for flag in ("--profile", "-p"):
        if flag in argv:
            idx = argv.index(flag)
            if idx + 1 < len(argv):
                os.environ["YT_PROFILE"] = argv[idx + 1]
                break


_preparse_profile(sys.argv)

try:
    from src.cli.parser import build_parser, dispatch_cli, translate_legacy_args
except ModuleNotFoundError:
    # Fallback for test fixtures stubbing sys.modules['src.cli'] as a flat module
    import importlib.util

    _parser_path = Path(__file__).resolve().parent / "src" / "cli" / "parser.py"
    _spec = importlib.util.spec_from_file_location("src.cli.parser", str(_parser_path))
    if _spec and _spec.loader:
        _parser_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_parser_mod)
        build_parser = _parser_mod.build_parser
        dispatch_cli = _parser_mod.dispatch_cli
        translate_legacy_args = _parser_mod.translate_legacy_args

from src.config import LOCK_FILE_PATH
from src.core.lock import (
    acquire_lock,
    register_signal_handlers,
    release_lock,
)
from src.daemon import run_pipeline_once
from src.log import setup_logging

logger = logging.getLogger("main")

__all__ = [
    "acquire_lock",
    "release_lock",
    "LOCK_FILE_PATH",
    "run_pipeline_once",
    "register_signal_handlers",
    "_preparse_profile",
    "build_parser",
    "main",
]


def main(argv: Sequence[str] | None = None) -> int:
    """Main CLI entrypoint: setup logging, signal handlers, parse arguments and dispatch."""
    setup_logging()
    register_signal_handlers()

    raw_args = list(argv) if argv is not None else sys.argv[1:]
    translated_args = translate_legacy_args(raw_args)

    parser = build_parser()
    args = parser.parse_args(translated_args)

    try:
        return dispatch_cli(args, parser)
    except SystemExit:
        raise
    except Exception as e:
        logger.error(f"Execution error: {e}")
        raise


if __name__ == "__main__":
    sys.exit(main())
