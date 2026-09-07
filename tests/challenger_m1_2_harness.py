#!/usr/bin/env python3
"""
tests/challenger_m1_2_harness.py - Empirical Challenger M1.2 Verification Harness.

Adversarial Stress Test Suite for yt-auto Milestone 1:
1. Idempotent Sync: 3 consecutive sync_catalog_from_assets() calls on DB clone with preserved usage.
2. Real DB Audit: shorts_queue.db integrity, count >= 50, purged monochromes, physical size >= 25KB.
3. Corrupt Asset Resilience: 0-byte and 100-byte corrupted MP4 files tested for discard/ignore behavior.
4. Monochrome Fallback Elimination: resolve_loop_video() with garbage categories across 180 combinations.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

# Ensure project root is in path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import DEFAULT_DB_PATH
from src.core.catalog import (
    LoopCatalogRepository,
    compute_file_sha256,
    resolve_loop_file_path,
    SYNTHETIC_MONOCHROME_LOOP_IDS,
)
from src.media.loop_engine import LoopVideoEngine


def test_1_idempotent_sync() -> Dict[str, Any]:
    """Test 1: Idempotent Sync over 3 consecutive executions."""
    print("\n" + "=" * 70)
    print("TEST 1: IDEMPOTENT SYNC (3 Consecutive Executions)")
    print("=" * 70)

    results: Dict[str, Any] = {
        "name": "Idempotent Sync",
        "passed": False,
        "runs": [],
        "metrics": {},
        "error": None,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        clone_db = Path(tmpdir) / "test_shorts_queue.db"
        real_db = Path(DEFAULT_DB_PATH)
        if not real_db.is_file():
            results["error"] = f"Real database not found at {real_db}"
            print(f"FAILED: {results['error']}")
            return results

        shutil.copyfile(real_db, clone_db)
        repo = LoopCatalogRepository(db_path=str(clone_db), auto_seed=False)

        # 1. Simulate usage counts and timestamps on 10 loops
        loops = repo.list_loops(limit=10)
        expected_usage: Dict[str, int] = {}
        for i, loop in enumerate(loops):
            usage = i + 3
            for _ in range(usage):
                repo.record_loop_usage(loop.loop_id)
            expected_usage[loop.loop_id] = usage

        # 2. Capture baseline snapshot
        conn = sqlite3.connect(str(clone_db))
        conn.row_factory = sqlite3.Row
        baseline_rows = {
            r["loop_id"]: {
                "usage_count": r["usage_count"],
                "last_used_at": r["last_used_at"],
                "sha256": r["sha256"],
                "file_path": r["file_path"],
                "file_size_bytes": r["file_size_bytes"],
            }
            for r in conn.execute(
                "SELECT loop_id, usage_count, last_used_at, sha256, file_path, file_size_bytes FROM video_loops"
            ).fetchall()
        }
        baseline_count = len(baseline_rows)
        print(f"Baseline rows: {baseline_count}")
        print(f"Simulated usage on {len(expected_usage)} loops.")

        # 3. Execute 3 consecutive syncs
        all_passed = True
        run_durations = []
        for run_idx in range(1, 4):
            t0 = time.perf_counter()
            synced_val = repo.sync_catalog_from_assets()
            dur = time.perf_counter() - t0
            run_durations.append(dur)

            current_rows = {
                r["loop_id"]: {
                    "usage_count": r["usage_count"],
                    "last_used_at": r["last_used_at"],
                    "sha256": r["sha256"],
                    "file_path": r["file_path"],
                    "file_size_bytes": r["file_size_bytes"],
                }
                for r in conn.execute(
                    "SELECT loop_id, usage_count, last_used_at, sha256, file_path, file_size_bytes FROM video_loops"
                ).fetchall()
            }
            current_count = len(current_rows)

            count_ok = current_count == baseline_count
            usage_ok = True
            sha_ok = True

            for lid, bdata in baseline_rows.items():
                cdata = current_rows.get(lid)
                if not cdata:
                    count_ok = False
                    break
                if cdata["usage_count"] != bdata["usage_count"]:
                    usage_ok = False
                if cdata["last_used_at"] != bdata["last_used_at"]:
                    usage_ok = False
                if cdata["sha256"] != bdata["sha256"]:
                    sha_ok = False

            run_info = {
                "run": run_idx,
                "synced_returned": synced_val,
                "duration_sec": round(dur, 3),
                "row_count": current_count,
                "count_preserved": count_ok,
                "usage_preserved": usage_ok,
                "sha256_preserved": sha_ok,
            }
            results["runs"].append(run_info)
            print(f"Run {run_idx}: dur={dur:.2f}s, count={current_count}/{baseline_count}, usage_ok={usage_ok}, sha_ok={sha_ok}")

            if not (count_ok and usage_ok and sha_ok):
                all_passed = False

        results["passed"] = all_passed
        results["metrics"] = {
            "baseline_count": baseline_count,
            "simulated_usage_loops": len(expected_usage),
            "run_durations_sec": run_durations,
            "avg_duration_sec": round(sum(run_durations) / len(run_durations), 3),
        }

    return results


def test_2_real_db_audit() -> Dict[str, Any]:
    """Test 2: Real Database Audit on shorts_queue.db."""
    print("\n" + "=" * 70)
    print("TEST 2: REAL DB AUDIT (/home/moku/projects/yt-auto/data/shorts_queue.db)")
    print("=" * 70)

    results: Dict[str, Any] = {
        "name": "Real DB Audit",
        "passed": False,
        "metrics": {},
        "failures": [],
    }

    real_db = Path(DEFAULT_DB_PATH)
    if not real_db.is_file():
        results["failures"].append(f"DB not found: {real_db}")
        print(f"FAILED: DB not found: {real_db}")
        return results

    conn = sqlite3.connect(str(real_db))
    conn.row_factory = sqlite3.Row

    # 1. Row count >= 50
    total_count = conn.execute("SELECT COUNT(*) FROM video_loops").fetchone()[0]
    h_count = conn.execute("SELECT COUNT(*) FROM video_loops WHERE orientation = 'horizontal'").fetchone()[0]
    v_count = conn.execute("SELECT COUNT(*) FROM video_loops WHERE orientation = 'vertical'").fetchone()[0]
    print(f"Total loops: {total_count} (horizontal={h_count}, vertical={v_count})")

    if total_count < 50:
        results["failures"].append(f"Total loop count {total_count} < 50 (expected >= 50, target 88)")

    # 2. Monochromes purged (count == 0)
    mono_rows = conn.execute("""
        SELECT loop_id, category, technology, sha256 FROM video_loops
        WHERE loop_id IN ('loop_maritime_lighthouse_h_544374', 'loop_arctic_desolation_v_800210')
           OR category IN ('maritime_lighthouse', 'arctic_desolation')
           OR (technology = 'ffmpeg_lavfi' AND sha256 = 'procedural')
    """).fetchall()
    mono_count = len(mono_rows)
    print(f"Monochrome loops found: {mono_count}")
    if mono_count > 0:
        results["failures"].append(f"Found {mono_count} unpurged monochrome loops in DB: {[r['loop_id'] for r in mono_rows]}")

    # 3. Every file path exists on disk and has size >= 25,000 bytes
    rows = conn.execute("SELECT loop_id, file_path, file_size_bytes, sha256 FROM video_loops").fetchall()
    missing_files = []
    too_small_files = []
    sha_mismatches = []
    sizes: List[int] = []

    for r in rows:
        lid = r["loop_id"]
        raw_path = r["file_path"]
        p = resolve_loop_file_path(raw_path)
        if not p.is_file():
            missing_files.append((lid, raw_path))
            continue

        st_sz = p.stat().st_size
        sizes.append(st_sz)
        if st_sz < 25_000:
            too_small_files.append((lid, st_sz, raw_path))

        actual_sha = compute_file_sha256(p)
        if actual_sha != r["sha256"]:
            sha_mismatches.append((lid, r["sha256"], actual_sha))

    print(f"Physical file verification: checked {len(rows)} files.")
    print(f"  Missing: {len(missing_files)}")
    print(f"  Too small (<25KB): {len(too_small_files)}")
    print(f"  SHA mismatches: {len(sha_mismatches)}")
    if sizes:
        print(f"  Min file size: {min(sizes):,} bytes ({min(sizes)/1024:.1f} KB)")
        print(f"  Max file size: {max(sizes):,} bytes ({max(sizes)/(1024*1024):.1f} MB)")
        print(f"  Avg file size: {sum(sizes)//len(sizes):,} bytes")

    if missing_files:
        results["failures"].append(f"{len(missing_files)} indexed files missing on disk: {missing_files[:3]}")
    if too_small_files:
        results["failures"].append(f"{len(too_small_files)} indexed files < 25KB: {too_small_files[:3]}")
    if sha_mismatches:
        results["failures"].append(f"{len(sha_mismatches)} SHA mismatches: {sha_mismatches[:3]}")

    results["passed"] = len(results["failures"]) == 0
    results["metrics"] = {
        "total_loops": total_count,
        "horizontal_loops": h_count,
        "vertical_loops": v_count,
        "monochrome_count": mono_count,
        "missing_files": len(missing_files),
        "too_small_files": len(too_small_files),
        "sha_mismatches": len(sha_mismatches),
        "min_size_bytes": min(sizes) if sizes else 0,
        "max_size_bytes": max(sizes) if sizes else 0,
    }

    return results


def test_3_corrupt_asset_resilience() -> Dict[str, Any]:
    """Test 3: Corrupt Asset Resilience (0-byte and 100-byte corrupted MP4s)."""
    print("\n" + "=" * 70)
    print("TEST 3: CORRUPT ASSET RESILIENCE (0-byte & 100-byte Corrupted MP4s)")
    print("=" * 70)

    results: Dict[str, Any] = {
        "name": "Corrupt Asset Resilience",
        "passed": False,
        "crashed": False,
        "zero_byte_discarded": False,
        "hundred_byte_discarded": False,
        "metrics": {},
        "findings": [],
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp_path = Path(tmpdir)
        test_assets = tmp_path / "assets"
        test_db = tmp_path / "corrupt_test.db"

        # Create assets layout:
        # 1. 0-byte file in horizontal/
        # 2. 100-byte corrupted non-MP4 bytes in horizontal/
        # 3. 0-byte file in vertical/
        # 4. 100-byte corrupted non-MP4 bytes in vertical/
        # 5. 100-byte corrupted in horizontal/horror/atomic/
        horiz = test_assets / "horizontal"
        vert = test_assets / "vertical"
        atomic_dir = test_assets / "horizontal" / "horror" / "atomic"

        horiz.mkdir(parents=True)
        vert.mkdir(parents=True)
        atomic_dir.mkdir(parents=True)

        f_zero_h = horiz / "test_zero_byte.mp4"
        f_zero_h.write_bytes(b"")

        f_100_h = horiz / "test_corrupt_100b.mp4"
        f_100_h.write_bytes(b"CORRUPT_HEADER_GARBAGE_DATA" + b"\x00\xff" * 36)

        f_zero_v = vert / "test_zero_v.mp4"
        f_zero_v.write_bytes(b"")

        f_100_v = vert / "test_corrupt_100b_v.mp4"
        f_100_v.write_bytes(b"CORRUPT_HEADER_GARBAGE_DATA" + b"\x00\xff" * 36)

        f_100_atomic = atomic_dir / "test_corrupt_atomic.mp4"
        f_100_atomic.write_bytes(b"CORRUPT_HEADER_GARBAGE_DATA" + b"\x00\xff" * 36)

        repo = LoopCatalogRepository(db_path=str(test_db), auto_seed=False)

        # Execute sync on corrupt assets
        crashed = False
        exception_str = None
        synced_count = 0
        try:
            synced_count = repo.sync_catalog_from_assets(assets_dir=test_assets)
        except Exception as e:
            crashed = True
            exception_str = str(e)

        results["crashed"] = crashed
        print(f"Crashed during sync: {crashed} (exception: {exception_str})")
        print(f"Sync returned count: {synced_count}")

        # Check DB contents
        conn = sqlite3.connect(str(test_db))
        conn.row_factory = sqlite3.Row
        indexed_rows = conn.execute("SELECT loop_id, file_path, file_size_bytes, technology, width, height FROM video_loops").fetchall()
        print(f"Rows found in video_loops: {len(indexed_rows)}")

        for r in indexed_rows:
            print(f"  -> {r['loop_id']}: size={r['file_size_bytes']}b, tech={r['technology']}, res={r['width']}x{r['height']}")

        # 0-byte check:
        zero_in_db = [r for r in indexed_rows if r["file_size_bytes"] == 0 or "zero" in r["loop_id"]]
        results["zero_byte_discarded"] = len(zero_in_db) == 0

        # 100-byte check:
        hundred_in_db = [r for r in indexed_rows if r["file_size_bytes"] < 25_000]
        results["hundred_byte_discarded"] = len(hundred_in_db) == 0

        if results["zero_byte_discarded"]:
            print("PASS: 0-byte MP4 files were discarded/ignored.")
        else:
            msg = f"FAIL: 0-byte MP4 files were indexed into DB: {[r['loop_id'] for r in zero_in_db]}"
            results["findings"].append(msg)
            print(msg)

        if results["hundred_byte_discarded"]:
            print("PASS: 100-byte corrupted MP4 files were discarded/ignored.")
        else:
            msg = (
                f"VULNERABILITY CONFIRMED: 100-byte corrupted MP4 files were NOT discarded/ignored. "
                f"sync_catalog_from_assets() indexed {len(hundred_in_db)} corrupted file(s) "
                f"(size={hundred_in_db[0]['file_size_bytes']}b) into video_loops table."
            )
            results["findings"].append(msg)
            print(msg)

        # Requirement 3: "Verify sync_catalog_from_assets() discards or ignores them without crashing."
        # If 100-byte corrupt files are indexed instead of discarded, this is a defect.
        results["passed"] = (not crashed) and results["zero_byte_discarded"] and results["hundred_byte_discarded"]
        results["metrics"] = {
            "crashed": crashed,
            "total_indexed": len(indexed_rows),
            "zero_byte_in_db": len(zero_in_db),
            "corrupted_small_in_db": len(hundred_in_db),
        }

    return results


def test_4_monochrome_fallback_elimination() -> Dict[str, Any]:
    """Test 4: Monochrome Fallback Elimination across 180 evaluation combinations."""
    print("\n" + "=" * 70)
    print("TEST 4: MONOCHROME FALLBACK ELIMINATION")
    print("=" * 70)

    results: Dict[str, Any] = {
        "name": "Monochrome Fallback Elimination",
        "passed": False,
        "total_evaluated": 0,
        "monochrome_hits": [],
        "channel_isolation_failures": [],
        "nonexistent_files": [],
        "metrics": {},
    }

    engine = LoopVideoEngine()

    test_categories = [
        "garbage_cat_12345",
        "nonexistent_theme_xyz",
        "maritime_lighthouse",     # Adversarial: directly requesting obsolete monochrome
        "arctic_desolation",       # Adversarial: directly requesting obsolete monochrome
        "procedural_fallback",
        "unknown_alien_category",
        "",                         # Empty string
        None,                       # None
        "!@#$%^&*()",              # Special characters
        "   ",                      # Whitespace only
    ]

    orientations = ["vertical", "horizontal"]
    channels = ["moku", "aelithia", None]
    seeds = [42, 999, None]

    total_evals = 0
    mono_hits = []
    iso_failures = []
    missing_files = []

    for cat in test_categories:
        for orient in orientations:
            for ch in channels:
                for seed_val in seeds:
                    total_evals += 1
                    try:
                        resolved_path = engine.resolve_loop_video(
                            category=cat,
                            orientation=orient,
                            channel=ch,
                            seed=seed_val,
                        )
                    except Exception as exc:
                        resolved_path = None
                        print(f"Exception for cat={cat!r}, orient={orient}, ch={ch}: {exc}")
                        missing_files.append((cat, orient, ch, str(exc)))
                        continue

                    p = Path(resolved_path)
                    p_name_lower = p.name.lower()
                    p_str_lower = str(p).lower()

                    # 1. Monochrome check
                    if "maritime_lighthouse" in p_name_lower or "arctic_desolation" in p_name_lower or "maritime_lighthouse" in p_str_lower or "arctic_desolation" in p_str_lower:
                        mono_hits.append({
                            "category": cat,
                            "orientation": orient,
                            "channel": ch,
                            "seed": seed_val,
                            "returned_file": p.name,
                        })

                    # 2. File exists and size >= 25KB
                    if not p.is_file() or p.stat().st_size < 25_000:
                        missing_files.append((cat, orient, ch, str(p)))

                    # 3. Channel isolation check
                    if ch == "moku":
                        # Should not be an aelithia-specific clip
                        if "aelithia_" in p_name_lower:
                            iso_failures.append({
                                "channel": ch,
                                "returned_file": p.name,
                                "category": cat,
                            })
                    elif ch == "aelithia":
                        # Should not be a moku-specific clip
                        if "moku_" in p_name_lower:
                            iso_failures.append({
                                "channel": ch,
                                "returned_file": p.name,
                                "category": cat,
                            })

    print(f"Evaluated combinations: {total_evals}")
    print(f"Monochrome hits: {len(mono_hits)}")
    print(f"Channel isolation violations: {len(iso_failures)}")
    print(f"Missing / unplayable files: {len(missing_files)}")

    results["total_evaluated"] = total_evals
    results["monochrome_hits"] = mono_hits
    results["channel_isolation_failures"] = iso_failures
    results["nonexistent_files"] = missing_files
    results["passed"] = (len(mono_hits) == 0) and (len(missing_files) == 0) and (len(iso_failures) == 0)
    results["metrics"] = {
        "total_evaluations": total_evals,
        "monochrome_hits_count": len(mono_hits),
        "channel_violations_count": len(iso_failures),
        "missing_files_count": len(missing_files),
    }

    return results


def main() -> int:
    print("=" * 70)
    print("CHALLENGER M1.2: EMPIRICAL STRESS & INTEGRITY HARNESS")
    print("=" * 70)
    start_time = time.perf_counter()

    t1 = test_1_idempotent_sync()
    t2 = test_2_real_db_audit()
    t3 = test_3_corrupt_asset_resilience()
    t4 = test_4_monochrome_fallback_elimination()

    total_duration = time.perf_counter() - start_time

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_duration_sec": round(total_duration, 2),
        "tests": {
            "test_1_idempotent_sync": t1,
            "test_2_real_db_audit": t2,
            "test_3_corrupt_asset_resilience": t3,
            "test_4_monochrome_fallback_elimination": t4,
        },
    }

    all_passed = t1["passed"] and t2["passed"] and t3["passed"] and t4["passed"]
    verdict = "APPROVE" if all_passed else "REQUEST_CHANGES"
    summary["verdict"] = verdict

    print("\n" + "=" * 70)
    print("SUMMARY OF EMPIRICAL VERIFICATION")
    print("=" * 70)
    print(f"Test 1 (Idempotent Sync):                   {'PASS' if t1['passed'] else 'FAIL'}")
    print(f"Test 2 (Real DB Audit):                     {'PASS' if t2['passed'] else 'FAIL'}")
    print(f"Test 3 (Corrupt Asset Resilience):          {'PASS' if t3['passed'] else 'FAIL'}")
    print(f"Test 4 (Monochrome Fallback Elimination):   {'PASS' if t4['passed'] else 'FAIL'}")
    print("-" * 70)
    print(f"OVERALL VERDICT: {verdict}")
    print("=" * 70)

    out_file = REPO_ROOT / "tests" / "challenger_m1_2_results.json"
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    print(f"Detailed results written to {out_file}")

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
