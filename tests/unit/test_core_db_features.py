"""Unit tests for Core DB features: 64-bit SimHash deduplication, idempotent leases, lanes CLI, and voice resolution."""
from __future__ import annotations

import argparse
import io
import json
import os
import sqlite3
import sys
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from src.core.domain import JobStatus, canonical_channel
from src.core.lanes import (
    load_lanes,
    load_voice_profiles,
    resolve_lane_for_run,
    resolve_voice_for_lane,
)
from src.core.repository import (
    QueueRepository,
    compute_simhash_64,
    connect,
    is_simhash_duplicate,
    migrate_database,
    simhash_hamming_distance,
    to_signed_64,
    to_unsigned_64,
)
from src.db import is_story_duplicate


@pytest.fixture
def repo(tmp_path):
    target = str(tmp_path / "test_queue.db")
    migrate_database(target)
    return QueueRepository(target)


class TestSimHashDeduplication:
    def test_simhash_deterministic(self):
        text = "Había una vez una criatura en la oscuridad del bosque SCP-173."
        h1 = compute_simhash_64(text)
        h2 = compute_simhash_64(text)
        assert h1 == h2
        assert isinstance(h1, int)
        assert h1 != 0

    def test_simhash_empty_and_none(self):
        assert compute_simhash_64("") == 0
        assert compute_simhash_64(None) == 0

    def test_hamming_distance_exact(self):
        # 0b101 vs 0b001 -> 1 bit difference
        assert simhash_hamming_distance(0b101, 0b001) == 1
        assert simhash_hamming_distance(0, 0) == 0
        assert simhash_hamming_distance(0xFF, 0x00) == 8

    def test_near_duplicate_detection(self):
        story1 = (
            "SCP-173 debe estar confinado en una habitación cerrada en todo momento. "
            "Cuando el personal deba entrar en el contenedor de contención de SCP-173, no menos de tres personas "
            "deben entrar y la puerta debe volver a cerrarse tras ellos. Dos personas deben mantener contacto visual continuo "
            "con SCP-173 hasta que todo el personal haya abandonado y vuelto a cerrar la celda. "
            "La criatura no puede moverse mientras esté en una línea de visión directa."
        )
        story1_mod = (
            "SCP-173 debe estar confinado en una habitación cerrada en todo momento. "
            "Cuando el personal deba entrar en el contenedor de contención de SCP-173, no menos de tres personas "
            "deben entrar y la puerta debe volver a cerrarse tras ellos. Dos personas deben mantener contacto visual continuo "
            "con SCP-173 hasta que todo el personal haya salido y vuelto a cerrar la celda. "
            "La criatura no puede moverse mientras esté en una línea de visión directa."
        )
        story2 = (
            "Hoy quiero contarles una historia de terror que me ocurrió en el bosque el año pasado. "
            "Había estado lloviendo toda la tarde y el camino de barro se volvió imposible de transitar con el coche. "
            "Decidí buscar refugio en una cabaña abandonada que encontré cerca del sendero principal."
        )

        h_base = compute_simhash_64(story1)
        h_mod = compute_simhash_64(story1_mod)
        h_diff = compute_simhash_64(story2)

        dist_near = simhash_hamming_distance(h_base, h_mod)
        dist_diff = simhash_hamming_distance(h_base, h_diff)

        assert dist_near <= 3
        assert is_simhash_duplicate(h_base, h_mod, max_distance=3)
        assert dist_diff > 3
        assert not is_simhash_duplicate(h_base, h_diff, max_distance=3)

    def test_db_is_story_duplicate_simhash_integration(self, tmp_path):
        db_path = str(tmp_path / "dedup.db")
        repo = QueueRepository(db_path)
        repo.initialize()

        story1 = (
            "SCP-173 debe estar confinado en una habitación cerrada en todo momento. "
            "Cuando el personal deba entrar en el contenedor de contención de SCP-173, no menos de tres personas "
            "deben entrar y la puerta debe volver a cerrarse tras ellos. Dos personas deben mantener contacto visual continuo "
            "con SCP-173 hasta que todo el personal haya abandonado y vuelto a cerrar la celda. "
            "La criatura no puede moverse mientras esté en una línea de visión directa."
        )
        story1_mod = (
            "SCP-173 debe estar confinado en una habitación cerrada en todo momento. "
            "Cuando el personal deba entrar en el contenedor de contención de SCP-173, no menos de tres personas "
            "deben entrar y la puerta debe volver a cerrarse tras ellos. Dos personas deben mantener contacto visual continuo "
            "con SCP-173 hasta que todo el personal haya salido y vuelto a cerrar la celda. "
            "La criatura no puede moverse mientras esté en una línea de visión directa."
        )
        story_diff = "Consejos de finanzas personales para ahorrar en la compra semanal de alimentos en el supermercado local."

        # Seed original story and record fingerprint
        story_id = "scp-173-seed"
        repo.enqueue(story_id, "SCP-173: La Escultura", story1, "https://x/scp173", "moku")
        repo.record_fingerprint(
            run_id="run-1",
            story_id=story_id,
            channel="moku",
            kind="script",
            payload=story1,
            normalized_text=story1,
        )

        # Exact title/content -> duplicate
        assert is_story_duplicate("moku", "SCP-173: La Escultura", story1, db_path=db_path)

        # Near duplicate content with different title/url -> near duplicate detected via SimHash
        assert is_story_duplicate("moku", "Otro Titulo Diferente", story1_mod, db_path=db_path)

        # Completely different story -> not duplicate
        assert not is_story_duplicate("moku", "Finanzas Sanas", story_diff, db_path=db_path)

    def test_signed_unsigned_sqlite_roundtrip(self):
        """Test signed vs unsigned 64-bit integer conversion for SQLite storage."""
        for val in [0, 1, 0x7FFFFFFFFFFFFFFF, 0x8000000000000000, 0xFFFFFFFFFFFFFFFF]:
            signed = to_signed_64(val)
            unsigned = to_unsigned_64(signed)
            assert unsigned == val
            assert -(1 << 63) <= signed < (1 << 63)


