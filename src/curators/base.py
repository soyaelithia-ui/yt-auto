"""
Base Strategy Interface and Director for Channel Narrative Curators.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from src.core.domain import CanonicalChannel


class INarrativeCurator(ABC):
    """Abstract Strategy interface for channel-specific narrative generation."""

    @property
    @abstractmethod
    def channel(self) -> str:
        """The canonical channel identifier handled by this curator."""
        ...

    @abstractmethod
    def build_short_narrative(self, topic: str, **kwargs: Any) -> str:
        """Builds a high-retention 40-55s Short narrative with dynamic 0-3s hook."""
        ...

    @abstractmethod
    def build_longform_narrative(
        self, topic: str, target_words: int = 1800, **kwargs: Any
    ) -> str:
        """Builds a multi-chapter longform narrative script."""
        ...

    @abstractmethod
    def get_organic_connectors(self) -> List[str]:
        """Returns channel-specific organic connectors without structural section headers."""
        ...


class NarrativeDirector:
    """Central registry and dispatcher for narrative curator strategies."""

    def __init__(self) -> None:
        self._curators: Dict[str, INarrativeCurator] = {}

    def register(self, curator: INarrativeCurator) -> None:
        key = curator.channel.lower()
        self._curators[key] = curator

    def get_curator(self, channel: str | CanonicalChannel) -> INarrativeCurator:
        ch_str = channel.value.lower() if isinstance(channel, CanonicalChannel) else str(channel).lower()
        if ch_str in self._curators:
            return self._curators[ch_str]

        # Canonical aliases mapping
        if ch_str in ("terror", "horror", "scp", "moku"):
            for candidate in (ch_str, "moku", "horror"):
                if candidate in self._curators:
                    return self._curators[candidate]
        elif ch_str in ("drama", "soy_el_malo", "aelithia", "aita"):
            for candidate in (ch_str, "aelithia", "drama"):
                if candidate in self._curators:
                    return self._curators[candidate]

        # Fallback to horror, moku or first registered
        return self._curators.get("horror") or self._curators.get("moku") or next(iter(self._curators.values()))

    def build_short(self, channel: str | CanonicalChannel, topic: str, **kwargs: Any) -> str:
        curator = self.get_curator(channel)
        return curator.build_short_narrative(topic, **kwargs)

    def build_longform(
        self, channel: str | CanonicalChannel, topic: str, target_words: int = 1800, **kwargs: Any
    ) -> str:
        curator = self.get_curator(channel)
        return curator.build_longform_narrative(topic, target_words=target_words, **kwargs)


_DIRECTOR_INSTANCE: Optional[NarrativeDirector] = None


def get_narrative_director() -> NarrativeDirector:
    """Returns the singleton NarrativeDirector populated with standard curators."""
    global _DIRECTOR_INSTANCE
    if _DIRECTOR_INSTANCE is None:
        from src.curators.drama import DramaCurator
        from src.curators.horror import HorrorCurator

        director = NarrativeDirector()
        director.register(HorrorCurator(channel="horror"))
        director.register(HorrorCurator(channel="moku"))
        director.register(DramaCurator(channel="drama"))
        director.register(DramaCurator(channel="aelithia"))
        _DIRECTOR_INSTANCE = director
    return _DIRECTOR_INSTANCE

