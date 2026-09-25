"""
src/media/multi_scene_compositor.py - Master Multi-Scene Dynamic Video Compositor.

Orchestrates multi-scene rendering (8-15s pacing for longform and shorts),
delegating scene segments to either the Hybrid Cinematic AI Engine or the Pure Procedural Engine.

Default assembly (DIRECTOR_SINGLE_PASS=1): when every scene is procedural and catalog loops
resolve, skip per-scene libx264 re-encodes and assemble via stream-copy trim + concat demuxer
(-c:v copy; near-zero CPU) or one filter_complex scale+concat when loops need resize.
Planner ``niche_hud`` (SCP / Reddit-AITA / abyssal) is burned with one extra FFmpeg
drawtext/drawbox stage on that concat graph (encode_defaults veryfast/CRF19) — not N
per-scene encodes, no Playwright, no wgpu, no per-frame Pillow. No HUD keeps -c:v copy
when geometry matches. Real FFmpeg xfade is opt-in (DIRECTOR_XFADE=1) because it shortens
the timeline.

Legacy multi-pass (per-scene encode → concat stream-copy → master) remains for hybrid scenes
or when DIRECTOR_SINGLE_PASS=0. Master still applies EBU R128 audio (-16 LUFS, -1.5 dBTP)
with sidechain ducking and optional libass ASS burn.
Conforms to BaseVideoCompositor interface.
"""
from __future__ import annotations

import re
import shutil
import tempfile
import time
from pathlib import Path
from src.media.encode_defaults import (
    default_ffmpeg_threads,
    default_render_crf,
    default_render_preset,
    loop_matches_target_geometry,
)
from typing import Any, Dict, List, Optional, Tuple, Union

from src.media.interface import BaseVideoCompositor, CompositorError
from src.log import get_logger
from src.media.subtitles import CodeSubtitleDrawer, SubtitleCue, SubtitleTheme
from src.media.subtitles_ass import (
    escape_ffmpeg_filter_path,
    force_pillow_subtitles_enabled,
    has_active_subtitles,
    libass_filter_clause,
    write_ass_from_cues_or_words,
)
from src.scene_manifest import (
    SceneConfig,
    SceneManifestV2,
    parse_scene_manifest_model,
)
from lib.ffmpeg import (
    probe_media,
    run_ffmpeg,
)
from src.media.director_single_pass import (
    build_hud_concat_video_filters,
    build_scale_concat_video_filters,
    build_xfade_video_filters,
    count_director_video_encodes,
    director_single_pass_enabled,
    director_xfade_enabled,
    hud_filter_snippets_for_scenes,
    manifest_eligible_for_loop_single_pass,
)

logger = get_logger("multi_scene_compositor")

__all__ = [
    "MultiSceneCompositor",
    "MultiSceneCompositorError",
]


class MultiSceneCompositorError(CompositorError):
    """Base exception for MultiSceneCompositor operations."""
    pass


