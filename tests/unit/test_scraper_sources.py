"""Unit tests for multi-source scraping, subreddit rotation, and SCP wiki scraper."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.core.lanes import parse_lane
from src.core.repository import connect, migrate_database
from src.scraper import (
    async_ensure_queue_depth,
    async_fetch_reddit_stories,
    async_replenish_queue,
    ensure_queue_depth,
    fetch_reddit_stories,
    replenish_queue,
)
from src.scraper_scp import (
    DEFAULT_LICENSE,
    CANONICAL_SCP_STORIES,
    async_fetch_scp_by_item,
    async_fetch_top_scp_articles,
    async_fetch_top_scp_from_crom,
    async_scrape_and_enqueue_scp,
    fetch_scp_by_item,
    fetch_top_scp_articles,
    fetch_top_scp_from_crom,
    parse_scp_text,
    parse_scp_wikidot_html,
    scrape_and_enqueue_scp,
)


@pytest.fixture
def test_db(tmp_path):
    db_file = str(tmp_path / "test_queue.db")
    migrate_database(db_file)
    return db_file


@pytest.fixture
def scp_lane():
    return parse_lane({
        "id": "moku-scp-shorts",
        "channel": "moku",
        "story_type": "scp",
        "orientation": "vertical",
        "duration": {"min_sec": 60, "target_sec": 150, "max_sec": 180},
        "words": {"min": 160, "max": 340, "recondense_max": 300},
        "template": "shorts_creepypasta",
        "voice_rate": "+20%",
        "cadence": {"min_gap_seconds": 300},
        "sources": {
            "kind": "reddit",
            "subreddits": ["SCP", "SCPDeclassified"],
            "listing_categories": [["hot", "day"], ["top", "week"]],
            "limit_per_fetch": 5,
            "queue_target_pending": 3,
        },
        "topic_filter": {
            "mode": "keyword",
            "keywords": ["scp", "anomal", "contención", "fundación"],
        },
    })


@pytest.fixture
def aita_lane():
    return parse_lane({
        "id": "aelithia-aita-long",
        "channel": "aelithia",
        "story_type": "reddit_aita",
        "orientation": "horizontal",
        "duration": {"min_sec": 600, "target_sec": 600, "max_sec": 1800},
        "words": {"min": 100, "max": None},
        "template": "aita",
        "voice_rate": "+0%",
        "cadence": {"min_gap_seconds": 1800},
        "sources": {
            "kind": "reddit",
            "subreddits": ["AmItheAsshole", "TrueOffMyChest"],
            "listing_categories": [["hot", "day"], ["top", "week"]],
            "limit_per_fetch": 5,
            "queue_target_pending": 3,
        },
        "topic_filter": {
            "mode": "keyword",
            "keywords": ["aita", "wibta", "soy el malo", "familia", "boda", "herencia"],
        },
    })


class TestSCPScraper:
    def test_canonical_scp_stories_contain_cc_by_sa_license(self):
        assert len(CANONICAL_SCP_STORIES) >= 5
        for item in CANONICAL_SCP_STORIES:
            assert item["source_license"] == DEFAULT_LICENSE
            assert item["source_license"] == "CC BY-SA 3.0"
            assert item["item_number"].startswith("SCP-")
            assert item["object_class"] in ("Safe", "Euclid", "Keter", "Thaumiel", "Apollyon")
            assert len(item["author"]) > 0
            assert len(item["containment_procedures"]) > 20
            assert len(item["description"]) > 20

    def test_fetch_scp_by_item(self):
        item_096 = fetch_scp_by_item("SCP-096")
        assert item_096 is not None
        assert item_096["item_number"] == "SCP-096"
        assert item_096["object_class"] == "Euclid"
        assert item_096["author"] == "Dr Dan"
        assert item_096["source_license"] == "CC BY-SA 3.0"

        item_173 = fetch_scp_by_item("173")
        assert item_173 is not None
        assert item_173["item_number"] == "SCP-173"
        assert item_173["object_class"] == "Euclid"

    def test_parse_scp_text(self):
        sample_text = (
            "Item #: SCP-999\n\n"
            "Object Class: Safe\n\n"
            "Special Containment Procedures: SCP-999 is allowed to freely roam the facility if it desires.\n\n"
            "Description: SCP-999 appears to be a large, amorphous, gelatinous mass of translucent orange slime."
        )
        parsed = parse_scp_text(sample_text, url="https://scp-wiki.wikidot.com/scp-999", author="ProfSnider", rating=2500)
        assert parsed["item_number"] == "SCP-999"
        assert parsed["object_class"] == "Safe"
        assert parsed["author"] == "ProfSnider"
        assert parsed["source_license"] == "CC BY-SA 3.0"
        assert "gelatinous mass" in parsed["description"]
        assert "freely roam" in parsed["containment_procedures"]

    def test_parse_scp_wikidot_html(self):
        sample_html = """
        <div id="page-content">
            <div class="page-rate-widget-box"><span>rate: +500</span></div>
            <p><strong>Item #:</strong> SCP-087</p>
            <p><strong>Object Class:</strong> Euclid</p>
            <p><strong>Special Containment Procedures:</strong> SCP-087 is located on the campus of [REDACTED].</p>
            <p><strong>Description:</strong> SCP-087 is an unlit platform staircase descending indefinitely.</p>
        </div>
        <div id="page-info-break"></div>
        """
        parsed = parse_scp_wikidot_html(sample_html, url="https://scp-wiki.wikidot.com/scp-087", author="Zaeyde", rating=1800)
        assert parsed is not None
        assert parsed["item_number"] == "SCP-087"
        assert parsed["object_class"] == "Euclid"
        assert parsed["source_license"] == "CC BY-SA 3.0"

    def test_scrape_and_enqueue_scp_stores_license_and_lane_id(self, test_db):
        enqueued_count = scrape_and_enqueue_scp(limit=3, db_path=test_db, lane_id="moku-scp-shorts", channel="moku")
        assert enqueued_count == 3

        with connect(test_db, read_only=True) as conn:
            rows = conn.execute("SELECT story_id, channel, lane_id, source_license, status FROM stories").fetchall()
            assert len(rows) == 3
            for row in rows:
                assert row["channel"] == "moku"
                assert row["lane_id"] == "moku-scp-shorts"
                assert row["source_license"] == "CC BY-SA 3.0"
                assert row["status"] == "PENDING"


class TestAsyncSCPScraper:
    @pytest.mark.anyio
    async def test_async_fetch_scp_by_item(self):
        item_096 = await async_fetch_scp_by_item("SCP-096")
        assert item_096 is not None
        assert item_096["item_number"] == "SCP-096"
        assert item_096["object_class"] == "Euclid"
        assert item_096["source_license"] == "CC BY-SA 3.0"

        item_173 = await async_fetch_scp_by_item("173")
        assert item_173 is not None
        assert item_173["item_number"] == "SCP-173"

    @pytest.mark.anyio
    async def test_async_fetch_top_scp_articles_canonical_fallback(self):
        articles = await async_fetch_top_scp_articles(limit=3)
        assert len(articles) == 3
        for art in articles:
            assert art["source_license"] == "CC BY-SA 3.0"
            assert art["item_number"].startswith("SCP-")

    @pytest.mark.anyio
    async def test_async_scrape_and_enqueue_scp(self, test_db):
        count = await async_scrape_and_enqueue_scp(limit=2, db_path=test_db, lane_id="moku-scp-shorts", channel="moku")
        assert count == 2
        with connect(test_db, read_only=True) as conn:
            rows = conn.execute("SELECT story_id, source_license, status FROM stories").fetchall()
            assert len(rows) == 2
            assert all(r["status"] == "PENDING" for r in rows)
            assert all(r["source_license"] == "CC BY-SA 3.0" for r in rows)


class TestEnsureQueueDepth:
    def test_ensure_queue_depth_already_satisfied(self, test_db, scp_lane):
        # Pre-seed database with 5 pending stories
        scrape_and_enqueue_scp(limit=5, db_path=test_db, lane_id=scp_lane.id, channel="moku")

        with patch("src.scraper.fetch_reddit_stories") as mock_fetch:
            depth = ensure_queue_depth(scp_lane, db_path=test_db)
            assert depth == 5
            mock_fetch.assert_not_called()

    def test_ensure_queue_depth_reddit_rotation_and_filtering(self, test_db, aita_lane):
        mock_posts = [
            {
                "id": "aita_001",
                "title": "AITA for refusing to pay for my sister's lavish wedding?",
                "content": "My family is furious with me because I refused to contribute inheritance money to her wedding.",
                "url": "https://reddit.com/r/AmItheAsshole/comments/aita_001",
                "score": 1500,
                "upvote_ratio": 0.95,
                "num_comments": 200,
            },
            {
                "id": "aita_002",
                "title": "Random gaming post about Minecraft servers",
                "content": "Here is how to configure your Minecraft server with plugins.",
                "url": "https://reddit.com/r/gaming/comments/game_002",
                "score": 100,
                "upvote_ratio": 0.80,
                "num_comments": 10,
            },
            {
                "id": "aita_003",
                "title": "WIBTA if I report my coworker for taking credit?",
                "content": "My coworker has been taking credit for all my project work with our family business.",
                "url": "https://reddit.com/r/AmItheAsshole/comments/aita_003",
                "score": 800,
                "upvote_ratio": 0.90,
                "num_comments": 50,
            },
        ]

        with patch("src.scraper.fetch_reddit_stories") as mock_fetch:
            mock_fetch.return_value = mock_posts
            depth = ensure_queue_depth(aita_lane, db_path=test_db)

            # aita_001 and aita_003 should match topic filter, aita_002 is rejected by topic filter
            assert depth >= 2
            with connect(test_db, read_only=True) as conn:
                rows = conn.execute("SELECT story_id, title, lane_id FROM stories WHERE status = 'PENDING'").fetchall()
                story_ids = {r["story_id"] for r in rows}
                assert "aita_001" in story_ids
                assert "aita_003" in story_ids
                assert "aita_002" not in story_ids

    def test_ensure_queue_depth_scp_fallback_when_reddit_empty(self, test_db, scp_lane):
        # Reddit returns empty -> scraper falls back to SCP wiki scraper for SCP lane
        with patch("src.scraper.fetch_reddit_stories") as mock_fetch:
            mock_fetch.return_value = []
            depth = ensure_queue_depth(scp_lane, db_path=test_db)
            assert depth >= 3
            with connect(test_db, read_only=True) as conn:
                rows = conn.execute("SELECT story_id, source_license FROM stories WHERE status = 'PENDING'").fetchall()
                assert len(rows) >= 3
                for row in rows:
                    assert row["source_license"] == "CC BY-SA 3.0"


class TestAsyncEnsureQueueDepth:
    @pytest.mark.anyio
    async def test_async_ensure_queue_depth_already_satisfied(self, test_db, scp_lane):
        await async_scrape_and_enqueue_scp(limit=5, db_path=test_db, lane_id=scp_lane.id, channel="moku")
        with patch("src.scraper.async_fetch_reddit_stories") as mock_fetch:
            depth = await async_ensure_queue_depth(scp_lane, db_path=test_db)
            assert depth == 5
            mock_fetch.assert_not_called()

    @pytest.mark.anyio
    async def test_async_ensure_queue_depth_reddit_rotation(self, test_db, aita_lane):
        mock_posts = [
            {
                "id": "aita_async_001",
                "title": "AITA for refusing to share inheritance with ex?",
                "content": "My ex demanded half of the inheritance my family left me.",
                "url": "https://reddit.com/r/AmItheAsshole/comments/aita_async_001",
                "score": 2000,
                "upvote_ratio": 0.96,
                "num_comments": 300,
            },
        ]
        with patch("src.scraper.async_fetch_reddit_stories", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_posts
            depth = await async_ensure_queue_depth(aita_lane, db_path=test_db)
            assert depth >= 1
            with connect(test_db, read_only=True) as conn:
                row = conn.execute("SELECT story_id, score, num_comments FROM stories WHERE story_id = 'aita_async_001'").fetchone()
                assert row is not None
                assert row["score"] == 2000
                assert row["num_comments"] == 300

    @pytest.mark.anyio
    async def test_async_replenish_queue(self, test_db):
        mock_posts = [
            {
                "id": "terror_rep_001",
                "title": "The Old Abandoned Cellar",
                "content": "I found a hidden door in my basement leading to a concrete chamber that wasn't on the house blueprint.",
                "url": "https://reddit.com/r/nosleep/comments/terror_rep_001",
                "score": 1200,
                "upvote_ratio": 0.98,
                "num_comments": 150,
            }
        ]
        with patch("src.scraper.async_fetch_reddit_stories", new_callable=AsyncMock) as mock_fetch:
            mock_fetch.return_value = mock_posts
            updated = await async_replenish_queue(channel="terror", min_stories=1, db_path=test_db)
            assert updated >= 1
            with connect(test_db, read_only=True) as conn:
                row = conn.execute("SELECT story_id, channel FROM stories WHERE story_id = 'terror_rep_001'").fetchone()
                assert row is not None
                assert row["channel"] in ("terror", "moku")

