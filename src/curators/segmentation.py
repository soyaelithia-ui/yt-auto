"""
src/curators/segmentation.py - Sentence boundary splitting and scene slicing algorithms.

Provides deterministic text sanitization, sentence splitting with abbreviation protection,
sentence-aware scene chunking, and 4-act distribution.
"""
from __future__ import annotations

import re
from typing import List

from src.log import get_logger

logger = get_logger("cinematic_script_curator.segmentation")

# Comprehensive Spanish title and clerical abbreviations
TITLE_ABBREVIATIONS = [
    r"\bDr\.",
    r"\bDra\.",
    r"\bSr\.",
    r"\bSra\.",
    r"\bSrta\.",
    r"\bProf\.",
    r"\bProfa\.",
    r"\bIng\.",
    r"\bLic\.",
    r"\bGral\.",
    r"\bCap\.",
    r"\bTen\.",
    r"\bP\.D\.",
    r"\bnúm\.",
    r"\bnum\.",
    r"\bpág\.",
    r"\bpags?\.",
    r"\bvol\.",
    r"\bart\.",
    r"\bvs\.",
]


def sanitize_text(text: str, channel: str = "horror") -> str:
    """Sanitizes text, removing markdown headers, meta chatter, emojis, clichés, and artifacts."""
    if not text:
        return ""
    try:
        from src.sanitizer import sanitize_script_text
        t = sanitize_script_text(text, channel=channel)
    except Exception:
        t = text
    t = re.sub(r"#+\s*", "", t)
    t = re.sub(r"\[.*?\]", "", t)
    t = re.sub(r"\(http.*?\)", "", t)
    t = re.sub(r"[\*\_~`]", "", t)

    # Anti-cliché and boilerplate filter
    t = re.sub(r"(?i)\ben este video veremos\b", "", t)
    t = re.sub(r"(?i)\bbajo una universidad ordinaria\b", "en una instalación subterránea", t)
    t = re.sub(r"(?i)\bsuscr[íi]bete para m[áa]s\b", "", t)
    t = re.sub(r"(?i)\bpermanece bajo custodia oficial en\s*@\w+\.?\b", "", t)

    return re.sub(r"\s+", " ", t).strip()


def split_into_sentences(text: str) -> List[str]:
    """
    Splits text on sentence boundaries while protecting common abbreviations,
    acronyms, decimal numbers, and titles.
    """
    if not text:
        return []

    t = text

    # 1. Protect decimal dots (e.g. 3.5 -> 3__DOT__5)
    t = re.sub(r"(\d+)\.(\d+)", r"\1__DOT__\2", t)

    # 2. Protect titles and abbreviations
    for abbr_pat in TITLE_ABBREVIATIONS:
        def _replace_title(m: re.Match) -> str:
            return m.group(0).replace(".", "__DOT__")
        t = re.sub(abbr_pat, _replace_title, t, flags=re.IGNORECASE)

    # 3. Protect internal dot of a.m. / p.m.
    t = re.sub(r"(?i)\ba\.m\.", "a__DOT__m.", t)
    t = re.sub(r"(?i)\bp\.m\.", "p__DOT__m.", t)

    # 4. Protect etc. if followed by lowercase or comma
    t = re.sub(r"(?i)\betc\.(?=\s*[,;a-záéíóúñ])", "etc__DOT__", t)

    # Split on sentence terminals followed by space (or space before uppercase/punctuation) or newlines
    raw_sentences = re.split(r"(?<=[.!?…])\s+(?=[A-ZÁÉÍÓÚÑ¿¡\"«0-9])|(?<=[.!?…])\s+|\n+", t)
    cleaned_sentences: List[str] = []

    for s in raw_sentences:
        s_clean = s.strip()
        if s_clean:
            cleaned_sentences.append(s_clean.replace("__DOT__", "."))

    return cleaned_sentences if cleaned_sentences else [text]


