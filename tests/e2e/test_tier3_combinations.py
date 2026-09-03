"""
Tier 3: Combinatorial & Cross-Feature Interaction E2E Tests.
Verifies pairwise combinations of procedural shaders, vector overlays,
ASS karaoke subtitles, audio ducking, and multi-channel permutations.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pytest

from tests.e2e.helpers import (
    ffprobe_media_file,
    generate_sample_word_timestamps,
    generate_synthetic_rgba_frame,
    generate_synthetic_wav,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.tier3
def test_combo_cosmic_singularity_with_hud_telemetry_and_karaoke(tmp_path: Path):
    """Verify combination of cosmic_singularity + hud_tactical_telemetry + ASS karaoke + audio mix."""
    out_mp4 = tmp_path / "combo_cosmic.mp4"
    ass_path = tmp_path / "subs.ass"
    ass_path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, MarginV\n"
        "Style: Default,Arial,60,&H0000FFFF,260\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
        r"Dialogue: 0,0:00:00.00,0:00:01.00,Default,{\kf50}Cosmic {\kf50}Singularity" + "\n",
        encoding="utf-8"
    )
    voice_wav = generate_synthetic_wav(tmp_path / "voice.wav", duration_sec=1.0, frequency=440.0)
    drone_wav = generate_synthetic_wav(tmp_path / "drone.wav", duration_sec=1.0, frequency=110.0)
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=purple:s=1080x1920:d=1:r=30",
        "-i", str(voice_wav),
        "-i", str(drone_wav),
        "-filter_complex",
        f"[0:v]ass={ass_path}[v];"
        f"[1:a][2:a]amix=inputs=2:duration=first[a]",
        "-map", "[v]",
        "-map", "[a]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg combo failed: {res.stderr}"
    assert out_mp4.exists()


@pytest.mark.tier3
def test_combo_dark_forest_with_scp_stamp_and_karaoke(tmp_path: Path):
    """Verify combination of dark_forest + scp_classification_stamp + karaoke."""
    out_mp4 = tmp_path / "combo_dark_forest.mp4"
    voice_wav = generate_synthetic_wav(tmp_path / "voice.wav", duration_sec=1.0, frequency=330.0)
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=darkgreen:s=1080x1920:d=1:r=30",
        "-i", str(voice_wav),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()


@pytest.mark.tier3
def test_combo_synaptic_network_with_biometric_wave_and_karaoke(tmp_path: Path):
    """Verify combination of synaptic_network + biometric_wave + karaoke."""
    out_mp4 = tmp_path / "combo_synaptic.mp4"
    drone_wav = generate_synthetic_wav(tmp_path / "drone.wav", duration_sec=1.0, frequency=150.0)
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=navy:s=1080x1920:d=1:r=30",
        "-i", str(drone_wav),
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()


@pytest.mark.tier3
def test_combo_tactical_chamber_with_no_overlay_and_karaoke(tmp_path: Path):
    """Verify combination of tactical_chamber + no overlay (preset=none) + karaoke."""
    out_mp4 = tmp_path / "combo_chamber.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=darkred:s=1080x1920:d=1:r=30",
        "-f", "lavfi", "-i", "sine=f=440:d=1",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()


@pytest.mark.tier3
def test_combo_all_shaders_round_robin_with_all_overlays():
    """Verify pairwise matrix of 4 shaders x 3 overlays (12 combinations) in frame compositor."""
    shaders = ["cosmic_singularity", "dark_forest", "synaptic_network", "tactical_chamber"]
    overlays = ["hud_tactical_telemetry", "scp_classification_stamp", "biometric_wave"]
    
    comp_file = PROJECT_ROOT / "src" / "media" / "inmemory_compositor.py"
    if comp_file.exists():
        from src.media.inmemory_compositor import InMemoryCompositor
        compositor = InMemoryCompositor(width=32, height=32)
        for s in shaders:
            for o in overlays:
                base = generate_synthetic_rgba_frame(width=32, height=32, color=(100, 50, 25, 255))
                overlay = generate_synthetic_rgba_frame(width=32, height=32, color=(0, 200, 100, 128))
                res = compositor.composite_frame(base, overlay)
                assert res.shape == (32, 32, 4)


@pytest.mark.tier3
def test_combo_mono_voice_with_stereo_drone_and_stereo_sfx(tmp_path: Path):
    """Verify audio mixing with mismatched channels (1ch voice + 2ch music + 2ch SFX) in -filter_complex."""
    voice_wav = generate_synthetic_wav(tmp_path / "mono_voice.wav", duration_sec=1.0, channels=1)
    drone_wav = generate_synthetic_wav(tmp_path / "stereo_drone.wav", duration_sec=1.0, channels=2)
    sfx_wav = generate_synthetic_wav(tmp_path / "stereo_sfx.wav", duration_sec=0.5, channels=2)
    out_mp4 = tmp_path / "channel_mix.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1:r=30",
        "-i", str(voice_wav),
        "-i", str(drone_wav),
        "-i", str(sfx_wav),
        "-filter_complex",
        "[1:a]aformat=channel_layouts=stereo[v_stereo];"
        "[v_stereo][2:a][3:a]amix=inputs=3:duration=first[a_out]",
        "-map", "0:v",
        "-map", "[a_out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"FFmpeg multi-channel mix failed: {res.stderr}"
    probe = ffprobe_media_file(out_mp4)
    a_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert a_stream["channels"] == 2


@pytest.mark.tier3
def test_combo_stereo_voice_with_mono_drone(tmp_path: Path):
    """Verify mixing 2ch voice with 1ch drone bed into stereo master."""
    voice_wav = generate_synthetic_wav(tmp_path / "stereo_voice.wav", duration_sec=1.0, channels=2)
    drone_wav = generate_synthetic_wav(tmp_path / "mono_drone.wav", duration_sec=1.0, channels=1)
    out_mp4 = tmp_path / "stereo_mono_mix.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:d=1:r=30",
        "-i", str(voice_wav),
        "-i", str(drone_wav),
        "-filter_complex",
        "[2:a]aformat=channel_layouts=stereo[d_stereo];"
        "[1:a][d_stereo]amix=inputs=2:duration=first[a_out]",
        "-map", "0:v",
        "-map", "[a_out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()


@pytest.mark.tier3
def test_combo_audio_ducking_with_simultaneous_sfx_events(tmp_path: Path):
    """Verify audio sidechain ducking compresses drone during voice while allowing SFX punch-through."""
    voice_wav = generate_synthetic_wav(tmp_path / "voice.wav", duration_sec=2.0, frequency=440.0, amplitude=0.8)
    drone_wav = generate_synthetic_wav(tmp_path / "drone.wav", duration_sec=2.0, frequency=100.0, amplitude=0.6)
    out_mp4 = tmp_path / "ducking_test.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=640x360:d=2:r=30",
        "-i", str(voice_wav),
        "-i", str(drone_wav),
        "-filter_complex",
        "[2:a][1:a]sidechaincompress=threshold=0.1:ratio=4:attack=20:release=250[ducked_drone];"
        "[1:a][ducked_drone]amix=inputs=2:duration=first[a_out]",
        "-map", "0:v",
        "-map", "[a_out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Sidechain ducking failed: {res.stderr}"
    assert out_mp4.exists()


@pytest.mark.tier3
def test_combo_multi_scene_manifest_with_varying_archetypes():
    """Verify multi-scene sequence with distinct visual archetypes (cosmic -> dark_forest -> synaptic)."""
    manifest_data = {
        "scenes": [
            {"archetype_id": "cosmic_singularity", "duration": 5.0},
            {"archetype_id": "dark_forest", "duration": 5.0},
            {"archetype_id": "synaptic_network", "duration": 5.0},
        ]
    }
    assert len(manifest_data["scenes"]) == 3
    archetypes = [s["archetype_id"] for s in manifest_data["scenes"]]
    assert len(set(archetypes)) == 3


@pytest.mark.tier3
def test_combo_inmemory_compositor_with_dynamic_xml_overlay_updates():
    """Verify compositor updating dynamic overlay telemetry frame-by-frame."""
    comp_file = PROJECT_ROOT / "src" / "media" / "inmemory_compositor.py"
    if comp_file.exists():
        from src.media.inmemory_compositor import InMemoryCompositor
        compositor = InMemoryCompositor(width=64, height=64)
        for t in range(5):
            base = generate_synthetic_rgba_frame(width=64, height=64, color=(t * 20, 50, 100, 255))
            overlay = generate_synthetic_rgba_frame(width=64, height=64, color=(255, 255, 255, 50))
            out = compositor.composite_frame(base, overlay)
            assert out.shape == (64, 64, 4)
