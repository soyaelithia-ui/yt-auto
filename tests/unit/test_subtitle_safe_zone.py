"""Unit tests for Subtitle Safe-Zone and ASS Terminal Karaoke Generation."""
from __future__ import annotations

import re
from pathlib import Path
import pytest

from src.compositing.subtitles import (
    TerminalKaraokeSubtitleGenerator,
    format_ass_timestamp,
)


def _parse_ass_style(content: str) -> dict[str, str]:
    """Extracts the Style definition fields from ASS [V4+ Styles] section."""
    lines = content.splitlines()
    in_styles = False
    format_line = ""
    style_line = ""
    for line in lines:
        if line.strip() == "[V4+ Styles]":
            in_styles = True
            continue
        elif in_styles and line.startswith("["):
            break

        if in_styles:
            if line.startswith("Format:"):
                format_line = line[len("Format:"):].strip()
            elif line.startswith("Style:"):
                style_line = line[len("Style:"):].strip()

    assert format_line, "Format line not found in [V4+ Styles]"
    assert style_line, "Style definition not found in [V4+ Styles]"

    keys = [k.strip() for k in format_line.split(",")]
    vals = [v.strip() for v in style_line.split(",")]
    return dict(zip(keys, vals))


def _parse_ass_dialogues(content: str) -> list[dict[str, str]]:
    """Extracts Dialogue lines from ASS content."""
    dialogues = []
    for line in content.splitlines():
        if line.startswith("Dialogue:"):
            parts = line[len("Dialogue:"):].strip().split(",", 9)
            if len(parts) >= 10:
                dialogues.append({
                    "layer": parts[0].strip(),
                    "start": parts[1].strip(),
                    "end": parts[2].strip(),
                    "style": parts[3].strip(),
                    "name": parts[4].strip(),
                    "margin_l": parts[5].strip(),
                    "margin_r": parts[6].strip(),
                    "margin_v": parts[7].strip(),
                    "effect": parts[8].strip(),
                    "text": parts[9].strip(),
                })
    return dialogues


class TestSubtitleSafeZone:
    """Tests vertical and horizontal safe-zone boundaries for ASS styling."""

    def test_portrait_safe_zone_margin_v_ge_480(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator()
        out_file = tmp_path / "portrait.ass"
        gen.generate_ass(
            word_timestamps=[{"word": "Test", "start": 0.0, "end": 0.5}],
            output_ass_path=out_file,
            width=1080,
            height=1920,
        )
        content = out_file.read_text(encoding="utf-8")
        style = _parse_ass_style(content)

        margin_v = int(style["MarginV"])
        assert margin_v >= 480, f"Portrait MarginV {margin_v} must be >= 480px to clear mobile Shorts UI"
        assert int(style["MarginL"]) >= 40
        assert int(style["MarginR"]) >= 40

    def test_landscape_safe_zone_margin_v_ge_130(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator()
        out_file = tmp_path / "landscape.ass"
        gen.generate_ass(
            word_timestamps=[{"word": "Landscape", "start": 0.0, "end": 0.5}],
            output_ass_path=out_file,
            width=1920,
            height=1080,
        )
        content = out_file.read_text(encoding="utf-8")
        style = _parse_ass_style(content)

        margin_v = int(style["MarginV"])
        assert margin_v >= 130, f"Landscape MarginV {margin_v} must be >= 130px"
        assert int(style["MarginL"]) >= 40
        assert int(style["MarginR"]) >= 40

    def test_empty_words_generates_valid_header_with_safe_zone(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator()
        out_file = tmp_path / "empty.ass"
        gen.generate_ass(
            word_timestamps=[],
            output_ass_path=out_file,
            width=1080,
            height=1920,
        )
        content = out_file.read_text(encoding="utf-8")
        style = _parse_ass_style(content)
        assert int(style["MarginV"]) >= 480

    def test_ass_karaoke_colors_primary_and_secondary(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator(
            active_color="&H0066FF00&",
            inactive_color="&H00FFFFFF&",
        )
        out_file = tmp_path / "colors.ass"
        gen.generate_ass(
            word_timestamps=[],
            output_ass_path=out_file,
            width=1080,
            height=1920,
        )
        content = out_file.read_text(encoding="utf-8")
        style = _parse_ass_style(content)
        assert style["PrimaryColour"] == "&H0066FF00&"
        assert style["SecondaryColour"] == "&H00FFFFFF&"


class TestKaraokeCueGroupingAndTiming:
    """Tests word-level karaoke cue grouping and timestamp integrity."""

    def test_nine_words_grouped_into_three_cues(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator()
        words = [
            {"word": f"word{i}", "start": i * 0.5, "end": (i + 1) * 0.5}
            for i in range(9)
        ]
        out_file = tmp_path / "cues.ass"
        gen.generate_ass(
            word_timestamps=words,
            output_ass_path=out_file,
            width=1080,
            height=1920,
            words_per_cue=3,
        )
        content = out_file.read_text(encoding="utf-8")
        dialogues = _parse_ass_dialogues(content)

        assert len(dialogues) == 3
        for d in dialogues:
            assert re.search(r"\{\\k\d+\}\w+", d["text"])

    def test_trailing_minimal_duration_word_padded(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator()
        words = [{"word": "Short", "start": 1.0, "end": 1.05}]
        out_file = tmp_path / "short.ass"
        gen.generate_ass(
            word_timestamps=words,
            output_ass_path=out_file,
            width=1080,
            height=1920,
        )
        content = out_file.read_text(encoding="utf-8")
        dialogues = _parse_ass_dialogues(content)

        assert len(dialogues) == 1
        assert dialogues[0]["start"] == "0:00:01.00"
        # Must be at least 0.10s duration
        assert dialogues[0]["end"] >= "0:00:01.10"
        assert r"{\k" in dialogues[0]["text"]

    def test_sequential_cues_non_overlapping_monotonic(self, tmp_path: Path):
        gen = TerminalKaraokeSubtitleGenerator()
        words = [
            {"word": "alpha", "start": 0.0, "end": 0.4},
            {"word": "beta", "start": 0.4, "end": 0.8},
            {"word": "gamma", "start": 0.8, "end": 1.2},
            {"word": "delta", "start": 1.2, "end": 1.6},
        ]
        out_file = tmp_path / "monotonic.ass"
        gen.generate_ass(
            word_timestamps=words,
            output_ass_path=out_file,
            width=1080,
            height=1920,
            words_per_cue=2,
        )
        content = out_file.read_text(encoding="utf-8")
        dialogues = _parse_ass_dialogues(content)

        assert len(dialogues) == 2
        # Verify timestamps format H:MM:SS.cs
        ts_pattern = re.compile(r"^\d+:\d{2}:\d{2}\.\d{2}$")
        for d in dialogues:
            assert ts_pattern.match(d["start"])
            assert ts_pattern.match(d["end"])
            assert d["end"] > d["start"]

    def test_format_ass_timestamp(self):
        assert format_ass_timestamp(0.0) == "0:00:00.00"
        assert format_ass_timestamp(65.432) == "0:01:05.43"
        assert format_ass_timestamp(3661.05) == "1:01:01.05"
