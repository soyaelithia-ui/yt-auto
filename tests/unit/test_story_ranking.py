"""Unit tests for story selection by real metadata (plan items 1a + 1b).

Covers:
- Reddit/PullPush metadata propagation (score, upvote_ratio, num_comments).
- REDDIT_MIN_SCORE / REDDIT_MIN_UPVOTE_RATIO filters (never applied to fallbacks).
- Score-ranked claim ordering with legacy opt-out via QUEUE_RANK_BY_SCORE=0.
- Additive story-column migration on pre-existing databases.
- Optional frontmatter in canonical .md/.txt worksets.
"""
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.core.repository import QueueRepository, connect
from src.db import init_db
from src.scraper import (
    _load_canonical_stories,
    _parse_frontmatter,
    fetch_reddit_stories,
)


LONG_TEXT = (
    "The basement door opened by itself again tonight. "
    "I heard footsteps climbing the stairs at exactly 3 AM. "
    "Nobody else in the house ever wakes up when it happens."
)


def _reddit_payload(children):
    return {"data": {"children": [{"data": child} for child in children]}}


def _pullpush_payload(items):
    return {"data": items}


def _mock_response(status_code=200, payload=None):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = payload
    return resp


# ---------------------------------------------------------------------------
# 1a: reddit/pullpush metadata extraction + optional filtering knobs
# ---------------------------------------------------------------------------


