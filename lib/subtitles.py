"""Subtitle generation (SRT + ASS karaoke) and validation (shared core)."""
from __future__ import annotations

import os
import re
from pathlib import Path

from src.core.resolution import SHORT_RESOLUTION

_MAX_WORDS_PER_SRT_CUE = 4

PORTRAIT_MIN_MARGIN_V = 480
LANDSCAPE_MIN_MARGIN_V = 130

_TEMPLATE_NAME_DEFAULTS = {
    "scp_classified": {
        "font_name": "Montserrat Black",
        "margin_l": 48,
        "margin_r": 48,
        "margin_v": 240,
        "alignment": 2,
        "border_style": 1,
        "outline": 4,
        "shadow": 3,
        "group_size": 4,
        "primary_color": "&H0000FFFF",
        "secondary_color": "&H00FFFFFF",
        "back_color": "&H90000000",
    },
    "shorts_creepypasta": {
        "font_name": "Montserrat Black",
        "margin_l": 60,
        "margin_r": 60,
        "margin_v": 250,
        "alignment": 2,
        "border_style": 1,
        "outline": 5,
        "shadow": 4,
        "group_size": 3,
        "primary_color": "&H00FFFFFF",
    },
    "shorts_aita": {
        "font_name": "Montserrat Black",
        "margin_l": 60,
        "margin_r": 60,
        "margin_v": 250,
        "alignment": 2,
        "border_style": 1,
        "outline": 5,
        "shadow": 4,
        "group_size": 3,
        "primary_color": "&H00FFFFFF",
    },
    "short_neon_horror": {
        "font_name": "Montserrat Black",
        "margin_l": 48,
        "margin_r": 48,
        "margin_v": 220,
        "alignment": 2,
        "border_style": 1,
        "outline": 4,
        "shadow": 3,
        "group_size": 3,
        "primary_color": "&H0000FFFF",
        "secondary_color": "&H00FFFFFF",
        "back_color": "&H90000000",
    },
    "reddit_card": {
        "font_name": "Montserrat Black",
        "margin_l": 48,
        "margin_r": 48,
        "margin_v": 230,
        "alignment": 2,
        "outline": 4,
        "shadow": 3,
        "group_size": 3,
        "primary_color": "&H0000FFFF",
        "secondary_color": "&H00FFFFFF",
        "back_color": "&H90000000",
    },
    "cyberpunk": {
        "font_name": "Montserrat Black",
        "margin_l": 48,
        "margin_r": 48,
        "margin_v": 230,
        "alignment": 2,
        "outline": 4,
        "shadow": 3,
        "group_size": 3,
        "primary_color": "&H0000FFFF",
        "secondary_color": "&H00FFFFFF",
        "back_color": "&H90000000",
    },
}


def _clean_word_for_karaoke(word: str) -> tuple[str, str]:
    """Split a Spanish inverted-punctuation prefix (¿/¡) from a word."""
    prefix = ""
    clean = str(word)
    while clean and clean[0] in ("¿", "¡"):
        prefix += clean[0]
        clean = clean[1:]
    return prefix, clean


def _resolve_video_resolution(video_res=None) -> tuple[int, int]:
    """Return (width, height), default SHORT_RESOLUTION (1080x1920). Accepts tuple, list or 'WxH' string."""
    if video_res is None:
        return SHORT_RESOLUTION
    if isinstance(video_res, (tuple, list)) and len(video_res) >= 2:
        try:
            return int(video_res[0]), int(video_res[1])
        except (TypeError, ValueError):
            return SHORT_RESOLUTION
    if isinstance(video_res, str):
        match = re.match(r"\s*(\d{2,5})\s*[x×]\s*(\d{2,5})\s*", video_res)
        if match:
            return int(match.group(1)), int(match.group(2))
    return SHORT_RESOLUTION


def _format_srt_timestamp(seconds: float) -> str:
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int(round((seconds - int(seconds)) * 1000))
    if millis >= 1000:
        millis = 0
        secs += 1
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def format_ass_timestamp(seconds: float) -> str:
    """Format seconds into ASS centisecond timestamps (0:00:00.12 format)."""
    seconds = max(0.0, float(seconds))
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    cents = int(round((seconds - int(seconds)) * 100))
    if cents >= 100:
        cents = 0
        secs += 1
    if secs >= 60:
        secs -= 60
        minutes += 1
    return f"{hours}:{minutes:02d}:{secs:02d}.{cents:02d}"


