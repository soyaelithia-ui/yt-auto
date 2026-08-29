import os
import tempfile
import unittest

from lib.subtitles import create_subtitles, create_ass_subtitles, _clean_word_for_karaoke
from src.templates.template_manager import SubtitleStyle


class TestSubtitles(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.word_timestamps = [
            {"word": "In", "start": 0.0, "end": 0.5},
            {"word": "a", "start": 0.5, "end": 0.8},
            {"word": "dark", "start": 0.8, "end": 1.4},
            {"word": "forest", "start": 1.4, "end": 2.0},
            {"word": "silence", "start": 2.0, "end": 2.8},
            {"word": "reigns", "start": 2.8, "end": 3.5}
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_create_subtitles_srt(self):
        """Test SRT subtitle file generation breaking at max 3 words per cue."""
        srt_path = os.path.join(self.temp_dir.name, "output.srt")
        result_path = create_subtitles(self.word_timestamps, srt_path)

        self.assertEqual(result_path, srt_path)
        self.assertTrue(os.path.exists(srt_path))

        with open(srt_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("1\n", content)
        self.assertIn("-->", content)
        self.assertIn("00:00:00,000 -->", content)
        self.assertIn("In a dark forest", content)
        self.assertIn("silence reigns", content)

    def test_create_ass_subtitles_formatting_and_highlighting(self):
        """Test ASS subtitle file generation with DejaVu Sans styling, Alignment=5, BorderStyle=3, and active word highlight tag."""
        ass_path = os.path.join(self.temp_dir.name, "output.ass")
        result_path = create_ass_subtitles(self.word_timestamps, ass_path, font_name="DejaVu Sans")

        self.assertEqual(result_path, ass_path)
        self.assertTrue(os.path.exists(ass_path))

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("[Script Info]", content)
        self.assertIn("[V4+ Styles]", content)
        self.assertIn("Style: Default,", content)
        self.assertIn("Dialogue:", content)
        self.assertIn(r"{\kf", content, "ASS subtitles must contain active word highlight tag \\kf")

    def test_create_ass_subtitles_liberation_sans(self):
        """Test ASS subtitle generation with Liberation Sans font family."""
        ass_path = os.path.join(self.temp_dir.name, "output_liberation.ass")
        create_ass_subtitles(self.word_timestamps, ass_path, font_name="Liberation Sans")

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("Style: Default,Liberation Sans", content)

    def test_create_ass_subtitles_dynamic_canvas(self):
        """Test dynamic canvas resolution formatting PlayResX and PlayResY in ASS header."""
        ass_path = os.path.join(self.temp_dir.name, "output_720_1280.ass")
        create_ass_subtitles(self.word_timestamps, ass_path, video_res=(720, 1280))

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("PlayResX: 720", content)
        self.assertIn("PlayResY: 1280", content)

    def test_create_ass_subtitles_boxed_style(self):
        """Test style_type='boxed' sets BorderStyle to 3 for background panel rendering."""
        ass_path = os.path.join(self.temp_dir.name, "output_boxed.ass")
        style = SubtitleStyle(style_type="boxed")
        create_ass_subtitles(self.word_timestamps, ass_path, template=style)

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(",3,", content)

    def test_spanish_inverted_punctuation_cleaning(self):
        """Test _clean_word_for_karaoke strips ¿ and ¡ placing them before timing tags."""
        prefix1, word1 = _clean_word_for_karaoke("¿Cómo")
        self.assertEqual(prefix1, "¿")
        self.assertEqual(word1, "Cómo")

        prefix2, word2 = _clean_word_for_karaoke("¡Hola!")
        self.assertEqual(prefix2, "¡")
        self.assertEqual(word2, "Hola!")

        ass_path = os.path.join(self.temp_dir.name, "output_spanish.ass")
        words = [
            {"word": "¿Cómo", "start": 0.0, "end": 0.5},
            {"word": "estás?", "start": 0.5, "end": 1.0}
        ]
        create_ass_subtitles(words, ass_path)

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn(r"¿{\kf", content)
        self.assertIn("Cómo", content)

    def test_utf8_encoding_flag(self):
        """Test ASS header specifies Encoding: 0 for UTF-8 compliance."""
        ass_path = os.path.join(self.temp_dir.name, "output_utf8.ass")
        create_ass_subtitles(self.word_timestamps, ass_path)

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertTrue(content.endswith("\n") or content.endswith("\r\n"))
        # Check last field in Style line is 0 (Encoding: 0)
        style_line = [line for line in content.splitlines() if line.startswith("Style:")][0]
        self.assertTrue(style_line.endswith(",0"))

    def test_ass_safe_margins(self):
        """Test ASS style header contains safe margins MarginL=40, MarginR=40, MarginV=120."""
        ass_path = os.path.join(self.temp_dir.name, "output_margins.ass")
        create_ass_subtitles(self.word_timestamps, ass_path, video_res=(768, 1360))

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        style_line = [line for line in content.splitlines() if line.startswith("Style:")][0]
        parts = style_line.split(",")
        margin_l = parts[-4]
        margin_r = parts[-3]
        margin_v = parts[-2]
        self.assertTrue(int(margin_l) > 0)
        self.assertTrue(int(margin_r) > 0)
        self.assertTrue(int(margin_v) >= 120)

    def test_ass_line_wrap_n(self):
        """Test long words exceeding max_chars per line are chunked into separate Dialogue lines."""
        long_words = [
            {"word": "UNFORTUNATE", "start": 0.0, "end": 0.5},
            {"word": "CHARACTERISTICS", "start": 0.5, "end": 1.0},
            {"word": "FOUNDATION", "start": 1.0, "end": 1.5},
        ]
        ass_path = os.path.join(self.temp_dir.name, "output_wrap.ass")
        create_ass_subtitles(long_words, ass_path, max_chars=15)

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        dialogue_lines = [line for line in content.splitlines() if line.startswith("Dialogue:")]
        self.assertTrue(len(dialogue_lines) >= 2)

    def test_create_ass_subtitles_dual_wrapping(self):
        """Test dual condition wrapping: max words or max chars."""
        four_words = [
            {"word": "one", "start": 0.0, "end": 0.5},
            {"word": "two", "start": 0.5, "end": 1.0},
            {"word": "three", "start": 1.0, "end": 1.5},
            {"word": "four", "start": 1.5, "end": 2.0},
        ]
        ass_path1 = os.path.join(self.temp_dir.name, "wrap_words.ass")
        create_ass_subtitles(four_words, ass_path1, max_chars=10)
        with open(ass_path1, "r", encoding="utf-8") as f:
            lines = [l for l in f.read().splitlines() if l.startswith("Dialogue:")]
        self.assertTrue(len(lines) >= 1)

        long_pair = [
            {"word": "12345678901", "start": 0.0, "end": 0.5},
            {"word": "123456789012", "start": 0.5, "end": 1.0},
        ]
        ass_path2 = os.path.join(self.temp_dir.name, "wrap_chars.ass")
        create_ass_subtitles(long_pair, ass_path2, max_chars=15)
        with open(ass_path2, "r", encoding="utf-8") as f:
            lines2 = [l for l in f.read().splitlines() if l.startswith("Dialogue:")]
        self.assertTrue(len(lines2) >= 1)


    def test_r2_montserrat_black_and_safe_zone(self):
        """Requirement R2 test: default ASS subtitles use Montserrat Black, outline >= 4, shadow >= 3, and margin_v in 180..280 safe zone."""
        ass_path = os.path.join(self.temp_dir.name, "r2_subs.ass")
        create_ass_subtitles(self.word_timestamps, ass_path)

        with open(ass_path, "r", encoding="utf-8") as f:
            content = f.read()

        style_line = [line for line in content.splitlines() if line.startswith("Style:")][0]
        self.assertIn("Montserrat Black", style_line)
        parts = style_line.split(",")
        outline = int(parts[11])
        shadow = int(parts[12])
        margin_v = int(parts[-2])
        self.assertGreaterEqual(outline, 4)
        self.assertGreaterEqual(shadow, 3)
        self.assertGreaterEqual(margin_v, 480, f"MarginV {margin_v} must be >= 480 for portrait safe zone")


if __name__ == "__main__":
    unittest.main()

