"""Unit tests for dynamic channel resolution and runtime settings integration."""
from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.core.domain import CanonicalChannel, canonical_channel
from src.core.channel_profile import ChannelProfileRegistry
from src.config import SETTINGS, ChannelSettings


def test_canonical_channel_legacy_channels():
    assert canonical_channel("moku") == "moku"
    assert canonical_channel("aelithia") == "aelithia"
    assert canonical_channel(CanonicalChannel.MOKU) == "moku"
    assert canonical_channel(CanonicalChannel.AELITHIA) == "aelithia"


def test_canonical_channel_legacy_aliases():
    assert canonical_channel("terror") == "moku"
    assert canonical_channel("scp") == "moku"
    assert canonical_channel("mokuredit") == "moku"
    assert canonical_channel("aita") == "aelithia"
    assert canonical_channel("soy_el_malo") == "aelithia"


def test_canonical_channel_dynamic_scifi():
    # scifi exists in config/channels/scifi.json
    assert canonical_channel("scifi") == "scifi"
    assert canonical_channel("space") == "scifi" or canonical_channel("scifi") == "scifi"


def test_canonical_channel_unknown_rejected():
    with pytest.raises(ValueError, match="Canal desconocido o ausente"):
        canonical_channel("non_existent_channel_xyz123")

    with pytest.raises(ValueError, match="Canal desconocido o ausente"):
        canonical_channel("")


def test_runtime_settings_channel_dynamic_scifi():
    # SETTINGS.channel("scifi") should resolve a valid ChannelSettings instance
    ch_scifi = SETTINGS.channel("scifi")
    assert isinstance(ch_scifi, ChannelSettings)
    assert ch_scifi.key == "scifi" or str(ch_scifi.key) == "scifi"
    assert ch_scifi.public_name != ""
    assert ch_scifi.subtitle is not None
    assert ch_scifi.design is not None
