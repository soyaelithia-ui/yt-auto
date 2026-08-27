#!/usr/bin/env python3
"""
dev/test_pipeline_harness.py - Antigravity CLI Harness & Zero-Quota Pipeline Diagnostic.

Verifies the entire decoupled agent architecture, schema contracts, and procedural classifiers
locally without burning LLM quota or requiring video rendering.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, List, Tuple

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

import jsonschema

from src.agents.base_agent import AGY_BIN_PATH, CANONICAL_MODEL, ProgrammaticAgent
from src.agents.image_auditor import ImageAuditorAgent
from src.agents.seo_optimizer import SeoOptimizerAgent
from src.core.scenic_detector import SCENIC_THEMES, detect_scenic_loop, detect_subtitle_style
from src.core.scheduler import AutoPilotScheduler
from src.log import get_logger

logger = get_logger("dev_harness_test")


def check_antigravity_cli() -> Tuple[bool, str]:
    """Verifies that the agy binary is located and executable."""
    if AGY_BIN_PATH.is_file() and os.access(AGY_BIN_PATH, os.X_OK):
        return True, f"Found at {AGY_BIN_PATH} (Model: {CANONICAL_MODEL})"
    which_agy = shutil.which("agy")
    if which_agy:
        return True, f"Found via PATH at {which_agy} (Model: {CANONICAL_MODEL})"
    return False, f"CLI binary not found at {AGY_BIN_PATH}"


def check_schemas() -> List[Tuple[str, bool, str]]:
    """Validates all canonical JSON schemas in schemas/."""
    schema_dir = ROOT_DIR / "schemas"
    results = []
    for schema_path in sorted(schema_dir.glob("*.schema.json")):
        name = schema_path.name
        try:
            with open(schema_path, "r", encoding="utf-8") as f:
                schema_doc = json.load(f)
            jsonschema.Draft7Validator.check_schema(schema_doc)
            results.append((name, True, "Valid Draft-07 Schema"))
        except Exception as exc:
            results.append((name, False, f"Invalid: {exc}"))
    return results


def test_image_auditor() -> Tuple[bool, str]:
    """Tests ImageAuditorAgent anti-filler logic and contract conformance."""
    auditor = ImageAuditorAgent()
    candidates = [
        {"id": "cand_official", "name": "SCP Foundation Emblem", "source_type": "official_emblem"},
        {"id": "cand_filler", "name": "Stock Photo Person Smiling", "source_type": "generic_filler_photo"},
        {"id": "cand_unrelated", "name": "Baking Flour Brand Logo", "source_type": "brand_logo"},
    ]
    report = auditor.audit_candidates("SCP-2000: Deus Ex Machina", candidates, use_agent=False)
    v_map = {v["asset_id"]: v["verdict"] for v in report["verdicts"]}

    passed = (
        v_map.get("cand_official") == "APPROVED_REFERENCE"
        and v_map.get("cand_filler") == "DISCARDED_GENERIC_FILLER"
        and v_map.get("cand_unrelated") == "REJECTED_LOW_RELEVANCE"
        and report["approved_count"] == 1
        and report["discarded_count"] == 2
    )
    if passed:
        return True, "Anti-Filler Policy enforced (1 approved, 2 discarded)"
    return False, f"Unexpected verdicts: {v_map}"


def test_seo_optimizer() -> Tuple[bool, str]:
    """Tests SeoOptimizerAgent output contract and content generation."""
    optimizer = SeoOptimizerAgent()
    data = optimizer.optimize("5 Misterios del Océano Profundo", target_format="short", use_agent=False)
    passed = (
        len(data["viral_title_options"]) >= 3
        and bool(data["selected_title"])
        and len(data["tags"]) >= 3
        and len(data["hashtags"]) >= 2
        and bool(data["pinned_comment"])
        and len(data["thumbnail_concepts"]) >= 1
    )
    if passed:
        return True, f"Generated '{data['selected_title']}' ({len(data['tags'])} tags)"
    return False, "Malformed SEO metadata"


def test_scenic_loops() -> Tuple[bool, str]:
    """Tests the 7 scenic theme detectors."""
    test_cases = [
        ("Yellowstone bunker SCP-2000", "scp_facility"),
        ("T-Rex fósiles jurásicos", "jurassic_dino"),
        ("Bosque tétrico de noche", "eerie_forest"),
        ("Jardín de rosas y romance", "rose_garden"),
        ("Nebulosa cósmica y galaxias", "cosmic_nebula"),
        ("Programación e Inteligencia Artificial", "cyber_matrix"),
        ("Océano abisal y tiburones", "deep_ocean"),
    ]
    for text, expected in test_cases:
        detected = detect_scenic_loop(text)
        if detected != expected:
            return False, f"Mismatch for '{text}': got '{detected}', expected '{expected}'"
    return True, f"All {len(test_cases)} scenic environments classified accurately"


def test_autopilot_scheduler() -> Tuple[bool, str]:
    """Tests AutoPilot scheduler state machine."""
    sched = AutoPilotScheduler.instance()
    initial_state = sched.is_active()
    sched.start(interval_hours=1.0)
    started_state = sched.is_active()
    topic = sched.trigger_now()
    sched.stop()
    stopped_state = sched.is_active()

    passed = (not initial_state) and started_state and (not stopped_state) and bool(topic)
    if passed:
        return True, f"Scheduler state transition verified (Triggered: '{topic}')"
    return False, "Scheduler state transition failed"


def main() -> int:
    print("=================================================================")
    print("🧪 Antigravity CLI Harness & Zero-Quota Pipeline Diagnostic")
    print(f"Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=================================================================\n")

    overall_success = True

    # 1. Check agy binary
    cli_ok, cli_detail = check_antigravity_cli()
    print(f"[{'PASS' if cli_ok else 'FAIL'}] Antigravity CLI Binary: {cli_detail}")
    if not cli_ok:
        overall_success = False

    # 2. Check schemas
    print("\n--- JSON Schema Contracts ---")
    schemas = check_schemas()
    for name, ok, detail in schemas:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name:32s}: {detail}")
        if not ok:
            overall_success = False

    # 3. Image Auditor
    print("\n--- Agent 5: Image Auditor (Anti-Filler) ---")
    auditor_ok, auditor_detail = test_image_auditor()
    print(f"[{'PASS' if auditor_ok else 'FAIL'}] Image Auditor Vetting: {auditor_detail}")
    if not auditor_ok:
        overall_success = False

    # 4. SEO Optimizer
    print("\n--- Agent 6: SEO & Viral Optimizer ---")
    seo_ok, seo_detail = test_seo_optimizer()
    print(f"[{'PASS' if seo_ok else 'FAIL'}] SEO Metadata Generation: {seo_detail}")
    if not seo_ok:
        overall_success = False

    # 5. Scenic Loops
    print("\n--- Scenic Loop & Atmosphere Classifiers ---")
    scenic_ok, scenic_detail = test_scenic_loops()
    print(f"[{'PASS' if scenic_ok else 'FAIL'}] 7 Scenic Themes: {scenic_detail}")
    if not scenic_ok:
        overall_success = False

    # 6. AutoPilot Scheduler
    print("\n--- AutoPilot Production Scheduler ---")
    sched_ok, sched_detail = test_autopilot_scheduler()
    print(f"[{'PASS' if sched_ok else 'FAIL'}] AutoPilot Worker: {sched_detail}")
    if not sched_ok:
        overall_success = False

    print("\n=================================================================")
    if overall_success:
        print("✅ DIAGNÓSTICO EXITOSO: Todos los componentes y arneses están operativos.")
        print("=================================================================")
        return 0
    else:
        print("❌ FALLAS DETECTADAS: Uno o más componentes no pasaron la verificación.")
        print("=================================================================")
        return 1


if __name__ == "__main__":
    sys.exit(main())
