"""Tests for plan item 3f — sha-keyed narration cache (TTS_CACHE).

The cache is content-addressed over (voice, rate, sanitized text); hits skip
synthesis entirely. TEST_MODE / TTS_CACHE=0 bypass it unconditionally.
"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lib.tts import (
    _tts_cache_enabled,
    _tts_cache_key,
    _tts_cache_load,
    _tts_cache_paths,
    _tts_cache_store,
)


class TestCacheKey(unittest.TestCase):
    def test_key_sensitivity(self):
        base = _tts_cache_key("hola", "v1", "+0%")
        self.assertEqual(base, _tts_cache_key("hola", "v1", "+0%"))
        self.assertNotEqual(base, _tts_cache_key("hola ", "v1", "+0%"))
        self.assertNotEqual(base, _tts_cache_key("hola", "v2", "+0%"))
        self.assertNotEqual(base, _tts_cache_key("hola", "v1", "+20%"))


class TestCacheEnabled(unittest.TestCase):
    def test_flag_zero_disables(self):
        with mock.patch.dict(os.environ, {"TTS_CACHE": "0"}):
            self.assertFalse(_tts_cache_enabled())

    def test_test_mode_bypasses(self):
        with mock.patch.dict(os.environ, {"TTS_CACHE": "1", "TEST_MODE": "1"}), \
                mock.patch("src.config.is_test_environment", return_value=True):
            self.assertFalse(_tts_cache_enabled())


class TestStoreLoadRoundTrip(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="tts_cache_")
        work_root = Path(self.tmp.name)
        patcher = mock.patch("src.config.SETTINGS")
        settings_mock = patcher.start()
        settings_mock.work_root = work_root
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)

    def _sample_result(self, audio_path: Path) -> dict:
        return {
            "audio_path": str(audio_path),
            "duration_sec": 42.5,
            "word_timestamps": [{"word": "eco", "start": 0.0, "end": 0.4}],
            "provider": "edge-tts",
            "voice": "es-MX-JorgeNeural",
            "boundary_type": "WordBoundary",
        }

    def test_store_then_load_hit(self):
        src_audio = Path(self.tmp.name) / "out.wav"
        src_audio.write_bytes(b"RIFF" + b"\x00" * 256)
        result = self._sample_result(src_audio)
        key = _tts_cache_key("texto", "es-MX-JorgeNeural", "+20%")

        _tts_cache_store(key, src_audio, result)

        wav_path, json_path = _tts_cache_paths(key)
        self.assertTrue(wav_path.is_file())
        meta = json.loads(json_path.read_text())
        self.assertEqual(meta["duration_sec"], 42.5)

        out_copy = Path(self.tmp.name) / "rerender.wav"
        loaded = _tts_cache_load(key, out_copy)
        self.assertIsNotNone(loaded)
        self.assertTrue(loaded["cache_hit"])
        self.assertEqual(loaded["duration_sec"], 42.5)
        self.assertEqual(out_copy.read_bytes(), src_audio.read_bytes())

    def test_missing_entry_is_miss(self):
        key = _tts_cache_key("nada", "v", "+0%")
        out_copy = Path(self.tmp.name) / "x.wav"
        self.assertIsNone(_tts_cache_load(key, out_copy))

    def test_corrupt_sidecar_is_miss(self):
        src_audio = Path(self.tmp.name) / "out.wav"
        src_audio.write_bytes(b"RIFFDATA")
        key = _tts_cache_key("corrupto", "v", "+0%")
        _tts_cache_store(key, src_audio, self._sample_result(src_audio))
        wav_path, json_path = _tts_cache_paths(key)
        json_path.write_text("{not json", encoding="utf-8")

        out_copy = Path(self.tmp.name) / "y.wav"
        self.assertIsNone(_tts_cache_load(key, out_copy))

    def test_zero_duration_sidecar_is_miss(self):
        src_audio = Path(self.tmp.name) / "out.wav"
        src_audio.write_bytes(b"RIFFDATA")
        key = _tts_cache_key("ceros", "v", "+0%")
        bad = self._sample_result(src_audio)
        bad["duration_sec"] = 0.0
        _tts_cache_store(key, src_audio, bad)

        out_copy = Path(self.tmp.name) / "z.wav"
        self.assertIsNone(_tts_cache_load(key, out_copy))


if __name__ == "__main__":
    unittest.main()
