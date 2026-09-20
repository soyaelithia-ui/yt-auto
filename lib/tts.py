"""TTS synthesis and audio helpers (shared core).

Generates WAV narration with word-level timestamps, sanitizes script text for
synthesis and masters voice audio with a loudness-normalized equalized chain.
"""
from __future__ import annotations

import asyncio
import io
import logging
import math
import os
import re
import signal
import subprocess
import sys
import time
import wave
from pathlib import Path

from src.core.errors import TTSSynthesisError

logger = logging.getLogger(__name__)


def _tts_cache_key(text: str, voice: str, rate: str, pitch: str = "+0Hz") -> str:
    """SHA-256 cache key over the exact synthesis inputs (post-sanitization)."""
    import hashlib

    return hashlib.sha256(f"{voice}|{rate}|{pitch}|{text}".encode("utf-8")).hexdigest()



def _tts_cache_enabled() -> bool:
    """Rollback flag: TTS_CACHE=0 disables content-addressed narration reuse."""
    if os.environ.get("TTS_CACHE", "1") != "1":
        return False
    from src.config import is_test_environment

    if is_test_environment() or "pytest" in sys.modules:
        return False
    return True


def _tts_cache_paths(key: str) -> tuple[Path, Path]:
    """Return (wav, json) cache paths for ``key`` under work_root/tts_cache."""
    from src.config import SETTINGS

    base = SETTINGS.work_root / "tts_cache" / key[:2]
    return base / f"{key}.wav", base / f"{key}.json"


def _tts_cache_load(key: str, out_path: Path) -> dict | None:
    """Return a cached result dict for ``key`` or None on miss/corruption."""
    try:
        wav_path, json_path = _tts_cache_paths(key)
        if not wav_path.is_file() or not json_path.is_file():
            return None
        if wav_path.stat().st_size == 0:
            return None
        import json as _json

        meta = _json.loads(json_path.read_text(encoding="utf-8"))
        duration = float(meta.get("duration_sec") or 0.0)
        words = list(meta.get("word_timestamps") or [])
        if duration <= 0:
            return None
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # Copy (never hardlink): run dirs are deleted independently of the cache.
        import shutil as _shutil

        _shutil.copyfile(str(wav_path), str(out_path))
        if not os.path.exists(str(out_path)) or os.path.getsize(str(out_path)) == 0:
            return None
        return {
            "audio_path": str(out_path),
            "duration_sec": duration,
            "word_timestamps": words,
            "provider": "edge-tts",
            "voice": meta.get("voice", ""),
            "boundary_type": "WordBoundary",
            "cache_hit": True,
        }
    except Exception:
        logger.debug("TTS cache load failed for key %s", key[:12], exc_info=True)
        return None


