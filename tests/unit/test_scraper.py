import unittest
from unittest.mock import patch, MagicMock
import requests

from src.scraper import fetch_reddit_stories, DEFAULT_USER_AGENT


class TestRedditScraper(unittest.TestCase):
    """Unit tests for Reddit Scraper and PullPush Fallback (src/scraper.py)."""

    def test_fetch_reddit_stories_direct_success(self):
        """Test fetching stories from direct Reddit JSON endpoint."""
        mock_json = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "story_001",
                            "title": "The Whispering Walls",
                            "selftext": "Every night at 3 AM the walls in my apartment start whispering...",
                            "permalink": "/r/nosleep/comments/story_001/the_whispering_walls/"
                        }
                    }
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_json
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "story_001")
            self.assertEqual(stories[0]["title"], "The Whispering Walls")
            self.assertEqual(stories[0]["url"], "https://www.reddit.com/r/nosleep/comments/story_001/the_whispering_walls/")

            # Verify User-Agent header was set in request
            args, kwargs = mock_get.call_args
            from src.scraper import USER_AGENTS
            self.assertIn(kwargs["headers"]["User-Agent"], USER_AGENTS)

    def test_fetch_reddit_stories_fallback_on_403(self):
        """Test automatic fallback to PullPush API when Reddit returns 403 Forbidden."""
        pullpush_json = {
            "data": [
                {
                    "id": "pp_001",
                    "title": "Shadows in the Woods",
                    "selftext": "The woods behind my house have always been off-limits...",
                    "permalink": "/r/nosleep/comments/pp_001/shadows_in_the_woods/",
                    "stickied": False,
                    "over_18": False
                }
            ]
        }

        with patch("requests.get") as mock_get:
            resp_403 = MagicMock()
            resp_403.status_code = 403

            resp_pp = MagicMock()
            resp_pp.status_code = 200
            resp_pp.json.return_value = pullpush_json

            mock_get.side_effect = [resp_403, resp_pp]

            stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "pp_001")
            self.assertEqual(stories[0]["title"], "Shadows in the Woods")
            self.assertEqual(mock_get.call_count, 2)
            self.assertIn("pullpush.io", mock_get.call_args_list[1][0][0])

    def test_fetch_reddit_stories_fallback_on_429(self):
        """Test automatic fallback to PullPush API when Reddit returns 429 Too Many Requests."""
        pullpush_json = {
            "data": [
                {
                    "id": "pp_002",
                    "title": "The Old Clock",
                    "selftext": "My grandmother inherited an ancient grandfather clock...",
                    "permalink": "/r/nosleep/comments/pp_002/the_old_clock/"
                }
            ]
        }

        with patch("requests.get") as mock_get:
            resp_429 = MagicMock()
            resp_429.status_code = 429

            resp_pp = MagicMock()
            resp_pp.status_code = 200
            resp_pp.json.return_value = pullpush_json

            mock_get.side_effect = [resp_429, resp_pp]

            stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "pp_002")

    def test_fetch_reddit_stories_fallback_on_network_exception(self):
        """Test automatic fallback to PullPush API when Reddit request raises RequestException."""
        pullpush_json = {
            "data": [
                {
                    "id": "pp_003",
                    "title": "Lighthouse Duty",
                    "selftext": "Working alone on a remote lighthouse comes with quiet nights...",
                    "permalink": "/r/nosleep/comments/pp_003/lighthouse_duty/"
                }
            ]
        }

        with patch("requests.get") as mock_get:
            resp_pp = MagicMock()
            resp_pp.status_code = 200
            resp_pp.json.return_value = pullpush_json

            mock_get.side_effect = [requests.RequestException("Connection refused"), resp_pp]

            stories = fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "pp_003")

    def test_fetch_reddit_stories_filtering(self):
        """Test filtering of stickied, deleted, NSFW, and short posts."""
        mock_json = {
            "data": {
                "children": [
                    {
                        # Stickied post - should be filtered out
                        "data": {
                            "id": "post_stickied",
                            "title": "Subreddit Rules & Info",
                            "selftext": "Please read the rules before posting stories here.",
                            "stickied": True,
                            "permalink": "/r/nosleep/comments/rules/"
                        }
                    },
                    {
                        # NSFW post - should be filtered out
                        "data": {
                            "id": "post_nsfw",
                            "title": "NSFW Horror",
                            "selftext": "Explicit horror narrative with gory details...",
                            "over_18": True,
                            "permalink": "/r/nosleep/comments/nsfw/"
                        }
                    },
                    {
                        # Deleted post - should be filtered out
                        "data": {
                            "id": "post_deleted",
                            "title": "Deleted Post",
                            "selftext": "[deleted]",
                            "permalink": "/r/nosleep/comments/del/"
                        }
                    },
                    {
                        # Short post - should be filtered out when min_length > len
                        "data": {
                            "id": "post_short",
                            "title": "Short",
                            "selftext": "Tiny",
                            "permalink": "/r/nosleep/comments/short/"
                        }
                    },
                    {
                        # Valid post - should be included
                        "data": {
                            "id": "post_valid",
                            "title": "Valid Creepypasta",
                            "selftext": "A terrifying story that keeps you up at night with mysterious sounds.",
                            "stickied": False,
                            "over_18": False,
                            "permalink": "/r/nosleep/comments/post_valid/"
                        }
                    }
                ]
            }
        }
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = mock_json
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="nosleep", limit=10, min_length=10)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "post_valid")

    def test_fetch_reddit_stories_404_returns_empty(self):
        """Test non-existent subreddit (404) returns empty list without error."""
        with patch("requests.get") as mock_get:
            mock_resp = MagicMock()
            mock_resp.status_code = 404
            mock_get.return_value = mock_resp

            stories = fetch_reddit_stories(subreddit="non_existent_subreddit_999", limit=5)
            self.assertEqual(stories, [])

    def test_is_high_quality_story_valid(self):
        """Test is_high_quality_story with a valid high-quality story."""
        from src.scraper import is_high_quality_story
        title = "The Creepy Old Cabin"
        content = (
            "I found an old cabin in the deep woods. "
            "It had shattered windows and the door was wide open. "
            "I stepped inside and heard a sudden whisper. "
            "It was calling my name, asking me to stay forever. "
            "I ran as fast as I could and never looked back."
        )
        self.assertTrue(is_high_quality_story(title, content))

    def test_is_high_quality_story_too_short(self):
        """Test is_high_quality_story with a story that is too short."""
        from src.scraper import is_high_quality_story
        title = "Short story"
        content = "Too short story."
        self.assertFalse(is_high_quality_story(title, content))

    def test_is_high_quality_story_repetitive_sentence(self):
        """Test is_high_quality_story with a story repeating a single sentence excessively."""
        from src.scraper import is_high_quality_story
        title = "Spam story"
        # Repeat the same sentence 4 times
        content = (
            "I always knew the old manor hid dark secrets. "
            "I always knew the old manor hid dark secrets. "
            "I always knew the old manor hid dark secrets. "
            "I always knew the old manor hid dark secrets. "
            "And then some extra unique text to fill the length requirement."
        )
        self.assertFalse(is_high_quality_story(title, content))

    def test_is_high_quality_story_high_redundancy_percentage(self):
        """Test is_high_quality_story with high duplication percentage of sentences."""
        from src.scraper import is_high_quality_story
        title = "Redundant story"
        content = (
            "This is the first sentence. "
            "This is the second sentence. "
            "This is the first sentence. "
            "This is the second sentence. "
            "This is the first sentence. "
            "This is the second sentence. "
            "This is the third sentence."
        )
        self.assertFalse(is_high_quality_story(title, content))


