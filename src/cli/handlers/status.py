"""Handler for 'status' subcommand, API diagnostics, error triage, and QA checks."""
from __future__ import annotations

import argparse
import json
import logging
from typing import Any

from src.api_health import check_all, format_status_report
from src.cli.legacy import cli_status, print_errors, print_status
from src.config import DEFAULT_DB_PATH

logger = logging.getLogger("main")


def handle_status(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Display system health, queue counts, external API status, error logs, or video QA."""
    db_path = getattr(args, "db_path", DEFAULT_DB_PATH)

    if getattr(args, "apis", False) or getattr(args, "check_apis", False):
        ch = "moku" if getattr(args, "channel", "all") in ("all", None) else args.channel
        report = check_all(ch)
        print(format_status_report(report, ch))
        return 0

    if getattr(args, "check_pub", False) or getattr(args, "check_publication", False):
        from src.monitor import run_publication_check

        res = run_publication_check()
        print("Publication Check Result:")
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return 0

    if getattr(args, "errors", False):
        print_errors(
            db_path=db_path,
            since=getattr(args, "since", "24h"),
            limit=getattr(args, "limit", 20),
            component=getattr(args, "component", None),
            level=getattr(args, "level", None),
            as_json=getattr(args, "json", False),
        )
        return 0

    if getattr(args, "agent_review", None):
        from src.agents.video_qa import run_video_qa

        report = run_video_qa(args.agent_review, db_path=db_path)
        if getattr(args, "json", False):
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            icon = "✅" if report.get("overall_pass") else "⚠️"
            print(f"{icon} Video QA {report['run_id']}: pass={report.get('overall_pass')} hallazgos={len(report.get('findings', []))}")
            for finding in report.get("findings", []):
                print(
                    f"  - [{finding.get('severity')}/{finding.get('category')}] "
                    f"{finding.get('description')} → {finding.get('suggested_fix', '-')}"
                )
            print(f"Bundle: {report.get('bundle_dir')}")
        return 0

    if getattr(args, "json", False):
        st = cli_status(db_path=db_path)
        print(json.dumps(st, ensure_ascii=False, indent=2, default=str))
    else:
        print_status(db_path=db_path)
    return 0
