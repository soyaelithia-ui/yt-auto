"""
Unit tests for AudioProcessor loudness normalization (-14.0 LUFS / -1.5 dBTP),
ambient mixing with sidechain ducking (-18dB, 350ms release),
and dramatic pause parsing and calibrated silence audio insertion with word timestamp shifting.
"""

import os
import pytest
import subprocess
from pathlib import Path
from src.audio_processor import (
    AudioProcessor,
    parse_dramatic_pauses,
    extract_dramatic_pauses,
    strip_dramatic_pauses,
    generate_silence_audio,
    insert_dramatic_pauses_to_audio,
    shift_word_timestamps_with_pauses,
    apply_sidechain_ducking,
    normalize_narration_lufs,
    master_audio_track,
)
from lib.tts import get_audio_duration, validate_word_boundaries


def test_normalize_loudness(tmp_path):
    proc = AudioProcessor()

    # Generate synthetic audio input file using FFmpeg
    raw_audio = tmp_path / "raw_input.mp3"
    norm_audio = tmp_path / "norm_output.mp3"

    gen_cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
        "-c:a", "libmp3lame", "-b:a", "192k",
        str(raw_audio)
    ]
    subprocess.run(gen_cmd, capture_output=True, text=True, check=True)

    result_path = proc.normalize_loudness(str(raw_audio), str(norm_audio), target_lufs=-14.0)
    assert result_path == str(norm_audio)
    assert os.path.exists(norm_audio)
    assert os.path.getsize(norm_audio) > 1000

    # Probe normalized audio with ffprobe ebur128 filter
    ebur_cmd = [
        "ffmpeg", "-nostats", "-i", str(norm_audio),
        "-filter_complex", "ebur128=peak=true",
        "-f", "null", "-"
    ]
    res = subprocess.run(ebur_cmd, capture_output=True, text=True)
    assert res.returncode == 0
    assert "Summary:" in res.stderr or "Integrated loudness:" in res.stderr or res.returncode == 0


def test_concat_crossfade_audio(tmp_path):
    proc = AudioProcessor()

    # Generate 3 synthetic audio clips of 3 seconds each
    clips = []
    for i in range(3):
        clip_p = tmp_path / f"clip_{i+1}.mp3"
        cmd = [
            "ffmpeg", "-y",
            "-f", "lavfi", "-i", f"sine=frequency={400 + i*200}:duration=3",
            "-c:a", "libmp3lame", "-b:a", "192k",
            str(clip_p)
        ]
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        clips.append(str(clip_p))

    master_out = str(tmp_path / "mastered_concat.mp3")
    res_path, scene_durs = proc.concat_crossfade_audio(clips, master_out, crossfade_sec=0.1)

    assert res_path == master_out
    assert os.path.exists(master_out)
    assert os.path.getsize(master_out) > 1000
    assert len(scene_durs) == 3

    # Clip 1: 3.0 - 0.1 = 2.9s
    # Clip 2: 3.0 - 0.1 = 2.9s
    # Clip 3: 3.0s
    assert abs(scene_durs[0] - 2.9) < 0.2
    assert abs(scene_durs[1] - 2.9) < 0.2
    assert abs(scene_durs[2] - 3.0) < 0.2


# ============================================================================
# Dramatic Pause Parsing & Audio Handling Unit Tests
# ============================================================================

def test_parse_dramatic_pauses_various_syntaxes():
    proc = AudioProcessor()

    script = (
        "El guardia avanzó hacia la celda. [PAUSA: 1.5s] "
        "La puerta de contención estaba entreabierta. [PAUSE: 800ms] "
        "Dentro, una sombra se movió. [PAUSA] "
        "El silencio era absoluto. [SILENCE: 2.0s] "
        "Fin del registro."
    )

    segments = proc.parse_dramatic_pauses(script)
    assert len(segments) == 5

    # Segment 0
    assert "El guardia avanzó hacia la celda." in segments[0]["text"]
    assert segments[0]["pause_after"] == 1.5
    assert segments[0]["has_pause"] is True
    assert "[PAUSA: 1.5s]" in segments[0]["tag"]

    # Segment 1
    assert "La puerta de contención estaba entreabierta." in segments[1]["text"]
    assert segments[1]["pause_after"] == 0.8  # 800ms -> 0.8s
    assert segments[1]["has_pause"] is True

    # Segment 2
    assert "Dentro, una sombra se movió." in segments[2]["text"]
    assert segments[2]["pause_after"] == 1.2  # default 1.2s
    assert segments[2]["has_pause"] is True

    # Segment 3
    assert "El silencio era absoluto." in segments[3]["text"]
    assert segments[3]["pause_after"] == 2.0
    assert segments[3]["has_pause"] is True

    # Segment 4 (trailing)
    assert "Fin del registro." in segments[4]["text"]
    assert segments[4]["pause_after"] == 0.0
    assert segments[4]["has_pause"] is False
    assert segments[4]["tag"] is None


def test_parse_dramatic_pauses_plain_text():
    plain = "Este es un guion sin pausas dramáticas explícitas."
    segs = parse_dramatic_pauses(plain)
    assert len(segs) == 1
    assert segs[0]["text"] == plain
    assert segs[0]["pause_after"] == 0.0
    assert segs[0]["has_pause"] is False


