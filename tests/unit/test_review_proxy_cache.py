"""Unit tests for the content-addressed Telegram review proxy cache."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from review.review_manager import ProxyCache


@pytest.fixture()
def master(tmp_path: Path) -> Path:
    p = tmp_path / "master.mp4"
    p.write_bytes(os.urandom(5 * 1024 * 1024))
    return p


@pytest.fixture()
def proxy(tmp_path: Path) -> Path:
    p = tmp_path / "review_proxy_master.mp4"
    p.write_bytes(b"\x00\x01proxy-bytes" * 1000)
    return p


def test_store_lookup_roundtrip(tmp_path: Path, master: Path, proxy: Path) -> None:
    cache = ProxyCache(root=tmp_path / "cache")
    assert cache.lookup(master, 50 * 1024 * 1024) is None
    stored = cache.store(master, 50 * 1024 * 1024, proxy)
    hit = cache.lookup(master, 50 * 1024 * 1024)
    assert hit == stored
    assert Path(hit).read_bytes() == proxy.read_bytes()


def test_bucket_separation(tmp_path: Path, master: Path, proxy: Path) -> None:
    cache = ProxyCache(root=tmp_path / "cache")
    a = cache.store(master, 40 * 1024 * 1024, proxy)
    b = cache.store(master, 55 * 1024 * 1024, proxy)
    assert a != b
    assert cache.lookup(master, 40 * 1024 * 1024) == a
    assert cache.lookup(master, 55 * 1024 * 1024) == b
    # Same bucket shares one entry.
    assert cache.lookup(master, 49 * 1024 * 1024) is not None


def test_mtime_invalidates_key(tmp_path: Path, master: Path, proxy: Path) -> None:
    cache = ProxyCache(root=tmp_path / "cache")
    first = cache.store(master, 50 * 1024 * 1024, proxy)
    os.utime(master, ns=(1_000_000_000, 1_000_000_000))
    second = cache.store(master, 50 * 1024 * 1024, proxy)
    assert first != second
    assert cache.lookup(master, 50 * 1024 * 1024) == second


def test_missing_master_is_a_miss(tmp_path: Path) -> None:
    cache = ProxyCache(root=tmp_path / "cache")
    assert cache.lookup(tmp_path / "nope.mp4", 50 * 1024 * 1024) is None
