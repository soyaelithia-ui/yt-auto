import os
import sqlite3
from pathlib import Path
from unittest.mock import Mock

import pytest

from src.config import CHANNELS_CONFIG, SETTINGS
from src.core.domain import (
    CanonicalChannel,
    JobStatus,
    PublicationProof,
    ProviderValidationError,
    canonical_channel,
)
from src.core.providers import publication_proof_from_response
from src.core.quality import forbidden_aliases, is_spanish_neutral, text_similarity
from src.core.repository import QueueRepository, connect, migrate_database
from src.core.scheduler import PersistentScheduler


def legacy_database(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        """
        CREATE TABLE stories (
            story_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            channel TEXT,
            error_msg TEXT,
            youtube_url TEXT
        )
        """
    )
    conn.executemany(
        "INSERT INTO stories(story_id,title,content,url,status,channel) "
        "VALUES(?,?,?,?,?,?)",
        [
            ("one", "Uno", "Contenido", "https://one", "PENDING", "terror"),
            (
                "two",
                "Dos",
                "Contenido",
                "https://two",
                "COMPLETED",
                "soy_el_malo",
            ),
        ],
    )
    conn.commit()
    conn.close()


def test_canonical_channels_are_strict_and_config_is_canonical():
    assert canonical_channel("terror") is CanonicalChannel.MOKU
    assert canonical_channel("soy_el_malo") is CanonicalChannel.AELITHIA
    assert set(CHANNELS_CONFIG) == {"moku", "aelithia", "scifi"}
    with pytest.raises(ValueError):
        canonical_channel("")
    with pytest.raises(ValueError):
        canonical_channel("unknown")


def test_migration_is_transactional_and_idempotent(tmp_path):
    db = tmp_path / "queue.db"
    legacy_database(db)
    dry = migrate_database(db, dry_run=True)
    assert dry.changed_rows == 2
    with sqlite3.connect(db) as conn:
        assert conn.execute(
            "SELECT COUNT(*) FROM stories WHERE channel='terror'"
        ).fetchone()[0] == 1
        assert conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE name='schema_migrations'"
        ).fetchone()[0] == 0

    applied = migrate_database(db)
    assert applied.quick_check == "ok"
    assert applied.changed_rows == 2
    second = migrate_database(db)
    assert second.changed_rows == 0
    assert second.applied_versions == ()
    with connect(db, read_only=True) as conn:
        channels = {
            row[0] for row in conn.execute("SELECT DISTINCT channel FROM stories")
        }
        assert channels == {"moku", "aelithia"}


def test_leases_only_recover_after_expiry(tmp_path):
    db = tmp_path / "queue.db"
    repo = QueueRepository(db)
    repo.initialize()
    assert repo.enqueue("one", "Uno", "Contenido", "https://one", "moku")
    assert repo.enqueue("two", "Dos", "Contenido", "https://two", "moku")
    first = repo.claim("moku", "worker-a", lease_seconds=100, now=1_000)
    assert first and first["story_id"] == "one"
    assert repo.claim("moku", "worker-b", now=1_001) is None
    assert repo.recover_expired_leases(now=1_099) == 0
    assert repo.recover_expired_leases(now=1_100) == 1
    second = repo.claim("moku", "worker-b", now=1_101)
    assert second and second["story_id"] == "one"
    with connect(db, read_only=True) as conn:
        status = conn.execute(
            "SELECT status FROM stories WHERE story_id='one'"
        ).fetchone()[0]
    assert status == JobStatus.PROCESSING.value


def test_scheduler_alternates_without_catchup(tmp_path):
    db = tmp_path / "queue.db"
    scheduler = PersistentScheduler(str(db), interval_seconds=1_800)
    scheduler.initialize()
    first = scheduler.take_due_turn(now=10_000)
    assert first and first.channel is CanonicalChannel.MOKU
    assert first.next_due_at == 11_800
    assert scheduler.take_due_turn(now=10_001) is None
    second = scheduler.take_due_turn(now=50_000)
    assert second and second.channel is CanonicalChannel.AELITHIA
    assert second.next_due_at == 51_800


def test_publication_requires_every_confirmed_field(tmp_path):
    db = tmp_path / "queue.db"
    repo = QueueRepository(db)
    repo.initialize()
    repo.enqueue("one", "Uno", "Contenido", "https://one", "moku")
    story = repo.claim("moku", "worker")
    assert story
    proof = PublicationProof(
        video_id="abc123XYZ",
        channel=CanonicalChannel.MOKU,
        visibility="public",
        title="Título",
        description="Descripción",
        thumbnail_confirmed=True,
    )
    repo.mark_published("one", story["run_id"], proof, provider="API")
    with connect(db, read_only=True) as conn:
        row = conn.execute(
            "SELECT status,youtube_url FROM stories WHERE story_id='one'"
        ).fetchone()
    assert row["status"] == JobStatus.PUBLISHED.value
    assert row["youtube_url"] == "https://www.youtube.com/watch?v=abc123XYZ"

    bad = dict(
        video_id="abc123XYZ",
        channel="moku",
        visibility="public",
        title="Título",
        description="Descripción",
        thumbnail_confirmed=False,
        verified=True,
    )
    with pytest.raises(ProviderValidationError):
        publication_proof_from_response(
            bad,
            expected_channel="moku",
            expected_title="Título",
            expected_description="Descripción",
        )


def test_language_alias_and_similarity_gates():
    text = (
        "Esta es una historia en español, porque la protagonista no sabía qué hacer "
        "cuando su familia llegó a la casa y todos querían hablar con ella."
    )
    assert is_spanish_neutral(text)
    assert forbidden_aliases("Suscríbete a terror y soy_el_malo") == [
        "soy_el_malo",
        "terror",
    ]
    assert text_similarity("una casa muy oscura", "una casa bastante oscura") > 0.4