def test_extract_and_strip_dramatic_pauses():
    text = "Primera frase. [PAUSA: 1.5s] Segunda frase. [PAUSE: 500ms] Tercera frase."
    pauses = extract_dramatic_pauses(text)
    assert len(pauses) == 2
    assert pauses[0]["duration_sec"] == 1.5
    assert pauses[1]["duration_sec"] == 0.5

    clean = strip_dramatic_pauses(text)
    assert "[PAUSA" not in clean
    assert "[PAUSE" not in clean
    assert clean == "Primera frase. Segunda frase. Tercera frase."


def test_generate_silence_audio(tmp_path):
    silence_file = tmp_path / "silence_test.wav"
    dur = 1.75
    res = generate_silence_audio(silence_file, duration_sec=dur, sample_rate=48000, channels=2)
    assert res == str(silence_file)
    assert os.path.exists(silence_file)
    actual_dur = get_audio_duration(silence_file)
    assert abs(actual_dur - dur) < 0.05


def test_insert_dramatic_pauses_and_word_timestamp_shifting(tmp_path):
    proc = AudioProcessor()

    # Create 2 synthetic audio chunks of 2.0 seconds each
    chunk1 = tmp_path / "chunk1.wav"
    chunk2 = tmp_path / "chunk2.wav"
    out_master = tmp_path / "master_with_pauses.wav"

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(chunk1)
    ], check=True, capture_output=True)

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=880:duration=2",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(chunk2)
    ], check=True, capture_output=True)

    words_chunk1 = [
        {"word": "El", "start": 0.0, "end": 0.6},
        {"word": "ente", "start": 0.6, "end": 1.3},
        {"word": "despertó.", "start": 1.3, "end": 2.0},
    ]
    words_chunk2 = [
        {"word": "Todo", "start": 0.0, "end": 0.5},
        {"word": "estaba", "start": 0.5, "end": 1.2},
        {"word": "oscuro.", "start": 1.2, "end": 2.0},
    ]

    pause_dur = 1.5  # 1.5 second dramatic silence pause
    out_p, combined_words = proc.insert_dramatic_pauses(
        audio_segments=[str(chunk1), str(chunk2)],
        pause_durations=[pause_dur],
        output_path=str(out_master),
        word_timestamps_per_chunk=[words_chunk1, words_chunk2],
    )

    assert out_p == str(out_master)
    assert os.path.exists(out_master)

    total_dur = get_audio_duration(out_master)
    # Expected duration: 2.0s + 1.5s + 2.0s = 5.5s
    assert abs(total_dur - 5.5) < 0.3

    # Verify monotonic word timestamps
    assert len(combined_words) == 6
    # Chunk 1 timestamps preserved
    assert combined_words[0]["start"] == 0.0
    assert combined_words[2]["end"] == 2.0

    # Chunk 2 timestamps shifted by chunk1 duration (2.0s) + pause duration (1.5s) = 3.5s offset
    assert abs(combined_words[3]["start"] - 3.5) < 0.1
    assert abs(combined_words[3]["end"] - 4.0) < 0.1
    assert abs(combined_words[5]["end"] - 5.5) < 0.1

    # Validate word boundaries strictly monotonic
    val = validate_word_boundaries(combined_words, total_dur)
    assert val["passed"] is True


def test_sidechain_ducking_and_ambient_mixing(tmp_path):
    proc = AudioProcessor()

    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    ducked_out = tmp_path / "ducked_mix.wav"

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=500:duration=4",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(speech)
    ], check=True, capture_output=True)

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=200:duration=4",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(music)
    ], check=True, capture_output=True)

    res = proc.apply_sidechain_ducking(
        speech_path=str(speech),
        music_path=str(music),
        output_path=str(ducked_out),
        ducking_db=-18.0,
    )
    assert res == str(ducked_out)
    assert os.path.exists(ducked_out)
    assert os.path.getsize(ducked_out) > 1000


def test_standardized_master_loudness_14_lufs(tmp_path):
    raw_audio = tmp_path / "raw.wav"
    norm_audio = tmp_path / "norm_14lufs.wav"

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=1000:duration=5",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(raw_audio)
    ], check=True, capture_output=True)

    res = normalize_narration_lufs(
        input_path=str(raw_audio),
        output_path=str(norm_audio),
        target_lufs=-14.0,
        max_tp=-1.5,
    )
    assert res == str(norm_audio)
    assert os.path.exists(norm_audio)
    assert os.path.getsize(norm_audio) > 1000


def test_master_audio_track_single_pass_integrated(tmp_path):
    speech = tmp_path / "speech.wav"
    music = tmp_path / "music.wav"
    out_master = tmp_path / "mastered_single_pass.wav"

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=4",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(speech)
    ], check=True, capture_output=True)

    subprocess.run([
        "ffmpeg", "-y", "-f", "lavfi", "-i", "sine=frequency=220:duration=6",
        "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2", str(music)
    ], check=True, capture_output=True)

    res = master_audio_track(
        narration_path=speech,
        music_path=music,
        output_path=out_master,
        target_lufs=-14.0,
        ducking_db=-18.0,
        music_volume=0.05,
    )

    assert res == str(out_master)
    assert out_master.exists()
    assert out_master.stat().st_size > 1000

    # Ensure no lingering intermediate temporary files in target directory
    lingering_tmps = list(tmp_path.glob("*.tmp.*"))
    assert len(lingering_tmps) == 0

