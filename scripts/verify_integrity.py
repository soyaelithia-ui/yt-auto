#!/usr/bin/env python3
"""
scripts/verify_integrity.py - Unified High-Performance Repository Integrity Runner.

Cadence Integrity Audit & Anti-Regression Kill Switch for yt-auto.
Enforces Project Governance Policy: Mandatory check every 25 commits or pre-run.

Supports:
  --fast: Skips heavy test suite collectability verification.
  --staged: Evaluates path and AST checks strictly on git staged files (< 50ms).
  --json: Emits machine-readable JSON schema for MCP tools and CI pipelines.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

# Auto-re-exec with repo .venv python if available and not already running in it
_repo_root = Path(__file__).resolve().parent.parent
_repo_venv = _repo_root / ".venv"
_repo_venv_py = _repo_venv / "bin" / "python3"
if (sys.prefix != str(_repo_venv.resolve())) and _repo_venv_py.is_file() and os.environ.get("INTEGRITY_REEXEC") != "1":
    os.environ["INTEGRITY_REEXEC"] = "1"
    os.execv(str(_repo_venv_py), [str(_repo_venv_py)] + sys.argv)

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import argparse
import json

from src.verification.guardrails import run_integrity_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Repository Invariant & Governance Verification Engine",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Fast mode: skip heavy test collectability inspection",
    )
    parser.add_argument(
        "--staged",
        action="store_true",
        help="Staged mode: inspect only git cached files for pre-commit (< 50ms)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Output structured JSON instead of formatted terminal text",
    )

    args = parser.parse_args()
    fast_mode = args.fast or os.environ.get("INTEGRITY_FAST") == "1"

    report = run_integrity_audit(
        REPO_ROOT,
        staged=args.staged,
        fast=fast_mode,
    )

    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
        return report.exit_code

    # Standard CLI formatted terminal output
    print("======================================================================")
    if args.staged:
        print("🛡️  [INTEGRITY AUDIT] Verifying Staged Pre-Commit Changes")
    else:
        print("🔍 [INTEGRITY AUDIT] Checking Repository Invariants & Governance SLA")
    print("======================================================================")

    for item in report.checks_passed:
        print(f"✅ [PASS] {item}")

    for fail in report.checks_failed:
        print(f"❌ [FAIL] {fail.get('message', fail.get('name'))}")
        for detail in fail.get("details", []):
            print(f"   {detail}")

    print("======================================================================")
    if report.healthy:
        if args.staged:
            print(f"🎉 [STATUS: HEALTHY] Pre-commit verification passed cleanly in {report.duration_ms}ms.")
        else:
            print(f"🎉 [STATUS: HEALTHY] All invariants verified at commit #{report.commit_count} ({report.duration_ms}ms).")
        print("🚀 Safe to proceed with development or production pipelines.")
        print("======================================================================")
    else:
        print(f"🛑 [REFUSAL TRIGGERED] {len(report.checks_failed)} integrity check(s) failed!")
        print("🚨 POLICY MANDATE: Work MUST be halted immediately. Alert the operator.")
        print("   Do NOT implement new features or run pipelines until sanitized.")
        print("======================================================================")

    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
