"""
Unit test suite for CanonicalChannel.SCIFI, alias resolution, safe enum access,
story type validation, and CLI injection prevention in channels and lanes (Phase 1).
"""
import pytest

from src.core.domain import CanonicalChannel, canonical_channel
from src.core.lanes import (
    ALLOWED_STORY_TYPES,
    LaneProfile,
    lanes_for_channel,
    parse_lane,
    resolve_lane_for_run,
    resolve_voice_profile_for_lane,
)


class TestCanonicalChannelAndLanesSecurity:
    """Tests for CanonicalChannel.SCIFI, safe enum access, and CLI injection prevention."""

    def test_canonical_channel_scifi_enum_and_aliases(self):
        """CanonicalChannel.SCIFI is registered and alias mappings resolve correctly."""
        assert hasattr(CanonicalChannel, "SCIFI")
        assert CanonicalChannel.SCIFI.value == "scifi"

        assert canonical_channel("scifi") == CanonicalChannel.SCIFI
        assert canonical_channel("singularidad_scifi") == CanonicalChannel.SCIFI
        assert canonical_channel("singularidad-scifi") == CanonicalChannel.SCIFI

    def test_allowed_story_types_includes_scifi(self):
        """ALLOWED_STORY_TYPES in src/core/lanes.py includes 'scifi'."""
        assert "scifi" in ALLOWED_STORY_TYPES

    def test_safe_enum_access_with_string_and_enum_channel(self):
        """
        lanes_for_channel and resolve_voice_profile_for_lane must safely handle
        both Enum instances and raw string channel representations without AttributeError.
        """
        # Testing safe channel extraction with raw string
        lanes = lanes_for_channel("moku")
        assert isinstance(lanes, tuple)
        assert len(lanes) > 0

        # Testing with CanonicalChannel enum
        lanes_enum = lanes_for_channel(CanonicalChannel.MOKU)
        assert isinstance(lanes_enum, tuple)
        assert len(lanes_enum) > 0

        # Safe voice profile resolution with string and enum
        vp_str = resolve_voice_profile_for_lane(channel="moku")
        assert vp_str["profile_name"] == "moku_terror"

        vp_enum = resolve_voice_profile_for_lane(channel=CanonicalChannel.MOKU)
        assert vp_enum["profile_name"] == "moku_terror"

    def test_parse_lane_with_scifi_story_type(self):
        """parse_lane accepts lane definition with 'story_type': 'scifi' without ValueError."""
        doc = {
            "id": "scifi-unit-test-shorts",
            "channel": "scifi",
            "story_type": "scifi",
            "orientation": "vertical",
            "duration": {"min_sec": 60, "target_sec": 120, "max_sec": 180},
            "words": {"min": 160, "max": 340, "recondense_max": 300},
            "template": "shorts_scifi",
            "voice_rate": "+0%",
            "cadence": {"min_gap_seconds": 300},
            "sources": {
                "kind": "reddit",
                "subreddits": ["scifi", "IsaacArthur"],
            },
        }
        lane = parse_lane(doc)
        assert lane.id == "scifi-unit-test-shorts"
        assert lane.story_type == "scifi"

    @pytest.mark.parametrize(
        "malicious_lane",
        [
            "moku-scp-shorts; rm -rf /",
            "moku-scp-shorts && echo pwned",
            "moku-scp-shorts | cat /etc/passwd",
            "`whoami`",
            "$(id)",
            "moku-scp-shorts > /dev/null",
            "../etc/passwd",
        ],
    )
    def test_cli_injection_in_lane_id_raises_value_error(self, malicious_lane):
        """
        Threat matrix: Injection of shell metacharacters or path traversal in lane_id
        must be rejected with ValueError.
        """
        with pytest.raises(ValueError) as exc_info:
            resolve_lane_for_run("moku", malicious_lane)
        err_msg = str(exc_info.value).lower()
        assert any(term in err_msg for term in ("inválido", "invalido", "sospechoso", "no existe", "invalid"))

    @pytest.mark.parametrize(
        "malicious_channel",
        [
            "moku; id",
            "moku && cat /etc/passwd",
            "moku | whoami",
            "`touch /tmp/evil`",
        ],
    )
    def test_cli_injection_in_channel_raises_value_error(self, malicious_channel):
        """
        Threat matrix: Injection of shell metacharacters in channel must be rejected with ValueError.
        """
        with pytest.raises(ValueError):
            resolve_lane_for_run(malicious_channel, "moku-scp-shorts")


