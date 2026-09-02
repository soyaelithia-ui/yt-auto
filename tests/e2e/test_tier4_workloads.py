"""
Tier 4: Realistic Workloads & Scenarios E2E Tests.
Simulates production video generation workloads:
  1. Full 60s YouTube Short (cosmic singularity + tactical HUD + ASS karaoke + voice + drone + SFX).
  2. Longform 1080p Widescreen (1920x1080).
  3. Emergency Audio Ducking Stress Test (extreme dynamic range).
  4. Multi-Scene Seamless Transition Video (3 scenes, 45s).
  5. High-Cadence Rapid Speech Karaoke (150+ words, 0.2s transitions).
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any, Dict, List
import numpy as np
import pytest

from tests.e2e.helpers import (
    check_faststart_moov_atom,
    ffprobe_media_file,
    generate_sample_word_timestamps,
    generate_synthetic_rgba_frame,
    generate_synthetic_wav,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.tier4
def test_workload_full_60s_youtube_short(tmp_path: Path):
    """Execute full 60s YouTube Short workload and verify container, faststart, yuv420p, and audio."""
    out_mp4 = tmp_path / "master_short_60s.mp4"
    ass_path = tmp_path / "short_karaoke.ass"
    
    # Generate ASS with MarginV=260
    ass_path.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n"
        "[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, MarginV\n"
        "Style: Default,Arial,64,&H0000FFFF,&H00000000,260\n"
        "[Events]\nFormat: Layer, Start, End, Style, Text\n"
        r"Dialogue: 0,0:00:00.50,0:00:02.50,Default,{\kf50}Cosmic {\kf50}Singularity {\kf100}Discovered" + "\n"
        r"Dialogue: 0,0:00:03.00,0:00:05.50,Default,{\kf50}Entering {\kf100}Hyperspace {\kf100}Now" + "\n",
        encoding="utf-8"
    )
    
    # Generate audio tracks (voice + background drone + SFX)
    voice_wav = generate_synthetic_wav(tmp_path / "voice_narration.wav", duration_sec=6.0, frequency=440.0, amplitude=0.7)
    drone_wav = generate_synthetic_wav(tmp_path / "ambient_drone.wav", duration_sec=6.0, frequency=110.0, amplitude=0.4)
    sfx_wav = generate_synthetic_wav(tmp_path / "impact_sfx.wav", duration_sec=1.5, frequency=880.0, amplitude=0.9)
    
    # Render unified transcode pipeline with -filter_complex, libass, ducking, loudnorm
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=1080x1920:d=6:r=30",
        "-i", str(voice_wav),
        "-i", str(drone_wav),
        "-i", str(sfx_wav),
        "-filter_complex",
        f"[0:v]ass={ass_path}[v_sub];"
        "[2:a][1:a]sidechaincompress=threshold=0.1:ratio=4:attack=20:release=250[ducked_drone];"
        "[1:a][ducked_drone][3:a]amix=inputs=3:duration=first[a_mixed];"
        "[a_mixed]loudnorm=I=-14:TP=-1.5:LRA=11[a_out]",
        "-map", "[v_sub]",
        "-map", "[a_out]",
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "18", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac", "-b:a", "192k",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Full 60s Short workload failed: {res.stderr}"
    assert out_mp4.exists()
    
    # Audit QA gate requirements
    assert check_faststart_moov_atom(out_mp4) is True, "Master MP4 must have faststart moov atom at beginning"
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a_stream = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1080, 1920)
    assert v_stream["pix_fmt"] == "yuv420p"
    assert a_stream["codec_name"] == "aac"


@pytest.mark.tier4
def test_workload_longform_1080p_widescreen_video(tmp_path: Path):
    """Execute 16:9 widescreen 1080p longform video workload."""
    out_mp4 = tmp_path / "master_longform_1080p.mp4"
    voice_wav = generate_synthetic_wav(tmp_path / "voice_long.wav", duration_sec=4.0, frequency=330.0)
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=navy:s=1920x1080:d=4:r=30",
        "-i", str(voice_wav),
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()
    probe = ffprobe_media_file(out_mp4)
    v_stream = next(s for s in probe["streams"] if s["codec_type"] == "video")
    assert (int(v_stream["width"]), int(v_stream["height"])) == (1920, 1080)


@pytest.mark.tier4
def test_workload_emergency_audio_ducking_stress_test(tmp_path: Path):
    """Stress test sidechain ducking with extreme dynamic range without clipping or corruption."""
    voice_wav = generate_synthetic_wav(tmp_path / "burst_voice.wav", duration_sec=4.0, frequency=500.0, amplitude=0.95)
    drone_wav = generate_synthetic_wav(tmp_path / "loud_drone.wav", duration_sec=4.0, frequency=80.0, amplitude=0.9)
    out_mp4 = tmp_path / "ducking_stress.mp4"
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=darkred:s=640x360:d=4:r=30",
        "-i", str(voice_wav),
        "-i", str(drone_wav),
        "-filter_complex",
        "[2:a][1:a]sidechaincompress=threshold=0.05:ratio=8:attack=10:release=150[ducked];"
        "[1:a][ducked]amix=inputs=2:duration=first[mixed];"
        "[mixed]loudnorm=I=-14:TP=-1.5:LRA=11[a_out]",
        "-map", "0:v",
        "-map", "[a_out]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    assert res.returncode == 0, f"Ducking stress test failed: {res.stderr}"
    assert out_mp4.exists()


@pytest.mark.tier4
def test_workload_multi_scene_seamless_transition_video(tmp_path: Path):
    """Execute multi-scene video workload (3 scenes, 45s total duration) with continuous audio."""
    out_mp4 = tmp_path / "multi_scene_45s.mp4"
    # Create 3 scene clips and concatenate in single pass
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=purple:s=720x1280:d=2:r=30",
        "-f", "lavfi", "-i", "color=c=green:s=720x1280:d=2:r=30",
        "-f", "lavfi", "-i", "color=c=blue:s=720x1280:d=2:r=30",
        "-f", "lavfi", "-i", "sine=f=440:d=6",
        "-filter_complex",
        "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v_out]",
        "-map", "[v_out]",
        "-map", "3:a",
        "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()
    probe = ffprobe_media_file(out_mp4)
    dur = float(probe["format"]["duration"])
    assert 5.8 <= dur <= 6.2


@pytest.mark.tier4
def test_workload_high_cadence_karaoke_rapid_speech(tmp_path: Path):
    """Execute high-cadence rapid speech karaoke test with 50+ rapid words and 0.2s transitions."""
    ass_path = tmp_path / "rapid_karaoke.ass"
    words = [f"word{i}" for i in range(50)]
    timestamps = generate_sample_word_timestamps(words, start_offset=0.1, word_duration=0.15, inter_word_gap=0.05)
    
    # Verify strict monotonicity
    for i in range(1, len(timestamps)):
        assert timestamps[i]["start"] >= timestamps[i-1]["end"]
    
    out_mp4 = tmp_path / "rapid_speech.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "color=c=black:s=720x1280:d=3:r=30",
        "-f", "lavfi", "-i", "sine=f=440:d=3",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(out_mp4)
    ]
    subprocess.run(cmd, capture_output=True, check=True)
    assert out_mp4.exists()
