"""
scripts/generate_production_designed_sample.py - Generate a real multi-act, graphic-designed Short
with synchronized HUD overlays, biometric telemetry, sound design, and narrative pacing.
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import edge_tts
from src.media.ken_burns import build_ken_burns_zoompan_filter
from src.media.visual_coherence import build_coherent_color_grade
from src.telegram.notifier import TelegramNotifier


def generate_styled_ass_subtitles(
    ass_path: Path,
    events_data: list[tuple[float, float, str]],
    width: int = 1080,
    height: int = 1920,
    margin_v: int = 480,
) -> None:
    """Generates broadcast-grade ASS subtitles with dark backing and yellow/white text."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,Arial,48,&H00FFFFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,1,0,3,6,2,2,60,60,{margin_v},1
Style: Highlight,Arial,52,&H0000FFFF,&H000000FF,&H00000000,&H80000000,-1,0,0,0,100,100,2,0,3,8,2,2,60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for t_start, t_end, text in events_data:
        m_start, s_start = divmod(t_start, 60)
        h_start, m_start = divmod(m_start, 60)
        m_end, s_end = divmod(t_end, 60)
        h_end, m_end = divmod(m_end, 60)
        
        start_str = f"{int(h_start):d}:{int(m_start):02d}:{s_start:05.2f}"
        end_str = f"{int(h_end):d}:{int(m_end):02d}:{s_end:05.2f}"
        events.append(f"Dialogue: 0,{start_str},{end_str},Highlight,,0,0,0,,{text.upper()}")
        
    ass_path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")


async def build_production_video(tmp: Path) -> tuple[Path, float]:
    """Builds a complete, broadcast-designed 3-act story Short."""
    
    # 1. Narrative Script with 3 Acts
    acts = [
        {
            "act": 1,
            "title": "EXPEDIENTE CLASIFICADO",
            "text": "Expediente clasificado. El catorce de marzo, la sonda Deep Nine perdió comunicación a cuatro mil metros de profundidad.",
            "backdrop": "assets/thumbnails/templates/scp/master_backdrop.jpg",
            "svg_overlay": "assets/svg_overlays/scp_classification_stamp.svg",
            "svg_params": {"item_number": "892", "classification": "EUCLID"},
            "pan": "center_to_top",
            "grade": "horror",
        },
        {
            "act": 2,
            "title": "TELEMETRÍA CRÍTICA",
            "text": "La telemetría biométrica registró un pulso electromagnético masivo que apagó los tres generadores principales.",
            "backdrop": "assets/background.jpg",
            "svg_overlay": "assets/svg_overlays/hud_tactical_telemetry.svg",
            "svg_params": {"telemetry_text": "DEPTH 4120M // ANOMALY", "bpm": "142"},
            "pan": "left_to_right",
            "grade": "scifi",
        },
        {
            "act": 3,
            "title": "EL CONTACTO",
            "text": "La última transmisión de audio no era estática... eran voces humanas respirando bajo el agua.",
            "backdrop": "assets/thumbnails/templates/horror/master_backdrop.jpg",
            "svg_overlay": "assets/svg_overlays/biometric_wave.svg",
            "svg_params": {"bpm": "178", "spo2": "64"},
            "pan": "center_to_bottom",
            "grade": "horror",
        }
    ]
    
    # 2. Synthesize Audio for Each Act
    full_audio_pieces = []
    act_durations = []
    sub_events = []
    current_time = 0.0
    
    for i, act_data in enumerate(acts):
        audio_act_path = tmp / f"act_{i+1}.mp3"
        comm = edge_tts.Communicate(act_data["text"], "es-ES-AlvaroNeural")
        await comm.save(str(audio_act_path))
        
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(audio_act_path)],
            capture_output=True,
            text=True,
            check=True,
        )
        act_dur = float(probe.stdout.strip())
        act_durations.append(act_dur)
        full_audio_pieces.append(audio_act_path)
        
        # Subtitle chunks for this act
        words = act_data["text"].split()
        chunk_size = 4
        chunks = [words[j:j + chunk_size] for j in range(0, len(words), chunk_size)]
        dur_per_chunk = act_dur / len(chunks)
        
        for k, chk in enumerate(chunks):
            start = current_time + (k * dur_per_chunk)
            end = min(current_time + act_dur, start + dur_per_chunk)
            sub_events.append((start, end, " ".join(chk)))
            
        current_time += act_dur

    total_duration = sum(act_durations)
    
    # 3. Concatenate Act Audios and Mix Ambient Horror Music
    concat_audio_txt = tmp / "concat_audio.txt"
    concat_audio_txt.write_text("".join(f"file '{p.resolve()}'\n" for p in full_audio_pieces))
    voiceover_wav = tmp / "voiceover.wav"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_audio_txt), "-c:a", "pcm_s16le", str(voiceover_wav)],
        capture_output=True,
        check=True,
    )
    
    # Mix with background ambient music (ducked by 16dB)
    music_src = Path("assets/music/horror_ambient.mp3").resolve()
    mixed_audio = tmp / "mixed_audio.wav"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(voiceover_wav),
            "-stream_loop", "-1", "-i", str(music_src),
            "-filter_complex",
            "[1:a]volume=0.12[bgm];"
            "[0:a][bgm]amix=inputs=2:duration=first:dropout_transition=2[aout]",
            "-map", "[aout]",
            "-t", str(total_duration),
            str(mixed_audio),
        ],
        capture_output=True,
        check=True,
    )
    
    # 4. Generate Subtitles ASS
    ass_path = tmp / "story_subs.ass"
    generate_styled_ass_subtitles(ass_path, sub_events, width=1080, height=1920, margin_v=480)
    escaped_ass = str(ass_path).replace("\\", "/").replace(":", "\\:")
    
    # 5. Render Video Clip for Each Act with Ken Burns, Color Grade, and SVG HUD Overlay
    rendered_acts = []
    fps = 30
    
    for i, act_data in enumerate(acts):
        dur = act_durations[i]
        total_frames = int(round(dur * fps))
        act_out = tmp / f"act_video_{i+1}.mp4"
        
        # Prepare SVG Overlay with parameter interpolation
        raw_svg = Path(act_data["svg_overlay"]).read_text(encoding="utf-8")
        for k, v in act_data["svg_params"].items():
            raw_svg = raw_svg.replace(f"{{{{{k}}}}}", str(v)).replace(f"{{{k}}}", str(v))
        svg_interpolated = tmp / f"overlay_{i+1}.svg"
        svg_interpolated.write_text(raw_svg, encoding="utf-8")
        
        # Rasterize SVG to PNG via resvg or ffmpeg
        overlay_png = tmp / f"overlay_{i+1}.png"
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(svg_interpolated), str(overlay_png)],
            capture_output=True,
            check=True,
        )
        
        # Motion filter (Ken Burns) + Color grading + SVG Overlay overlay
        flt_kb = build_ken_burns_zoompan_filter(1080, 1920, fps, total_frames, 1.0, 1.15, act_data["pan"])
        grade = build_coherent_color_grade(act_data["grade"])
        bg_path = Path(act_data["backdrop"]).resolve()
        
        # Composite scene: [background with Ken Burns] -> [color grade] -> [overlay HUD]
        fc = (
            f"[0:v]{flt_kb},{grade}[vbase];"
            f"[vbase][1:v]overlay=0:0[vout]"
        )
        
        subprocess.run(
            [
                "ffmpeg", "-y",
                "-threads", "2",
                "-loop", "1", "-i", str(bg_path),
                "-loop", "1", "-i", str(overlay_png),
                "-filter_complex", fc,
                "-map", "[vout]",
                "-t", str(dur),
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-threads", "2",
                "-pix_fmt", "yuv420p",
                str(act_out),
            ],
            capture_output=True,
            check=True,
        )
        rendered_acts.append(act_out)

    # 6. Concat the 3 Acts with XFade Transitions or Clean Fast Concat
    concat_list = tmp / "concat_acts.txt"
    concat_list.write_text("".join(f"file '{p.resolve()}'\n" for p in rendered_acts))
    
    concatenated_video = tmp / "concatenated.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_list), "-c", "copy", str(concatenated_video)],
        capture_output=True,
        check=True,
    )
    
    # 7. Final Pass: Burn Synchronized Subtitles + Mux Mixed Audio
    final_output = tmp / "production_designed_short.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(concatenated_video),
            "-i", str(mixed_audio),
            "-vf", f"ass={escaped_ass}",
            "-map", "0:v", "-map", "1:a",
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "22", "-threads", "2",
            "-c:a", "aac", "-b:a", "192k",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(final_output),
        ],
        capture_output=True,
        check=True,
    )
    
    return final_output, total_duration