class TestIdempotentLeases:
    def test_lane_lease_on_conflict_idempotency(self, repo):
        repo.enqueue("s-lease-1", "Titulo Lease", "Contenido largo " * 20, "https://x/l1", "horror")
        job1 = repo.claim_for_lane("horror-scp-shorts", "horror", "worker-1", lease_seconds=600)
        assert job1 is not None

        # Expire or retry: inserting another lease for the same story does not violate PK
        with connect(repo.db_path) as conn:
            conn.execute(
                """
                INSERT INTO lane_leases(
                    job_id, lane_id, channel, owner, run_id, acquired_at,
                    heartbeat_at, expires_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_id) DO UPDATE SET
                    owner = excluded.owner,
                    heartbeat_at = excluded.heartbeat_at,
                    expires_at = excluded.expires_at
                """,
                ("s-lease-1", "horror-scp-shorts", "horror", "worker-renewed", "run-renewed", 1000, 1000, 2000),
            )
            conn.commit()

            row = conn.execute("SELECT owner, expires_at FROM lane_leases WHERE job_id = 's-lease-1'").fetchone()
            assert row["owner"] == "worker-renewed"
            assert row["expires_at"] == 2000

    def test_queue_score_priority_ordering(self, repo, monkeypatch):
        """Verify claim() prioritizes higher score stories by default."""
        repo.enqueue("low_score", "Low Score Story", "Low Content", "https://x/low", "horror", score=100)
        repo.enqueue("high_score", "High Score Story", "High Content", "https://x/high", "horror", score=950)
        repo.enqueue("mid_score", "Mid Score Story", "Mid Content", "https://x/mid", "horror", score=500)

        # Default: orders by score DESC
        job = repo.claim("horror", "worker-score-test")
        assert job is not None
        assert job["story_id"] == "high_score"

        # FIFO mode when QUEUE_RANK_BY_SCORE="0"
        monkeypatch.setenv("QUEUE_RANK_BY_SCORE", "0")
        # Enqueue another low and high
        repo.enqueue("fifo_1", "FIFO 1", "Content 1", "https://x/f1", "drama", score=10)
        repo.enqueue("fifo_2", "FIFO 2", "Content 2", "https://x/f2", "drama", score=999)
        job_fifo = repo.claim("drama", "worker-fifo-test")
        assert job_fifo is not None
        assert job_fifo["story_id"] == "fifo_1"

    def test_dual_tier_lease_fencing_and_recovery(self, repo):
        """Test fencing across channel leases and lane leases."""
        repo.enqueue("story-ch", "Story Channel", "Content", "https://x/ch1", "horror")
        repo.enqueue("story-lane", "Story Lane", "Content", "https://x/lane1", "horror", lane_id="horror-scp-shorts")

        claimed_ch = repo.claim("horror", "worker-ch", lease_seconds=10, now=100)
        assert claimed_ch is not None
        run_ch = claimed_ch["run_id"]

        claimed_lane = repo.claim_for_lane("horror-scp-shorts", "horror", "worker-lane", lease_seconds=10, now=100)
        # Note: channel lease active blocks lane lease claim for same channel in claim_for_lane
        # Release or let channel lease expire
        assert repo.recover_expired_leases(now=120) == 1

        # Now lane claim succeeds
        claimed_lane2 = repo.claim_for_lane("horror-scp-shorts", "horror", "worker-lane", lease_seconds=10, now=125)
        assert claimed_lane2 is not None
        run_lane = claimed_lane2["run_id"]

        # Heartbeat lane lease
        assert repo.heartbeat_lane_lease(run_lane, "worker-lane", lease_seconds=50, now=130) is True
        # Imposter heartbeat rejected
        assert repo.heartbeat_lane_lease(run_lane, "worker-imposter", lease_seconds=50, now=130) is False

        # Recover lane leases
        assert repo.recover_expired_lane_leases(now=200) == 1


