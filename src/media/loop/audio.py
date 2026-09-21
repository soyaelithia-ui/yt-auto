"""Audio processing: automated sidechain ducking, lowpass filtering, and EBU R128 loudness mastering."""

from __future__ import annotations

from src.log import get_logger

logger = get_logger("loop_audio")


class LoopAudioMixin:
    """Methods for constructing FFmpeg audio filter chains with sidechain ducking and loudness normalization."""

    def build_audio_filter(
        self,
        has_music: bool = True,
        music_volume: float = 0.04,
        ducking_threshold: float = 0.035,
        ducking_ratio: float = 8.0,
        ducking_attack_ms: float = 20.0,
        ducking_release_ms: float = 350.0,
        lowpass_freq: int = 12000,
        master_loudness: bool = True,
        target_lufs: float = -16.0,
        max_tp: float = -1.5,
        lra: float = 11.0,
    ) -> str:
        """
        Generates FFmpeg audio filter graph with sidechain ducking and EBU R128 loudness mastering.
        """
        if has_music:
            lp_clause = f"lowpass=f={lowpass_freq}," if lowpass_freq and lowpass_freq > 0 else ""
            graph = (
                f"[1:a]aresample=44100,asplit=2[speech_sc][speech_mix];"
                f"[2:a]aresample=44100,{lp_clause}volume={music_volume:.4f}[music_in];"
                f"[music_in][speech_sc]sidechaincompress=threshold={ducking_threshold}:ratio={ducking_ratio}:attack={ducking_attack_ms}:release={ducking_release_ms}:makeup=1[music_ducked];"
                f"[speech_mix][music_ducked]amix=inputs=2:duration=first:normalize=0[amixed];"
            )
            if master_loudness:
                graph += f"[amixed]loudnorm=I={target_lufs}:TP={max_tp}:LRA={lra},aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
            else:
                graph += f"[amixed]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
            return graph
        else:
            if master_loudness:
                return (
                    f"[1:a]aresample=44100,loudnorm=I={target_lufs}:TP={max_tp}:LRA={lra},"
                    f"aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
                )
            else:
                return f"[1:a]aresample=44100,aformat=sample_fmts=fltp:sample_rates=44100:channel_layouts=stereo[aout]"
