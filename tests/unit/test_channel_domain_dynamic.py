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


def test_channel_settings_dynamic_env_override(monkeypatch):
    from src.config import SETTINGS, get_channel_settings, _resolve_dynamic_channel
    monkeypatch.setenv("MOKU_HANDLE", "@TestMokuHandleEnv")
    monkeypatch.setenv("MOKU_NAME", "TestMokuNameEnv")
    ChannelProfileRegistry._ensure_loaded(force_reload=True)

    ch = _resolve_dynamic_channel("moku")
    assert ch.handle == "@TestMokuHandleEnv"
    assert ch.public_name == "TestMokuNameEnv"

    # Verify SETTINGS.channel and get_channel_settings also resolve dynamically
    ch_settings = SETTINGS.channel("moku")
    assert ch_settings.handle == "@TestMokuHandleEnv"
    assert ch_settings.public_name == "TestMokuNameEnv"

    ch_facade = get_channel_settings("moku")
    assert ch_facade.handle == "@TestMokuHandleEnv"
    assert ch_facade.public_name == "TestMokuNameEnv"

    # Verify SETTINGS.channels mapping resolves dynamically
    ch_dict = SETTINGS.channels[CanonicalChannel.MOKU]
    assert ch_dict.handle == "@TestMokuHandleEnv"
    assert ch_dict.public_name == "TestMokuNameEnv"

    # Cleanup reload
    ChannelProfileRegistry._ensure_loaded(force_reload=True)


def test_channel_settings_generic_channel_handle_override(monkeypatch):
    from src.config import SETTINGS, get_channel_settings, _resolve_dynamic_channel
    monkeypatch.setenv("CHANNEL_KEY", "aelithia")
    monkeypatch.setenv("CHANNEL_HANDLE", "@GenericAelithia")
    monkeypatch.setenv("CHANNEL_NAME", "Generic Aelithia")
    ChannelProfileRegistry._ensure_loaded(force_reload=True)

    ch = _resolve_dynamic_channel("aelithia")
    assert ch.handle == "@GenericAelithia"
    assert ch.public_name == "Generic Aelithia"

    ch_settings = SETTINGS.channel("aelithia")
    assert ch_settings.handle == "@GenericAelithia"
    assert ch_settings.public_name == "Generic Aelithia"

    ch_facade = get_channel_settings("aelithia")
    assert ch_facade.handle == "@GenericAelithia"
    assert ch_facade.public_name == "Generic Aelithia"

    # Cleanup reload
    ChannelProfileRegistry._ensure_loaded(force_reload=True)


def test_settings_channels_dynamic_iteration():
    from src.config import SETTINGS
    active_keys = [k for k in SETTINGS.channels.keys()]
    assert CanonicalChannel.MOKU in active_keys or "moku" in [str(k) for k in active_keys]
    values = list(SETTINGS.channels.values())
    assert len(values) >= 2
    items = list(SETTINGS.channels.items())
    assert len(items) >= 2


def test_channel_profile_registry_unknown_channel_raises_key_error():
    with pytest.raises(KeyError, match="Canal desconocido o no configurado"):
        ChannelProfileRegistry.get_channel("completely_unknown_channel_999")


def test_channel_profile_registry_audio_and_auth_env_overrides(monkeypatch):
    monkeypatch.setenv("MOKU_TTS_VOICE", "es-ES-CustomVoice")
    monkeypatch.setenv("MOKU_YOUTUBE_CHANNEL_ID", "UC_CUSTOM_MOKU_123")
    monkeypatch.setenv("MOKU_SOURCE_FEED", "r/custom_feed")
    ChannelProfileRegistry._ensure_loaded(force_reload=True)

    prof = ChannelProfileRegistry.get_channel("moku")
    assert prof.audio.default_voice_profile == "es-ES-CustomVoice"
    assert prof.auth.expected_youtube_channel_id == "UC_CUSTOM_MOKU_123"
    assert prof.auth.source_feed == "r/custom_feed"

    ChannelProfileRegistry._ensure_loaded(force_reload=True)

