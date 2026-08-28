"""
src/audio/vocal_chain.py - Vocal processing chains (intercom bunker, hydrophone radio, blackbox tape).
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional, Union

from src.narrative.schema import VoicePreset
from src.log import get_logger

logger = get_logger("vocal_chain")

VOCAL_FILTERGRAPHS = {
    VoicePreset.INTERCOM_BUNKER: (
        "highpass=f=350,lowpass=f=3400,"
        "equalizer=f=1200:t=q:w=1.5:g=4,"
        "equalizer=f=2600:t=q:w=2:g=3.5,"
        "aeval='val(0)*1.8-0.6*val(0)*val(0)*val(0)',"
        "aecho=0.8:0.4:22|42:0.25|0.15,"
        "dynaudnorm=f=75:g=15"
    ),
    VoicePreset.HYDROPHONE_RADIO: (
        "highpass=f=450,lowpass=f=2800,"
        "equalizer=f=900:t=q:w=2.0:g=6,"
        "equalizer=f=2200:t=q:w=1.8:g=4,"
        "aeval='val(0)*1.6-0.4*val(0)*val(0)*val(0)',"
        "aecho=0.7:0.5:45|90:0.3|0.2,"
        "dynaudnorm=f=75:g=15"
    ),
    VoicePreset.BLACKBOX_TAPE: (
        "highpass=f=300,lowpass=f=4000,"
        "equalizer=f=1800:t=q:w=1.2:g=3,"
        "equalizer=f=3200:t=q:w=2.0:g=-4,"
        "aeval='val(0)*1.9-0.7*val(0)*val(0)*val(0)',"
        "aecho=0.6:0.3:15|30:0.2|0.1,"
        "dynaudnorm=f=75:g=15"
    ),
}


class VocalChainProcessor:
    """Applies specialized vintage/telecommunication audio processing chains to TTS voice narrations."""

    def __init__(self) -> None:
        pass

    def apply_chain(
        self,
        input_voice_path: Union[str, Path],
        output_voice_path: Union[str, Path],
        preset: Union[VoicePreset, str] = VoicePreset.INTERCOM_BUNKER,
    ) -> Path:
        """
        Transforms raw dry TTS audio into a processed bunker/intercom voice track using FFmpeg.
        """
        in_p = Path(input_voice_path)
        out_p = Path(output_voice_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)

        if not in_p.is_file():
            raise FileNotFoundError(f"Input voice file not found: {in_p}")

        if isinstance(preset, str):
            try:
                preset = VoicePreset(preset)
            except ValueError:
                preset = VoicePreset.INTERCOM_BUNKER

        filtergraph = VOCAL_FILTERGRAPHS.get(preset, VOCAL_FILTERGRAPHS[VoicePreset.INTERCOM_BUNKER])

        cmd = [
            "ffmpeg", "-y", "-v", "error",
            "-i", str(in_p),
            "-af", filtergraph,
            "-c:a", "pcm_s16le",
            "-ar", "44100",
            str(out_p),
        ]

        logger.info("Aplicando cadena vocal '%s' con FFmpeg...", preset.value)
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

        return out_p