def _tts_cache_store(key: str, audio_path: Path, result: dict) -> None:
    """Persist a successful synthesis into the content-addressed cache."""
    try:
        wav_path, json_path = _tts_cache_paths(key)
        wav_path.parent.mkdir(parents=True, exist_ok=True)
        import shutil as _shutil

        _shutil.copyfile(str(audio_path), str(wav_path))
        import json as _json

        json_path.write_text(
            _json.dumps(
                {
                    "duration_sec": result.get("duration_sec"),
                    "word_timestamps": result.get("word_timestamps") or [],
                    "voice": result.get("voice"),
                    "provider": result.get("provider"),
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
    except Exception:
        logger.debug("TTS cache store failed for key %s", key[:12], exc_info=True)


def _run_subproc(
    cmd: list[str],
    timeout: float | None = 60,
    check: bool = True,
    capture_output: bool = True,
    text: bool = True,
    start_new_session: bool = True,
) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            cmd,
            timeout=timeout,
            check=check,
            capture_output=capture_output,
            text=text,
            start_new_session=start_new_session,
        )
    except subprocess.TimeoutExpired:
        raise

DEFAULT_FALLBACK_TEXT = (
    "Secreto aterrador oculto en la oscuridad. Historias de terror narradas "
    "con intensidad para los amantes del miedo nocturno."
)

_HEADER_LINE = re.compile(
    r"^\s*(?:#+\s*|\*{1,2}\s*)?(?:título|title)\s*[:：].*$",
    re.IGNORECASE | re.UNICODE,
)
_MARKDOWN_LEADERS = re.compile(r"^\s*(?:[-*_>#+]+\s+)+")


def sanitize_text_for_tts(text: str | None) -> str:
    """Sanitize narration text before Edge-TTS synthesis."""
    if not text:
        return ""

    raw = str(text)

    # 0. Apply strict Pre-TTS cleaner if available
    try:
        from src.sanitizer import limpiar_texto_para_tts
        raw = limpiar_texto_para_tts(raw)
    except Exception as exc:
        logger.warning("Pre-TTS cleaner exception: %s", exc)

    # 1. Strip HTTP error pages, server error strings, and URLs
    raw = re.sub(r"(?i)\bError\s+\d{3}\b(?:\s*\([^)]*\))?", "", raw)
    raw = re.sub(r"(?i)\b(?:Server\s+Error|Gateway\s+Time-?out|Access\s+Denied|Page\s+Not\s+Found)\b", "", raw)
    raw = re.sub(r"(?i)\bhttps?://\S+", "", raw)

    # 2. Convert subreddit mentions to natural speech (r/nosleep -> sub reddit nosleep)
    raw = re.sub(r"\br/([a-zA-Z0-9_]+)\b", r"sub reddit \1", raw)

    # 3. Clean slashes so TTS never speaks "barra" or "diagonal"
    raw = re.sub(r"\bkm/h\b", "kilómetros por hora", raw, flags=re.IGNORECASE)
    raw = re.sub(r"\by/o\b", "y o", raw, flags=re.IGNORECASE)
    raw = re.sub(r"(\w+)/(\w+)", r"\1 \2", raw)
    raw = raw.replace("/", " ")

    # 4. Strip markdown formatting (*, #, _, ~, `, |, [], {}, >) and structural labels
    raw = strip_markdown_for_tts(raw)

    # 5. Filter empty or header lines
    lines = []
    for line in raw.splitlines():
        if _HEADER_LINE.match(line):
            continue
        if re.match(r"(?i)^\s*(?:secci[óo]n|cap[íi]tulo|parte)\s+[a-záéíóú0-9IVXLCDMivxlcdm]+[:.-]?\s*$", line):
            continue
        cleaned = _MARKDOWN_LEADERS.sub("", line, count=1) if lines else line
        if not lines and cleaned.strip() == "":
            continue
        lines.append(cleaned)
    return "\n".join(lines).strip()


def strip_markdown_for_tts(text: str | None) -> str:
    """Remove markdown emphasis markers and structural labels that would leak into synthesized audio."""
    if not text:
        return ""
    cleaned = str(text)
    from src.sanitizer import (
        RE_MARKDOWN_HEADERS,
        RE_STRUCTURAL_HEADERS_PREFIX,
        RE_STRUCTURAL_HEADERS_LINE,
        RE_CHAPTER_HEADER_LINE,
        RE_STRUCTURAL_HEADERS_INLINE,
        RE_TITLE_PREFIX,
        RE_MARKDOWN_BOLD,
        RE_MARKDOWN_ITALIC,
        RE_MARKDOWN_CHARS_ALL,
    )

    # Protect dramatic pause tags from bracket removal
    pause_tokens: dict[str, str] = {}
    def _protect_pause(match):
        tok = f"__DRAMATIC_PAUSE_TOKEN_{len(pause_tokens)}__"
        pause_tokens[tok] = match.group(0)
        return tok

    cleaned = re.sub(r"\[\s*(?:PAUSA|PAUSE|SILENCE)[^\]]*\]", _protect_pause, cleaned, flags=re.IGNORECASE)

    # Strip markdown headers (e.g. # Header, ## Subheader, ### Capítulo 1)
    cleaned = RE_MARKDOWN_HEADERS.sub("", cleaned)
    # Strip unbracketed and bracketed structural labels (Sección Primera:, Capítulo 1:, etc.)
    cleaned = RE_STRUCTURAL_HEADERS_PREFIX.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_LINE.sub("", cleaned)
    cleaned = RE_CHAPTER_HEADER_LINE.sub("", cleaned)
    cleaned = RE_STRUCTURAL_HEADERS_INLINE.sub("", cleaned)
    cleaned = RE_TITLE_PREFIX.sub("", cleaned)
    # Strip bold / italics / links / markdown characters
    cleaned = RE_MARKDOWN_BOLD.sub(r"\1", cleaned)
    cleaned = RE_MARKDOWN_ITALIC.sub(r"\1", cleaned)
    cleaned = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", cleaned)
    cleaned = RE_MARKDOWN_CHARS_ALL.sub("", cleaned)

    # Restore protected pause tags
    for tok, tag in pause_tokens.items():
        cleaned = cleaned.replace(tok, tag)

    return cleaned.strip()


def _word_timestamps_for(text: str, duration_sec: float) -> list[dict]:
    from lib.audio import strip_dramatic_pauses
    clean = strip_dramatic_pauses(text)
    words = [w for w in re.split(r"\s+", clean.strip()) if w]
    if not words:
        return []
    step = duration_sec / len(words)
    stamps = []
    for idx, word in enumerate(words):
        start = round(idx * step, 3)
        end = round((idx + 1) * step, 3)
        stamps.append({"word": word, "start": start, "end": end})
    if stamps:
        stamps[-1]["end"] = duration_sec
    return stamps


# ---------------------------------------------------------------------------
# Chunked synthesis (YT_TTS_CHUNKED=1). Default OFF: legacy single-stream path.
# ---------------------------------------------------------------------------

_CHUNK_GAP_SEC = 0.15  # hueco conservador entre chunks para desplazar timestamps
_CHUNK_MAX_RETRIES = 3


def _is_chunked_enabled() -> bool:
    """Rollback flag: YT_TTS_CHUNKED=1 activa síntesis por chunks con reintento parcial."""
    return os.environ.get("YT_TTS_CHUNKED", "0") == "1"


def _split_script_chunks(text: str, max_chars: int = 1800) -> list[str]:
    """Split narration into <=max_chars chunks at paragraph/sentence boundaries.

    Prefiere '\n\n', luego finales de oración (.!?… + espacio); nunca corta a
    mitad de palabra. Determinista; devuelve solo chunks no vacíos.
    """
    if not text:
        return []
    raw = text.strip()
    if not raw:
        return []

    # 1) Split on paragraph boundaries, then pack paragraphs greedily.
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", raw) if p.strip()]
    if not paragraphs:
        paragraphs = [raw]

    def _pack(pieces: list[str], limit: int) -> list[str]:
        packed: list[str] = []
        current = ""
        for piece in pieces:
            candidate = f"{current} {piece}".strip() if current else piece
            if len(candidate) <= limit:
                current = candidate
            else:
                if current:
                    packed.append(current)
                    current = piece if len(piece) <= limit else ""
                    if not current:
                        continue
                # single oversized piece -> sentence-level split
                sentences = [
                    s.strip()
                    for s in re.split(r"(?<=[.!?…])\s+", piece)
                    if s.strip()
                ]
                sub_current = ""
                for sentence in sentences:
                    sub_candidate = f"{sub_current} {sentence}".strip() if sub_current else sentence
                    if len(sub_candidate) <= limit:
                        sub_current = sub_candidate
                        continue
                    if sub_current:
                        packed.append(sub_current)
                    # oversized single sentence -> hard word-boundary split
                    while len(sentence) > limit:
                        cut = sentence.rfind(" ", 0, limit)
                        if cut <= 0:
                            cut = limit
                        packed.append(sentence[:cut].strip())
                        sentence = sentence[cut:].strip()
                    sub_current = sentence
                if sub_current:
                    current = sub_current
            if len(current) > limit:
                # current can only exceed limit when piece itself fit poorly
                words = current.split(" ")
                buf = ""
                for w in words:
                    cand = f"{buf} {w}".strip() if buf else w
                    if len(cand) > limit and buf:
                        packed.append(buf)
                        buf = w
                        while len(buf) > limit:
                            packed.append(buf[:limit])
                            buf = buf[limit:]
                    else:
                        buf = cand
                current = buf
        if current:
            packed.append(current)
        return [c for c in (p.strip() for p in packed) if c]

    merged_pieces: list[str] = []
    for para in paragraphs:
        if len(para) <= max_chars:
            merged_pieces.append(para)
        else:
            merged_pieces.extend(_split_oversized_paragraph(para, max_chars))
    return _merge_small_trailing(_pack(merged_pieces, max_chars))


def _split_oversized_paragraph(para: str, limit: int) -> list[str]:
    """Split one paragraph over the limit into sentence/word-bounded pieces."""
    sentences = [s.strip() for s in re.split(r"(?<=[.!?…])\s+", para) if s.strip()]
    pieces: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            pieces.append(current)
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit)
            if cut <= 0:
                cut = limit
            pieces.append(sentence[:cut].strip())
            sentence = sentence[cut:].strip()
        current = sentence
    if current:
        pieces.append(current)
    return pieces


def _merge_small_trailing(chunks: list[str], min_chars: int = 80) -> list[str]:
    """Merge a tiny trailing chunk into its predecessor to avoid stub segments."""
    if len(chunks) >= 2 and len(chunks[-1]) < min_chars:
        chunks = chunks[:-2] + [f"{chunks[-2]} {chunks[-1]}".strip()]
    return chunks


def _synthesize_chunk(
    chunk_text: str,
    voice: str,
    rate: str,
    pitch: str = "+0Hz",
) -> tuple[bytes, list[dict]]:
    """Synthesize ONE chunk in memory; boundaries are relative to chunk start."""
    import edge_tts

    mp3_buf = io.BytesIO()
    words: list[dict] = []

    async def _stream():
        comm = edge_tts.Communicate(chunk_text, voice, rate=rate, pitch=pitch)
        async for chunk in comm.stream():
            if chunk.get("type") == "audio":
                mp3_buf.write(chunk["data"])
            elif chunk.get("type") in ("WordBoundary", "SentenceBoundary"):
                words.append({
                    "word": chunk.get("text", ""),
                    "start": chunk.get("offset", 0) / 10000000.0,
                    "end": (chunk.get("offset", 0) + chunk.get("duration", 0)) / 10000000.0,
                })

    asyncio.run(_stream())
    data = mp3_buf.getvalue()
    if not data:
        raise TTSSynthesisError(
            f"Chunk synthesis produced empty audio ({len(chunk_text)} chars)",
            voice=voice,
            provider="edge-tts",
        )
    return data, words


def synthesize_chunked_mp3(
    text: str,
    voice: str,
    rate: str,
    pitch: str = "+0Hz",
    *,
    max_chars: int = 1800,
) -> tuple[bytes, list[dict]]:
    """Synthesize per-chunk with per-chunk retry; concatenate MP3 bytes.

    Los offsets de WordBoundary se desplazan por la duración acumulada de los
    chunks previos (último 'end' + hueco conservador de 0.15s): es una
    aproximación porque el hueco real depende del contenedor concatenado.
    """
    from src.core.errors import TTSSynthesisError as _TTS_ERR

    chunks = _split_script_chunks(text, max_chars=max_chars)
    if len(chunks) <= 1:
        # single chunk keeps identical semantics to the whole-text path
        chunks = chunks or [""]

    audio = io.BytesIO()
    all_words: list[dict] = []
    offset_shift = 0.0
    last_error: Exception | None = None

    for idx, chunk_text in enumerate(chunks):
        data: bytes | None = None
        words: list[dict] | None = None
        attempt = 0
        while attempt < _CHUNK_MAX_RETRIES:
            attempt += 1
            try:
                try:
                    data, words = _synthesize_chunk(chunk_text, voice, rate, pitch=pitch)
                except TypeError as te:
                    if "pitch" in str(te) or "unexpected keyword" in str(te):
                        data, words = _synthesize_chunk(chunk_text, voice, rate)
                    else:
                        raise
                break
            except Exception as exc:  # noqa: BLE001 - retry per chunk only
                last_error = exc
                logger.warning(
                    "Chunk %d/%d synthesis attempt %d failed: %s",
                    idx + 1, len(chunks), attempt, exc,
                )
                time.sleep(1.0 * attempt)
        if data is None or words is None:
            raise _TTS_ERR(
                f"Chunk {idx + 1}/{len(chunks)} failed after "
                f"{_CHUNK_MAX_RETRIES} attempts: {last_error}",
                voice=voice,
                provider="edge-tts",
            ) from last_error

        audio.write(data)
        shifted = [
            {
                "word": w["word"],
                "start": round(w["start"] + offset_shift, 6),
                "end": round(w["end"] + offset_shift, 6),
            }
            for w in words
        ]
        all_words.extend(shifted)

        # Duración acumulada: último end del chunk + hueco conservador.
        if shifted:
            offset_shift = shifted[-1]["end"] + _CHUNK_GAP_SEC
        elif data:
            # sin boundaries no podemos derivar duración; el shift queda igual
            logger.debug("Chunk %d sin WordBoundaries; offset no avanzado", idx + 1)

    return audio.getvalue(), all_words


def generate_audio(
    script: str | None = None,
    audio_path: str | None = None,
    target_duration_sec: float = 605.0,
    channel: str = "moku",
    **kwargs,
) -> dict:
    """Generate narration audio using Edge-TTS with word-level timestamps."""
    script_text = kwargs.get("script_text", script) if script is not None else script
    if script is None and "script_text" not in kwargs:
        script_text = None
    output = kwargs.get("output_audio_path") or audio_path
    target = float(kwargs.get("target_duration_sec", target_duration_sec))
    if target <= 0:
        target = 605.0

    if output is None:
        raise ValueError("generate_audio requires an output audio path")
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    text = sanitize_text_for_tts(script_text if script_text is not None else "")
    if not text.strip():
        text = DEFAULT_FALLBACK_TEXT

    from src.branding import resolve_channel_key
    from src.core.lanes import resolve_voice_for_lane, resolve_voice_profile_for_lane

    lane_arg = kwargs.get("lane") or kwargs.get("lane_profile") or kwargs.get("lane_id")
    profile_dict: dict = {}
    try:
        profile_dict = resolve_voice_profile_for_lane(lane_arg, channel=channel)
    except Exception:
        pass

    target_voice = kwargs.get("voice")
    if not target_voice:
        target_voice = profile_dict.get("id") or resolve_voice_for_lane(lane_arg, channel=channel)

    target_rate = kwargs.get("rate")
    if not target_rate:
        if hasattr(lane_arg, "voice_rate") and lane_arg.voice_rate:
            target_rate = str(lane_arg.voice_rate)
        elif isinstance(lane_arg, dict) and lane_arg.get("voice_rate"):
            target_rate = str(lane_arg["voice_rate"])
        elif profile_dict.get("speed"):
            target_rate = str(profile_dict["speed"])
        elif target_duration_sec and float(target_duration_sec) >= 600.0:
            target_rate = "+0%"
        else:
            target_rate = "+0%"

    target_pitch = kwargs.get("pitch")
    if not target_pitch:
        if profile_dict.get("pitch"):
            target_pitch = str(profile_dict["pitch"])
        else:
            target_pitch = "+0Hz"

    cache_key = None
    if _tts_cache_enabled():
        cache_key = _tts_cache_key(text, target_voice, str(target_rate), str(target_pitch))
        cached = _tts_cache_load(cache_key, out_path)
        if cached is not None:
            logger.info("TTS cache hit for key %s", cache_key[:12])
            return cached

    is_test = (
        os.environ.get("TEST_MODE") == "1"
        or (os.environ.get("TEST_MODE") != "0" and ("PYTEST_CURRENT_TEST" in os.environ or "pytest" in sys.modules))
    )

    from lib.audio import (
        parse_dramatic_pauses,
        insert_dramatic_pauses_to_audio,
        strip_dramatic_pauses,
        generate_silence_audio,
    )

    pause_segments = parse_dramatic_pauses(text)
    has_dramatic_pauses = any(seg.get("has_pause") for seg in pause_segments) and len(pause_segments) > 1

    if has_dramatic_pauses:
        chunk_paths: list[str] = []
        pause_durations: list[float] = []
        all_chunk_words: list[list[dict]] = []
        temp_files_to_clean: list[str] = []

        total_words_count = max(1, len(strip_dramatic_pauses(text).split()))
        cumulative_pause_time = sum(seg.get("pause_after", 0.0) for seg in pause_segments)
        effective_speech_target = max(1.0, target - cumulative_pause_time)

        try:
            for s_idx, seg in enumerate(pause_segments):
                seg_text = seg.get("text", "").strip()
                p_dur = seg.get("pause_after", 0.0)
                pause_durations.append(p_dur)

                if not seg_text:
                    continue

                chunk_out = str(out_path) + f".tmp_pause_seg_{s_idx}.wav"
                temp_files_to_clean.append(chunk_out)

                seg_word_count = len(seg_text.split())
                chunk_target_sec = max(0.5, (seg_word_count / total_words_count) * effective_speech_target)

                seg_res = generate_audio(
                    script_text=seg_text,
                    output_audio_path=chunk_out,
                    target_duration_sec=chunk_target_sec,
                    channel=channel,
                    voice=target_voice,
                    rate=target_rate,
                    pitch=target_pitch,
                    lane=lane_arg,
                    **{k: v for k, v in kwargs.items() if k not in ("script", "script_text", "output_audio_path", "target_duration_sec", "voice", "rate", "pitch", "lane", "lane_profile", "lane_id")},
                )
                chunk_paths.append(chunk_out)
                all_chunk_words.append(seg_res.get("word_timestamps", []))

            out_file, shifted_timestamps = insert_dramatic_pauses_to_audio(
                audio_paths=chunk_paths,
                pause_durations=pause_durations[:len(chunk_paths)],
                output_path=str(out_path),
                word_timestamps_per_chunk=all_chunk_words,
            )
            final_dur = get_audio_duration(str(out_path))

            result = {
                "audio_path": str(out_path),
                "duration_sec": final_dur,
                "word_timestamps": shifted_timestamps,
                "provider": "edge-tts-with-pauses" if not is_test else "synthetic-test-pcm-with-pauses",
                "voice": target_voice,
                "rate": target_rate,
                "pitch": target_pitch,
                "boundary_type": "WordBoundary",
            }
            if _tts_cache_enabled() and cache_key:
                _tts_cache_store(cache_key, out_path, result)
            return result
        finally:
            for tf in temp_files_to_clean:
                if os.path.exists(tf):
                    try:
                        os.remove(tf)
                    except OSError:
                        pass

    if is_test:
        import math
        import struct
        import wave
        sample_rate = 8000
        duration_sec = target_duration_sec if target_duration_sec and target_duration_sec > 0 else 10.0
        num_samples = int(sample_rate * duration_sec)
        # Tono senoidal de baja amplitud en vez de silencio digital puro:
        # loudnorm sobre cero exacto emite frames NaN y el encoder AAC falla
        # ("Input contains (near) NaN/+-Inf") en las renders reales del suite.
        period = 40  # muestras de un ciclo de 200 Hz @ 8 kHz
        cycle = b"".join(
            struct.pack("<h", int(1200 * math.sin(2 * math.pi * i / period)))
            for i in range(period)
        )
        full, rest = divmod(num_samples, period)
        payload = cycle * full + cycle[: rest * 2]
        with wave.open(str(out_path), "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(sample_rate)
            wav_file.writeframes(payload)
        return {
            "audio_path": str(out_path),
            "duration_sec": duration_sec,
            "word_timestamps": _word_timestamps_for(text, duration_sec),
            "provider": "synthetic-test-pcm",
            "voice": target_voice,
            "rate": target_rate,
            "pitch": target_pitch,
            "boundary_type": "WordBoundary",
        }

    # Attempt Edge-TTS synthesis
    tracked_temp_files: set[str] = set()
    try:
        if _is_chunked_enabled():
            import edge_tts  # noqa: F401 - parity with legacy branch availability check

            mp3_tmp = str(out_path) + ".tmp.mp3"
            tmp_wav = str(out_path) + ".tmp.wav"
            tracked_temp_files.add(mp3_tmp)
            tracked_temp_files.add(tmp_wav)
            mp3_bytes, words = synthesize_chunked_mp3(text, target_voice, target_rate, pitch=target_pitch)
            with open(mp3_tmp, "wb") as f:
                f.write(mp3_bytes)
            _run_subproc(
                ["ffmpeg", "-y", "-i", mp3_tmp, "-ar", "44100", "-ac", "2", tmp_wav],
                check=True,
                timeout=120,
            )
            if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 0:
                os.replace(tmp_wav, str(out_path))
            dur = get_audio_duration(str(out_path))
            if not words:
                words = _word_timestamps_for(text, dur)
            _result = {
                "audio_path": str(out_path),
                "duration_sec": dur,
                "word_timestamps": words,
                "provider": "edge-tts",
                "voice": target_voice,
                "rate": target_rate,
                "pitch": target_pitch,
                "boundary_type": "WordBoundary",
            }
            if _tts_cache_enabled() and cache_key:
                _tts_cache_store(cache_key, out_path, _result)
            return _result
        try:
            import asyncio
            import edge_tts

            async def _synth_edge():
                mp3_tmp = str(out_path) + ".tmp.mp3"
                tmp_wav = str(out_path) + ".tmp.wav"
                tracked_temp_files.add(mp3_tmp)
                tracked_temp_files.add(tmp_wav)
                comm = edge_tts.Communicate(text, target_voice, rate=target_rate, pitch=target_pitch)
                words: list[dict] = []
                with open(mp3_tmp, "wb") as f:
                    async for chunk in comm.stream():
                        if chunk.get("type") == "audio":
                            f.write(chunk["data"])
                        elif chunk.get("type") in ("WordBoundary", "SentenceBoundary"):
                            words.append({
                                "word": chunk.get("text", ""),
                                "start": chunk.get("offset", 0) / 10000000.0,
                                "end": (chunk.get("offset", 0) + chunk.get("duration", 0)) / 10000000.0,
                            })
                _run_subproc(
                    ["ffmpeg", "-y", "-i", mp3_tmp, "-ar", "44100", "-ac", "2", tmp_wav],
                    check=True,
                    timeout=60,
                )
                if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 0:
                    os.replace(tmp_wav, str(out_path))
                dur = get_audio_duration(str(out_path))
                if not words:
                    words = _word_timestamps_for(text, dur)
                return dur, words

            duration_sec, word_timestamps = asyncio.run(_synth_edge())
            _result = {
                "audio_path": str(out_path),
                "duration_sec": duration_sec,
                "word_timestamps": word_timestamps,
                "provider": "edge-tts",
                "voice": target_voice,
                "rate": target_rate,
                "pitch": target_pitch,
                "boundary_type": "WordBoundary",
            }
            if _tts_cache_enabled() and cache_key:
                _tts_cache_store(cache_key, out_path, _result)
            return _result
        except Exception as exc:
            logger.warning("Edge-TTS synthesis primary attempt failed: %s. Initiating retries...", exc)
            for attempt in range(1, 3):
                try:
                    time.sleep(1.0 * attempt)
                    mp3_tmp = str(out_path) + f".tmp.{attempt}.mp3"
                    tmp_wav = str(out_path) + f".tmp.{attempt}.wav"
                    tracked_temp_files.add(mp3_tmp)
                    tracked_temp_files.add(tmp_wav)
                    comm = edge_tts.Communicate(text, target_voice, rate=target_rate, pitch=target_pitch)
                    
                    async def _stream_to_file(file_path):
                        ret_words: list[dict] = []
                        with open(file_path, "wb") as f:
                            async for chunk in comm.stream():
                                if chunk.get("type") == "audio":
                                    f.write(chunk["data"])
                                elif chunk.get("type") in ("WordBoundary", "SentenceBoundary"):
                                    ret_words.append({
                                        "word": chunk.get("text", ""),
                                        "start": chunk.get("offset", 0) / 10000000.0,
                                        "end": (chunk.get("offset", 0) + chunk.get("duration", 0)) / 10000000.0,
                                    })
                        return ret_words

                    words = asyncio.run(_stream_to_file(mp3_tmp))
                    _run_subproc(
                        ["ffmpeg", "-y", "-i", mp3_tmp, "-ar", "44100", "-ac", "2", tmp_wav],
                        check=True,
                        timeout=60,
                    )
                    if os.path.exists(tmp_wav) and os.path.getsize(tmp_wav) > 0:
                        os.replace(tmp_wav, str(out_path))
                    dur = get_audio_duration(str(out_path))
                    if dur > 0:
                        total_expected_words = len([w for w in text.split() if w.strip()])
                        if not words or len(words) < max(4, total_expected_words // 2):
                            words = _word_timestamps_for(text, dur)
                        _result = {
                            "audio_path": str(out_path),
                            "duration_sec": dur,
                            "word_timestamps": words,
                            "provider": "edge-tts",
                            "voice": target_voice,
                            "rate": target_rate,
                            "pitch": target_pitch,
                            "boundary_type": "WordBoundary",
                        }
                        if _tts_cache_enabled() and cache_key:
                            _tts_cache_store(cache_key, out_path, _result)
                        return _result
                except Exception as retry_exc:
                    logger.warning("Edge-TTS retry attempt %d failed: %s", attempt, retry_exc)

            raise TTSSynthesisError(
                f"Edge-TTS synthesis failed after retries for voice '{target_voice}': {exc}",
                voice=target_voice,
                provider="edge-tts",
                details={"voice": target_voice, "target_duration_sec": target_duration_sec},
            ) from exc
    finally:
        for tf in tracked_temp_files:
            if os.path.exists(tf):
                try:
                    os.remove(tf)
                except OSError:
                    pass


def get_wav_duration(path: str | os.PathLike) -> float:
    """Return audio duration in seconds; 0.0 for missing/corrupt files.

    Parses WAV headers via the stdlib (no subprocess); probes MP3/AAC/etc.
    through ffprobe only when the file starts with recognizable
    compressed-audio magic (ID3 or MPEG sync), avoiding subprocess calls
    for arbitrary non-audio payloads.
    """
    if not os.path.exists(str(path)):
        return 0.0
    try:
        with wave.open(str(path), "rb") as wav:
            return wav.getnframes() / max(wav.getframerate(), 1)
    except (wave.Error, OSError, ValueError) as exc:
        logger.debug("WAV header duration probe skipped (%s): %s", path, exc)
    try:
        with open(str(path), "rb") as fh:
            head = fh.read(16)
        if not (head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 0xFF and (head[1] & 0xE0) == 0xE0)):
            return 0.0
        result = _run_subproc(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=False, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        logger.debug("FFprobe duration probe skipped (%s): %s", path, exc)
    return 0.0


def get_audio_duration(path: str | os.PathLike) -> float:
    """Probe audio duration via ffprobe with WAV fallback."""
    if not os.path.exists(str(path)):
        return 0.0
    try:
        result = _run_subproc(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            check=False, timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return float(result.stdout.strip())
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        logger.debug("FFprobe get_audio_duration skipped (%s): %s", path, exc)
    return get_wav_duration(path)


def validate_audio_artifact(path: str | os.PathLike, minimum_duration: float = 0.0) -> dict:
    """Validate a synthesized audio artifact exists and meets the duration gate."""
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        raise TTSSynthesisError(f"Audio artifact missing or empty: {p}", details={"path": str(p)})
    duration = get_wav_duration(p)
    if minimum_duration > 0 and duration < minimum_duration:
        raise TTSSynthesisError(
            f"Audio artifact {p.name} is too short: {duration:.2f}s < {minimum_duration:.2f}s",
            details={"path": str(p), "duration": duration, "min_duration": minimum_duration},
        )
    return {"passed": True, "path": str(p), "duration_sec": duration}


def validate_word_boundaries(
    timestamps: list[dict],
    duration_sec: float,
    expected_word_count: int | None = None,
) -> dict:
    """Validate word timestamps are monotonic and cover the narration.

    Raises RuntimeError when start times are not monotonically increasing.
    """
    if not timestamps:
        raise ValueError("Word timestamp list is empty")
    previous = None
    for stamp in timestamps:
        start = stamp.get("start", 0.0)
        if previous is not None and start < previous - 1e-6:
            raise RuntimeError(
                "Los timestamps de palabras deben ser monotónicos (empiezan en el pasado)"
            )
        if stamp.get("end", start) < start - 1e-6:
            raise RuntimeError("Los timestamps de palabras no son monotónicos")
        previous = start
    start0 = timestamps[0].get("start", 0.0)
    end_last = timestamps[-1].get("end", duration_sec)
    coverage = 0.0
    if duration_sec > 0:
        coverage = max(0.0, min(1.0, (end_last - start0) / duration_sec))
    return {
        "passed": True,
        "word_count": len(timestamps),
        "temporal_coverage": coverage,
        "start": start0,
        "end": end_last,
    }


def master_voice_audio(
    audio_path: str | os.PathLike,
    target_lufs: float = -14.0,
    true_peak_dbtp: float = -1.5,
    **kwargs: Any,
) -> str:
    """Master voice audio: 120 Hz EQ cut + EBU R128 loudnorm (I=-14.0 LUFS).

    Se omite cuando YT_FOLD_MASTERING=1 (la masterización corre en línea
    dentro del filter_complex de build_audio_chain).
    """
    path = str(audio_path)
    tmp_out = path + ".tmp.master.wav"
    cmd = [
        "ffmpeg", "-y",
        "-i", path,
        "-af", f"equalizer=f=120:t=q:w=1:g=-2,loudnorm=I={target_lufs}:TP={true_peak_dbtp}:LRA=11",
        "-ar", "48000", "-ac", "2",
        tmp_out,
    ]
    try:
        res = _run_subproc(cmd, check=True, timeout=120)
        if os.path.exists(tmp_out) and os.path.getsize(tmp_out) > 0:
            os.replace(tmp_out, path)
    except Exception as exc:
        logger.warning("master_voice_audio failed for %s: %s", path, exc)
    finally:
        if os.path.exists(tmp_out):
            try:
                os.remove(tmp_out)
            except OSError:
                pass
    return path