"""
Tests for database path validation and mock rejection in src/core/repository.py.
"""
from __future__ import annotations

import glob
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock

import pytest

from src.core.repository import connect, validate_db_path, wal_checkpoint_passive


def test_validate_db_path_valid_types(tmp_path: Path):
    """validate_db_path accepts valid str, Path, os.PathLike, and memory indicators."""
    p_str = str(tmp_path / "valid.db")
    res_str = validate_db_path(p_str)
    assert isinstance(res_str, Path)
    assert str(res_str) == p_str

    p_path = tmp_path / "valid_path.db"
    res_path = validate_db_path(p_path)
    assert isinstance(res_path, Path)
    assert res_path == p_path

    assert validate_db_path(":memory:") == ":memory:"
    assert validate_db_path("file::memory:?cache=shared") == ":memory:"


def test_validate_db_path_rejects_mock_and_none():
    """validate_db_path raises TypeError for None, Mock, MagicMock, and invalid types."""
    with pytest.raises(TypeError, match="cannot be None"):
        validate_db_path(None)

    with pytest.raises(TypeError, match="Mock objects are not valid"):
        validate_db_path(MagicMock())

    with pytest.raises(TypeError, match="Mock objects are not valid"):
        validate_db_path(Mock())

    with pytest.raises(TypeError, match="db_path must be str, Path, or os.PathLike"):
        validate_db_path(12345)

    with pytest.raises(TypeError, match="db_path must be str, Path, or os.PathLike"):
        validate_db_path(["/path/to/db"])

    with pytest.raises(TypeError, match="db_path must be str, Path, or os.PathLike"):
        validate_db_path({"path": "/path/to/db"})


def test_validate_db_path_rejects_empty_and_stringified_mock():
    """validate_db_path raises ValueError for empty strings and stringified mocks."""
    with pytest.raises(ValueError, match="cannot be empty string"):
        validate_db_path("")

    with pytest.raises(ValueError, match="cannot be empty string"):
        validate_db_path("   ")

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        validate_db_path("<MagicMock name='mock.db_path' id='139907887533472'>")

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        validate_db_path("<Mock name='mock.db_path' id='139907887533472'>")

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        validate_db_path("/data/dir/MagicMock name='mock.db_path'/test.db")


def test_connect_rejects_mock_and_creates_no_files():
    """connect(MagicMock) raises TypeError and creates zero files on disk."""
    root_before = set(glob.glob("<MagicMock*") + glob.glob("*MagicMock*"))
    with pytest.raises(TypeError, match="Mock objects are not valid"):
        with connect(MagicMock()):
            pass
    root_after = set(glob.glob("<MagicMock*") + glob.glob("*MagicMock*"))
    assert root_before == root_after, "connect(MagicMock()) created files on disk"


def test_connect_rejects_stringified_mock_and_creates_no_files():
    """connect('<MagicMock...>') raises ValueError and creates zero files on disk."""
    mock_str = "<MagicMock name='mock.db_path' id='139907887533472'>"
    root_before = set(glob.glob("<MagicMock*") + glob.glob("*MagicMock*"))
    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        with connect(mock_str):
            pass
    root_after = set(glob.glob("<MagicMock*") + glob.glob("*MagicMock*"))
    assert root_before == root_after, "connect('<MagicMock...>') created files on disk"


def test_wal_checkpoint_passive_rejects_mock():
    """wal_checkpoint_passive rejects mock objects and stringified mocks."""
    with pytest.raises(TypeError, match="Mock objects are not valid"):
        wal_checkpoint_passive(MagicMock())

    with pytest.raises(ValueError, match="Stringified mock representation detected"):
        wal_checkpoint_passive("<MagicMock name='mock.db_path' id='139907887533472'>")
