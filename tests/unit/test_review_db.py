"""
Tests for database path validation and mock rejection in review/db.py.
"""
from __future__ import annotations

import glob
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from review.db import ReviewStateStore, get_db_connection, init_review_db, validate_db_path
from review.domain import ReviewJob, ReviewStatus


def test_review_validate_db_path_valid(tmp_path: Path):
    """review/db.py validate_db_path accepts valid paths and memory indicators."""
    db_file = tmp_path / "review.db"
    res = validate_db_path(db_file)
    assert isinstance(res, Path)
    assert res == db_file

    assert validate_db_path(":memory:") == ":memory:"


def test_review_db_rejects_mock_and_none():
    """ReviewStateStore, init_review_db, and get_db_connection raise TypeError on mock/None."""
    with pytest.raises(TypeError, match="cannot be None"):
        validate_db_path(None)

    with pytest.raises(TypeError, match="Mock objects are not valid"):
        validate_db_path(MagicMock())

    with pytest.raises(TypeError, match="Mock objects are not valid"):
        init_review_db(MagicMock())

    with pytest.raises(TypeError, match="Mock objects are not valid"):
        with get_db_connection(MagicMock()):
            pass

    with pytest.raises(TypeError, match="Mock objects are not valid"):
        ReviewStateStore(MagicMock())


def test_review_db_rejects_stringified_mock_with_zero_disk_side_effects():
    """ReviewStateStore, init_review_db, and get_db_connection raise ValueError on stringified mock."""
    mock_str = "<MagicMock name='mock.db_path' id='139907887533472'>"

    root_before = set(glob.glob("<MagicMock*") + glob.glob("*MagicMock*"))

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        init_review_db(mock_str)

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        with get_db_connection(mock_str):
            pass

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        ReviewStateStore(mock_str)

    root_after = set(glob.glob("<MagicMock*") + glob.glob("*MagicMock*"))
    assert root_before == root_after, "Operations on stringified mock created files on disk"


def test_review_state_store_valid_lifecycle(tmp_path: Path):
    """ReviewStateStore works correctly with valid filesystem paths."""
    db_path = tmp_path / "valid_review.db"
    store = ReviewStateStore(str(db_path))
    assert store.db_path == str(db_path)

    job = ReviewJob(
        job_id="job_001",
        channel="moku",
        version=1,
        title="Test Story",
        status=ReviewStatus.PENDING_REVIEW,
    )
    saved = store.create_job(job)
    assert saved.job_id == "job_001"
    fetched = store.get_job("job_001", 1)
    assert fetched is not None
    assert fetched.title == "Test Story"
