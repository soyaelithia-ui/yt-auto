"""Vendored brand font wiring (2d): resolve_font_path + libass fontsdir."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from lib import video as shared_video
from lib.video import (
    VENDORED_FONT_NAME,
    _ass_fontsdir_option,
    _repo_root,
    resolve_font_path,
)

VENDORED_FONT = Path(_repo_root()) / "assets" / "fonts" / VENDORED_FONT_NAME


def _vendored_asset_present() -> bool:
    return VENDORED_FONT.is_file() and VENDORED_FONT.stat().st_size > 100 * 1024


class TestFontVendoring(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        # A dev .env may pin a font; every test here needs a clean slate.
        self._env = os.environ.pop("SHORTS_FONT_PATH", None)

    def tearDown(self):
        self.temp_dir.cleanup()
        if self._env is not None:
            os.environ["SHORTS_FONT_PATH"] = self._env

    def test_resolve_font_path_prefers_vendored_brand_font(self):
        """resolve_font_path returns the vendored Montserrat Black when present."""
        if not _vendored_asset_present():
            self.skipTest("assets/fonts/Montserrat-Black.ttf not vendored")
        self.assertEqual(resolve_font_path(), str(VENDORED_FONT))

    def test_shorts_font_path_env_override_wins(self):
        """Explicit SHORTS_FONT_PATH beats the vendored candidate."""
        override = os.path.join(self.temp_dir.name, "custom.ttf")
        with open(override, "wb") as f:
            f.write(b"\x00\x01\x00\x00" + b"\x00" * 64)
        with patch.dict(os.environ, {"SHORTS_FONT_PATH": override}):
            self.assertEqual(resolve_font_path(), override)

    def test_resolve_font_path_falls_back_when_repo_has_no_fonts(self):
        """Missing vendored asset -> previous behaviour (system fallback / '')."""
        fake_root = Path(self.temp_dir.name)
        with patch.object(shared_video, "_repo_root", return_value=fake_root):
            resolved = resolve_font_path()
        self.assertNotEqual(resolved, str(fake_root / "assets" / "fonts" / VENDORED_FONT_NAME))
        if resolved:
            self.assertTrue(os.path.exists(resolved))

    def test_ass_fontsdir_option_points_at_vendored_dir(self):
        """fontsdir option resolves to <repo>/assets/fonts when the dir exists."""
        if not (Path(_repo_root()) / "assets" / "fonts").is_dir():
            self.skipTest("assets/fonts directory not present")
        option = _ass_fontsdir_option()
        self.assertTrue(option.startswith(":fontsdir="))
        self.assertFalse(option.startswith(":fontsdir='"))
        self.assertIn("/assets/fonts", option)
        self.assertNotIn("'", option)

    def test_ass_fontsdir_option_empty_when_dir_missing(self):
        """No font dir -> empty option, filtergraph keeps the legacy shape."""
        fake_root = Path(self.temp_dir.name)
        self.assertFalse((fake_root / "assets" / "fonts").exists())
        with patch.object(shared_video, "_repo_root", return_value=fake_root):
            self.assertEqual(_ass_fontsdir_option(), "")

    def _compose_filtergraph_for(self, subtitle_path: str) -> str:
        audio_path = os.path.join(self.temp_dir.name, "audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")
        img = os.path.join(self.temp_dir.name, "scene.jpg")
        from PIL import Image

        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(img)
        out_video = os.path.join(self.temp_dir.name, "out.mp4")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("lib.video.validate_video_format", return_value=True):
                shared_video.compose_video(
                    audio_path, subtitle_path, "", out_video,
                    duration_sec=5.0,
                    min_duration=0.0,
                    scene_images=[img],
                    video_mode="short",
                    channel="moku",
                )
            cmd = mock_run.call_args[0][0]
            idx = cmd.index("-filter_complex")
            return cmd[idx + 1]

    def test_filtergraph_carries_fontsdir_for_ass_burn_in(self):
        """ASS burn-in gains :fontsdir= pointing at the vendored dir."""
        sub_path = os.path.join(self.temp_dir.name, "subs.ass")
        with open(sub_path, "w") as f:
            f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[Events]\n")
        if not (Path(_repo_root()) / "assets" / "fonts").is_dir():
            with patch.object(shared_video, "_repo_root", return_value=_repo_root()):
                graph = self._compose_filtergraph_for(sub_path)
            self.assertIn("ass=filename=", graph)
            self.skipTest("assets/fonts directory not present")

        graph = self._compose_filtergraph_for(sub_path)
        self.assertIn(".ass:fontsdir=", graph)
        self.assertNotIn("fontsdir='", graph)
        self.assertIn("fontsdir=" + str(Path(_repo_root()) / "assets" / "fonts"), graph)

    def test_srt_branch_has_no_fontsdir_option(self):
        """Only libass burn-in needs the font dir; SRT path stays untouched."""
        sub_path = os.path.join(self.temp_dir.name, "subs.srt")
        with open(sub_path, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:04,000\nHola\n")
        graph = self._compose_filtergraph_for(sub_path)
        self.assertIn("subtitles=filename=", graph)
        self.assertNotIn("fontsdir=", graph)


if __name__ == "__main__":
    unittest.main()