def test_direct_reddit_payload_carries_metadata():
    payload = _reddit_payload([
        {
            "id": "meta_001",
            "title": "The Whispering Basement",
            "selftext": LONG_TEXT,
            "permalink": "/r/nosleep/comments/meta_001/the_whispering_basement/",
            "score": 4200,
            "upvote_ratio": 0.97,
            "num_comments": 815,
        }
    ])
    with patch("requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, payload)
        stories = fetch_reddit_stories(subreddit="nosleep", limit=5)

    assert len(stories) == 1
    assert stories[0]["score"] == 4200
    assert stories[0]["upvote_ratio"] == pytest.approx(0.97)
    assert stories[0]["num_comments"] == 815


def test_pullpush_fallback_carries_metadata(monkeypatch):
    """PullPush serves the same fields, sometimes as strings; both parse."""
    pullpush_json = _pullpush_payload([
        {
            "id": "pp_meta",
            "title": "Shadows in the Woods",
            "selftext": LONG_TEXT,
            "permalink": "/r/nosleep/comments/pp_meta/shadows/",
            "score": "950",
            "upvote_ratio": "0.93",
            "num_comments": "44",
        }
    ])
    with patch("requests.get") as mock_get:
        mock_get.side_effect = [
            _mock_response(403),
            _mock_response(200, pullpush_json),
        ]
        stories = fetch_reddit_stories(subreddit="nosleep", limit=5)

    assert len(stories) == 1
    assert stories[0]["id"] == "pp_meta"
    assert stories[0]["score"] == 950
    assert stories[0]["upvote_ratio"] == pytest.approx(0.93)
    assert stories[0]["num_comments"] == 44


def test_missing_or_non_numeric_metadata_defaults_to_zero():
    payload = _reddit_payload([
        {
            "id": "no_meta",
            "title": "No usable metadata here",
            "selftext": LONG_TEXT,
            "score": "not-a-number",
            "upvote_ratio": None,
            "num_comments": [],
        }
    ])
    with patch("requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, payload)
        stories = fetch_reddit_stories(subreddit="nosleep", limit=5)

    assert len(stories) == 1
    assert stories[0]["score"] == 0
    assert stories[0]["upvote_ratio"] == 0.0
    assert stories[0]["num_comments"] == 0


def test_min_score_filter_skips_low_score_posts(monkeypatch):
    payload = _reddit_payload([
        {
            "id": "low_score",
            "title": "Barely noticed story",
            "selftext": LONG_TEXT,
            "score": 3,
        },
        {
            "id": "high_score",
            "title": "Community favourite story",
            "selftext": LONG_TEXT,
            "score": 500,
        },
    ])

    # Default (unset env): no filtering at all.
    with patch("requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, payload)
        stories = fetch_reddit_stories(subreddit="nosleep", limit=5, min_length=10)
    assert {s["id"] for s in stories} == {"low_score", "high_score"}

    monkeypatch.setenv("REDDIT_MIN_SCORE", "10")
    with patch("requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, payload)
        stories = fetch_reddit_stories(subreddit="nosleep", limit=5, min_length=10)
    assert [s["id"] for s in stories] == ["high_score"]


def test_min_upvote_ratio_filter(monkeypatch):
    payload = _reddit_payload([
        {
            "id": "controversial",
            "title": "Divisive tale indeed",
            "selftext": LONG_TEXT,
            "score": 900,
            "upvote_ratio": 0.55,
        },
        {
            "id": "beloved",
            "title": "Universally liked tale",
            "selftext": LONG_TEXT,
            "score": 300,
            "upvote_ratio": 0.99,
        },
    ])
    monkeypatch.setenv("REDDIT_MIN_UPVOTE_RATIO", "0.75")
    with patch("requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, payload)
        stories = fetch_reddit_stories(subreddit="nosleep", limit=5, min_length=10)
    assert [s["id"] for s in stories] == ["beloved"]


def test_score_filter_never_applies_to_canonical_fallback(monkeypatch):
    """When scrapers fail, local canonical worksets bypass the metadata knobs."""
    monkeypatch.setenv("REDDIT_MIN_SCORE", "999999")
    monkeypatch.setenv("REDDIT_MIN_UPVOTE_RATIO", "1.0")
    with patch("requests.get") as mock_get:
        mock_get.return_value = _mock_response(200, _reddit_payload([]))
        stories = fetch_reddit_stories(subreddit="nosleep", limit=25)

    assert len(stories) > 0
    assert all(s["id"] and s["title"] for s in stories)


# ---------------------------------------------------------------------------
# 1b: optional frontmatter in canonical .md/.txt worksets
# ---------------------------------------------------------------------------


def test_parse_frontmatter_basic():
    meta = _parse_frontmatter(["---", "score: 4200", "tags: scp,clasico", "---"])
    assert meta == {"score": "4200", "tags": "scp,clasico"}


def test_parse_frontmatter_absent_and_unterminated():
    assert _parse_frontmatter(["Titulo", "Cuerpo"]) == {}
    # Unterminated block keeps legacy behaviour (no frontmatter consumed).
    assert _parse_frontmatter(["---", "score: 5"]) == {}


def _load_from_canonical_dir(canon_dir: Path):
    with patch("src.scraper.Path") as mock_path_cls:
        mock_path_cls.return_value.resolve.return_value.parent.parent = canon_dir
        return _load_canonical_stories(min_length=10)


def test_load_canonical_md_with_frontmatter(tmp_path):
    canon = tmp_path / "data" / "worksets" / "canonical"
    canon.mkdir(parents=True)
    body = "Una historia larga y escalofriante sobre el tunel sellado. " * 6
    (canon / "front.md").write_text(
        "---\nscore: 4200\ntags: scp,clasico\n---\n"
        "El tunel que no estaba en los planos\n"
        f"{body}\n",
        encoding="utf-8",
    )

    stories = _load_from_canonical_dir(tmp_path)

    story = next(s for s in stories if s["id"] == "FILE-front")
    assert story["title"] == "El tunel que no estaba en los planos"
    assert story["score"] == 4200
    assert story["tags"] == ["scp", "clasico"]
    assert story["content"].startswith("Una historia larga")


def test_load_canonical_without_frontmatter_is_unchanged(tmp_path):
    canon = tmp_path / "data" / "worksets" / "canonical"
    canon.mkdir(parents=True)
    body = "Historia de prueba sin metadatos en ninguna linea. " * 5
    (canon / "plain.txt").write_text(f"Titulo plano\n{body}\n", encoding="utf-8")

    stories = _load_from_canonical_dir(tmp_path)

    assert len(stories) == 1
    # Byte-identical to the legacy shape: exactly four keys, no score/tags.
    assert stories[0] == {
        "id": "FILE-plain",
        "title": "Titulo plano",
        "content": body.strip(),
        "url": "https://reddit.com/r/canonical/FILE-plain",
    }


def test_real_shipped_worksets_have_no_frontmatter_keys():
    """The five bundled .md files carry no frontmatter and must parse as before."""
    stories = [
        s
        for s in _load_canonical_stories(min_length=100)
        if not s["id"].startswith("CANONICAL-")
    ]
    assert len(stories) >= 5
    for story in stories:
        assert "score" not in story
        assert "tags" not in story
        assert set(story) == {"id", "title", "content", "url"}


# ---------------------------------------------------------------------------
# 1a: queue persistence + score-ranked claim
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _rank_enabled_by_default(monkeypatch):
    monkeypatch.delenv("QUEUE_RANK_BY_SCORE", raising=False)


def _repo(tmp_path):
    db_path = str(tmp_path / "rank_queue.db")
    repo = QueueRepository(db_path)
    repo.initialize()
    return repo


def test_enqueue_persists_all_metadata(tmp_path):
    repo = _repo(tmp_path)
    assert repo.enqueue(
        "full_meta", "Full", LONG_TEXT, "https://full", "moku",
        score=4321, upvote_ratio=0.98, num_comments=313,
    )
    with connect(repo.db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT score, upvote_ratio, num_comments FROM stories "
            "WHERE story_id = 'full_meta'"
        ).fetchone()
    assert row["score"] == 4321
    assert row["upvote_ratio"] == pytest.approx(0.98)
    assert row["num_comments"] == 313


def test_db_facade_passes_metadata_through(tmp_path):
    from src.db import enqueue_story

    db_file = str(tmp_path / "facade.db")
    init_db(db_file)
    assert enqueue_story(
        story_id="facade_001",
        title="Facade",
        content=LONG_TEXT,
        url="https://facade/001",
        channel="moku",
        score=250,
        upvote_ratio=0.91,
        num_comments=17,
        db_path=db_file,
    )
    with connect(db_file, read_only=True) as conn:
        row = conn.execute(
            "SELECT score, upvote_ratio, num_comments FROM stories "
            "WHERE story_id = 'facade_001'"
        ).fetchone()
    assert row["score"] == 250
    assert row["upvote_ratio"] == pytest.approx(0.91)
    assert row["num_comments"] == 17


def test_higher_score_claimed_first(tmp_path):
    repo = _repo(tmp_path)
    # Alphabetical ids + shared timestamps mean legacy order would pick "aaa";
    # ranking by score must override that and pick the high scorer.
    assert repo.enqueue("aaa_low", "Low", LONG_TEXT, "https://aaa", "moku", score=12)
    assert repo.enqueue("zzz_high", "High", LONG_TEXT, "https://zzz", "moku", score=900)

    claimed = repo.claim("moku", owner="worker-a")
    assert claimed is not None
    assert claimed["story_id"] == "zzz_high"


def test_legacy_order_when_rank_flag_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEUE_RANK_BY_SCORE", "0")
    repo = _repo(tmp_path)
    assert repo.enqueue("aaa_first", "Low", LONG_TEXT, "https://aaa", "moku", score=900)
    assert repo.enqueue("zzz_second", "High", LONG_TEXT, "https://zzz", "moku", score=1)

    claimed = repo.claim("moku", owner="worker-a")
    assert claimed is not None
    assert claimed["story_id"] == "aaa_first"


def test_tie_scores_fall_back_to_created_at_then_story_id(tmp_path):
    repo = _repo(tmp_path)
    # Identical scores: insertion order coincides with story_id order so the
    # assertion holds whether or not CURRENT_TIMESTAMP resolves to the same second.
    assert repo.enqueue("tie_first", "First", LONG_TEXT, "https://t1", "moku", score=77)
    assert repo.enqueue("tie_second", "Second", LONG_TEXT, "https://t2", "moku", score=77)

    claimed = repo.claim("moku", owner="worker-a")
    assert claimed is not None
    assert claimed["story_id"] == "tie_first"


def test_claim_returns_metadata_columns(tmp_path):
    repo = _repo(tmp_path)
    repo.enqueue(
        "meta_claim", "Meta", LONG_TEXT, "https://mc", "moku",
        score=64, upvote_ratio=0.88, num_comments=12,
    )
    claimed = repo.claim("moku", owner="worker-a")
    assert claimed is not None
    assert claimed["score"] == 64
    assert claimed["upvote_ratio"] == pytest.approx(0.88)
    assert claimed["num_comments"] == 12


# ---------------------------------------------------------------------------
# Migration: old databases gain the new columns with safe defaults
# ---------------------------------------------------------------------------


def test_preexisting_table_gains_columns_with_defaults(tmp_path):
    db_path = str(tmp_path / "legacy_queue.db")

    # Simulate an old deployment: a stories table WITHOUT the new columns.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE stories (
            story_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            content TEXT NOT NULL,
            url TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL DEFAULT 'PENDING',
            error_msg TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            channel TEXT DEFAULT 'moku',
            youtube_url TEXT
        )
        """
    )
    conn.execute(
        "INSERT INTO stories(story_id, title, content, url, status, channel) "
        "VALUES ('legacy_row', 'Legacy', 'Contenido', 'https://legacy', 'PENDING', 'moku')"
    )
    conn.commit()
    conn.close()

    init_db(db_path)

    with connect(db_path, read_only=True) as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(stories)")}
    assert {"score", "upvote_ratio", "num_comments"} <= cols

    with connect(db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT score, upvote_ratio, num_comments FROM stories "
            "WHERE story_id = 'legacy_row'"
        ).fetchone()
    assert row["score"] == 0
    assert row["upvote_ratio"] == 0.0
    assert row["num_comments"] == 0

    # Pre-existing rows default to score 0, so a fresh high-score story wins.
    repo = QueueRepository(db_path)
    assert repo.enqueue(
        "fresh_hot", "Fresh", LONG_TEXT, "https://fresh", "moku", score=1500
    )
    claimed = repo.claim("moku", owner="worker-a")
    assert claimed is not None
    assert claimed["story_id"] == "fresh_hot"


def test_migration_is_idempotent(tmp_path):
    repo = QueueRepository(str(tmp_path / "idempotent.db"))
    first = repo.initialize()
    second = repo.initialize()
    assert first.quick_check == "ok"
    assert second.quick_check == "ok"

    with connect(repo.db_path, read_only=True) as conn:
        names = [row["name"] for row in conn.execute("PRAGMA table_info(stories)")]
    assert names.count("score") == 1
    assert names.count("upvote_ratio") == 1
    assert names.count("num_comments") == 1
