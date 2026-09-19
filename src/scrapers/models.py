"""src/scrapers/models.py - Strongly-typed story scraping models and data contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ScrapedStory:
    """Strongly typed data contract representing a raw scraped story from any source."""

    id: str
    title: str
    content: str = ""
    author: str = ""
    url: str = ""
    story_id: str = ""
    score: int = 0
    upvote_ratio: float = 1.0
    source_subreddit: str = ""
    created_utc: float = 0.0
    selftext: str = ""
    num_comments: int = 0
    over_18: bool = False
    format: str = "short"
    lane_id: str = "terror"
    source_license: str = ""
    item_number: str = ""
    object_class: str = ""
    containment_procedures: str = ""
    description: str = ""
    rating: int = 0
    extra: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.story_id:
            self.story_id = self.id
        if not self.content and self.selftext:
            self.content = self.selftext
        if not self.selftext and self.content:
            self.selftext = self.content

    def to_dict(self) -> dict[str, Any]:
        """Convert the typed story record into a dictionary compatible with queue repositories."""
        data: dict[str, Any] = {
            "id": self.id,
            "story_id": self.story_id,
            "title": self.title,
            "author": self.author,
            "score": self.score,
            "upvote_ratio": self.upvote_ratio,
            "url": self.url,
            "content": self.content,
            "selftext": self.selftext,
            "num_comments": self.num_comments,
            "over_18": self.over_18,
            "format": self.format,
            "lane_id": self.lane_id,
        }
        if self.source_subreddit:
            data["source_subreddit"] = self.source_subreddit
        if self.created_utc:
            data["created_utc"] = self.created_utc
        if self.source_license:
            data["source_license"] = self.source_license
        if self.item_number:
            data["item_number"] = self.item_number
        if self.object_class:
            data["object_class"] = self.object_class
        if self.containment_procedures:
            data["containment_procedures"] = self.containment_procedures
        if self.description:
            data["description"] = self.description
        if self.rating:
            data["rating"] = self.rating
        if self.extra:
            data.update(self.extra)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScrapedStory:
        """Instantiate a typed ScrapedStory from a generic dictionary."""
        known_fields = {
            "id",
            "story_id",
            "title",
            "author",
            "url",
            "score",
            "upvote_ratio",
            "source_subreddit",
            "created_utc",
            "content",
            "selftext",
            "num_comments",
            "over_18",
            "format",
            "lane_id",
            "source_license",
            "item_number",
            "object_class",
            "containment_procedures",
            "description",
            "rating",
        }
        base_kwargs = {k: v for k, v in data.items() if k in known_fields}
        extra_kwargs = {k: v for k, v in data.items() if k not in known_fields}
        if "id" not in base_kwargs and "story_id" in base_kwargs:
            base_kwargs["id"] = base_kwargs["story_id"]
        elif "id" not in base_kwargs and "title" in base_kwargs:
            base_kwargs["id"] = base_kwargs["title"]
        return cls(**base_kwargs, extra=extra_kwargs)
