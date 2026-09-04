#!/usr/bin/env python3
"""
E2E Test Runner for yt-auto Visual Pipeline.

Provides command-line options for executing multi-tier E2E tests,
generating structured JSON and JUnit test reports, and enforcing
strict exit code semantics:
  - 0: All executed tests passed (or passed/skipped).
  - 1: One or more tests failed.
  - 2: CLI argument or configuration error.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import pytest


FEATURE_DEFINITIONS = {
    "F01": "Legacy Code & Template Deletion",
    "F02": "Media Exports & Registry Refactor",
    "F03": "Pipeline Branch Pruning",
    "F04": "Native Procedural Engine (quarantined/_legacy; wgpu opt-in)",
    "F05": "WGSL Shaders Catalog",
    "F06": "SVG Overlay Engine (resvg-py)",
    "F07": "SVG Vector Assets Catalog",
    "F08": "In-Memory Frame Compositor",
    "F09": "ASS Subtitle Generator",
    "F10": "Monotonic Timestamp Sanitizer",
    "F11": "Unified Atomic FFmpeg Encoder",
    "F12": "SceneManifest Contract Synchronization",
    "F13": "Scene Planner Agent Sync",
    "F14": "Deterministic Video QA Gate",
    "F15": "Documentation Synchronization",
    "F16": "E2E Testing Suite (Tiers 1–4)",
}


class E2ETestResultCollector:
    """Pytest plugin hook to collect structured per-test execution data."""

    def __init__(self) -> None:
        self.tests: List[Dict[str, Any]] = []
        self.start_time: float = time.time()
        self.end_time: float = 0.0

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        if report.when == "call" or (report.when == "setup" and report.outcome != "passed"):
            # Determine feature and tier from nodeid or test name
            nodeid = report.nodeid
            test_name = report.head_line or nodeid.split("::")[-1]
            
            tier = "unknown"
            if "test_tier1" in nodeid:
                tier = "tier1"
            elif "test_tier2" in nodeid:
                tier = "tier2"
            elif "test_tier3" in nodeid:
                tier = "tier3"
            elif "test_tier4" in nodeid:
                tier = "tier4"

            feature = "general"
            for fid in FEATURE_DEFINITIONS.keys():
                if f"_{fid.lower()}_" in test_name.lower() or f"test_{fid.lower()}" in test_name.lower():
                    feature = fid
                    break

            error_text = None
            if report.failed:
                error_text = str(report.longrepr)

            self.tests.append({
                "nodeid": nodeid,
                "name": test_name,
                "tier": tier,
                "feature": feature,
                "outcome": report.outcome,
                "duration": round(report.duration, 4),
                "error": error_text,
            })

    def get_summary(self) -> Dict[str, Any]:
        total = len(self.tests)
        passed = sum(1 for t in self.tests if t["outcome"] == "passed")
        failed = sum(1 for t in self.tests if t["outcome"] == "failed")
        skipped = sum(1 for t in self.tests if t["outcome"] == "skipped")
        duration = round((self.end_time or time.time()) - self.start_time, 2)

        by_tier: Dict[str, Dict[str, int]] = {}
        for t in ["tier1", "tier2", "tier3", "tier4"]:
            tier_tests = [x for x in self.tests if x["tier"] == t]
            by_tier[t] = {
                "total": len(tier_tests),
                "passed": sum(1 for x in tier_tests if x["outcome"] == "passed"),
                "failed": sum(1 for x in tier_tests if x["outcome"] == "failed"),
                "skipped": sum(1 for x in tier_tests if x["outcome"] == "skipped"),
            }

        by_feature: Dict[str, Dict[str, int]] = {}
        for fid in FEATURE_DEFINITIONS.keys():
            feat_tests = [x for x in self.tests if x["feature"] == fid]
            by_feature[fid] = {
                "name": FEATURE_DEFINITIONS[fid],
                "total": len(feat_tests),
                "passed": sum(1 for x in feat_tests if x["outcome"] == "passed"),
                "failed": sum(1 for x in feat_tests if x["outcome"] == "failed"),
                "skipped": sum(1 for x in feat_tests if x["outcome"] == "skipped"),
            }

        return {
            "summary": {
                "total": total,
                "passed": passed,
                "failed": failed,
                "skipped": skipped,
                "duration_seconds": duration,
                "success": failed == 0,
            },
            "by_tier": by_tier,
            "by_feature": by_feature,
            "tests": self.tests,
        }


def parse_arguments(args: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="E2E Test Runner for yt-auto Visual Pipeline",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--tier",
        choices=["1", "2", "3", "4", "all"],
        default="all",
        help="Filter execution by test tier (1=features, 2=boundaries, 3=combos, 4=workloads, all=all tiers)",
    )
    parser.add_argument(
        "--feature",
        type=str,
        default=None,
        help="Filter execution by specific feature ID (e.g., F01, F04, F11)",
    )
    parser.add_argument(
        "--json-report",
        "--json",
        type=str,
        default=None,
        dest="json_report",
        help="Path to write structured JSON test report",
    )
    parser.add_argument(
        "--junit",
        type=str,
        default=None,
        help="Path to write JUnit XML report",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output during test execution",
    )
    parser.add_argument(
        "--fail-fast",
        "-x",
        action="store_true",
        help="Stop execution immediately on first test failure",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Per-test timeout in seconds",
    )
    parser.add_argument(
        "--list-features",
        action="store_true",
        help="List all registered features and exit",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and list tests without running them",
    )
    return parser.parse_args(args)


def print_feature_list() -> None:
    print("=" * 70)
    print("yt-auto Visual Pipeline Feature Inventory")
    print("=" * 70)
    print(f"{'Feature ID':<12} | {'Description'}")
    print("-" * 70)
    for fid, name in FEATURE_DEFINITIONS.items():
        print(f"{fid:<12} | {name}")
    print("=" * 70)


def print_summary_table(summary: Dict[str, Any]) -> None:
    s = summary["summary"]
    print("\n" + "=" * 70)
    print("E2E TEST EXECUTION SUMMARY")
    print("=" * 70)
    print(f"Total Tests Executed : {s['total']}")
    print(f"Passed               : {s['passed']}")
    print(f"Failed               : {s['failed']}")
    print(f"Skipped              : {s['skipped']}")
    print(f"Duration             : {s['duration_seconds']}s")
    print(f"Status               : {'PASSED' if s['success'] else 'FAILED'}")
    print("-" * 70)
    print("Breakdown by Tier:")
    for tier, data in summary["by_tier"].items():
        print(f"  - {tier.upper():<6}: Total {data['total']:<3} | Passed {data['passed']:<3} | Failed {data['failed']:<3} | Skipped {data['skipped']:<3}")
    print("-" * 70)
    print("Breakdown by Feature:")
    for fid, data in summary["by_feature"].items():
        if data["total"] > 0:
            print(f"  - {fid} ({data['name'][:30]:<30}): Total {data['total']:<2} | Passed {data['passed']:<2} | Failed {data['failed']:<2}")
    print("=" * 70)


def main(raw_args: Optional[List[str]] = None) -> int:
    try:
        args = parse_arguments(raw_args)
    except SystemExit as e:
        return 2 if e.code != 0 else 0

    if args.list_features:
        print_feature_list()
        return 0

    project_root = Path(__file__).resolve().parents[2]
    tests_dir = project_root / "tests" / "e2e"

    pytest_args = ["-m", "not live"]

    if args.verbose:
        pytest_args.append("-v")
    else:
        pytest_args.append("-q")

    if args.fail_fast:
        pytest_args.append("-x")

    if args.dry_run:
        pytest_args.append("--collect-only")

    # Tier selection
    if args.tier == "1":
        pytest_args.append(str(tests_dir / "test_tier1_features.py"))
    elif args.tier == "2":
        pytest_args.append(str(tests_dir / "test_tier2_boundaries.py"))
    elif args.tier == "3":
        pytest_args.append(str(tests_dir / "test_tier3_combinations.py"))
    elif args.tier == "4":
        pytest_args.append(str(tests_dir / "test_tier4_workloads.py"))
    else:
        pytest_args.append(str(tests_dir))

    # Feature filtering
    if args.feature:
        feat = args.feature.upper()
        if feat not in FEATURE_DEFINITIONS:
            print(f"Error: Unknown feature '{args.feature}'. Use --list-features to see valid features.", file=sys.stderr)
            return 2
        pytest_args.extend(["-k", f"_{feat.lower()}_ or test_{feat.lower()}"])

    if args.junit:
        pytest_args.extend(["--junitxml", args.junit])

    collector = E2ETestResultCollector()

    print(f"Starting E2E test run (Tier: {args.tier}, Feature: {args.feature or 'All'})...")
    
    exit_code = pytest.main(pytest_args, plugins=[collector])
    collector.end_time = time.time()

    summary_data = collector.get_summary()

    print_summary_table(summary_data)

    if args.json_report:
        report_path = Path(args.json_report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(summary_data, f, indent=2)
        print(f"Structured JSON report written to: {report_path}")

    # Return exit code: 0 if all tests passed (or 0 tests in dry-run), 1 if failures
    if exit_code == pytest.ExitCode.OK:
        return 0
    elif exit_code == pytest.ExitCode.NO_TESTS_COLLECTED:
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
