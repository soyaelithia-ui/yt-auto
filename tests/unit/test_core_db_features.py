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


class TestIdempotentLeases:
    def test_lane_lease_on_conflict_idempotency(self, repo):
        repo.enqueue("s-lease-1", "Titulo Lease", "Contenido largo " * 20, "https://x/l1", "moku")
        job1 = repo.claim_for_lane("moku-scp-shorts", "moku", "worker-1", lease_seconds=600)
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
                ("s-lease-1", "moku-scp-shorts", "moku", "worker-renewed", "run-renewed", 1000, 1000, 2000),
            )
            conn.commit()

            row = conn.execute("SELECT owner, expires_at FROM lane_leases WHERE job_id = 's-lease-1'").fetchone()
            assert row["owner"] == "worker-renewed"
            assert row["expires_at"] == 2000


class TestLanesCLIAndVoiceProfiles:
    def test_voice_profiles_resolution(self):
        profiles = load_voice_profiles()
        assert "editorial_profiles" in profiles
        assert "scp_documentary_es" in profiles["editorial_profiles"]

        voice_scp = resolve_voice_for_lane("moku-scp-shorts")
        voice_horror = resolve_voice_for_lane("moku-horror-long")
        voice_aita = resolve_voice_for_lane("aelithia-aita-long")

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
        assert "moku-scp-shorts" in output
        assert "moku-horror-long" in output
        assert "aelithia-aita-long" in output

        # Test JSON output
        args_json = argparse.Namespace(db_path=db_path, json=True, channel="all")
        buf_json = io.StringIO()
        with redirect_stdout(buf_json):
            ret_json = handle_lanes(args_json)
        assert ret_json == 0
        data = json.loads(buf_json.getvalue())
        assert data["count"] == 3
        lane_ids = [item["lane_id"] for item in data["lanes"]]
        assert "moku-scp-shorts" in lane_ids
        assert "moku-horror-long" in lane_ids
        assert "aelithia-aita-long" in lane_ids