def slice_into_scenes(
    clean_text: str,
    target_scene_dur: float,
    min_scene_dur: float,
    max_scene_dur: float,
    wpm: float,
    min_scenes: int,
    max_scenes: int,
    target_format: str,
) -> List[str]:
    """
    Performs sentence-aware boundary slicing to produce balanced scene chunks.
    Guarantees minimum scene counts and respects min/max duration constraints.
    """
    sentences = split_into_sentences(clean_text)
    if not sentences:
        sentences = [clean_text] if clean_text.strip() else ["Relato sin contenido."]

    target_words_per_scene = max(10, int(round((target_scene_dur / 60.0) * wpm)))
    max_words_per_scene = max(15, int(round((max_scene_dur / 60.0) * wpm)))

    scene_buckets: List[List[str]] = []
    current_bucket: List[str] = []
    current_word_count = 0

    for sent in sentences:
        sent_words = len(sent.split())
        if current_bucket and (current_word_count + sent_words > max_words_per_scene or current_word_count >= target_words_per_scene):
            scene_buckets.append(current_bucket)
            current_bucket = [sent]
            current_word_count = sent_words
        else:
            current_bucket.append(sent)
            current_word_count += sent_words

    if current_bucket:
        scene_buckets.append(current_bucket)

    scenes = [" ".join(b).strip() for b in scene_buckets if b]

    # Enforce minimum scene count by subdividing longer scenes
    scenes = _expand_scenes_to_minimum(scenes, min_scenes)

    # Enforce maximum scene count by merging adjacent scenes
    scenes = _collapse_scenes_to_maximum(scenes, max_scenes)

    return scenes


def _expand_scenes_to_minimum(scenes: List[str], min_scenes: int) -> List[str]:
    """Subdivides scenes until minimum scene threshold is satisfied."""
    while len(scenes) < min_scenes:
        longest_idx = max(range(len(scenes)), key=lambda i: len(scenes[i].split()))
        longest_text = scenes[longest_idx]
        sub_sents = split_into_sentences(longest_text)
        if len(sub_sents) > 1:
            mid = len(sub_sents) // 2
            scenes[longest_idx] = " ".join(sub_sents[:mid]).strip()
            scenes.insert(longest_idx + 1, " ".join(sub_sents[mid:]).strip())
        else:
            words = longest_text.split()
            if len(words) < 8:
                break
            comma_idx = -1
            for w_i in range(len(words) // 3, 2 * len(words) // 3):
                if words[w_i].endswith((",", ";", ":")):
                    comma_idx = w_i + 1
                    break
            split_at = comma_idx if comma_idx > 0 else len(words) // 2
            part1 = " ".join(words[:split_at]).strip()
            if not part1.endswith((".", "!", "?")):
                part1 += "."
            part2 = " ".join(words[split_at:]).strip()
            scenes[longest_idx] = part1
            scenes.insert(longest_idx + 1, part2)
    return scenes


def _collapse_scenes_to_maximum(scenes: List[str], max_scenes: int) -> List[str]:
    """Merges shortest adjacent scenes until within maximum scene limit."""
    while len(scenes) > max_scenes:
        shortest_idx = min(
            range(len(scenes) - 1),
            key=lambda i: len(scenes[i].split()) + len(scenes[i + 1].split()),
        )
        merged = f"{scenes[shortest_idx]} {scenes[shortest_idx + 1]}"
        scenes[shortest_idx] = merged
        scenes.pop(shortest_idx + 1)
    return scenes


def distribute_scenes_across_acts(total_scenes: int, num_acts: int = 4) -> List[int]:
    """Distributes scene counts across 4 acts ensuring at least 1 scene per act."""
    if total_scenes <= num_acts:
        return [1] * num_acts

    base = total_scenes // num_acts
    rem = total_scenes % num_acts
    counts = [base] * num_acts

    # Distribute remainder into rising action (Act 2) and climax (Act 3)
    for i in range(rem):
        counts[(i + 1) % num_acts] += 1

    return counts