class TestPhase2MultiChannelLanesAndNarratives:
    """Tests for 6-lane configuration parity, voice profile, narratives, and curation."""

    def test_six_lanes_configuration_parity(self):
        """config/lanes.json defines active lanes across Moku and Aelithia, with SciFi disabled."""
        from src.core.lanes import load_lanes

        active_lanes = load_lanes()
        active_ids = {lane.id for lane in active_lanes}
        expected_active_ids = {
            "moku-scp-shorts",
            "moku-horror-long",
            "aelithia-drama-shorts",
            "aelithia-aita-long",
        }
        assert active_ids == expected_active_ids, f"Expected {expected_active_ids}, got {active_ids}"
        assert len(active_lanes) == 4

        # Verify Sci-Fi lanes are defined but disabled
        all_lanes = load_lanes(include_disabled=True)
        all_ids = {lane.id for lane in all_lanes}
        expected_all_ids = {
            "moku-scp-shorts",
            "moku-horror-long",
            "aelithia-drama-shorts",
            "aelithia-aita-long",
            "scifi-singularity-shorts",
            "scifi-singularity-long",
        }
        assert all_ids == expected_all_ids, f"Expected {expected_all_ids}, got {all_ids}"
        assert len(all_lanes) == 6

        # Check orientation breakdown of active lanes: 2 vertical (Shorts), 2 horizontal (Longform)
        verticals = [l for l in active_lanes if l.orientation == "vertical"]
        horizontals = [l for l in active_lanes if l.orientation == "horizontal"]
        assert len(verticals) == 2
        assert len(horizontals) == 2

    def test_scifi_voice_profile_registered(self):
        """scifi_documentary_es voice profile is registered in config/voice_profiles.json."""
        import json
        from pathlib import Path
        from src.config import BASE_DIR

        profiles_path = BASE_DIR / "config" / "voice_profiles.json"
        with open(profiles_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        profiles = data.get("editorial_profiles", {})
        assert "scifi_documentary_es" in profiles
        prof = profiles["scifi_documentary_es"]
        approved = prof.get("approved_voices", [])
        assert len(approved) >= 1
        voice_ids = [v["id"] for v in approved]
        assert "es-ES-AlvaroNeural" in voice_ids or "es-MX-JorgeNeural" in voice_ids

    def test_scifi_voice_profile_lookup_via_lane(self):
        """resolve_voice_profile_for_lane resolves scifi_documentary_es for SciFi lanes."""
        vp = resolve_voice_profile_for_lane(lane="scifi-singularity-shorts", channel="scifi")
        assert vp["profile_name"] == "scifi_documentary_es"

    def test_scifi_narrative_builders_and_dispatch(self):
        """SciFi short and longform narrative builders generate substantive lore and dispatch cleanly."""
        from src.templates.narratives import (
            build_channel_narrative,
            build_scifi_longform_narrative,
            build_scifi_short_narrative,
        )

        short_text = build_scifi_short_narrative("Horizonte de Sucesos", channel="scifi")
        assert len(short_text.split()) >= 60
        assert "Singularidad" in short_text or "astro" in short_text.lower() or "horizonte" in short_text.lower() or "espacio" in short_text.lower()

        long_text = build_scifi_longform_narrative("Paradoja de Fermi", channel="scifi", target_duration_minutes=10.0)
        assert len(long_text.split()) >= 300

        # Test routing dispatch in build_channel_narrative
        dispatched_short = build_channel_narrative("Agujero Negro", channel="scifi", video_mode="short")
        assert len(dispatched_short.split()) >= 60

        dispatched_long = build_channel_narrative("Paradoja de Fermi", channel="scifi", video_mode="longform")
        assert len(dispatched_long.split()) >= 300

    def test_lane_curation_configs_registered_for_all_lanes(self):
        """src/agents/script_curator.py defines curation profiles for all 6 production lanes."""
        from src.agents.script_curator import (
            LANE_CURATION_CONFIGS,
            CinematicScriptCuratorAgent,
        )

        for required_lane in (
            "moku-scp-shorts",
            "moku-horror-long",
            "aelithia-drama-shorts",
            "aelithia-aita-long",
            "scifi-singularity-shorts",
            "scifi-singularity-long",
        ):
            assert required_lane in LANE_CURATION_CONFIGS, f"Missing curation config for {required_lane}"
            cfg = LANE_CURATION_CONFIGS[required_lane]
            assert "acts" in cfg
            assert len(cfg["acts"]) >= 3

        agent = CinematicScriptCuratorAgent()
        resolved_id, _ = agent._resolve_lane_config("scifi-singularity-shorts", "short")
        assert resolved_id == "scifi-singularity-shorts"

        resolved_long, _ = agent._resolve_lane_config("scifi-singularity-long", "longform")
        assert resolved_long == "scifi-singularity-long"

        resolved_drama, _ = agent._resolve_lane_config("aelithia-drama-shorts", "short")
        assert resolved_drama == "aelithia-drama-shorts"

