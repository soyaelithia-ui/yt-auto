"""
src/export/pipeline.py - Master Cosmic/Analog Horror Video Production Pipeline.
"""
from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import time
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from src.narrative.engine import CosmicNarrativeEngine
from src.narrative.schema import (
    AudioContract,
    CosmicScriptContract,
    NarrativeArchetype,
    VideoFormat,
)
from src.audio.mixer import CosmicAudioMixer
from src.compositing.subtitles import TerminalKaraokeSubtitleGenerator
from src.compositing.stream_renderer import DirectStreamCompositor
from src.export.presets import ExportPreset, get_preset_for_format
from src.log import get_logger

logger = get_logger("cosmic_pipeline")


class CosmicVideoPipeline:
    """End-to-End master orchestrator for Cosmic Horror & Sci-Fi procedural video production."""

    def __init__(self, work_dir: Optional[Union[str, Path]] = None) -> None:
        self.work_dir = Path(work_dir) if work_dir else (Path("work") / "cosmic_pipeline")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.narrative_engine = CosmicNarrativeEngine()
        self.audio_mixer = CosmicAudioMixer(work_dir=self.work_dir / "audio")
        self.subtitle_generator = TerminalKaraokeSubtitleGenerator()
        self.compositor = DirectStreamCompositor()

    def generate_video(
        self,
        topic: Optional[str] = None,
        script_contract: Optional[CosmicScriptContract] = None,
        archetype: Union[NarrativeArchetype, str] = NarrativeArchetype.HYDROACOUSTIC_TELEMETRY,
        video_format: VideoFormat = VideoFormat.SHORT_VERTICAL,
        duration_sec: Optional[float] = None,
        output_mp4: Optional[Union[str, Path]] = None,
        custom_voice_wav: Optional[Union[str, Path]] = None,
        custom_word_timestamps: Optional[List[Dict[str, Any]]] = None,
        fps: Optional[int] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Executes the 5-module production pipeline.
        Returns a dictionary with artifact paths and generation metadata.
        """
        preset = get_preset_for_format(video_format)
        target_dur = float(duration_sec or preset.default_duration_sec)
        target_w = width or preset.width
        target_h = height or preset.height
        target_fps = fps or preset.fps

        run_id = f"cosmic_{int(time.time())}_{os.getpid()}"
        run_folder = self.work_dir / run_id
        run_folder.mkdir(parents=True, exist_ok=True)

        final_mp4 = Path(output_mp4) if output_mp4 else (Path("output") / f"{run_id}.mp4")
        final_mp4.parent.mkdir(parents=True, exist_ok=True)

        logger.info("=================================================================")
        logger.info("🚀 Master Cosmic Video Pipeline: '%s'", topic or "Expediente")
        logger.info("Formato: %s (%dx%d @ %dfps, %.1fs)", video_format.value, target_w, target_h, target_fps, target_dur)
        logger.info("Directorio de ejecución: %s", run_folder)
        logger.info("=================================================================")

        # 1. Module 1: Narrative Script Generation
        if not script_contract:
            logger.info("Módulo 1: Generando guión estructurado con curva de tensión de 5 fases...")
            script = self.narrative_engine.generate_script(
                topic=topic,
                archetype=archetype,
                video_format=video_format,
                duration_sec=target_dur,
            )
        else:
            script = script_contract

        script_json_file = run_folder / "script_contract.json"
        script_json_file.write_text(script.to_json(), encoding="utf-8")

        # 2. TTS Voice Narration / Timestamps Synthesis
        logger.info("Módulo 2 (Paso A): Sintetizando o preparando pista de voz de locución...")
        voice_wav, word_timestamps, effective_dur = self._prepare_voice_track(
            script=script,
            custom_voice_wav=custom_voice_wav,
            custom_word_timestamps=custom_word_timestamps,
            work_folder=run_folder,
            target_dur=target_dur,
        )

        final_dur = max(target_dur, effective_dur) if duration_sec is None else target_dur

        # 3. Module 2: Audio Synthesis & Mastering
        logger.info("Módulo 2 (Paso B): Mezclando Sub-Drone, Cadena Vocal y SFX con Sidechain Ducking...")
        master_audio_wav = run_folder / "master_audio.wav"
        self.audio_mixer.master_soundtrack(
            audio_contract=script.audio,
            raw_voice_wav=voice_wav,
            output_master_wav=master_audio_wav,
            total_duration_sec=final_dur,
        )

        # 4. Module 4: Subtitles Generation
        logger.info("Módulo 4: Generando subtítulos ASS terminal karaoke...")
        subtitles_ass = run_folder / "subtitles.ass"
        self.subtitle_generator.generate_ass(
            word_timestamps=word_timestamps,
            output_ass_path=subtitles_ass,
            width=target_w,
            height=target_h,
        )

        # 5. Module 3 & 4: Direct WebGL Stream to FFmpeg Render
        logger.info("Módulo 3 & 4: Renderizando WebGL multi-pass directamente a FFmpeg stdin...")
        self.compositor.render_and_mux(
            script_contract=script,
            output_mp4_path=final_mp4,
            master_audio_path=master_audio_wav,
            subtitles_ass_path=subtitles_ass if preset.require_subtitles else None,
            duration_sec=final_dur,
            width=target_w,
            height=target_h,
            fps=target_fps,
        )

        logger.info("=================================================================")
        logger.info("✅ Producción finalizada exitosamente: %s (%d KB)", final_mp4, final_mp4.stat().st_size // 1024)
        logger.info("=================================================================")

        return {
            "status": "success",
            "video_path": str(final_mp4.resolve()),
            "script_contract": script.to_dict(),
            "master_audio_path": str(master_audio_wav.resolve()),
            "subtitles_path": str(subtitles_ass.resolve()),
            "duration_sec": final_dur,
            "width": target_w,
            "height": target_h,
            "fps": target_fps,
        }

    def _prepare_voice_track(
        self,
        script: CosmicScriptContract,
        custom_voice_wav: Optional[Union[str, Path]],
        custom_word_timestamps: Optional[List[Dict[str, Any]]],
        work_folder: Path,
        target_dur: float,
    ) -> Tuple[Path, List[Dict[str, Any]], float]:
        """Ensures voice WAV and word timestamps are present, generating synthetic fallback if offline."""
        voice_out = work_folder / "dry_voice.wav"

        if custom_voice_wav and Path(custom_voice_wav).is_file():
            shutil.copy2(custom_voice_wav, voice_out)
            timestamps = custom_word_timestamps or self._approximate_timestamps(script.audio.voice_text, target_dur)
            return voice_out, timestamps, target_dur

        # Try Edge-TTS if available
        try:
            from lib.tts import synthesize_narration_with_timestamps
            res = synthesize_narration_with_timestamps(
                text=script.audio.voice_text,
                out_path=voice_out,
                voice="es-ES-AlvaroNeural",
            )
            if voice_out.is_file() and voice_out.stat().st_size > 0:
                dur = float(res.get("duration_sec", target_dur))
                words = res.get("word_timestamps", [])
                return voice_out, words, dur
        except Exception as e:
            logger.warning("Edge-TTS no disponible, recurriendo a sintetizador vocal determinista (%s)", e)

        # Deterministic Speech Fallback
        words_list = script.audio.voice_text.replace("...", "").split()
        sample_rate = 44100
        total_samples = int(sample_rate * target_dur)
        t = [i / sample_rate for i in range(total_samples)]

        # Modulated synthetic carrier
        import numpy as np
        t_arr = np.arange(total_samples, dtype=np.float32) / sample_rate
        f_speech = 160.0 + 35.0 * np.sin(2.0 * np.pi * 3.5 * t_arr)
        carrier = np.sin(2.0 * np.pi * np.cumsum(f_speech) / sample_rate) * 0.45

        # Rhythmic syllable envelope
        env = np.abs(np.sin(2.0 * np.pi * 4.2 * t_arr)) ** 0.8
        speech_synth = (carrier * env * 32767.0).astype(np.int16)

        with wave.open(str(voice_out), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(speech_synth.tobytes())

        timestamps = self._approximate_timestamps(script.audio.voice_text, target_dur)
        return voice_out, timestamps, target_dur

    def _approximate_timestamps(self, text: str, total_dur: float) -> List[Dict[str, Any]]:
        words = text.replace("...", "").replace("[ALERTA DE SECTOR]", "").replace("[DATOS EXPURGADOS]", "").split()
        if not words:
            return []

        word_dur = total_dur / float(len(words))
        stamps = []
        for idx, w in enumerate(words):
            start = round(idx * word_dur, 2)
            end = round((idx + 1) * word_dur - 0.05, 2)
            stamps.append({"word": w, "start": start, "end": end})
        return stamps
