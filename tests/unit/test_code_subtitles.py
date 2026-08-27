"""
tests/unit/test_code_subtitles.py - Unit tests for Programmatic Subtitle Engine (CodeSubtitleDrawer).
"""
from pathlib import Path
from PIL import Image

from src.media.subtitles import (
    CodeSubtitleDrawer,
    SubtitleCue,
    SubtitleWord,
    SubtitleTheme,
    THEME_PRESETS,
    apply_code_subtitles_to_video,
)


def test_parse_word_timestamps_into_cues():
    words = [
        {"word": "El", "start": 0.0, "end": 0.3},
        {"word": "sujeto", "start": 0.3, "end": 0.8},
        {"word": "SCP-200", "start": 0.8, "end": 1.5},
        {"word": "parecía", "start": 1.5, "end": 2.0},
        {"word": "un", "start": 2.0, "end": 2.2},
        {"word": "niño", "start": 2.2, "end": 2.7},
    ]
    cues = CodeSubtitleDrawer.parse_word_timestamps(words, words_per_cue=3)
    assert len(cues) == 2
    assert cues[0].full_text == "El sujeto SCP-200"
    assert cues[0].start_sec == 0.0
    assert len(cues[0].words) == 3
    assert cues[1].full_text == "parecía un niño"


def test_draw_subtitles_on_frame():
    drawer = CodeSubtitleDrawer(theme=THEME_PRESETS["scp_neon"])
    frame = Image.new("RGB", (1080, 1920), (10, 20, 15))
    
    words = [
        {"word": "ANOMALÍA", "start": 0.0, "end": 1.0},
        {"word": "DETECTADA", "start": 1.0, "end": 2.0},
    ]
    cues = CodeSubtitleDrawer.parse_word_timestamps(words, words_per_cue=2)

    frame_copy = frame.copy()
    # Frame at t = 0.5s (First word active)
    rendered_f1 = drawer.draw_on_frame(frame, current_time_sec=0.5, cues=cues)
    assert rendered_f1.size == (1080, 1920)
    assert rendered_f1.tobytes() != frame_copy.tobytes()

    # Frame at t = 10.0s (Outside cues range -> returns unedited frame)
    rendered_f2 = drawer.draw_on_frame(frame, current_time_sec=10.0, cues=cues)
    assert rendered_f2.size == (1080, 1920)