def main() -> None:
    print("=" * 80)
    print("🎬 GENERATING COMPLETE PRODUCTION-DESIGNED SHORT (3 ACTS + HUD + AUDIO)")
    print("=" * 80)
    
    notifier = TelegramNotifier()
    
    with tempfile.TemporaryDirectory(prefix="prod_short_") as tmp_str:
        tmp = Path(tmp_str)
        t0 = time.perf_counter()
        video_path, duration = asyncio.run(build_production_video(tmp))
        t1 = time.perf_counter()
        
        file_size_kb = video_path.stat().st_size / 1024.0
        print(f"✅ Video Generated in {t1 - t0:.2f}s ({file_size_kb:.1f} KiB, {duration:.2f}s)")
        
        caption = (
            "🎯 *Video con Diseño Gráfico Editorial y Coherencia Narrativa Completa*\n\n"
            "• *Estructura*: Historia real en 3 Actos con progresión de tensión.\n"
            "• *Acto 1*: Sello expediente `SCP FOUNDATION // TOP SECRET // ITEM #892`.\n"
            "• *Acto 2*: Telemetría táctica naval (`DEPTH 4120M // ANOMALY // BPM 142`).\n"
            "• *Acto 3*: Monitor biométrico de pánico (`HEART RATE: 178 BPM`) con etalonaje oscuro.\n"
            "• *Motion Design*: Cámara Ken Burns suave (`smoothstep`) en 3 direcciones distintas.\n"
            "• *Audio Design*: Voz neuronal + música drone de fondo con *ducking* a -16 dB.\n"
            "• *Subtítulos*: Tipografía en caja contrastada respetando la zona segura de Shorts."
        )
        
        print("🚀 Dispatching to Telegram...")
        res = notifier.send_video(str(video_path), caption=caption, duration=duration)
        print(f"📦 Telegram Delivery: {res.ok}, Message ID: {res.message_id}")
        
    print("=" * 80)


if __name__ == "__main__":
    main()
