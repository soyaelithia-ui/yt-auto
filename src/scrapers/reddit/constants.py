"""src/scrapers/reddit/constants.py - Reddit scraping user agents and channel subreddits."""

from __future__ import annotations

from typing import Dict, List

DEFAULT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) YoutubeAutomation/1.0"
USER_AGENTS: List[str] = [DEFAULT_USER_AGENT]

CHANNEL_SUBREDDITS: Dict[str, List[str]] = {
    "horror": ["nosleep", "scarystories", "darktales", "creepypasta", "shortscarystories", "libraryofshadows"],
    "drama": [
        "AmItheAsshole",
        "AITA",
        "TrueOffMyChest",
        "relationship_advice",
        "Confession",
        "badparents",
        "AskReddit",
        "ProRevenge",
        "NuclearRevenge",
        "PettyRevenge",
    ],
}

__all__ = [
    "DEFAULT_USER_AGENT",
    "USER_AGENTS",
    "CHANNEL_SUBREDDITS",
]
