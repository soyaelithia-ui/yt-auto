"""Narrative Beat Curation & Narrative Beat Segmentation module for YouTube Shorts."""

import re
from typing import List, Dict, Any, Tuple


def extract_story_beats(script_text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Extract narrative beats from an SCP formatted script.
    
    If the script contains explicit markers like [BEAT 1: ITEM & CLASE],
    this function splits the script into narrative beats and strips the tags
    to provide clean narration text for Edge-TTS. Discards pre-beat preambles.
    
    If no tags are present, it falls back to splitting by double newlines or sentences.

    Returns:
        (clean_script_text, list_of_beat_dicts)
    """
    if not script_text or not isinstance(script_text, str):
        return "", []

    # Clean HTML entities and unescape before processing
    try:
        from src.sanitizer import sanitize_html_entities
        script_text = sanitize_html_entities(script_text)
    except ImportError:
        pass

    from src.sanitizer import ORDINAL_OR_ROMAN

    # Strip title header lines (e.g. "Título: ...") from spoken narration text
    script_text = re.sub(r"(?i)^\s*(?:t[íi]tulo|title)\s*[:：][^\n]*\n*", "", script_text.strip(), flags=re.MULTILINE).strip()

    # Strip unbracketed and bracketed section/chapter headers and markdown headers
    script_text = re.sub(r"(?i)^[>*\s]*#+\s*[^\n]*\n*", "", script_text, flags=re.MULTILINE)
    script_text = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)", "", script_text, flags=re.MULTILINE)
    script_text = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte|bloque|fase|paso)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?\s*$", "", script_text, flags=re.MULTILINE)
    script_text = re.sub(r"(?i)###?\s*cap[íi]tulo\s*\d*[:.-]?[^\n]*\n*", "", script_text)
    script_text = re.sub(r"(?i)\b(?:secci[óo]n|cap[íi]tulo)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?", "", script_text)

    try:
        from src.sanitizer import sanitize_llm_script
        script_text = sanitize_llm_script(script_text, mode="short")
    except ImportError:
        pass

    lines = script_text.split('\n')
    current_beat_label = "BEAT 1"
    beat_texts: List[Dict[str, Any]] = []
    current_text_buf: List[str] = []
    first_tag_seen = False

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        match = re.search(r'\[(?:BEAT|SECCION|SHOT)\s*\d*\s*:?\s*([^\]]*)\]', stripped, re.IGNORECASE)
        if match:
            if first_tag_seen:
                if current_text_buf:
                    text_content = ' '.join(current_text_buf).strip()
                    if text_content:
                        beat_texts.append({
                            "label": current_beat_label,
                            "text": text_content,
                        })
            else:
                first_tag_seen = True
            current_text_buf = []
            tag_label = match.group(1).strip() or f"BEAT {len(beat_texts) + 1}"
            current_beat_label = tag_label
            # Remove the marker tag from line
            line_rem = re.sub(r'\[(?:BEAT|SECCION|SHOT)\s*\d*\s*:?\s*[^\]]*\]', '', stripped, flags=re.IGNORECASE).strip()
            # Also clean any structural header prefixes from remaining line content
            line_rem = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)", "", line_rem).strip()
            line_rem = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?$", "", line_rem).strip()
            line_rem = re.sub(r"(?i)^#+\s*", "", line_rem).strip()
            if line_rem:
                current_text_buf.append(line_rem)
        else:
            # Strip structural header prefixes if present on regular lines
            line_clean = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)", "", stripped).strip()
            line_clean = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?$", "", line_clean).strip()
            line_clean = re.sub(r"(?i)^#+\s*", "", line_clean).strip()
            line_clean = re.sub(r"(?i)^\s*(?:t[íi]tulo|title)\s*[:：]\s*", "", line_clean).strip()
            if line_clean:
                current_text_buf.append(line_clean)

    if current_text_buf and first_tag_seen:
        text_content = ' '.join(current_text_buf).strip()
        if text_content:
            beat_texts.append({
                "label": current_beat_label,
                "text": text_content,
            })

    # If no markers were found, fall back to paragraph or sentence chunking
    if not beat_texts or not first_tag_seen:
        paragraphs = [p.strip() for p in script_text.split('\n\n') if p.strip()]
        if len(paragraphs) > 1:
            beat_texts = [
                {"label": f"BEAT {i+1}", "text": p}
                for i, p in enumerate(paragraphs)
            ]
        else:
            # Chunk sentences into ~4-6 beats
            sentences = re.split(r'(?<=[.!?])\s+', script_text.strip())
            chunk_size = max(1, len(sentences) // 4)
            beat_texts = []
            for i in range(0, len(sentences), chunk_size):
                chunk = ' '.join(sentences[i:i + chunk_size]).strip()
                if chunk:
                    beat_texts.append({"label": f"BEAT {len(beat_texts)+1}", "text": chunk})

    # Final cleanup on all beat texts to ensure zero structural headers
    for b in beat_texts:
        b_text = b.get("text", "")
        b_text = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte)\s+" + ORDINAL_OR_ROMAN + r"(?:\s*[:.-]|\s+)", "", b_text)
        b_text = re.sub(r"(?i)^[>*\s#]*(?:secci[óo]n|cap[íi]tulo|parte)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?\s*$", "", b_text)
        b_text = re.sub(r"(?i)\b(?:cap[íi]tulo|secci[óo]n)\s+" + ORDINAL_OR_ROMAN + r"[:.-]?", "", b_text)
        b_text = re.sub(r"(?i)^#+\s*", "", b_text)
        b["text"] = b_text.strip()

    clean_script = '\n\n'.join(b["text"] for b in beat_texts if b.get("text", "").strip())
    return clean_script, beat_texts


def validate_beat_format(script_text: str) -> bool:
    """
    Verifies that the narration script keeps an authentic beat format.
    Must be a non-empty string and contain beat markers (e.g. [BEAT 1: ...]).
    """
    if not script_text or not isinstance(script_text, str) or not script_text.strip():
        return False

    # Check for prompt leak indicators
    leak_pattern = r'(?:MANTÉ?N EL 100%|prohibido resumir|INSTRUCCIONES DE ESTILO|INSTRUCCIÓN CRÍTICA|system prompt)'
    if re.search(leak_pattern, script_text, re.IGNORECASE):
        return False

    # Check for beat tags
    has_beat_tags = bool(re.search(r'\[(?:BEAT|SECCION|SHOT)\s*\d*\s*:?\s*([^\]]*)\]', script_text, re.IGNORECASE))
    if not has_beat_tags:
        return False

    # Extract beats to verify beat 1 content
    clean_script, beats = extract_story_beats(script_text)
    if not beats or len(beats) == 0:
        return False

    # Verify beat 1 exists
    beat1_text = beats[0].get("text", "").strip()
    if not beat1_text:
        return False

    return True


def calculate_beat_shot_durations(
    word_timestamps: List[Dict[str, Any]],
    beats: List[Dict[str, Any]],
    total_audio_duration: float
) -> List[float]:
    """
    Calculate precise shot durations for each narrative beat using TTS word timing.

    Args:
        word_timestamps: List of dicts with keys 'word', 'start', 'end'.
        beats: List of beat dicts with key 'text'.
        total_audio_duration: Total video audio duration in seconds.

    Returns:
        List of float durations in seconds for each beat/shot.
    """
    if not beats:
        return [total_audio_duration] if total_audio_duration > 0 else [5.0]

    if not word_timestamps or len(word_timestamps) == 0:
        equal_dur = total_audio_duration / len(beats)
        return [round(equal_dur, 3)] * len(beats)

    total_words = len(word_timestamps)
    beat_durations: List[float] = []
    prev_end = 0.0

    beat_word_counts = []
    for b in beats:
        w_list = b["text"].split()
        beat_word_counts.append(max(1, len(w_list)))

    sum_beat_words = sum(beat_word_counts)
    current_word_idx = 0

    for i, count in enumerate(beat_word_counts):
        fraction = count / sum_beat_words
        words_for_beat = int(round(fraction * total_words))
        words_for_beat = max(1, words_for_beat)
        
        target_idx = min(total_words - 1, current_word_idx + words_for_beat - 1)
        if i == len(beat_word_counts) - 1:
            target_idx = total_words - 1

        end_timestamp = float(word_timestamps[target_idx].get("end", total_audio_duration))
        if i == len(beat_word_counts) - 1:
            end_timestamp = max(end_timestamp, total_audio_duration)

        dur = max(1.0, end_timestamp - prev_end)
        beat_durations.append(round(dur, 3))
        prev_end = end_timestamp
        current_word_idx = target_idx + 1

    return beat_durations


def expand_beat_shot_durations(durations: List[float]) -> List[float]:
    """Expands narrative beat shot durations to strictly satisfy 8-15s visual cadence rules."""
    from src.video import expand_durations_to_cadence
    return expand_durations_to_cadence(durations)

