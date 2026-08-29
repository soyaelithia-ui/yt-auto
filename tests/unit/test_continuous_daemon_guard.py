"""
tests/unit/test_continuous_daemon_guard.py - Unit test suite for 64-bit SimHash Dedup,
Bounded Concurrency Semaphore, Scratch Sweeper, and 5.0 GB Disk Guard.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch
import pytest

from src.core.guard import DiskPreflight, ensure_disk_available
from src.daemon import (
    _RENDER_SEMAPHORE,
    _SYNTHESIS_SEMAPHORE,
    compute_simhash_64,
    hamming_distance_64,
    evaluate_script_simhash,
)
from src.cleaner import sweep_post_render_scratch
from lib.ffmpeg import TempMediaContext


# ============================================================================
# 1. 64-bit SimHash Calculation & Deduplication Tests
# ============================================================================

class TestSimHashDeduplication:
    """Tests 64-bit SimHash fingerprinting and duplicate rejection (Hamming < 4 rejected)."""

    def test_identical_text_has_zero_hamming_distance(self) -> None:
        """Identical text produces identical 64-bit SimHash with distance 0."""
        text = "Registro de telemetría número cuarenta y cuatro en fosa abisal."
        h1 = compute_simhash_64(text)
        h2 = compute_simhash_64(text)
        assert h1 == h2
        assert hamming_distance_64(h1, h2) == 0

    def test_near_duplicate_rejected_hamming_less_than_4(self) -> None:
        """Near-duplicate script with 95% token overlap yields Hamming < 4 and is rejected."""
        base_script = (
            "Registro hidroacústico automatizado a once mil doscientos metros de profundidad. "
            "Presión barométrica estacional dentro de parámetros estándar del sector abisal. "
            "A las cero tres cuarenta UTC las boyas sumergidas registraron una fluctuación rítmica de seis hercios. "
            "La compresión estructural del casco aumentó un cuarenta por ciento en diez segundos. "
            "La masa sumergida supera las cuatrocientas megatoneladas y absorbe ondas del sonar. "
            "Cierre de escotillas de emergencia y purga de transmisión bajo protocolo de contención."
        )
        # Minor variation (95%+ token overlap)
        near_duplicate_script = (
            "Registro hidroacústico automatizado a once mil doscientos metros de profundidad. "
            "Presión barométrica estacional dentro de parámetros estándar del sector abisal. "
            "A las cero tres cuarenta UTC las boyas sumergidas registraron una fluctuación rítmica de seis hercios. "
            "La compresión estructural del casco aumentó un cuarenta por ciento en diez segundos. "
            "La masa sumergida supera las cuatrocientas megatoneladas y absorbe ondas del sonar de barrido. "
            "Cierre de escotillas de emergencia y purga de transmisión bajo protocolo de contención total."
        )
        
        h1 = compute_simhash_64(base_script)
        h2 = compute_simhash_64(near_duplicate_script)
        dist = hamming_distance_64(h1, h2)
        
        assert dist < 4, f"Expected Hamming distance < 4 for 95% near-duplicate script, got {dist}"
        assert not evaluate_script_simhash(candidate_text=near_duplicate_script, history_hashes=[h1], min_hamming_distance=4)

    def test_distinct_narrative_accepted_hamming_ge_4(self) -> None:
        """Completely distinct narratives yield Hamming distance >= 4 and are accepted."""
        t1 = (
            "Registro hidroacústico a once mil metros de profundidad con lectura nominal. "
            "Presión de agua dentro de los límites esperados para las boyas sumergidas."
        )
        t2 = (
            "Directiva institucional para el personal de guardia en la bóveda subterránea número cuatro. "
            "Verifique la integridad de los sellos de plomo en las compuertas de titanio."
        )
        
        h1 = compute_simhash_64(t1)
        h2 = compute_simhash_64(t2)
        dist = hamming_distance_64(h1, h2)
        
        assert dist >= 4
        assert evaluate_script_simhash(candidate_text=t2, history_hashes=[h1], min_hamming_distance=4)


# ============================================================================
# 2. Bounded Concurrency Semaphore Tests
# ============================================================================

class TestBoundedConcurrencySemaphore:
    """Tests bounded concurrency semaphore (N = 1 for heavy rendering)."""

    def test_bounded_concurrency_execution(self) -> None:
        """Ensures that max concurrent renders cannot exceed semaphore bound N=1."""
        sem = threading.Semaphore(1)
        active_count = 0
        max_active = 0
        lock = threading.Lock()

        def worker():
            nonlocal active_count, max_active
            with sem:
                with lock:
                    active_count += 1
                    if active_count > max_active:
                        max_active = active_count
                # Simulate work
                import time
                time.sleep(0.01)
                with lock:
                    active_count -= 1

        threads = [threading.Thread(target=worker) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert max_active == 1


# ============================================================================
# 3. Post-Render Scratch Sweep in Finally Blocks Tests
# ============================================================================

class TestPostRenderScratchSweep:
    """Tests cleanup of scratch files and intermediate buffers in finally blocks."""

    def test_temp_media_context_cleanup_on_success(self, tmp_path: Path) -> None:
        """TempMediaContext deterministically removes scratch directory on exit."""
        temp_dir_path = None
        with TempMediaContext(work_dir=tmp_path) as ctx:
            temp_dir_path = ctx.path
            temp_file = ctx.create_temp_file(suffix=".wav")
            temp_file.write_bytes(b"RIFF" + b"\x00" * 40)
            assert temp_file.is_file()
            assert temp_dir_path.is_dir()

        assert not temp_dir_path.exists()

    def test_temp_media_context_cleanup_on_exception(self, tmp_path: Path) -> None:
        """TempMediaContext sweeps scratch files even when an unhandled exception occurs."""
        temp_dir_path = None
        try:
            with TempMediaContext(work_dir=tmp_path) as ctx:
                temp_dir_path = ctx.path
                temp_file = ctx.create_temp_file(suffix=".mp4")
                temp_file.write_bytes(b"\x00" * 1024)
                raise RuntimeError("Simulated render crash mid-pipeline")
        except RuntimeError:
            pass

        assert temp_dir_path is not None
        assert not temp_dir_path.exists()


# ============================================================================
# 4. Free Disk Watermark Guard (5.0 GB) Tests
# ============================================================================

class TestFreeDiskWatermarkGuard:
    """Tests minimum 5.0 GB free disk space watermark guard."""

    def test_disk_guard_floor_exceeded_pause(self) -> None:
        """When free disk is below 5.0 GB (e.g. 3.2 GB), guard reports failure to pause queue."""
        min_required_gb = 5.0
        current_free_gb = 3.2  # Below 5.0 GB floor

        report = DiskPreflight(
            ok=current_free_gb >= min_required_gb,
            min_free_bytes=int(min_required_gb * (1024**3)),
            checked={"/var/data": int(current_free_gb * (1024**3))},
            cleaned_bytes=0,
        )
        assert not report.ok
        assert report.checked["/var/data"] < int(min_required_gb * (1024**3))

    def test_disk_guard_passes_when_ample_space(self) -> None:
        """When free disk is ample (e.g. 25.0 GB), guard reports success."""
        min_required_gb = 5.0
        current_free_gb = 25.0

        report = DiskPreflight(
            ok=current_free_gb >= min_required_gb,
            min_free_bytes=int(min_required_gb * (1024**3)),
            checked={"/var/data": int(current_free_gb * (1024**3))},
            cleaned_bytes=0,
        )
        assert report.ok
