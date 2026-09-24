"""Unit tests for src/core/inventory.py AI-native published video inventory."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from src.core.inventory import (
    PublishedVideoRecord,
    backup_inventory_to_drive,
    compute_simhash,
    extract_hook_and_synopsis,
    extract_thematic_tags,
    get_inventory_ai_digest,
    get_published_inventory,
    normalize_text_nfc,
    record_published_inventory,
)
from src.core.repository import connect, migrate_database


@pytest.fixture()
def db_path(tmp_path: Path) -> str:
    target = str(tmp_path / "test_inventory_queue.db")
    migrate_database(target)
    return target


def test_normalize_and_simhash():
    raw = "\x1b[31mTexto de prueba para la historia\x1b[0m"
    norm = normalize_text_nfc(raw)
    assert norm == "Texto de prueba para la historia"

    h1 = compute_simhash("Una historia aterradora sobre un bosque oscuro.")
    h2 = compute_simhash("Una historia aterradora sobre un bosque oscuro.")
    h3 = compute_simhash("Un dilema completamente diferente sobre una boda.")
    assert h1 == h2
    assert h1.startswith("0x")
    assert len(h1) == 18
    assert h1 != h3


def test_extract_hook_and_synopsis():
    title = "¿Soy la mala por rechazar el chantaje?"
    text = "Mi hermano me exigió 5000 dólares. Le dije que no porque era para una fiesta. Toda la familia se enojó."
    hook, synopsis = extract_hook_and_synopsis(title, text)
    assert "Mi hermano me exigió" in hook
    assert "Le dije que no" in synopsis


def test_extract_thematic_tags():
    tags = extract_thematic_tags("Boda familiar y dilema con suegra", "Historia sobre herencia y dinero #navidad")
    assert "boda" in tags
    assert "suegra" in tags
    assert "herencia" in tags
    assert "navidad" in tags


def test_record_and_get_published_inventory(db_path: str):
    rec = record_published_inventory(
        db_path=db_path,
        run_id="run_001",
        story_id="story_001",
        video_id="vid_test_123",
        url="https://www.youtube.com/watch?v=vid_test_123",
        channel="moku",
        title="La criatura del sótano",
        description="Una entidad desconocida emerge en la noche.",
        full_script="Una entidad desconocida emerge en la noche. Nadie pudo escapar del horror.",
        video_sha256="abc123sha256",
        drive_video_id="drive_file_999",
        drive_backup_metadata={"video": "drive_file_999", "cover": "cover_888"},
        predictive_success_score=0.91,
        score_rationale="Gancho de alto impacto y atmósfera opresiva.",
        used_resources={"loop": "horror_dark_01.mp4", "voice": "es-ES-AlvaroNeural"},
        duration_sec=48.5,
    )

    assert rec.publication_id > 0
    assert rec.video_id == "vid_test_123"
    assert rec.predictive_success_score == 0.91
    assert rec.used_resources["voice"] == "es-ES-AlvaroNeural"

    # Query inventory
    all_recs = get_published_inventory(db_path, channel="moku")
    assert len(all_recs) == 1
    queried = all_recs[0]
    assert queried.video_id == "vid_test_123"
    assert queried.drive_video_id == "drive_file_999"
    assert queried.drive_backup_metadata["cover"] == "cover_888"
    assert queried.video_sha256 == "abc123sha256"

    # AI Digest format
    digest = get_inventory_ai_digest(db_path, channel="moku")
    assert digest["total_catalog_count"] == 1
    assert digest["recent_publications"][0]["video_id"] == "vid_test_123"
    assert digest["recent_publications"][0]["predictive_score"] == 0.91
    assert "hook" in digest["recent_publications"][0]
    assert "simhash" in digest["recent_publications"][0]


def test_backup_inventory_to_drive(db_path: str, monkeypatch):
    # Record one publication
    record_published_inventory(
        db_path=db_path,
        run_id="run_backup",
        story_id="story_backup",
        video_id="vid_backup",
        url="https://www.youtube.com/watch?v=vid_backup",
        channel="aelithia",
        title="¿Soy la mala por exigir mi dinero?",
        description="Descripción del dilema",
    )

    monkeypatch.setenv("DRIVE_MOCK", "1")
    monkeypatch.setenv("DRIVE_FOLDER_ID", "test_folder_123")

    result = backup_inventory_to_drive(db_path=db_path, folder_id="test_folder_123")
    assert result["ok"] is True
    assert "database_backup" in result
    assert "digest_backup" in result
    assert result["database_backup"]["file_id"].startswith("mock-drive-")
    assert result["digest_backup"]["file_id"].startswith("mock-drive-")


def test_update_publication_preserves_hook_synopsis_themes(db_path: str):
    """Verify updating a publication with empty/None hook, synopsis, and themes preserves existing rich values."""
    # 1. Create initial publication with curated hook, synopsis, and themes
    initial = record_published_inventory(
        db_path=db_path,
        run_id="run_init_100",
        story_id="story_init_100",
        video_id="vid_preserve_hook_themes",
        url="https://www.youtube.com/watch?v=vid_preserve_hook_themes",
        channel="moku",
        title="El misterio de la cabaña olvidada",
        description="Una expedición nocturna en la cabaña olvidada con secretos oscuros.",
        full_script="El grupo ingresó a la cabaña sin saber qué les esperaba en la oscuridad eterna.",
        hook_summary="Nunca abras esa puerta después de medianoche.",
        synopsis="Una expedición en una cabaña maldita desencadena una pesadilla sobrenatural.",
        themes=["paranormal", "cabaña", "misterio_profundo"],
    )
    assert initial.hook_summary == "Nunca abras esa puerta después de medianoche."
    assert initial.synopsis == "Una expedición en una cabaña maldita desencadena una pesadilla sobrenatural."
    assert initial.themes == ["paranormal", "cabaña", "misterio_profundo"]

    # 2. Update with empty string hook/synopsis and empty list themes
    updated_empty = record_published_inventory(
        db_path=db_path,
        run_id="yt-sync-vid_preserve_hook_themes",
        story_id="story-sync-vid_preserve_hook_themes",
        video_id="vid_preserve_hook_themes",
        url="https://www.youtube.com/watch?v=vid_preserve_hook_themes",
        channel="moku",
        title="El misterio de la cabaña olvidada (Updated Title)",
        description="Una expedición nocturna en la cabaña olvidada con secretos oscuros.",
        hook_summary="",
        synopsis="",
        themes=[],
        view_count=1200,
        like_count=95,
    )
    assert updated_empty.hook_summary == "Nunca abras esa puerta después de medianoche."
    assert updated_empty.synopsis == "Una expedición en una cabaña maldita desencadena una pesadilla sobrenatural."
    assert updated_empty.themes == ["paranormal", "cabaña", "misterio_profundo"]
    assert updated_empty.view_count == 1200

    # Verify directly from database row
    with connect(db_path) as conn:
        row = conn.execute(
            "SELECT hook_summary, synopsis, themes_json FROM publications WHERE video_id = ?",
            ("vid_preserve_hook_themes",),
        ).fetchone()
        assert row["hook_summary"] == "Nunca abras esa puerta después de medianoche."
        assert row["synopsis"] == "Una expedición en una cabaña maldita desencadena una pesadilla sobrenatural."
        assert json.loads(row["themes_json"]) == ["paranormal", "cabaña", "misterio_profundo"]

    # 3. Update with None hook/synopsis/themes (e.g. background link sync)
    updated_none = record_published_inventory(
        db_path=db_path,
        run_id="yt-collect-vid_preserve_hook_themes",
        story_id="story-collect-vid_preserve_hook_themes",
        video_id="vid_preserve_hook_themes",
        url="https://www.youtube.com/watch?v=vid_preserve_hook_themes",
        channel="moku",
        title="El misterio de la cabaña olvidada (Final Title)",
        description="Una expedición nocturna en la cabaña olvidada con secretos oscuros.",
        hook_summary=None,
        synopsis=None,
        themes=None,
        comment_count=42,
    )
    assert updated_none.hook_summary == "Nunca abras esa puerta después de medianoche."
    assert updated_none.synopsis == "Una expedición en una cabaña maldita desencadena una pesadilla sobrenatural."
    assert updated_none.themes == ["paranormal", "cabaña", "misterio_profundo"]
    assert updated_none.comment_count == 42

    with connect(db_path) as conn:
        row2 = conn.execute(
            "SELECT hook_summary, synopsis, themes_json FROM publications WHERE video_id = ?",
            ("vid_preserve_hook_themes",),
        ).fetchone()
        assert row2["hook_summary"] == "Nunca abras esa puerta después de medianoche."
        assert row2["synopsis"] == "Una expedición en una cabaña maldita desencadena una pesadilla sobrenatural."
        assert json.loads(row2["themes_json"]) == ["paranormal", "cabaña", "misterio_profundo"]