class TestAsyncRedditScraper(unittest.IsolatedAsyncioTestCase):
    """Unit tests for asynchronous non-blocking Reddit Scraper (src/scraper.py)."""

    async def test_async_fetch_reddit_stories_direct_success(self):
        """Test async fetching stories from direct Reddit JSON endpoint."""
        from src.scraper import async_fetch_reddit_stories
        mock_json = {
            "data": {
                "children": [
                    {
                        "data": {
                            "id": "async_story_001",
                            "title": "The Forgotten Mirror in the Attic",
                            "selftext": "Every full moon, the antique mirror in my grandmother's attic reveals a room that does not exist...",
                            "permalink": "/r/nosleep/comments/async_story_001/mirror/",
                            "score": 450,
                            "upvote_ratio": 0.98,
                            "num_comments": 85
                        }
                    }
                ]
            }
        }
        with patch("src.scraper._fetch_url_aiohttp") as mock_fetch:
            mock_fetch.return_value = (200, mock_json, {})
            stories = await async_fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "async_story_001")
            self.assertEqual(stories[0]["title"], "The Forgotten Mirror in the Attic")
            self.assertEqual(stories[0]["score"], 450)
            self.assertEqual(stories[0]["upvote_ratio"], 0.98)
            self.assertEqual(stories[0]["num_comments"], 85)

    async def test_async_fetch_reddit_stories_fallback_on_403_to_pullpush(self):
        """Test async immediate failover to PullPush when Reddit returns 403 Forbidden."""
        from src.scraper import async_fetch_reddit_stories
        pullpush_json = {
            "data": [
                {
                    "id": "pp_async_001",
                    "title": "The Watcher in the Pines",
                    "selftext": "I was hired as a fire lookout tower guard in northern Oregon...",
                    "permalink": "/r/nosleep/comments/pp_async_001/watcher/",
                    "score": 250,
                    "upvote_ratio": 0.92,
                    "num_comments": 40
                }
            ]
        }
        with patch("src.scraper._fetch_url_aiohttp") as mock_fetch:
            # 1st call for Reddit returns 403, 2nd call for PullPush returns 200
            mock_fetch.side_effect = [(403, None, {}), (200, pullpush_json, {})]
            stories = await async_fetch_reddit_stories(subreddit="nosleep", limit=5)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "pp_async_001")
            self.assertEqual(stories[0]["title"], "The Watcher in the Pines")
            self.assertEqual(mock_fetch.call_count, 2)

    async def test_async_fetch_reddit_stories_fallback_on_429_with_retry_after(self):
        """Test async 429 rate limit backoff and fallback to PullPush."""
        from src.scraper import async_fetch_reddit_stories
        pullpush_json = {
            "data": [
                {
                    "id": "pp_async_429",
                    "title": "The Subway Whispers",
                    "selftext": "There are voices between the 14th Street and 23rd Street stations...",
                    "permalink": "/r/nosleep/comments/pp_async_429/subway/"
                }
            ]
        }
        with patch("src.scraper._fetch_url_aiohttp") as mock_fetch:
            # Reddit returns 429 with retry-after header
            mock_fetch.side_effect = [
                (429, None, {"retry-after": "0.01"}),
                (429, None, {"retry-after": "0.01"}),
                (429, None, {"retry-after": "0.01"}),
                (200, pullpush_json, {})
            ]
            stories = await async_fetch_reddit_stories(subreddit="nosleep", limit=5, max_retries=3)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "pp_async_429")

    async def test_async_fetch_reddit_stories_fallback_on_5xx_server_error(self):
        """Test async 500 server error backoff and fallback to PullPush."""
        from src.scraper import async_fetch_reddit_stories
        pullpush_json = {
            "data": [
                {
                    "id": "pp_500",
                    "title": "Midnight Radio Signals",
                    "selftext": "Tuning into frequency 98.7 at exactly 3:15 AM changed my life...",
                    "permalink": "/r/nosleep/comments/pp_500/radio/"
                }
            ]
        }
        with patch("src.scraper._fetch_url_aiohttp") as mock_fetch:
            mock_fetch.side_effect = [
                (500, None, {}),
                (502, None, {}),
                (503, None, {}),
                (200, pullpush_json, {})
            ]
            stories = await async_fetch_reddit_stories(subreddit="nosleep", limit=5, max_retries=3)
            self.assertEqual(len(stories), 1)
            self.assertEqual(stories[0]["id"], "pp_500")

    async def test_async_fetch_reddit_stories_total_failure_canonical_fallback(self):
        """Test seamless fallback to local canonical workset / preset stories on total network failure."""
        from src.scraper import async_fetch_reddit_stories
        with patch("src.scraper._fetch_url_aiohttp") as mock_fetch:
            # Both Reddit and PullPush fail completely
            mock_fetch.side_effect = [(500, None, {}), (500, None, {}), (500, None, {}), (500, None, {}), (500, None, {}), (500, None, {})]
            stories = await async_fetch_reddit_stories(subreddit="nosleep", limit=2)
            self.assertTrue(len(stories) >= 1)
            # Should have loaded canonical or preset stories
            story_ids = [s["id"] for s in stories]
            self.assertTrue(any(s.startswith("CANONICAL") or s.startswith("FILE") for s in story_ids))

    async def test_async_rate_limiter_and_backoff(self):
        """Test AsyncRateLimiter acquire and release semantics."""
        from src.scraper import AsyncRateLimiter, _async_backoff_sleep
        limiter = AsyncRateLimiter(max_concurrent=2, rate_limit_per_second=50.0)
        async with limiter:
            self.assertEqual(limiter.semaphore._value, 1)

        # Test backoff calculation
        sleep_dur = await _async_backoff_sleep(attempt=0, base=0.01, max_backoff=1.0)
        self.assertGreater(sleep_dur, 0.0)

        sleep_retry = await _async_backoff_sleep(attempt=0, base=1.0, max_backoff=5.0, retry_after=0.01)
        self.assertAlmostEqual(sleep_retry, 0.01, places=2)


if __name__ == "__main__":
    unittest.main()