class TestLanesCLIAndVoiceProfiles:
    def test_voice_profiles_resolution(self):
        profiles = load_voice_profiles()
        assert "editorial_profiles" in profiles
        assert "scp_documentary_es" in profiles["editorial_profiles"]

        voice_scp = resolve_voice_for_lane("horror-scp-shorts")
        voice_horror = resolve_voice_for_lane("horror-horror-long")
        voice_aita = resolve_voice_for_lane("drama-aita-long")

        assert voice_scp in ("es-ES-AlvaroNeural", "es-ES-ElviraNeural", "es-MX-JorgeNeural")
        assert voice_horror in ("es-ES-AlvaroNeural", "es-MX-JorgeNeural")
        assert voice_aita == "es-MX-DaliaNeural"

    def test_lanes_cli_handler(self, tmp_path):
        from src.cli.handlers.lanes import handle_lanes

        db_path = str(tmp_path / "lanes_cli.db")
        migrate_database(db_path)

        # Test Text Table output
        args = argparse.Namespace(db_path=db_path, json=False, channel="all")
        buf = io.StringIO()
        with redirect_stdout(buf):
            ret = handle_lanes(args)
        assert ret == 0
        output = buf.getvalue()
        assert "PRODUCTION LANES" in output
        assert "horror-scp-shorts" in output
        assert "horror-horror-long" in output
        assert "drama-aita-long" in output

        # Test JSON output
        args_json = argparse.Namespace(db_path=db_path, json=True, channel="all")
        buf_json = io.StringIO()
        with redirect_stdout(buf_json):
            ret_json = handle_lanes(args_json)
        assert ret_json == 0
        data = json.loads(buf_json.getvalue())
        from src.core.lanes import load_lanes
        assert data["count"] == len(load_lanes())
        lane_ids = [item["lane_id"] for item in data["lanes"]]
        assert "horror-scp-shorts" in lane_ids
        assert "horror-horror-long" in lane_ids
        assert "drama-aita-long" in lane_ids

