import os
import tempfile
import unittest
import wave
import sys
from unittest.mock import patch, MagicMock

from src.tts import generate_audio, sanitize_text_for_tts


class TestTTS(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_generate_audio_fallback_synthetic_pcm(self):
        """Test fallback synthetic PCM audio generation when AZURE_SPEECH_KEY is absent."""
        audio_path = os.path.join(self.temp_dir.name, "test_fallback.wav")
        script = "This is a test script for synthetic audio generation."

        with patch.dict(os.environ, {}, clear=True):
            info = generate_audio(
                script, audio_path, target_duration_sec=605.0, channel="moku"
            )

        self.assertTrue(os.path.exists(info["audio_path"]))
        self.assertGreaterEqual(info["duration_sec"], 600.0)
        self.assertTrue(len(info["word_timestamps"]) > 0)

        # Verify output is a valid WAV file
        with wave.open(audio_path, "rb") as wav_file:
            self.assertEqual(wav_file.getnchannels(), 1)
            self.assertEqual(wav_file.getsampwidth(), 2)
            self.assertEqual(wav_file.getframerate(), 8000)
            duration = wav_file.getnframes() / float(wav_file.getframerate())
            self.assertAlmostEqual(duration, info["duration_sec"], delta=1.0)

    def test_generate_audio_word_timestamps_structure(self):
        """Test structure of word timestamp objects."""
        audio_path = os.path.join(self.temp_dir.name, "test_stamps.wav")
        script = "Word one two three."
        
        info = generate_audio(
            script, audio_path, target_duration_sec=605.0, channel="moku"
        )
        stamps = info["word_timestamps"]
        
        self.assertGreaterEqual(len(stamps), len(script.split()))
        for stamp in stamps:
            self.assertIn("word", stamp)
            self.assertIn("start", stamp)
            self.assertIn("end", stamp)
            self.assertLessEqual(stamp["start"], stamp["end"])

    def test_generate_audio_empty_script_fallback(self):
        """Test handling of empty script text."""
        audio_path = os.path.join(self.temp_dir.name, "test_empty.wav")
        info = generate_audio(
            "", audio_path, target_duration_sec=605.0, channel="moku"
        )
        
        self.assertTrue(os.path.exists(info["audio_path"]))
        self.assertGreaterEqual(len(info["word_timestamps"]), 2)

    def test_generate_audio_with_azure_mock(self):
        """Test Azure Speech SDK integration logic with mocks."""
        audio_path = os.path.join(self.temp_dir.name, "azure_test.wav")
        script = "Testing Azure Speech SDK."

        mock_speechsdk = MagicMock()
        mock_synthesizer = MagicMock()
        mock_speechsdk.SpeechSynthesizer.return_value = mock_synthesizer
        
        mock_result = MagicMock()
        mock_result.reason = mock_speechsdk.ResultReason.SynthesizingAudioCompleted
        mock_synthesizer.speak_ssml_async.return_value.get.return_value = mock_result

        mock_azure = MagicMock()
        mock_azure.cognitiveservices = MagicMock()
        mock_azure.cognitiveservices.speech = mock_speechsdk

        modules_dict = dict(sys.modules)
        modules_dict["azure"] = mock_azure
        modules_dict["azure.cognitiveservices"] = mock_azure.cognitiveservices
        modules_dict["azure.cognitiveservices.speech"] = mock_speechsdk

        with patch.dict(sys.modules, modules_dict):
            with patch.dict(os.environ, {"AZURE_SPEECH_KEY": "fake_key", "AZURE_SPEECH_REGION": "eastus"}):
                # Create empty file to represent output audio creation by Azure SDK
                with open(audio_path, "wb") as f:
                    f.write(b"RIFF")
                
                info = generate_audio(script, audio_path, target_duration_sec=605.0, channel="aelithia")
                self.assertEqual(info["audio_path"], audio_path)
                self.assertFalse(
                    mock_synthesizer.speak_ssml_async.called,
                    "Paid Azure TTS must remain disabled",
                )

    def test_sanitize_text_for_tts_spanish_headers_and_greetings(self):
        """Test sanitize_text_for_tts strips Spanish title headers (including markdown formatted) and preserves narrative text."""
        text = "Título: El Misterio del Bosque.\n\nEn lo profundo de la noche, el relato de hoy es impactante."
        sanitized = sanitize_text_for_tts(text)
        self.assertNotIn("Título:", sanitized)
        self.assertTrue(sanitized.startswith("En lo profundo de la noche"))

        # Test markdown headers: **Título:**, *Título:*, **Title:**, *Title:*
        md_cases = [
            "**Título:** El Bosque Misterioso\n\nEra una noche oscura.",
            "*Título:* El Bosque Misterioso\n\nEra una noche oscura.",
            "**Title:** The Dark Forest\n\nIt was a dark night.",
            "*Title:* The Dark Forest\n\nIt was a dark night.",
            "### Título: El Bosque\n\nEra una noche oscura.",
        ]
        for md_text in md_cases:
            out = sanitize_text_for_tts(md_text)
            self.assertNotIn("Título:", out, f"Failed for input: {md_text}")
            self.assertNotIn("Title:", out, f"Failed for input: {md_text}")
            self.assertNotIn("El Bosque Misterioso", out, f"Failed for input: {md_text}")
            self.assertNotIn("The Dark Forest", out, f"Failed for input: {md_text}")

    @patch("subprocess.run")
    def test_master_voice_audio_invokes_ffmpeg(self, mock_run):
        """Test master_voice_audio calls FFmpeg with equalizer and loudnorm filter chain."""
        from src.tts import master_voice_audio
        audio_path = os.path.join(self.temp_dir.name, "voice_input.wav")
        with open(audio_path, "wb") as f:
            f.write(b"RIFF_WAV_HEADER_DATA")

        mock_run.return_value = MagicMock(returncode=0)
        res = master_voice_audio(audio_path)
        self.assertEqual(res, audio_path)
        self.assertTrue(mock_run.called)
        cmd = mock_run.call_args[0][0]
        self.assertIn("ffmpeg", cmd)
        af_idx = cmd.index("-af")
        filter_str = cmd[af_idx + 1]
        self.assertIn("equalizer=f=120", filter_str)
        self.assertIn("loudnorm=I=-14", filter_str)


if __name__ == "__main__":
    unittest.main()