_format_ass_timestamp = format_ass_timestamp


def _word_stamp_range(stamp: dict) -> tuple[float, float]:
    start = stamp.get("start", stamp.get("w_start", 0.0))
    end = stamp.get("end", stamp.get("w_end", float(start) + 0.001))
    return float(start), float(end)


def _word_text(stamp: dict) -> str:
    word = stamp.get("text", stamp.get("word", ""))
    return str(word)


def _chunk_words_subtitle(word_timestamps, max_words: int) -> list[list[dict]]:
    return [list(word_timestamps[i:i + max_words]) for i in range(0, len(word_timestamps), max_words)]


_DANGLING_END = frozenset({"de", "del", "en", "el", "la", "los", "las", "a", "al",
                           "con", "por", "para", "y", "o", "u", "su", "sus"})


def _dangling_base(word: str) -> bool:
    """True if this word, as the last token of a cue, would dangle."""
    return str(word).strip().rstrip(".,!?;:¿¡…").lower() in _DANGLING_END


def _chunk_cues(word_timestamps, max_words: int) -> list[list[dict]]:
    """Partition words into cues never ending on a dangling word/preposition."""
    normalized_stamps: list[dict] = []
    for stamp in (word_timestamps or []):
        txt = _word_text(stamp).strip()
        tokens = [t for t in re.split(r"\s+", txt) if t]
        if len(tokens) <= 1:
            normalized_stamps.append(stamp)
        else:
            s_time, e_time = _word_stamp_range(stamp)
            dur = max(0.001, e_time - s_time)
            step = dur / len(tokens)
            for idx, tok in enumerate(tokens):
                normalized_stamps.append({
                    "word": tok,
                    "start": round(s_time + idx * step, 3),
                    "end": round(s_time + (idx + 1) * step, 3),
                })

    chunks: list[list[dict]] = []
    current: list[dict] = []
    for stamp in normalized_stamps:
        current.append(stamp)
        word = _word_text(stamp).strip()
        if word.endswith((".", "!", "?")) and len(current) >= 2:
            chunks.append(current)
            current = []
        elif len(current) >= max_words and not _dangling_base(word):
            chunks.append(current)
            current = []
    if current:
        if chunks and _dangling_base(_word_text(chunks[-1][-1]).strip()):
            chunks[-1].extend(current)
        else:
            chunks.append(current)
    merged: list[list[dict]] = []
    for chunk in chunks:
        if merged and _dangling_base(_word_text(merged[-1][-1]).strip()):
            merged[-1].extend(chunk)
        else:
            merged.append(chunk)
    if merged and _dangling_base(_word_text(merged[-1][-1]).strip()):
        if len(merged) > 1 and len(merged[-1]) == 1:
            last = merged.pop()
            merged[-1].extend(last)
        elif len(merged[-1]) > 1:
            merged[-1].pop()
    return merged