class MultiSceneCompositor(BaseVideoCompositor):
    """
    Production-grade master compositor implementing the 4-agent dual-engine multi-scene pipeline.
    """

    def __init__(
        self,
        hybrid_engine: Optional[Any] = None,
        loop_engine: Optional[Any] = None,
        procedural_engine: Optional[Any] = None,
    ) -> None:
        if hybrid_engine is not None:
            self.hybrid_engine = hybrid_engine
        else:
            from src.media.hybrid_engine import HybridVideoEngine
            self.hybrid_engine = HybridVideoEngine()

        if loop_engine is not None:
            self.loop_engine = loop_engine
        elif procedural_engine is not None:
            self.loop_engine = procedural_engine
        else:
            from src.media.loop_engine import LoopVideoEngine
            self.loop_engine = LoopVideoEngine()

    @property
    def procedural_engine(self) -> Any:
        return self.loop_engine

    @procedural_engine.setter
    def procedural_engine(self, val: Any) -> None:
        self.loop_engine = val

    def render(
        self,
        manifest_path: Union[Path, str],
        output_video_path: Union[Path, str],
        crf: int | None = None,
        preset: str | None = None,
        **extra_kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Renders a full multi-scene video from a validated scene_manifest.json.
        """
        manifest = parse_scene_manifest_model(manifest_path)
        out_p = Path(output_video_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)

        width = manifest.resolution[0]
        height = manifest.resolution[1]
        fps = manifest.fps
        total_duration = max(0.5, float(manifest.total_duration_sec))

        logger.info(
            "🎬 Starting Multi-Scene Master Render: story=%s, lane=%s, scenes=%d, total_duration=%.2fs, res=%dx%d",
            manifest.story_id,
            manifest.lane_id,
            len(manifest.scenes),
            total_duration,
            width,
            height,
        )

        t0 = time.time()
        rendered_scene_files: List[Tuple[SceneConfig, Path]] = []
        assembly_plan = count_director_video_encodes(
            n_scenes=len(manifest.scenes),
            single_pass=False,
            use_xfade=False,
            needs_scale=False,
        )
        has_ass_burn = False

        # Prefer native libass ASS burn-in (master assembly). Pillow frame-bridge is opt-in only.
        word_timestamps = extra_kwargs.get("word_timestamps")
        subtitle_cues: Optional[List[SubtitleCue]] = extra_kwargs.get("subtitle_cues")
        subtitle_theme: Optional[SubtitleTheme] = extra_kwargs.get("subtitle_theme")
        if crf is None:
            crf = default_render_crf()
        if preset is None:
            preset = default_render_preset()
        force_pillow = force_pillow_subtitles_enabled(extra_kwargs)
        if force_pillow and (not subtitle_cues) and word_timestamps:
            subtitle_cues = CodeSubtitleDrawer.parse_word_timestamps(word_timestamps)
        if not force_pillow:
            # Production default: never push cues into per-frame Pillow drawers.
            subtitle_cues = None

        import concurrent.futures

        worker_count = min(2, len(manifest.scenes)) if manifest.scenes else 1
        threads_per_worker = max(1, default_ffmpeg_threads() // max(1, worker_count))

        with tempfile.TemporaryDirectory(prefix="multiscene_render_") as tmp_dir_str:
            tmp_dir = Path(tmp_dir_str)
            video_only_assembled = tmp_dir / "video_assembled.mp4"

            # 0. Early Subtitle Resolution — allow single-pass graph fusion to avoid 2-pass re-encodes
            subtitle_file = extra_kwargs.get("subtitle_path") or extra_kwargs.get("subtitles_path") or extra_kwargs.get("ass_path")
            sub_p: Optional[Path] = None
            if subtitle_file and Path(subtitle_file).is_file():
                sub_p = Path(subtitle_file).resolve()
            elif (not force_pillow) and (word_timestamps or extra_kwargs.get("subtitle_cues")):
                ass_tmp = tmp_dir / "multiscene_subs.ass"
                write_ass_from_cues_or_words(
                    output_path=ass_tmp,
                    word_timestamps=word_timestamps if isinstance(word_timestamps, list) else None,
                    cues=extra_kwargs.get("subtitle_cues"),
                    video_width=width,
                    video_height=height,
                )
                if ass_tmp.is_file():
                    sub_p = ass_tmp.resolve()
            if force_pillow and subtitle_cues:
                sub_p = None
            has_ass_burn = bool(sub_p and has_active_subtitles(sub_p))

            self._single_pass_burned_subtitles = False
            used_single_pass = False
            if (
                director_single_pass_enabled()
                and manifest_eligible_for_loop_single_pass(manifest.scenes)
                and not force_pillow
            ):
                try:
                    used_single_pass = self._assemble_procedural_loops_single_pass(
                        manifest=manifest,
                        output_mp4=video_only_assembled,
                        width=width,
                        height=height,
                        fps=fps,
                        crf=crf,
                        preset=preset,
                        tmp_dir=tmp_dir,
                        subtitle_path=sub_p,
                    )
                except Exception as exc:
                    logger.warning(
                        "DIRECTOR_SINGLE_PASS failed (%s); falling back to legacy multi-pass",
                        exc,
                    )
                    used_single_pass = False

            if not used_single_pass:
                # 1. Parallel Scene Segment Rendering (legacy multi-pass)
                def _render_scene_worker(item: Tuple[int, SceneConfig]) -> Tuple[int, SceneConfig, Path]:
                    idx, scene = item
                    sc_out = tmp_dir / f"scene_{idx:03d}_{scene.scene_id}.mp4"
                    logger.info(
                        "Rendering Scene %d/%d (id=%s, engine=%s, dur=%.2fs, tension=%d, threads=%d)",
                        idx + 1,
                        len(manifest.scenes),
                        scene.scene_id,
                        scene.engine_type,
                        scene.duration_sec,
                        scene.tension_level,
                        threads_per_worker,
                    )

                    if scene.engine_type == "hybrid_cinematic_ai":
                        self.hybrid_engine.render_scene_segment(
                            scene=scene,
                            width=width,
                            height=height,
                            fps=fps,
                            output_mp4=sc_out,
                            crf=crf,
                            subtitle_cues=subtitle_cues,
                            scene_start_sec=scene.start_sec,
                            subtitle_theme=subtitle_theme,
                            threads=threads_per_worker,
                        )
                    else:
                        self.loop_engine.render_scene_segment(
                            scene=scene,
                            width=width,
                            height=height,
                            fps=fps,
                            lane_id=manifest.lane_id,
                            output_mp4=sc_out,
                            crf=crf,
                            subtitle_cues=subtitle_cues,
                            scene_start_sec=scene.start_sec,
                            subtitle_theme=subtitle_theme,
                            threads=threads_per_worker,
                        )
                    return (idx, scene, sc_out)

                with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
                    parallel_results = list(executor.map(_render_scene_worker, enumerate(manifest.scenes)))

                parallel_results.sort(key=lambda x: x[0])
                rendered_scene_files = [(r[1], r[2]) for r in parallel_results]

                # 2. Assemble video stream (instant stream copy concat)
                self._assemble_video_scenes(rendered_scene_files, video_only_assembled, width, height, fps)
                assembly_plan = count_director_video_encodes(
                    n_scenes=len(manifest.scenes),
                    single_pass=False,
                    use_xfade=False,
                    needs_scale=False,
                )
            else:
                assembly_plan = getattr(self, "_last_assembly_plan", assembly_plan)

            # 3. Master audio mixing (narration + BGM + sidechain ducking + EBU R128)
            narration_audio = (
                Path(manifest.audio_tracks.narration_path).resolve()
                if manifest.audio_tracks.narration_path
                and Path(manifest.audio_tracks.narration_path).is_file()
                else None
            )
            music_audio = Path(manifest.audio_tracks.music_path).resolve() if manifest.audio_tracks.music_path and Path(manifest.audio_tracks.music_path).is_file() else None

            # 4. Fast Master Assembly with FFmpeg — stream-copy if subtitles were burned in single pass
            sub_p_master = None if getattr(self, "_single_pass_burned_subtitles", False) else sub_p
            has_ass_burn = bool((sub_p and has_active_subtitles(sub_p)) or getattr(self, "_single_pass_burned_subtitles", False))

            self._master_assembly(
                video_input=video_only_assembled,
                narration_audio=narration_audio,
                music_audio=music_audio,
                music_volume=manifest.audio_tracks.music_volume,
                subtitle_path=sub_p_master,
                total_duration=total_duration,
                width=width,
                height=height,
                crf=crf,
                preset=preset,
                output_mp4=out_p,
            )

        elapsed = time.time() - t0
        file_size = out_p.stat().st_size if out_p.exists() else 0
        logger.info(
            "🎉 Multi-Scene Master Render COMPLETED in %.2fs. Master: %s (%.2f MB)",
            elapsed,
            out_p,
            file_size / (1024 * 1024),
        )

        return {
            "status": "success",
            "output_path": str(out_p),
            "file_size_bytes": file_size,
            "render_time_sec": elapsed,
            "scenes_count": len(manifest.scenes),
            "engine": "multi_scene_dual_engine",
            "director_assembly": assembly_plan.as_dict(),
            "director_video_encodes_estimate": assembly_plan.total_video_encodes(
                has_ass_burn=has_ass_burn
            ),
        }


    def _resolve_procedural_loop_path(
        self,
        scene: SceneConfig,
        *,
        width: int,
        height: int,
        lane_id: str,
    ) -> Optional[Path]:
        """Resolve a catalog/on-disk loop for a scene without re-encoding."""
        asset_candidate = getattr(scene, "asset_path", None) or getattr(scene, "loop_path", None)
        if asset_candidate and Path(asset_candidate).is_file():
            return Path(asset_candidate).resolve()

        eng = self.loop_engine
        orientation = "vertical" if height > width else "horizontal"
        env_name = scene.environment_name or lane_id or "dark_ambient"
        base_env = re.sub(r"\s*\(Cut\s+\d+\)", "", str(env_name)).strip()
        category = eng.normalize_category(base_env) if hasattr(eng, "normalize_category") else base_env

        if hasattr(eng, "resolve_loop_video"):
            try:
                cand = eng.resolve_loop_video(
                    category=category,
                    orientation=orientation,
                    channel=lane_id,
                    allow_fallback=False,
                )
                if cand and isinstance(cand, Path) and cand.is_file():
                    return cand.resolve()
            except Exception:
                pass

        return None

    def _stream_copy_signature(
        self, loop_path: Path
    ) -> Optional[Tuple[int, int, str, str, str]]:
        """Return (w, h, codec, pix_fmt, time_base) for concat demuxer -c:v copy safety."""
        try:
            probe = probe_media(loop_path)
            vs = probe.video_streams[0] if probe.video_streams else probe.primary_video
            if vs is None:
                return None
            time_base = ""
            for s in (probe.raw_payload or {}).get("streams", []):
                if s.get("codec_type") == "video":
                    time_base = str(s.get("time_base") or "")
                    break
            return (
                int(vs.width),
                int(vs.height),
                str(getattr(vs, "codec_name", "") or ""),
                str(getattr(vs, "pix_fmt", "") or ""),
                time_base,
            )
        except Exception:
            return None

    def _loop_matches_target(self, loop_path: Path, width: int, height: int) -> bool:
        # Shared SSOT with proc_engine / encode_defaults (PR #12).
        return loop_matches_target_geometry(loop_path, width, height)

    def _loops_homogeneous_for_stream_copy(
        self, loop_paths: List[Path], width: int, height: int
    ) -> bool:
        """True only when all loops share WxH/codec/pix_fmt/time_base and match target WxH."""
        if not loop_paths:
            return False
        sigs: List[Tuple[int, int, str, str, str]] = []
        for p in loop_paths:
            sig = self._stream_copy_signature(p)
            if sig is None:
                return False
            if sig[0] != int(width) or sig[1] != int(height):
                return False
            # Require codec + pix_fmt so concat demuxer -c:v copy is safe.
            if not sig[2] or not sig[3]:
                return False
            sigs.append(sig)
        first = sigs[0]
        return all(s == first for s in sigs)


    def _assemble_procedural_loops_single_pass(
        self,
        *,
        manifest: SceneManifestV2,
        output_mp4: Path,
        width: int,
        height: int,
        fps: int,
        crf: int,
        preset: str,
        tmp_dir: Path,
        subtitle_path: Optional[Path] = None,
    ) -> bool:
        """Assemble all-procedural scenes from catalog loops without per-scene re-encodes.

        Planner ``niche_hud`` is applied as one FFmpeg filter_complex (drawtext/drawbox)
        on the concat/xfade graph. Subtitles are fused into the single encode when present,
        eliminating a secondary re-encode. No HUD/subs + homogeneous geometry keeps ``-c:v copy``.

        Returns True on success (output_mp4 written). Raises or returns False on ineligibility.
        """
        loop_paths: List[Path] = []
        durations: List[float] = []
        for scene in manifest.scenes:
            lp = self._resolve_procedural_loop_path(
                scene, width=width, height=height, lane_id=manifest.lane_id
            )
            if lp is None or not lp.is_file():
                logger.info(
                    "Single-pass skip: no loop for scene=%s env=%s",
                    scene.scene_id,
                    scene.environment_name,
                )
                return False
            loop_paths.append(lp)
            durations.append(max(0.5, float(scene.duration_sec)))

        # Stream-copy only when every loop matches target WxH AND is codec/pix_fmt/timebase-homogeneous
        # AND no planner niche HUD (HUD requires a drawtext/drawbox re-encode).
        # Otherwise one scale+concat / concat+HUD / xfade encode.
        needs_scale = not self._loops_homogeneous_for_stream_copy(
            loop_paths, width, height
        )
        use_xfade = director_xfade_enabled() and len(loop_paths) > 1
        hud_snippets = hud_filter_snippets_for_scenes(manifest.scenes, width, height)
        has_hud = any(bool(s) for s in hud_snippets)

        plan = count_director_video_encodes(
            n_scenes=len(loop_paths),
            single_pass=True,
            use_xfade=use_xfade,
            needs_scale=needs_scale,
            has_hud=has_hud,
        )
        self._last_assembly_plan = plan
        logger.info(
            "DIRECTOR_SINGLE_PASS mode=%s scenes=%d needs_scale=%s xfade=%s hud=%s "
            "(eliminates %d per-scene encodes)",
            plan.mode,
            len(loop_paths),
            needs_scale,
            use_xfade,
            has_hud,
            len(loop_paths),
        )

        if not needs_scale and not use_xfade and not has_hud:
            # Near-zero CPU: stream-copy trim each loop, then concat demuxer -c:v copy.
            trimmed: List[Path] = []
            for i, (lp, dur) in enumerate(zip(loop_paths, durations)):
                out_seg = tmp_dir / f"sp_trim_{i:03d}.mp4"
                cmd = [
                    "ffmpeg", "-y",
                    "-stream_loop", "-1",
                    "-i", str(lp),
                    "-t", f"{dur:.3f}",
                    "-c:v", "copy",
                    "-an",
                    "-movflags", "+faststart",
                    str(out_seg),
                ]
                run_ffmpeg(cmd)
                trimmed.append(out_seg)
            self._assemble_video_scenes(
                [(manifest.scenes[i], trimmed[i]) for i in range(len(trimmed))],
                output_mp4,
                width,
                height,
                fps,
            )
            return output_mp4.is_file()

        # One filter_complex encode (scale+concat, concat+HUD, or xfade). HUD is fused
        # into this graph — never N per-scene encodes. Re-encode uses encode_defaults.
        cmd: List[str] = ["ffmpeg", "-y"]
        for lp, dur in zip(loop_paths, durations):
            cmd.extend(["-stream_loop", "-1", "-t", f"{dur:.3f}", "-i", str(lp)])

        hud_arg = hud_snippets if has_hud else None
        if use_xfade:
            # Use first scene transition duration when present.
            t_req = 0.75
            t0 = getattr(manifest.scenes[0], "transition_out", None)
            if t0 is not None and getattr(t0, "duration_sec", None):
                t_req = float(t0.duration_sec)
            parts, v_out, _out_dur = build_xfade_video_filters(
                durations, width, height, fps, transition_sec=t_req, hud_snippets=hud_arg
            )
        elif needs_scale:
            parts, v_out = build_scale_concat_video_filters(
                len(loop_paths), width, height, fps, hud_snippets=hud_arg
            )
        else:
            # Homogeneous loops + HUD: one extra drawtext/drawbox stage on concat (no scale).
            parts, v_out = build_hud_concat_video_filters(len(loop_paths), hud_snippets)

        if has_hud:
            crf = default_render_crf()
            preset = default_render_preset()

        # Fuse subtitles into the single encode to avoid a 2nd re-encode pass
        if subtitle_path and has_active_subtitles(subtitle_path):
            if str(subtitle_path).lower().endswith(".ass"):
                fonts_dir = Path("assets/fonts").resolve()
                fonts_arg = fonts_dir if fonts_dir.is_dir() else None
                parts.append(f"{v_out}{libass_filter_clause(subtitle_path, fonts_arg)}[vsub]")
            else:
                parts.append(f"{v_out}subtitles=filename={escape_ffmpeg_filter_path(subtitle_path)}[vsub]")
            v_out = "[vsub]"
            self._single_pass_burned_subtitles = True
        else:
            self._single_pass_burned_subtitles = False

        cmd.extend([
            "-filter_complex", ";".join(parts),
            "-map", v_out,
            "-c:v", "libx264",
            "-crf", str(crf),
            "-preset", str(preset),
            "-pix_fmt", "yuv420p",
            "-colorspace", "bt709",
            "-color_primaries", "bt709",
            "-color_trc", "bt709",
            "-an",
            "-movflags", "+faststart",
            str(output_mp4),
        ])
        run_ffmpeg(cmd)
        return output_mp4.is_file()

    def _assemble_video_scenes(
        self,
        scene_files: List[Tuple[SceneConfig, Path]],
        output_mp4: Path,
        width: int,
        height: int,
        fps: int,
    ) -> None:
        """Stitches individual scene MP4 files into a single video track with stream copy."""
        if len(scene_files) == 1:
            shutil.copy2(scene_files[0][1], output_mp4)
            return

        concat_list_file = output_mp4.parent / "scenes_concat_list.txt"
        with open(concat_list_file, "w") as f:
            for _, sc_path in scene_files:
                f.write(f"file '{sc_path.resolve()}'\n")

        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat_list_file),
            "-c:v", "copy",
            "-movflags", "+faststart",
            str(output_mp4),
        ]
        run_ffmpeg(cmd)

    def _master_assembly(
        self,
        video_input: Path,
        narration_audio: Optional[Path],
        music_audio: Optional[Path],
        music_volume: float,
        subtitle_path: Optional[Path],
        total_duration: float,
        width: int,
        height: int,
        crf: int,
        preset: str,
        output_mp4: Path,
    ) -> None:
        """
        Ultra-fast Master Audio/Video Assembly:
        Stream copies pre-rendered 1080p video in ~1s and mixes EBU R128 audio with sidechain ducking.
        """
        cmd: List[str] = ["ffmpeg", "-y", "-i", str(video_input)]
        video_copy = not has_active_subtitles(subtitle_path)

        if not video_copy and subtitle_path:
            vf_parts = []
            if not loop_matches_target_geometry(video_input, width, height):
                vf_parts.append(f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}")
            if str(subtitle_path).lower().endswith(".ass"):
                fonts_dir = Path("assets/fonts").resolve()
                fonts_arg = fonts_dir if fonts_dir.is_dir() else None
                vf_parts.append(libass_filter_clause(subtitle_path, fonts_arg))
            else:
                vf_parts.append(f"subtitles=filename={escape_ffmpeg_filter_path(subtitle_path)}")
            vf_parts.append("format=yuv420p")
            vf_chain = ",".join(vf_parts)

        # Audio handling (sample rate unified to 44100; loudnorm I=-16 per Experto YT)
        has_audio_map = False
        if narration_audio and narration_audio.is_file():
            has_audio_map = True
            cmd.extend(["-i", str(narration_audio)])
            if music_audio and music_audio.is_file():
                cmd.extend(["-stream_loop", "-1", "-i", str(music_audio)])
                if video_copy:
                    filter_complex = (
                        f"[1:a]aresample=44100,asplit=2[speech_sc][speech_mix];"
                        f"[2:a]aresample=44100,lowpass=f=12000,volume={music_volume:.4f}[music_in];"
                        f"[music_in][speech_sc]sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[music_ducked];"
                        f"[speech_mix][music_ducked]amix=inputs=2:duration=first:normalize=0[amixed];"
                        f"[amixed]loudnorm=I=-16.0:TP=-1.5:LRA=11.0,aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
                    )
                    cmd.extend(["-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[aout]"])
                else:
                    filter_complex = (
                        f"[0:v]{vf_chain}[vout];"
                        f"[1:a]aresample=44100,asplit=2[speech_sc][speech_mix];"
                        f"[2:a]aresample=44100,lowpass=f=12000,volume={music_volume:.4f}[music_in];"
                        f"[music_in][speech_sc]sidechaincompress=threshold=0.035:ratio=8.0:attack=20.0:release=350.0:makeup=1[music_ducked];"
                        f"[speech_mix][music_ducked]amix=inputs=2:duration=first:normalize=0[amixed];"
                        f"[amixed]loudnorm=I=-16.0:TP=-1.5:LRA=11.0,aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
                    )
                    cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"])
            else:
                if video_copy:
                    filter_complex = (
                        f"[1:a]loudnorm=I=-16.0:TP=-1.5:LRA=11.0,aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
                    )
                    cmd.extend(["-filter_complex", filter_complex, "-map", "0:v:0", "-map", "[aout]"])
                else:
                    filter_complex = (
                        f"[0:v]{vf_chain}[vout];"
                        f"[1:a]loudnorm=I=-16.0:TP=-1.5:LRA=11.0,aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
                    )
                    cmd.extend(["-filter_complex", filter_complex, "-map", "[vout]", "-map", "[aout]"])
        else:
            if video_copy:
                cmd.extend(["-map", "0:v:0"])
            else:
                cmd.extend(["-vf", vf_chain, "-map", "0:v:0"])

        cmd.extend(["-t", f"{total_duration:.3f}"])
        if video_copy:
            cmd.extend(["-c:v", "copy"])
        else:
            cmd.extend([
                "-c:v", "libx264",
                "-crf", str(crf),
                "-preset", str(preset),
                "-colorspace", "bt709",
                "-color_primaries", "bt709",
                "-color_trc", "bt709",
            ])

        if has_audio_map:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "192k",
                "-ar", "44100",
                "-ac", "2",
            ])
        cmd.extend([
            "-threads", str(default_ffmpeg_threads()),
            "-movflags", "+faststart",
            str(output_mp4),
        ])
        run_ffmpeg(cmd)
