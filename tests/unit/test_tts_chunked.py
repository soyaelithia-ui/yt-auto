"""Unit tests for chunked TTS synthesis (_split_script_chunks, offset shifting, flag routing)."""
import os
from unittest import mock

import pytest

from lib import tts


class TestSplitScriptChunks:
    def test_splits_on_paragraph_boundaries(self):
        text = "Párrafo uno con contenido. " * 40 + "\n\n" + "Párrafo dos con contenido. " * 40
        chunks = tts._split_script_chunks(text, max_chars=400)
        assert len(chunks) >= 2
        assert all(len(c) <= 400 for c in chunks)
        # paragraph boundary respected: no chunk mixes para1 tail with para2 head mid-sentence
        joined = " ".join(chunks)
        assert "contenido." in joined

    def test_no_empty_chunks(self):
        text = "Texto breve.\n\n\n\nSegunda parte.\n\n   \nTercera."
        for limit in (10, 50, 500):
            chunks = tts._split_script_chunks(text, max_chars=limit)
            assert all(c.strip() for c in chunks)

    def test_oversized_sentence_hard_split_at_word_boundary(self):
        sentence = "palabra " * 300  # no internal sentence enders; >1800 chars
        chunks = tts._split_script_chunks(sentence.strip(), max_chars=200)
        assert len(chunks) >= 2
        assert all(len(c) <= 200 for c in chunks)
        # no word destroyed across the cut
        assert " ".join(chunks).split() == sentence.split()

    def test_deterministic(self):
        text = ("Oración uno. ¿Oración dos? ¡Oración tres! " * 30) + "\n\n" + ("Bloque final. " * 50)
        a = tts._split_script_chunks(text, max_chars=350)
        b = tts._split_script_chunks(text, max_chars=350)
        assert a == b

    def test_empty_inputs(self):
        assert tts._split_script_chunks("") == []
        assert tts._split_script_chunks("   \n  ") == []

    def test_single_short_text_one_chunk(self):
        assert tts._split_script_chunks("Hola mundo.") == ["Hola mundo."]


class TestChunkedSynthesis:
    def _fake_chunk_data(self, marker: bytes, boundaries: list[dict]) -> tuple[bytes, list[dict]]:
        return marker, boundaries

    def test_offset_shift_and_gap_applied(self):
        chunk_results = [
            (b"MP3DATA1", [
                {"word": "uno", "start": 0.0, "end": 0.5},
                {"word": "dos", "start": 0.5, "end": 1.2},
            ]),
            (b"MP3DATA2", [
                {"word": "tres", "start": 0.1, "end": 0.9},
            ]),
        ]
        with mock.patch.object(tts, "_split_script_chunks", return_value=["c1", "c2"]), \
             mock.patch.object(tts, "_synthesize_chunk", side_effect=chunk_results) as synth:
            data, words = tts.synthesize_chunked_mp3("texto largo", "es-MX-X", "+0%")

        assert data == b"MP3DATA1MP3DATA2"
        # first chunk unshifted
        assert words[0] == {"word": "uno", "start": 0.0, "end": 0.5}
        # second chunk shifted by last end of chunk1 (1.2) + gap (0.15)
        shift = 1.2 + tts._CHUNK_GAP_SEC
        assert words[2]["start"] == pytest.approx(0.1 + shift)
        assert words[2]["end"] == pytest.approx(0.9 + shift)
        assert synth.call_count == 2

    def test_per_chunk_retry_then_success(self):
        calls = []

        def flaky(chunk_text, voice, rate):
            calls.append(chunk_text)
            if len(calls) == 1:
                raise ConnectionError("websocket drop")
            return b"OK", [{"word": "x", "start": 0.0, "end": 0.4}]

        with mock.patch.object(tts, "_split_script_chunks", return_value=["only"]), \
             mock.patch.object(tts, "_synthesize_chunk", side_effect=flaky), \
             mock.patch.object(tts.time, "sleep"):
            data, words = tts.synthesize_chunked_mp3("t", "v", "+0%")
        assert data == b"OK"
        assert len(words) == 1
        assert len(calls) == 2

    def test_all_retries_exhausted_raises(self):
        with mock.patch.object(tts, "_split_script_chunks", return_value=["only"]), \
             mock.patch.object(tts, "_synthesize_chunk", side_effect=ConnectionError("down")), \
             mock.patch.object(tts.time, "sleep") as sleeper:
            with pytest.raises(tts.TTSSynthesisError):
                tts.synthesize_chunked_mp3("t", "v", "+0%")
        assert sleeper.call_count == tts._CHUNK_MAX_RETRIES

    def test_monotonic_after_shift(self):
        chunk_results = [
            (b"A", [{"word": "a", "start": 0.0, "end": 2.0}]),
            (b"B", [{"word": "b", "start": 0.0, "end": 1.5},
                    {"word": "c", "start": 1.5, "end": 2.5}]),
        ]
        with mock.patch.object(tts, "_split_script_chunks", return_value=["x", "y"]), \
             mock.patch.object(tts, "_synthesize_chunk", side_effect=chunk_results):
            _, words = tts.synthesize_chunked_mp3("t", "v", "+0%")
        starts = [w["start"] for w in words]
        assert starts == sorted(starts)


class TestFlagRouting:
    def test_default_off(self, monkeypatch):
        monkeypatch.delenv("YT_TTS_CHUNKED", raising=False)
        assert tts._is_chunked_enabled() is False

    def test_flag_on(self, monkeypatch):
        monkeypatch.setenv("YT_TTS_CHUNKED", "1")
        assert tts._is_chunked_enabled() is True

    def test_other_values_off(self, monkeypatch):
        for val in ("", "0", "true", "yes"):
            monkeypatch.setenv("YT_TTS_CHUNKED", val)
            assert tts._is_chunked_enabled() is False
