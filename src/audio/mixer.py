"""
src/audio/mixer.py - Multi-Track Audio Mixer with Sidechain Ducking and EBU R128 Mastering.

Implements the broadcast mastering pipeline:
1. Procedural Sub-Drone Bed
2. Intercom/Bunker Voice Narration (as sidechain control and main vocal)
3. Sample-accurate SFX insertion via FFmpeg adelay
4. Sidechain compressor: speech automatically ducks drone (~-10 dB, attack 15ms, release 350ms)
5. Normalization: loudnorm=I=-16:TP=-1.5:LRA=11
"""
from __future__ import annotations

import os
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from lib.ffmpeg import run_ffmpeg, FFmpegExecutionError
from src.narrative.schema import AudioContract, SFXCue
from src.audio.procedural_drone import ProceduralDroneSynthesizer
from src.audio.vocal_chain import VocalChainProcessor
from src.audio.sfx_library import SFXLibrarySynthesizer
from src.log import get_logger

logger = get_logger("audio_mixer")


class CosmicAudioMixer:
    """Orchestrates multi-track audio generation, vocal chains, SFX timeline, and sidechain ducking."""

    def __init__(self, work_dir: Optional[Union[str, Path]] = None) -> None:
        self.work_dir = Path(work_dir) if work_dir else Path("work/audio_mix")
        self.work_dir.mkdir(parents=True, exist_ok=True)
        self.drone_synth = ProceduralDroneSynthesizer(sample_rate=44100)
        self.vocal_proc = VocalChainProcessor()
        self.sfx_synth = SFXLibrarySynthesizer(sample_rate=44100)

    def master_soundtrack(
        self,
        audio_contract: AudioContract,
        raw_voice_wav: Path,
        output_master_wav: Path,
        total_duration_sec: float,
    ) -> Path:
        """
        Executes end-to-end multi-track mixdown:
        1. Process raw voice through vocal chain
        2. Synthesize procedural drone for total duration
        3. Synthesize and compose SFX track with exact timestamps
        4. Mix with FFmpeg filter_complex sidechain ducking and loudnorm
        """
        output_master_wav.parent.mkdir(parents=True, exist_ok=True)

        # 1. Process Voice
        proc_voice_wav = self.work_dir / "voice_processed.wav"
        if raw_voice_wav.is_file():
            self.vocal_proc.apply_chain(
                input_voice_path=raw_voice_wav,
                output_voice_path=proc_voice_wav,
                preset=audio_contract.voice_preset,
            )
        else:
            raise FileNotFoundError(f"Raw voice WAV not found at: {raw_voice_wav}")

        # 2. Synthesize Drone
        drone_wav = self.work_dir / "drone_bed.wav"
        self.drone_synth.generate_wav(
            output_path=drone_wav,
            duration_sec=total_duration_sec + 2.0,
            base_freq_hz=audio_contract.drone_base_freq_hz,
            amplitude=0.32,
            stereo=True,
        )

        # 3. Synthesize & Combine SFX into an SFX track
        sfx_wav = self._build_sfx_track(audio_contract.sfx_timeline, total_duration_sec)

        # 4. Multi-track Mix with Sidechain Ducking and EBU R128 Loudness Normalization
        self._execute_ffmpeg_mixdown(
            voice_path=proc_voice_wav,
            drone_path=drone_wav,
            sfx_path=sfx_wav,
            output_path=output_master_wav,
            duration_sec=total_duration_sec,
        )

        logger.info("✅ Audio masterizado con éxito en: %s", output_master_wav)
        return output_master_wav

    def _build_sfx_track(self, sfx_timeline: List[SFXCue], total_dur: float) -> Path:
        """Creates a consolidated multi-sfx audio track with adelay offsets."""
        sfx_track_wav = self.work_dir / "sfx_timeline.wav"

        if not sfx_timeline:
            # Generate empty silence track
            safe_dur = max(0.1, float(total_dur))
            cmd = [
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", f"anullsrc=r=44100:cl=stereo:d={safe_dur}",
                "-c:a", "pcm_s16le", str(sfx_track_wav)
            ]
            run_ffmpeg(cmd, check=True)
            return sfx_track_wav

        # Synthesize individual SFX files
        input_args = []
        filter_parts = []

        for idx, cue in enumerate(sfx_timeline):
            cue_sfx_path = self.work_dir / f"sfx_{idx}_{cue.sfx_id}.wav"
            self.sfx_synth.generate_sfx_wav(cue.sfx_id, cue_sfx_path)
            input_args.extend(["-i", str(cue_sfx_path)])

            delay_ms = int(max(0.0, cue.time_sec) * 1000)
            vol = max(0.1, min(2.0, float(cue.volume)))
            filter_parts.append(f"[{idx}:a]volume={vol},adelay={delay_ms}|{delay_ms},apad=whole_dur={total_dur}s[sfx{idx}]")

        if len(sfx_timeline) == 1:
            filter_parts.append("[sfx0]anull[sfx_out]")
        else:
            mix_inputs = "".join([f"[sfx{i}]" for i in range(len(sfx_timeline))])
            filter_parts.append(f"{mix_inputs}amix=inputs={len(sfx_timeline)}:duration=longest:dropout_transition=0[sfx_out]")

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            *input_args,
            "-filter_complex", ";".join(filter_parts),
            "-map", "[sfx_out]",
            "-t", str(total_dur),
            "-c:a", "pcm_s16le",
            str(sfx_track_wav)
        ]
        run_ffmpeg(cmd, check=True)
        return sfx_track_wav

    def _execute_ffmpeg_mixdown(
        self,
        voice_path: Path,
        drone_path: Path,
        sfx_path: Path,
        output_path: Path,
        duration_sec: float,
    ) -> None:
        """
        FFmpeg filtergraph sidechain ducking mix:
        - Voice splits into control and mix
        - Drone is compressed when voice is active (ducked by -18dB)
        - SFX mixed in with adelay alignment
        - Mastered with broadcast EBU R128 loudnorm=I=-16:TP=-1.5:LRA=11
        """
        filter_complex = (
            "[0:a]volume=1.0,asplit=2[v_ctrl][v_mix];"
            "[1:a]volume=0.35[drone_in];"
            "[drone_in][v_ctrl]sidechaincompress=threshold=0.08:ratio=5:attack=15:release=350[drone_ducked];"
            "[2:a]volume=0.85[sfx_in];"
            "[drone_ducked][v_mix][sfx_in]amix=inputs=3:duration=longest:dropout_transition=2[mixed];"
            "[mixed]loudnorm=I=-16:TP=-1.5:LRA=11[aout]"
        )

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(voice_path),
            "-i", str(drone_path),
            "-i", str(sfx_path),
            "-filter_complex", filter_complex,
            "-map", "[aout]",
            "-t", str(duration_sec),
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            str(output_path),
        ]

        logger.info("Ejecutando mezcla multipista con Sidechain Ducking y EBU R128...")
        run_ffmpeg(cmd, check=True)
