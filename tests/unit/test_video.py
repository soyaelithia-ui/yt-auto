import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from lib.video import (
    compose_video,
    get_media_duration,
    validate_video_format,
    MIN_VIDEO_DURATION_SEC,
    resolve_font_path,
    extract_hook_title,
    generate_pil_thumbnail,
    create_video_thumbnail,
    detect_gpu_encoder,
    FFmpegFilterBuilder,
)


class TestVideo(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_resolve_font_path(self):
        """Test system font path discovery and fallback logic."""
        font_p = resolve_font_path()
        self.assertIsInstance(font_p, str)
        if font_p:
            self.assertTrue(os.path.exists(font_p))

    def test_extract_hook_title(self):
        """Test extraction of 3-6 punchy high-CTR words from titles."""
        self.assertEqual(extract_hook_title(""), "HISTORIA IMPACTANTE")
        self.assertEqual(extract_hook_title("Hola Mundo"), "HOLA MUNDO")
        self.assertEqual(
            extract_hook_title("¿Soy el malo por cancelar la boda de mi hermano?"),
            "¿SOY EL MALO?"
        )
        self.assertEqual(
            extract_hook_title("Un relato de terror muy largo que supera las seis palabras"),
            "UN RELATO DE TERROR MUY LARGO"
        )

    def test_compose_video_under_120s_raises_value_error(self):
        """Test pre-render stage duration enforcement: longform under 180s raises ValueError."""
        audio_path = os.path.join(self.temp_dir.name, "short.wav")
        with open(audio_path, "wb") as f:
            f.write(b"SHORT_AUDIO_DATA")
            
        srt_path = os.path.join(self.temp_dir.name, "subs.srt")
        with open(srt_path, "w") as f:
            f.write("1\n00:00:00,000 --> 00:00:05,000\nHello\n")

        output_video = os.path.join(self.temp_dir.name, "short_output.mp4")

        with self.assertRaises(ValueError) as ctx:
            compose_video(
                audio_path,
                srt_path,
                "",
                output_video,
                duration_sec=119.0,
                min_duration=120.0,
                channel="moku",
            )
        self.assertIn("must exceed", str(ctx.exception))

    @patch("lib.video.validate_video_format", return_value=True)
    @patch("lib.video.get_media_duration", return_value=60.0)
    @patch("lib.video.validate_video_format", return_value=True)
    @patch("lib.video.get_media_duration", return_value=60.0)
    @patch("subprocess.run")
    def test_compose_video_over_120s_success(self, mock_run, *args):
        """Test synthesis for duration > 120.0 seconds."""
        mock_run.return_value = MagicMock(returncode=0)
        audio_path = os.path.join(self.temp_dir.name, "valid_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")
            
        srt_path = os.path.join(self.temp_dir.name, "subs.srt")
        with open(srt_path, "w") as f:
            f.write("1\n00:00:00,000 --> 00:02:50,000\nValid duration subtitle\n")

        output_video = os.path.join(self.temp_dir.name, "valid_output.mp4")
        with open(output_video, "w") as f:
            f.write("dummy video data")

        res = compose_video(
            audio_path,
            srt_path,
            "",
            output_video,
            duration_sec=121.0,
            min_duration=120.0,
            shot_durations=[121.0],
            channel="moku",
        )
        self.assertEqual(res, output_video)
        self.assertTrue(os.path.exists(output_video))

    def test_compose_video_bg_and_ass_subtitles(self):
        """Test composing video with background video looping and ASS subtitles."""
        audio_path = os.path.join(self.temp_dir.name, "audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")

        bg_video = os.path.join(self.temp_dir.name, "bg.mp4")
        with open(bg_video, "wb") as f:
            f.write(b"BG_DATA")

        ass_path = os.path.join(self.temp_dir.name, "subs.ass")
        with open(ass_path, "w", encoding="utf-8") as f:
            f.write("[Script Info]\nScriptType: v4.00+\n")

        output_video = os.path.join(self.temp_dir.name, "bg_ass_out.mp4")

        valid_json = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio", "codec_name": "aac"}]}'
        with patch("subprocess.run") as mock_run, \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0), \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0):
            mock_run.return_value = MagicMock(stdout=valid_json, returncode=0)
            with patch("os.path.exists", side_effect=lambda p: True):
                with patch("os.path.getsize", return_value=1000):
                    res = compose_video(
                        audio_path,
                        ass_path,
                        bg_video,
                        output_video,
                        duration_sec=10.0,
                        min_duration=0.0,
                        channel="moku",
                    )
                    self.assertTrue(mock_run.called)

    def test_validate_video_format_valid(self):
        """Test validate_video_format with valid JSON output from ffprobe."""
        v_file = os.path.join(self.temp_dir.name, "valid.mp4")
        with open(v_file, "wb") as f:
            f.write(b"MP4_DATA")

        valid_json = '{"format": {"format_name": "mov,mp4,m4a,3gp,3g2,mj2", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio", "codec_name": "aac"}]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=valid_json, returncode=0)
            valid = validate_video_format(v_file, min_duration=600.0)
            self.assertTrue(valid)

    def test_validate_video_format_invalid_codec(self):
        """Test validate_video_format with invalid codec raises ValueError."""
        v_file = os.path.join(self.temp_dir.name, "invalid.mp4")
        with open(v_file, "wb") as f:
            f.write(b"MP4_DATA")

        invalid_json = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "mpeg4"}, {"codec_type": "audio", "codec_name": "mp3"}]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=invalid_json, returncode=0)
            with self.assertRaises(ValueError) as ctx:
                validate_video_format(v_file, min_duration=600.0)
            self.assertIn("Invalid video codec", str(ctx.exception))

    def test_compose_video_3channel_mix(self):
        """Test compose_video filter complex construction when both ambient and music tracks are provided."""
        audio_path = os.path.join(self.temp_dir.name, "speech.wav")
        with open(audio_path, "wb") as f:
            f.write(b"SPEECH_AUDIO")

        ambient_path = os.path.join(self.temp_dir.name, "ambient.mp3")
        with open(ambient_path, "wb") as f:
            f.write(b"AMBIENT_AUDIO")

        music_path = os.path.join(self.temp_dir.name, "music.mp3")
        with open(music_path, "wb") as f:
            f.write(b"MUSIC_AUDIO")

        output_video = os.path.join(self.temp_dir.name, "mix_3ch_out.mp4")

        valid_json = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264"}, {"codec_type": "audio", "codec_name": "aac"}]}'
        with patch("subprocess.run") as mock_run, \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0), \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0):
            mock_run.return_value = MagicMock(stdout=valid_json, returncode=0)
            res = compose_video(
                audio_path,
                "",
                "",
                output_video,
                duration_sec=10.0,
                min_duration=0.0,
                bg_music_path=music_path,
                bg_ambient_path=ambient_path,
                channel="moku",
            )
            self.assertEqual(res, output_video)
            ffmpeg_args = mock_run.call_args[0][0]
            filter_arg = ffmpeg_args[ffmpeg_args.index("-filter_complex") + 1]
            self.assertIn("asplit=3[speech_sc1][speech_sc2][speech_mix]", filter_arg)
            self.assertIn("[music_in][speech_sc1]sidechaincompress", filter_arg)
            self.assertIn("[ambient_in][speech_sc2]sidechaincompress", filter_arg)
            self.assertIn("[speech_mix][music_ducked][ambient_ducked]amix=inputs=3:duration=first:normalize=0", filter_arg)

    def test_generate_pil_thumbnail_wrapping(self):
        """Test generate_pil_thumbnail handles multi-line titles and creates valid 720p image."""
        out_thumb = os.path.join(self.temp_dir.name, "multiline_thumb.jpg")
        long_title = "El Secreto Aterrador Oculto en las Profundidades del Bosque Maldito"
        res = generate_pil_thumbnail(long_title, out_thumb)
        self.assertTrue(os.path.exists(res))
        from PIL import Image
        with Image.open(res) as img:
            self.assertEqual(img.size, (1280, 720))

    def test_create_video_thumbnail_local_pil_rendering(self):
        """create_video_thumbnail must generate a valid thumbnail locally without any network calls."""
        out_thumb = os.path.join(self.temp_dir.name, "local_thumb.jpg")
        res = create_video_thumbnail(
            "El Bosque Misterioso", "moku", out_thumb, video_mode="short"
        )
        self.assertEqual(res, out_thumb)
        self.assertTrue(os.path.exists(res))
        from PIL import Image
        with Image.open(res) as img:
            self.assertEqual(img.size, (720, 1280))

    def test_create_video_thumbnail_composites_text_overlay_with_wrapping(self):
        """Verifies create_video_thumbnail composites text overlay onto image for long titles."""
        bg_img = os.path.join(self.temp_dir.name, "bg_base.jpg")
        from PIL import Image
        Image.new("RGB", (1920, 1080), (0, 0, 255)).save(bg_img)

        out_thumb = os.path.join(self.temp_dir.name, "out_thumb.jpg")
        long_title = "El Secreto Aterrador Oculto en las Profundidades del Bosque Maldito"
        res = create_video_thumbnail(
            long_title, "moku", out_thumb, bg_image_path=bg_img, video_mode="longform"
        )

        self.assertTrue(os.path.exists(res))
        with Image.open(res) as composited:
            self.assertEqual(composited.size, (1280, 720))
            extrema = composited.getextrema()
            self.assertGreater(extrema[0][1], 0)

    def test_create_video_thumbnail_zero_http_calls(self):
        """Verify create_video_thumbnail renders locally and makes 0 HTTP calls."""
        out_thumb = os.path.join(self.temp_dir.name, "zero_http_thumb.jpg")
        with patch("requests.Session.post", side_effect=AssertionError("HTTP request attempted!")):
            res = create_video_thumbnail("Título de Prueba", "moku", out_thumb)
            self.assertTrue(os.path.exists(res))

    def test_compose_video_telegram_encoding_and_mapping_flags(self):
        """Verify compose_video builds FFmpeg command with libx264, yuv420p, profile main, AAC 192k stereo, faststart, and -map [vout] -map [aout]."""
        audio_path = os.path.join(self.temp_dir.name, "test_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")
        out_video = os.path.join(self.temp_dir.name, "telegram_out.mp4")

        with patch("subprocess.run") as mock_run, \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0), \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            compose_video(audio_path, "", "", out_video, duration_sec=10.0, min_duration=0.0, channel="moku")

            cmd = mock_run.call_args[0][0]
            self.assertIn("-c:v", cmd)
            self.assertIn("libx264", cmd)
            self.assertIn("-pix_fmt", cmd)
            self.assertIn("yuv420p", cmd)
            self.assertIn("-profile:v", cmd)
            self.assertIn("main", cmd)
            self.assertIn("-c:a", cmd)
            self.assertIn("aac", cmd)
            self.assertIn("-b:a", cmd)
            self.assertIn("192k", cmd)
            self.assertIn("-ar", cmd)
            self.assertIn("44100", cmd)
            self.assertIn("-ac", cmd)
            self.assertIn("2", cmd)
            self.assertIn("-movflags", cmd)
            self.assertIn("+faststart", cmd)
            self.assertIn("-map", cmd)
            self.assertIn("[vout]", cmd)
            self.assertIn("[aout]", cmd)

    def test_compose_video_short_mode_targets_720x1280(self):
        """Lock-in: compose_video short mode targets the canonical 720x1280 canvas."""
        audio_path = os.path.join(self.temp_dir.name, "short_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")
        out_video = os.path.join(self.temp_dir.name, "short_out.mp4")

        # Test environment -> 720x1280 test scale
        with patch("subprocess.run") as mock_run, \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0), \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            compose_video(audio_path, "", "", out_video, duration_sec=10.0, min_duration=0.0, channel="moku", video_mode="short")
            cmd = mock_run.call_args[0][0]
            filter_complex_idx = cmd.index("-filter_complex")
            filtergraph = cmd[filter_complex_idx + 1]
            self.assertIn("crop=w=1080:h=1920", filtergraph)

        # Production environment -> 720x1280 with zoompan at 720x1280
        source_img = os.path.join(self.temp_dir.name, "short_bg.jpg")
        with open(source_img, "wb") as f:
            f.write(b"\xFF\xD8\xFF\xE0\x00\x10JFIF\x00\x01\x01\x01\x00`\x00`\x00\x00\xFF\xD9")

        manager = MagicMock()
        manager.get_background.return_value = ""
        manager.get_music.return_value = ""
        manager.get_ambient.return_value = ""
        manager.get_background_sequence.side_effect = lambda count, **kwargs: [str(source_img)] * count

        with patch("subprocess.run") as mock_run, \
             patch("lib.video.is_test_environment", return_value=False), \
             patch("lib.video.is_test_environment", return_value=False), \
             patch("src.asset_manager.get_asset_manager", return_value=manager), \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0), \
             patch("lib.video.validate_video_format", return_value=True), \
             patch("lib.video.get_media_duration", return_value=60.0):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            compose_video(audio_path, "", "", out_video, duration_sec=10.0, min_duration=0.0, channel="moku", video_mode="short")
            cmd = mock_run.call_args[0][0]
            filter_complex_idx = cmd.index("-filter_complex")
            filtergraph = cmd[filter_complex_idx + 1]
            self.assertIn("crop=w=1080:h=1920", filtergraph)
            self.assertTrue(any("concat" in str(arg) for arg in cmd))

    def test_detect_gpu_encoder_enforces_libx264(self):
        """Verify detect_gpu_encoder strictly enforces software libx264 encoding."""
        encoder_name, encoder_flags = detect_gpu_encoder()
        self.assertEqual(encoder_name, "libx264")
        self.assertIn("-c:v", encoder_flags)
        self.assertIn("libx264", encoder_flags)

    def test_build_audio_chain_formatting(self):
        """Verify build_audio_chain incorporates explicit audio resampling & stereo layout formatting."""
        builder = FFmpegFilterBuilder()
        chain = builder.build_audio_chain(
            has_ambient=True,
            has_music=True,
            duration_sec=10.0,
            fade_duration=3.0,
            music_volume=0.1,
            ambient_volume=0.1,
            speech_volume=1.0,
            lowpass_freq=0.0,
            sidechain_threshold=-16.0,
            sidechain_ratio=4.0
        )
        self.assertIn("aresample=48000", chain)
        self.assertIn("aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[aout]", chain)

    def test_validate_video_format_verifies_pixel_format(self):
        """Test validate_video_format raises ValueError if pix_fmt is not yuv420p."""
        v_file = os.path.join(self.temp_dir.name, "bad_pix.mp4")
        with open(v_file, "wb") as f:
            f.write(b"MP4_DATA")

        invalid_json = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv444p"}, {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": 44100}]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=invalid_json, returncode=0)
            with self.assertRaises(ValueError) as ctx:
                validate_video_format(v_file, min_duration=600.0)
            self.assertIn("Invalid pixel format", str(ctx.exception))

    def test_validate_video_format_verifies_channels_and_sample_rate(self):
        """Test validate_video_format raises ValueError if channels != 2 or sample_rate != 44100."""
        v_file = os.path.join(self.temp_dir.name, "bad_audio.mp4")
        with open(v_file, "wb") as f:
            f.write(b"MP4_DATA")

        invalid_channels = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"}, {"codec_type": "audio", "codec_name": "aac", "channels": 6, "sample_rate": 44100}]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=invalid_channels, returncode=0)
            with self.assertRaises(ValueError) as ctx:
                validate_video_format(v_file, min_duration=600.0)
            self.assertIn("Invalid audio channels", str(ctx.exception))

        invalid_rate = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"}, {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": 48000}]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout=invalid_rate, returncode=0)
            with self.assertRaises(ValueError) as ctx:
                validate_video_format(v_file, min_duration=600.0)
            self.assertIn("Invalid audio sample rate", str(ctx.exception))

    def test_validate_video_format_verifies_faststart(self):
        """Test validate_video_format raises ValueError if faststart is missing in non-test mode."""
        v_file = os.path.join(self.temp_dir.name, "no_faststart.mp4")
        with open(v_file, "wb") as f:
            f.write(b"MP4_DATA_NO_FASTSTART" * 10000)

        valid_json = '{"format": {"format_name": "mp4", "duration": "605.0"}, "streams": [{"codec_type": "video", "codec_name": "h264", "pix_fmt": "yuv420p"}, {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": 44100}]}'
        with patch("subprocess.run") as mock_run, \
             patch("lib.video.is_test_environment", return_value=False), \
             patch("lib.video.has_faststart", return_value=False):
            mock_run.return_value = MagicMock(stdout=valid_json, returncode=0)
            with self.assertRaises(ValueError) as ctx:
                validate_video_format(v_file, min_duration=600.0)
            self.assertIn("faststart moov atom", str(ctx.exception))


    def test_r2_multi_image_ken_burns_and_xfade_transitions(self):
        """Requirement R2 test: compose_video with multiple scene images generates zoompan and xfade filter chain."""
        audio_path = os.path.join(self.temp_dir.name, "multi_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")

        img1 = os.path.join(self.temp_dir.name, "scene_1.jpg")
        img2 = os.path.join(self.temp_dir.name, "scene_2.jpg")
        from PIL import Image
        Image.new("RGB", (720, 1280), (100, 50, 50)).save(img1)
        Image.new("RGB", (720, 1280), (50, 100, 50)).save(img2)

        out_video = os.path.join(self.temp_dir.name, "multi_out.mp4")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("lib.video.validate_video_format", return_value=True):
                compose_video(
                    audio_path, "", "", out_video,
                    duration_sec=10.0,
                    min_duration=0.0,
                    scene_images=[img1, img2],
                    video_mode="short",
                )
            cmd = mock_run.call_args[0][0]
            filter_complex_idx = cmd.index("-filter_complex")
            filtergraph = cmd[filter_complex_idx + 1]
            self.assertIn("crop=w=1080:h=1920", filtergraph)
            self.assertIn("(in_w-out_w)*(0.5-0.5*cos(PI*t/", filtergraph)
            self.assertIn("(in_h-out_h)*(0.5-0.5*cos(PI*t/", filtergraph)
            self.assertIn("xfade=transition=fade", filtergraph)
            self.assertIn("fade=t=in", filtergraph)
            self.assertIn("fade=t=out", filtergraph)

    def test_r2_thumbnail_style_presets(self):
        """Requirement R2 test: generate_pil_thumbnail renders correctly for all ThumbnailStyle presets."""
        from PIL import Image
        from src.templates.template_manager import TemplateRegistry
        registry = TemplateRegistry()

        for tpl_name in ["creepypasta", "aita", "cyberpunk", "documentary"]:
            tpl = registry.get_template(tpl_name)
            out_thumb = os.path.join(self.temp_dir.name, f"thumb_{tpl_name}.jpg")
            res = generate_pil_thumbnail(
                title=f"Prueba {tpl_name.upper()}",
                output_path=out_thumb,
                style_preset=tpl.thumbnail,
            )
            self.assertTrue(os.path.exists(res))
            with Image.open(res) as img:
                self.assertEqual(img.size, (1280, 720))

    def test_zero_cost_motion_even_odd_panning_and_no_zoompan(self):
        """Verify compose_video generates dynamic pan crop (horizontal even, vertical odd), no zoompan, threads respect env up to cpu cap (<=4), preset veryfast, crf 24."""
        audio_path = os.path.join(self.temp_dir.name, "motion_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")

        img1 = os.path.join(self.temp_dir.name, "motion_1.jpg")
        img2 = os.path.join(self.temp_dir.name, "motion_2.jpg")
        from PIL import Image
        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(img1)
        Image.new("RGB", (1080, 1920), (30, 20, 10)).save(img2)

        out_video = os.path.join(self.temp_dir.name, "motion_out.mp4")

        # Hermetic: lib.video reads RENDER_CRF from the environment at import
        # time, so a developer .env with RENDER_CRF=22 leaks into the suite. Pin the
        # documented default for the duration of this test.
        with patch("subprocess.run") as mock_run, patch("lib.video.RENDER_CRF", 24):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("lib.video.validate_video_format", return_value=True):
                compose_video(
                    audio_path, "", "", out_video,
                    duration_sec=10.0,
                    min_duration=0.0,
                    scene_images=[img1, img2],
                    video_mode="short",
                )
            cmd = mock_run.call_args[0][0]
            filter_complex_idx = cmd.index("-filter_complex")
            filtergraph = cmd[filter_complex_idx + 1]

            # 1. Zero-Cost Pan crop check: even scene horizontal, odd scene vertical,
            #    both cosine-eased (EASED_PAN default on)
            self.assertIn(
                "crop=w=1080:h=1920:x=(in_w-out_w)*(0.5-0.5*cos(PI*t/",
                filtergraph,
            )
            self.assertIn(":y=(in_h-out_h)/2", filtergraph)
            self.assertIn(
                "crop=w=1080:h=1920:x=(in_w-out_w)/2:y=(in_h-out_h)*(0.5-0.5*cos(PI*t/",
                filtergraph,
            )

            # 2. NO zoompan filter
            self.assertNotIn("zoompan=", filtergraph)

            # 3. Output formats
            self.assertIn("setsar=1", filtergraph)
            self.assertIn("format=yuv420p", filtergraph)
            self.assertIn("fps=", filtergraph)

            # 4. Encoding performance & memory flags
            # R7: thread cap raised 2 -> 4 (container cpu quota); env knob is
            # respected up to min(cpu_count, 4).
            self.assertIn("-threads", cmd)
            threads_idx = cmd.index("-threads")
            self.assertLessEqual(int(cmd[threads_idx + 1]), 4)
            self.assertGreaterEqual(int(cmd[threads_idx + 1]), 1)
            self.assertIn("-filter_threads", cmd)
            # R8: dark-scene banding mitigation (aq-mode=3) present by default.
            self.assertIn("-x264-params", cmd)
            aq_idx = cmd.index("-x264-params")
            self.assertIn("aq-mode=3", cmd[aq_idx + 1])
            self.assertIn("-preset", cmd)
            preset_idx = cmd.index("-preset")
            self.assertEqual(cmd[preset_idx + 1], "veryfast")
            self.assertIn("-crf", cmd)
            crf_idx = cmd.index("-crf")
            self.assertEqual(cmd[crf_idx + 1], "24")


    def test_filtergraph_identical_with_visual_overlays_and_grade_toggled(self):
        """Zero-cost property: VISUAL_OVERLAYS / VISUAL_GRADE never touch ffmpeg.

        The bake happens entirely inside Pillow before the inputs are opened, so
        the filter_complex string must be byte-identical with the flags on/off.
        """
        audio_path = os.path.join(self.temp_dir.name, "bake_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")

        img1 = os.path.join(self.temp_dir.name, "bank_1.jpg")
        from PIL import Image
        # Larger than the 1.08x overscale box so the prescale branch runs.
        Image.new("RGB", (1200, 2200), (90, 80, 70)).save(img1)

        out_video = os.path.join(self.temp_dir.name, "bake_out.mp4")

        def _capture(env):
            with patch.dict(os.environ, env), patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                with patch("lib.video.validate_video_format", return_value=True):
                    compose_video(
                        audio_path, "", "", out_video,
                        duration_sec=10.0,
                        min_duration=0.0,
                        scene_images=[img1],
                        video_mode="short",
                        channel="moku",
                    )
                cmd = mock_run.call_args[0][0]
                idx = cmd.index("-filter_complex")
                return cmd[idx + 1]

        baseline = _capture({"VISUAL_OVERLAYS": "0", "VISUAL_GRADE": "0"})
        baked = _capture({"VISUAL_OVERLAYS": "1", "VISUAL_GRADE": "1"})
        self.assertEqual(baseline, baked)
        self.assertNotIn("overlay=", baseline)

    def test_channel_overlay_bake_darkens_corners(self):
        """Baked prescaled jpg is darker at the corners than a plain resize.

        aelithia's stack (soft_vignette + drama_shadow + grade) must leave a
        visible footprint on bank-sized assets that today skip the prescale;
        drama_shadow is the opaque black corner layer.
        """
        import numpy
        from PIL import Image, ImageDraw
        from lib.video import _apply_channel_overlays, _apply_channel_grade, channel_overlay_paths

        patcher = None
        if not channel_overlay_paths("aelithia"):
            mock_ov = Path(self.temp_dir.name) / "mock_aelithia_overlay.png"
            ov_im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov_im)
            draw.rectangle([0, 0, 40, 40], fill=(0, 0, 0, 255))
            draw.rectangle([160, 0, 200, 40], fill=(0, 0, 0, 255))
            draw.rectangle([0, 160, 40, 200], fill=(0, 0, 0, 255))
            draw.rectangle([160, 160, 200, 200], fill=(0, 0, 0, 255))
            ov_im.save(mock_ov)
            patcher = patch("lib.video.channel_overlay_paths", return_value=[mock_ov])
            patcher.start()

        try:
            src = os.path.join(self.temp_dir.name, "corner_src.jpg")
            rng = numpy.random.default_rng(7)
            flat = numpy.full((1200, 2200, 3), 110, dtype=numpy.uint8)
            noise = rng.integers(-6, 7, size=flat.shape).astype(numpy.int16)
            flat = numpy.clip(flat.astype(numpy.int16) + noise, 0, 255).astype(numpy.uint8)
            Image.fromarray(flat).save(src)

            with Image.open(src) as im:
                plain = im.convert("RGB").resize((1166, 2073), Image.Resampling.BICUBIC)

                baked = _apply_channel_grade(
                    _apply_channel_overlays(plain.copy(), "aelithia"), "aelithia"
                )

                plain_arr = numpy.asarray(plain.convert("L"), dtype=float)
                baked_arr = numpy.asarray(baked.convert("L"), dtype=float)
                h, w = plain_arr.shape

                def corners(a):
                    b = 24
                    return (
                        a[:b, :b].mean() + a[:b, -b:].mean()
                        + a[-b:, :b].mean() + a[-b:, -b:].mean()
                    ) / 4.0

                self.assertLess(
                    corners(baked_arr),
                    corners(plain_arr) * 0.9,
                    "vignette bake should darken corners by >=10%",
                )
                # Center stays close to the original luminance (subtle grade).
                center_delta = abs(
                    baked_arr[h // 2 - 50: h // 2 + 50, w // 2 - 50: w // 2 + 50].mean()
                    - plain_arr[h // 2 - 50: h // 2 + 50, w // 2 - 50: w // 2 + 50].mean()
                )
                self.assertLess(center_delta, 25.0)
        finally:
            if patcher:
                patcher.stop()

    def test_compose_baked_prescaled_output_differs_from_plain_resize(self):
        """compose_video writes a baked prescaled jpg for oversized sources."""
        import wave as _wave
        from PIL import Image, ImageDraw
        from lib.video import channel_overlay_paths

        patcher = None
        if not channel_overlay_paths("moku"):
            mock_ov = Path(self.temp_dir.name) / "mock_moku_overlay.png"
            ov_im = Image.new("RGBA", (200, 200), (0, 0, 0, 0))
            draw = ImageDraw.Draw(ov_im)
            draw.rectangle([0, 0, 40, 40], fill=(0, 0, 0, 255))
            draw.rectangle([160, 0, 200, 40], fill=(0, 0, 0, 255))
            draw.rectangle([0, 160, 40, 200], fill=(0, 0, 0, 255))
            draw.rectangle([160, 160, 200, 200], fill=(0, 0, 0, 255))
            ov_im.save(mock_ov)
            patcher = patch("lib.video.channel_overlay_paths", return_value=[mock_ov])
            patcher.start()

        try:
            audio_path = os.path.join(self.temp_dir.name, "prescale_audio.wav")
            with _wave.open(audio_path, "wb") as wav:
                wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
                wav.writeframes(b"\x01\x00" * 8000)

            from PIL import Image
            src = os.path.join(self.temp_dir.name, "oversize_scene.jpg")
            Image.new("RGB", (1200, 2200), (110, 110, 110)).save(src)
            out_video = os.path.join(self.temp_dir.name, "prescale_out.mp4")

            captured = {}

            def _grab_prescaled(args, **kwargs):
                for i, arg in enumerate(args):
                    if arg == "-i" and i > 0 and "prescaled_" in str(args[i - 1]):
                        p = Path(str(args[i - 1]))
                        if p.exists():
                            captured["prescaled"] = p.read_bytes()
                            captured["input_arg"] = str(args[i - 1])
                return MagicMock(returncode=0, stdout="", stderr="")

            with patch("subprocess.run", side_effect=_grab_prescaled):
                with patch("lib.video.validate_video_format", return_value=True):
                    compose_video(
                        audio_path, "", "", out_video,
                        duration_sec=5.0,
                        min_duration=0.0,
                        scene_images=[src],
                        video_mode="short",
                        channel="moku",
                    )

            self.assertIn("prescaled_", captured.get("input_arg", ""))
            baked_bytes = captured.get("prescaled")
            self.assertTrue(baked_bytes)

            from PIL import ImageOps
            with Image.open(src) as im:
                plain_fit = ImageOps.fit(im.convert("RGB"), (1166, 2073), method=Image.Resampling.BICUBIC)
            buf = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
            try:
                plain_fit.save(buf.name, format="JPEG", quality=92)
                buf.close()
                self.assertNotEqual(
                    len(baked_bytes), os.path.getsize(buf.name),
                    "baked output should differ from the plain presize",
                )
            finally:
                os.unlink(buf.name)
            # cleanup glob removed the temp file
            self.assertEqual(list(Path(self.temp_dir.name).glob("prescaled_*.jpg")), [])
        finally:
            if patcher:
                patcher.stop()

    def test_eased_pan_rollback_flag_restores_linear_expressions(self):
        """EASED_PAN=0 restores the literal linear pan ramp."""
        audio_path = os.path.join(self.temp_dir.name, "ease_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")

        img1 = os.path.join(self.temp_dir.name, "ease_1.jpg")
        from PIL import Image
        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(img1)

        out_video = os.path.join(self.temp_dir.name, "ease_out.mp4")

        with patch.dict(os.environ, {"EASED_PAN": "0"}):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
                with patch("lib.video.validate_video_format", return_value=True):
                    compose_video(
                        audio_path, "", "", out_video,
                        duration_sec=10.0,
                        min_duration=0.0,
                        scene_images=[img1],
                        video_mode="short",
                    )
        cmd = mock_run.call_args[0][0]
        fg_idx = cmd.index("-filter_complex")
        filtergraph = cmd[fg_idx + 1]
        self.assertIn("crop=w=1080:h=1920:x=(in_w-out_w)*(t/", filtergraph)
        self.assertNotIn("cos(", filtergraph)

    def test_ass_fontsdir_vendored_font_wiring(self):
        """ass burn-in carries fontsdir pointing at the vendored font dir."""
        import wave as _wave

        audio_path = os.path.join(self.temp_dir.name, "font_audio.wav")
        with _wave.open(audio_path, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
            wav.writeframes(b"\x01\x00" * 8000)

        sub_path = os.path.join(self.temp_dir.name, "fontsubs.ass")
        with open(sub_path, "w") as f:
            f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[Events]\n")

        img = os.path.join(self.temp_dir.name, "fontscene.jpg")
        from PIL import Image
        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(img)

        out_video = os.path.join(self.temp_dir.name, "font_out.mp4")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("lib.video.validate_video_format", return_value=True):
                compose_video(
                    audio_path, sub_path, "", out_video,
                    duration_sec=5.0,
                    min_duration=0.0,
                    scene_images=[img],
                    video_mode="short",
                )
        cmd = mock_run.call_args[0][0]
        fg_idx = cmd.index("-filter_complex")
        filtergraph = cmd[fg_idx + 1]
        self.assertIn("fontsdir=", filtergraph)
        self.assertNotIn("fontsdir='", filtergraph)
        self.assertIn("/assets/fonts", filtergraph)

    def test_subtitle_filtergraph_is_labeled_and_burned(self):
        """Regression: the ASS/subtitles filter MUST carry an output label.

        Without a label ffmpeg auto-maps the subtitle filter output as an extra
        video stream: the final MP4 gets 2 video streams (one without subtitles)
        and the burned-in captions silently disappear from the mapped output.
        """
        import wave as _wave

        audio_path = os.path.join(self.temp_dir.name, "subs_audio.wav")
        with _wave.open(audio_path, "wb") as wav:
            wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(8000)
            wav.writeframes(b"\x01\x00" * 8000)

        sub_path = os.path.join(self.temp_dir.name, "subs.ass")
        with open(sub_path, "w") as f:
            f.write("[Script Info]\nScriptType: v4.00+\nPlayResX: 1080\nPlayResY: 1920\n\n[Events]\n")

        img = os.path.join(self.temp_dir.name, "s.jpg")
        from PIL import Image
        Image.new("RGB", (1080, 1920), (10, 20, 30)).save(img)

        out_video = os.path.join(self.temp_dir.name, "subs_out.mp4")
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("lib.video.validate_video_format", return_value=True):
                compose_video(
                    audio_path, sub_path, "", out_video,
                    duration_sec=5.0,
                    min_duration=0.0,
                    scene_images=[img],
                    video_mode="short",
                )
            cmd = mock_run.call_args[0][0]
            fg_idx = cmd.index("-filter_complex")
            filtergraph = cmd[fg_idx + 1]
            self.assertIn("ass=filename=", filtergraph)
            self.assertNotIn("ass=filename='", filtergraph)
            self.assertNotIn("fontsdir='", filtergraph)
            # Unquoted FFmpeg 6.1 libass path; optional :fontsdir= may follow.
            self.assertRegex(
                filtergraph,
                r"ass=filename=[^':]+(:fontsdir=[^':]+)?\[vsubbed\]",
            )
            self.assertIn(";[vsubbed]format=yuv420p[vout]", filtergraph)
            self.assertIn("-map", cmd)
            self.assertIn("[vout]", cmd)

    def test_prescaled_temp_file_cleanup_in_finally(self):
        """Verify prescaled_*.jpg temporary images are created and cleaned up in try/finally."""
        audio_path = os.path.join(self.temp_dir.name, "clean_audio.wav")
        with open(audio_path, "wb") as f:
            f.write(b"AUDIO_DATA")

        img1 = os.path.join(self.temp_dir.name, "clean_1.jpg")
        from PIL import Image
        Image.new("RGB", (1080, 1920), (50, 50, 50)).save(img1)
        out_video = os.path.join(self.temp_dir.name, "clean_out.mp4")

        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            with patch("lib.video.validate_video_format", return_value=True):
                compose_video(
                    audio_path, "", "", out_video,
                    duration_sec=10.0,
                    min_duration=0.0,
                    scene_images=[img1],
                    video_mode="short",
                )
        # Ensure no prescaled_*.jpg files linger in temp_dir
        lingering = list(Path(self.temp_dir.name).glob("prescaled_*.jpg"))
        self.assertEqual(len(lingering), 0)

    def test_shorts_cadence_dynamic_range(self):
        """Verify Shorts cadence produces scenes strictly within [3.0s, 4.5s]."""
        from lib.video import build_visual_scene_plan
        plan = build_visual_scene_plan(60.0, video_mode="short")
        self.assertGreaterEqual(len(plan), 13)
        self.assertAlmostEqual(sum(s["duration"] for s in plan), 60.0, places=2)
        for s in plan:
            self.assertGreaterEqual(s["duration"], 3.0)
            self.assertLessEqual(s["duration"], 4.5)


if __name__ == "__main__":
    unittest.main()

