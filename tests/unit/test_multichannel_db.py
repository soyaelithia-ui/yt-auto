"""Unit tests for strict 3-channel SQLite database deduplication."""
import pytest
import sqlite3
from src.db import is_story_duplicate, enqueue_story, is_story_processed

def test_is_story_duplicate_per_channel(tmp_path):
    db_file = str(tmp_path / "test_dedup.db")
    
    # Enqueue story for channel moku
    added = enqueue_story(
        story_id="moku_story_001",
        title="La Sombra del Bosque",
        content="Contenido de la historia de terror en el bosque.",
        url="http://example.com/story1",
        channel="moku",
        db_path=db_file
    )
    assert added is True
    
    # Story should be detected as duplicate for channel moku
    assert is_story_duplicate("moku", "La Sombra del Bosque", db_path=db_file) is True
    assert is_story_duplicate("moku", "moku_story_001", db_path=db_file) is True
    
    # Same title on different channel (aelithia) should NOT collide if not enqueued for aelithia
    assert is_story_duplicate("aelithia", "La Sombra del Bosque", db_path=db_file) is False

def test_is_story_processed_check(tmp_path):
    db_file = str(tmp_path / "test_processed.db")
    enqueue_story(
        story_id="story_xyz",
        title="Misterio",
        content="Texto misterioso",
        url="http://example.com/xyz",
        channel="moku",
        db_path=db_file
    )
    assert is_story_processed("story_xyz", db_path=db_file) is True
    assert is_story_processed("non_existent_id", db_path=db_file) is False
