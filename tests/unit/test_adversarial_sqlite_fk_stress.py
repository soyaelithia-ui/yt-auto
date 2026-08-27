"""Adversarial stress test for SQLite Foreign Key safety and Stage Checkpoints."""

import sqlite3
import tempfile
from pathlib import Path
import pytest

from src.core.repository import QueueRepository, connect
from src.core.checkpoints import (
    record_checkpoint,
    resume_plan,
    latest_valid_artifact,
    CHECKPOINT_KINDS,
)


@pytest.mark.unit
class TestSQLiteFKSafetyStress:
    """Stress test SQLite foreign key enforcement with synthetic and arbitrary run_ids."""

    def test_record_artifact_synthetic_run_id_auto_creates_parent_run(self, tmp_path):
        """Verify that record_artifact with non-existent run_id succeeds under PRAGMA foreign_keys = ON."""
        db_file = tmp_path / "test_fk_safety.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        # Explicitly verify FK is enabled
        with connect(str(db_file)) as conn:
            fk_enabled = conn.execute("PRAGMA foreign_keys").fetchone()[0]
            assert fk_enabled == 1, "Foreign keys must be enabled in SQLite connection"

        # Try recording artifacts under completely synthetic / un-registered run_ids
        synthetic_run_1 = "synthetic-run-uuid-1111"
        synthetic_run_2 = "synthetic-run-uuid-2222"
        synthetic_run_3 = "aelithia_synth_9999"

        # Record script artifact
        dummy_file = tmp_path / "script.txt"
        dummy_file.write_text("Texto de guión simulado para prueba de FK", encoding="utf-8")

        repo.record_artifact(
            run_id=synthetic_run_1,
            kind="script",
            local_path=str(dummy_file),
            size_bytes=dummy_file.stat().st_size,
            sha256="abc1234567890",
            verified=True,
            story_key="story_xyz:moku-scp-shorts",
        )

        # Verify parent row was automatically inserted in `runs`
        with connect(str(db_file)) as conn:
            run_row = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (synthetic_run_1,)
            ).fetchone()
            assert run_row is not None
            assert run_row["run_id"] == synthetic_run_1
            assert run_row["channel"] == "moku"

            artifact_row = conn.execute(
                "SELECT * FROM artifacts WHERE run_id = ? AND kind = 'script'",
                (synthetic_run_1,),
            ).fetchone()
            assert artifact_row is not None
            assert artifact_row["story_key"] == "story_xyz:moku-scp-shorts"

        # Record aelithia story key -> channel should resolve to 'aelithia'
        repo.record_artifact(
            run_id=synthetic_run_3,
            kind="video",
            local_path=str(dummy_file),
            size_bytes=dummy_file.stat().st_size,
            verified=True,
            story_key="story_abc:aelithia-aita-long",
        )

        with connect(str(db_file)) as conn:
            run_row_3 = conn.execute(
                "SELECT * FROM runs WHERE run_id = ?", (synthetic_run_3,)
            ).fetchone()
            assert run_row_3 is not None
            assert run_row_3["channel"] == "aelithia"

    def test_checkpoint_stages_lifecycle_with_synthetic_runs(self, tmp_path):
        """Test full checkpoint pipeline stages (script -> audio -> subtitles_ass -> video -> thumbnail)
        recorded under synthetic run_ids and recovered across runs."""
        db_file = tmp_path / "test_checkpoints_fk.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        story_id = "story_test_chk_001"
        lane_id = "moku-scp-shorts"
        key = f"{story_id}:{lane_id}"

        # Create dummy stage files
        stage_files = {}
        for kind in CHECKPOINT_KINDS:
            f = tmp_path / f"{story_id}_{kind}.dat"
            f.write_text(f"Dummy artifact content for stage {kind}", encoding="utf-8")
            stage_files[kind] = f

        # Run 1 creates script, audio, subtitles_ass but fails before video
        run_1 = "run_attempt_1"
        for kind in ("script", "audio", "subtitles_ass"):
            record_checkpoint(
                repository=repo,
                run_id=run_1,
                key=key,
                kind=kind,
                path=stage_files[kind],
            )

        # Run 2 checks resume plan
        plan = resume_plan(str(db_file), story_id, lane_id, now_run_id="run_attempt_2")
        assert plan.has_reusable is True
        assert len(plan.reusable) == 3
        assert "script" in plan.reusable
        assert "audio" in plan.reusable
        assert "subtitles_ass" in plan.reusable
        assert "video" not in plan.reusable
        assert plan.resume_from_index == 3  # Starts at 'video'

        # Run 2 records video and thumbnail
        run_2 = "run_attempt_2"
        for kind in ("video", "thumbnail"):
            record_checkpoint(
                repository=repo,
                run_id=run_2,
                key=key,
                kind=kind,
                path=stage_files[kind],
            )

        # Run 3 checks resume plan -> all 5 stages reusable
        plan3 = resume_plan(str(db_file), story_id, lane_id, now_run_id="run_attempt_3")
        assert len(plan3.reusable) == 5
        assert plan3.resume_from_index == 5

    def test_checkpoint_invalidation_when_file_modified_or_missing(self, tmp_path):
        """When an artifact file is modified (sha256 mismatch) or deleted, resume plan invalidates downstream."""
        db_file = tmp_path / "test_checkpoints_invalidation.db"
        repo = QueueRepository(str(db_file))
        repo.initialize()

        story_id = "story_inval_001"
        lane_id = "moku-horror-long"
        key = f"{story_id}:{lane_id}"

        # Create 3 stages
        script_file = tmp_path / "script.txt"
        script_file.write_text("Guión original", encoding="utf-8")
        audio_file = tmp_path / "audio.mp3"
        audio_file.write_text("Audio original bytes 12345", encoding="utf-8")
        subs_file = tmp_path / "subs.ass"
        subs_file.write_text("Subtítulos originales", encoding="utf-8")

        record_checkpoint(repo, "run_1", key, "script", script_file)
        record_checkpoint(repo, "run_1", key, "audio", audio_file)
        record_checkpoint(repo, "run_1", key, "subtitles_ass", subs_file)

        # Corrupt audio file (change content and size)
        audio_file.write_text("Audio corrupto modificado", encoding="utf-8")

        # Resume plan should only reuse script, since audio failed validation
        plan = resume_plan(str(db_file), story_id, lane_id, now_run_id="run_2")
        assert "script" in plan.reusable
        assert "audio" not in plan.reusable
        assert "subtitles_ass" not in plan.reusable  # Invalidation cascades to subsequent stages
        assert plan.resume_from_index == 1