def _chunk_words_grammatically(word_timestamps, max_words: int = 4) -> list[list[dict]]:
    """Chunk words into subtitle lines, breaking after sentence-final words."""
    chunks: list[list[dict]] = []
    current: list[dict] = []
    for stamp in word_timestamps:
        current.append(stamp)
        word = _word_text(stamp).strip()
        if len(current) >= max_words or word.endswith((".", "!", "?")):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def create_subtitles(
    word_timestamps: list[dict],
    output_path: str | os.PathLike,
    template=None,
    video_res=None,
    script_text: str | None = None,
) -> str:
    """Write a standard SRT file grouping up to 3 words per cue (dangling-safe)."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for num, chunk in enumerate(_chunk_cues(word_timestamps, _MAX_WORDS_PER_SRT_CUE), start=1):
        start = _word_stamp_range(chunk[0])[0]
        end = _word_stamp_range(chunk[-1])[1]
        text = " ".join(_word_text(w) for w in chunk)
        lines.append(
            f"{num}\n"
            f"{_format_srt_timestamp(start)} --> {_format_srt_timestamp(end)}\n{text}\n"
        )
    out.write_text("\n".join(lines), encoding="utf-8")
    return str(out)


def _ass_style_spec(template, font_name, play_w: int, play_h: int, **kwargs) -> dict:
    spec = {
        "font_name": font_name or "Montserrat Black",
        "font_size": 40,
        "primary_color": "&H00FFFFFF",
        "secondary_color": "&H00FFFFFF",
        "outline_color": "&H00000000",
        "back_color": "&H90000000",
        "bold": 1,
        "border_style": 1,
        "outline": 4,
        "shadow": 3,
        "alignment": 2,
        "margin_l": 40,
        "margin_r": 40,
        "margin_v": 230,
        "group_size": 4,
        "style_type": "karaoke",
    }
    if isinstance(template, str):
        spec.update(_TEMPLATE_NAME_DEFAULTS.get(template, {}))
    elif template is not None:
        subtitles = getattr(template, "subtitles", template)
        for field in ("font_name", "primary_color", "secondary_color", "outline_color",
                      "back_color", "margin_l", "margin_r", "margin_v", "group_size",
                      "border_style", "style_type"):
            value = getattr(subtitles, field, None)
            if value is not None:
                spec[field] = value
        spec["bold"] = int(bool(getattr(subtitles, "bold", True)))
        spec["outline"] = getattr(subtitles, "outline_width", spec["outline"])
        spec["shadow"] = getattr(subtitles, "shadow_depth", spec["shadow"])
        alignment = getattr(subtitles, "alignment", 5)
        if alignment:
            spec["alignment"] = alignment
        if spec["style_type"] == "boxed":
            spec["border_style"] = 3
    else:
        pass
    if font_name:
        spec["font_name"] = font_name
    if kwargs.get("downward_drift_px"):
        spec["margin_v"] = int(spec.get("margin_v", 230)) + max(0, int(kwargs["downward_drift_px"]))
    if play_h > play_w:
        spec["margin_v"] = max(PORTRAIT_MIN_MARGIN_V, int(spec.get("margin_v", PORTRAIT_MIN_MARGIN_V)))
    spec["outline"] = max(3, int(spec.get("outline", 4)))
    spec["margin_l"] = max(40, int(spec.get("margin_l", 40)))
    spec["margin_r"] = max(40, int(spec.get("margin_r", 40)))
    if spec.get("margin_v", 0) >= 320:
        spec["margin_l"] = max(spec["margin_l"], 72)
        spec["margin_r"] = max(spec["margin_r"], 72)
    scale = max(0.5, play_w / 1080.0)
    font_base = spec["font_size"]
    spec["font_size"] = max(24, int(font_base * scale))
    return spec


_FONT_METRICS_CACHE: dict = {}


def get_font_metrics(font_name: str = "Montserrat Black", font_size: int = 40):
    """Load Pillow ImageFont with caching for font metrics and bounding box measurement."""
    cache_key = (font_name, font_size)
    if cache_key in _FONT_METRICS_CACHE:
        return _FONT_METRICS_CACHE[cache_key]
    try:
        from PIL import ImageFont
        local_font_candidates = [
            Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Montserrat-Black.ttf",
            Path(__file__).resolve().parent.parent / "assets" / "fonts" / "Montserrat-Bold.ttf",
        ]
        for candidate in local_font_candidates:
            if candidate.is_file():
                font = ImageFont.truetype(str(candidate), size=font_size)
                _FONT_METRICS_CACHE[cache_key] = font
                return font
        font = ImageFont.load_default()
        _FONT_METRICS_CACHE[cache_key] = font
        return font
    except Exception:
        _FONT_METRICS_CACHE[cache_key] = None
        return None


def estimate_text_width_px(text: str, font_name: str = "Montserrat Black", font_size: int = 40) -> float:
    """Estimate pixel width of text using Pillow font.getlength with fallback."""
    clean = _strip_ass_tags(text)
    if not clean:
        return 0.0
    font = get_font_metrics(font_name, font_size)
    if font and hasattr(font, "getlength"):
        try:
            return float(font.getlength(clean))
        except Exception:
            pass
    return len(clean) * (font_size * 0.55)


def _ass_karaoke_token(token: dict) -> str:
    word = _word_text(token)
    if not word:
        return ""
    prefix, clean = _clean_word_for_karaoke(word)
    if not clean:
        return prefix
    start, end = _word_stamp_range(token)
    cs = max(1, int(round((end - start) * 100)))
    return f"{prefix}{{\\kf{cs}}}{clean}"


def _ass_dialogues(
    word_timestamps: list[dict],
    group_size: int,
    max_chars: int,
    max_width_px: float = 960.0,
    font_name: str = "Montserrat Black",
    font_size: int = 40,
) -> list[tuple[float, float, str]]:

    events: list[tuple[float, float, str]] = []
    group: list[dict] = []
    group_chars = 0

    def flush():
        nonlocal group, group_chars
        if not group:
            return
        start = _word_stamp_range(group[0])[0]
        end = _word_stamp_range(group[-1])[1]
        events.append((start, end, " ".join(_ass_karaoke_token(t) for t in group)))
        group = []
        group_chars = 0

    for token in word_timestamps:
        word = _word_text(token)
        if group and (len(group) >= group_size or group_chars + len(word) + 1 > max_chars):
            if _dangling_base(_word_text(group[-1])) and len(group) < group_size * 2:
                pass
            else:
                flush()
        group.append(token)
        group_chars += len(word) + 1
    flush()
    # Character-level splitting of lines that are still too long
    split_events: list[tuple[float, float, str]] = []
    for start, end, text in events:
        visible = _strip_ass_tags(text)
        if len(visible) <= max_chars:
            split_events.append((start, end, text))
            continue
        words = text.split(" ")
        lines: list[str] = []
        current = ""
        current_len = 0
        for part in words:
            part_len = len(_strip_ass_tags(part))
            if current and current_len + part_len + 1 > max_chars:
                lines.append(current)
                current = part
                current_len = part_len
            else:
                current = (current + " " + part).strip()
                current_len += part_len + 1
        if current:
            lines.append(current)
        # Never dump a paragraph as one centered cue.
        if len(lines) <= 2:
            split_events.append((start, end, r"\N".join(lines)))
            continue
        span = max(0.01, end - start)
        n = (len(lines) + 1) // 2
        for i in range(0, len(lines), 2):
            chunk = lines[i:i + 2]
            t0 = start + span * (i / max(1, len(lines)))
            t1 = start + span * (min(i + 2, len(lines)) / max(1, len(lines)))
            split_events.append((t0, t1, r"\N".join(chunk)))
    repaired = _repair_dangling_events(split_events)
    if repaired:
        trimmed = _drop_trailing_dangling(repaired[-1][2])
        if trimmed:
            repaired[-1] = (repaired[-1][0], repaired[-1][1], trimmed)
        elif len(repaired) > 1:
            repaired.pop()
    return repaired


def _drop_trailing_dangling(text: str) -> str:
    """Strip a trailing dangling preposition from the last karaoke token."""
    parts = text.split(" ")
    while parts:
        last_vis = _strip_ass_tags(parts[-1]).replace("\\N", " ").strip()
        token = last_vis.split()[-1] if last_vis.split() else ""
        if token and _dangling_base(token):
            parts.pop()
            continue
        break
    return " ".join(parts).strip()


def _line_ends_dangling(text: str) -> bool:
    """True if a rendered cue line ends on a dangling word/preposition."""
    tokens = _strip_ass_tags(text).replace("\\N", " ").replace("\n", " ").split()
    return bool(tokens) and _dangling_base(tokens[-1])


def _repair_dangling_events(
    events: list[tuple[float, float, str]],
) -> list[tuple[float, float, str]]:
    """Merge dangling tails forward so no cue ends on a dangling word."""
    for _ in range(5):
        fixed = False
        merged: list[tuple[float, float, str]] = []
        for start, end, text in events:
            if merged and _line_ends_dangling(merged[-1][2]):
                prev_text = merged[-1][2]
                clean_parts = _strip_ass_tags(prev_text).replace(r"\N", " ").replace("\n", " ").split()
                if len(clean_parts) > 1:
                    stolen = clean_parts[-1]
                    idx = prev_text.rfind(stolen)
                    if idx != -1:
                        head = prev_text[:idx].rstrip(" \\\nN")
                        if head:
                            merged[-1] = (merged[-1][0], merged[-1][1], head)
                            text = stolen + " " + text
                            fixed = True
                elif len(clean_parts) == 1:
                    t0, _, single_word = merged.pop()
                    start = min(start, t0)
                    text = single_word + " " + text
                    fixed = True
            merged.append((start, end, text))
        events = merged
        if not fixed:
            break
    return events


def _strip_ass_tags(text: str) -> str:
    from src.sanitizer import strip_ass_tags
    return strip_ass_tags(text)


def _ass_header(play_w: int, play_h: int, style: dict) -> str:
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {play_w}\n"
        f"PlayResY: {play_h}\n"
        "ScaledBorderAndShadow: yes\n"
        "\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, "
        "Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, "
        "Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\n"
        "Style: Default," + ",".join(_ass_style_fields(style)) + "\n"
        "\n"
    )


def _ass_style_fields(style: dict) -> list[str]:
    return [
        str(style["font_name"]),
        str(style["font_size"]),
        str(style["primary_color"]),
        str(style["secondary_color"]),
        str(style["outline_color"]),
        str(style["back_color"]),
        str(style["bold"]),
        "0",
        "0",
        "0",
        "100",
        "100",
        "0",
        "0",
        str(style["border_style"]),
        str(style["outline"]),
        str(style["shadow"]),
        str(style["alignment"]),
        str(style["margin_l"]),
        str(style["margin_r"]),
        str(style["margin_v"]),
        "0",
    ]


def create_ass_subtitles(
    word_timestamps: list[dict],
    output_path: str | os.PathLike,
    template=None,
    video_res=None,
    font_name: str | None = None,
    max_chars: int | None = None,
    group_size: int | None = None,
    **kwargs,
) -> str:
    """Write ASS subtitles with per-word karaoke timing (`{\\kfN}` tags)."""
    play_w, play_h = _resolve_video_resolution(video_res)
    style = _ass_style_spec(template, font_name, play_w, play_h, **kwargs)
    group_size = int(group_size or style["group_size"])
    resolved_max_chars = int(max_chars if max_chars is not None else style.get("max_chars", 25))
    max_width = float(play_w - style.get("margin_l", 40) - style.get("margin_r", 40))
    events = _ass_dialogues(
        word_timestamps,
        group_size=group_size,
        max_chars=resolved_max_chars,
        max_width_px=max_width,
        font_name=style.get("font_name", "Montserrat Black"),
        font_size=style.get("font_size", 40),
    )
    content = _ass_header(play_w, play_h, style)
    content += "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n"
    pop_in = r"{\fscx108\fscy108\t(0,120,\fscx100\fscy100)}" if template == "scp_classified" else ""
    for start_s, end_s, text in events:
        line_text = pop_in + text if pop_in else text
        content += (
            f"Dialogue: 0,{_format_ass_timestamp(start_s)},{_format_ass_timestamp(end_s)},"
            f"Default,,0,0,0,,{line_text}\n"
        )
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(content, encoding="utf-8")
    return str(out)


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_word_timestamps(word_timestamps: list[dict]) -> None:
    """Raise ValueError if word start times are not monotonically increasing."""
    previous = None
    for stamp in word_timestamps:
        start = _word_stamp_range(stamp)[0]
        if previous is not None and start < previous - 1e-9:
            raise ValueError(
                "Los timestamps de palabras no son monotónicos (decrecen en el tiempo)"
            )
        previous = start


def validate_subtitle_artifact(
    path: str | os.PathLike,
    duration_sec: float | None = None,
    expected_words: int | None = None,
) -> dict:
    """Validate a subtitle file: parse cues and compute temporal coverage."""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Subtitle artifact missing: {p}")
    text = p.read_text(encoding="utf-8")
    cues = re.findall(r"Dialogue: \d+,\s*([^,]+),\s*([^,]+)", text)
    if not cues:
        cues = re.findall(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", text)
    word_count = len(re.findall(r"\{\\kf\d+\}([^ }]+)|\{\\kf\d+\}(?:[^\\s]+)", text))
    if not word_count:
        word_count = len(re.findall(r"[^\W\d_]+", text))
    end_secs = max((_parse_srt_sec(end) for _, end in cues), default=0.0)
    coverage = 0.0
    if duration_sec and duration_sec > 0:
        coverage = max(0.0, min(1.0, end_secs / duration_sec))
    return {
        "passed": True,
        "path": str(p),
        "cues": len(cues),
        "coverage": coverage,
        "end_seconds": end_secs,
        "word_count": word_count,
    }


def _parse_srt_sec(timestamp: str) -> float:
    match = re.match(r"(\d+):(\d+):(\d+)[.,](\d+)", timestamp.strip())
    if not match:
        return 0.0
    h, m, s, ms = (int(g) for g in match.groups())
    return h * 3600 + m * 60 + s + ms / 1000.0


def validate_subtitle_grammar_and_syntax(path: str | os.PathLike) -> bool:
    """Full grammar/syntax scan; raises ValueError on dangling endings."""
    p = Path(path)
    if not p.exists():
        raise ValueError(f"Subtitle file missing: {p}")
    for plain in _subtitle_cue_texts(p.read_text(encoding="utf-8")):
        if not plain:
            continue
        tokens = plain.replace("\\N", " ").replace("\n", " ").split()
        if tokens:
            last_tok = tokens[-1]
            has_terminal = bool(re.search(r"[.!?…\"\']+$", last_tok))
            cleaned_word = last_tok.lower().rstrip(".,!?;:¿¡…\"'")
            if not has_terminal and cleaned_word in _DANGLING_END:
                raise ValueError(
                    f"Subtitle cue ends with dangling word/preposition: {plain!r}"
                )
    return True


def _subtitle_cue_texts(content: str) -> list[str]:
    """Extract plain-text cue texts from either ASS (Dialogue:) or SRT content."""
    has_dialogue = any(line.startswith("Dialogue:") for line in content.splitlines())
    if has_dialogue:
        out: list[str] = []
        for line in content.splitlines():
            if not line.startswith("Dialogue:"):
                continue
            text = line.split(",,")[-1]
            out.append(_strip_ass_tags(text).strip())
        return out
    out: list[str] = []
    pending: list[str] = []
    in_cue = False
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            if in_cue and pending:
                out.append(" ".join(pending))
            pending, in_cue = [], False
            continue
        if re.fullmatch(r"\d{1,6}", stripped):
            in_cue = True
            pending = []
            continue
        if "-->" in stripped:
            continue
        if in_cue:
            pending.append(_strip_ass_tags(stripped))
    if pending:
        out.append(" ".join(pending))
    return [text for text in out if text]


def generate_safe_area_validation_artifact(ass_path: str | os.PathLike, out_jpg_path: str | os.PathLike) -> str:
    """Render a safe-area grid JPEG from the ASS PlayRes for manual validation."""
    from PIL import Image, ImageDraw
    out = Path(out_jpg_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    play_w, play_h = 768, 1360
    try:
        text = Path(ass_path).read_text(encoding="utf-8")
        match_w = re.search(r"PlayResX:\s*(\d+)", text)
        match_h = re.search(r"PlayResY:\s*(\d+)", text)
        if match_w:
            play_w = int(match_w.group(1))
        if match_h:
            play_h = int(match_h.group(1))
    except Exception:
        pass
    img = Image.new("RGB", (play_w, play_h), (12, 12, 16))
    draw = ImageDraw.Draw(img)
    safe_margin = 120
    draw.rectangle(
        [safe_margin, safe_margin, play_w - safe_margin, play_h - safe_margin],
        outline=(255, 255, 0),
        width=2,
    )
    draw.rectangle(
        [safe_margin + 60, safe_margin + 60, play_w - safe_margin - 60, play_h - safe_margin - 60],
        outline=(255, 153, 0),
        width=1,
    )
    for x in range(0, play_w, play_w // 3):
        draw.line([x, 0, x, play_h], fill=(80, 80, 90), width=1)
    for y in range(0, play_h, play_h // 3):
        draw.line([0, y, play_w, y], fill=(80, 80, 90), width=1)
    draw.line([0, play_h // 2, play_w, play_h // 2], fill=(255, 255, 255), width=2)
    img.save(out, format="JPEG", quality=88)
    return str(out)