#!/usr/bin/env python3
"""
scripts/inspect_visual_output.py - Empirical Visual Inspection & QA Rig.

Allows inspecting video frames, semantic motif resolution, and thumbnail creation
fragment-by-fragment without blind execution.

Usage:
  python3 scripts/inspect_visual_output.py --topic "Terror con caramelos" --lane moku-scp-shorts
  python3 scripts/inspect_visual_output.py --topic "Misterio en el faro" --lane moku-horror-longform
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from src.config import BASE_DIR
from src.core.catalog import LoopCatalogRepository, compute_file_sha256
from src.core.scenic_detector import extract_story_motifs
from src.media.loop_engine import LoopVideoEngine
from src.media.thumbnails import ThumbnailConfig, ThumbnailEngine

ARTIFACTS_DIR = Path("/home/moku/.gemini/antigravity-cli/brain/94b740c5-bbbf-45d3-b964-be25b918b147")


def extract_frame(video_path: Path, timestamp_sec: float, output_img: Path) -> bool:
    """Extracts a single high-quality frame from a video using ffmpeg."""
    output_img.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg",
        "-y",
        "-ss", str(timestamp_sec),
        "-i", str(video_path),
        "-vframes", "1",
        "-q:v", "2",
        str(output_img),
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return res.returncode == 0 and output_img.is_file() and output_img.stat().st_size > 0


def inspect_story(
    topic: str,
    channel: str = "moku",
    lane: str = "moku-scp-shorts",
    output_dir: Path | None = None,
    copy_to_artifacts: bool = True,
) -> dict:
    """
    Executes end-to-end visual resolution, extracts empirical keyframes,
    generates matching high-CTR thumbnail, and reports metrics.
    """
    out_dir = output_dir or (REPO_ROOT / "output" / "visual_inspection" / channel / topic.replace(" ", "_").lower())
    out_dir.mkdir(parents=True, exist_ok=True)

    is_horizontal = (
        "long" in lane.lower()
        or "16:9" in lane.lower()
        or "horizontal" in lane.lower()
    )
    orientation = "horizontal" if is_horizontal else "vertical"

    print(f"\n======================================================================")
    print(f"🎬 [VISUAL INSPECTION RIG] Empirical Story Resolution & Frame Audit")
    print(f"======================================================================")
    print(f"  Topic:       {topic}")
    print(f"  Channel:     {channel}")
    print(f"  Lane:        {lane} ({orientation})")
    print(f"  Output Dir:  {out_dir}")

    # 1. Semantic Motif Extraction
    motifs = extract_story_motifs(topic)
    print(f"\n🔍 [1. Motif Detection]")
    print(f"  Detected Motifs: {motifs if motifs else '(none - fallback to lane default)'}")

    # 2. Multi-Scene Loop Video Asset Resolution
    loop_engine = LoopVideoEngine()
    target_category = "horror" if channel == "moku" else ("scifi" if channel == "scifi" else "drama")
    
    shot_count = 4
    resolved_scenes = []
    for s_idx in range(shot_count):
        sp = loop_engine.resolve_loop_video(
            category=target_category,
            channel=channel,
            motifs=motifs,
            topic=topic,
            orientation=orientation,
            seed=s_idx * 101,
            exclude_loop_ids=resolved_scenes,
        )
        resolved_scenes.append(str(sp))

    hero_scene = Path(resolved_scenes[0])
    asset_sha = compute_file_sha256(hero_scene) if hero_scene.is_file() else "N/A"
    print(f"\n🎥 [2. Multi-Scene Resolution]")
    for idx, sc in enumerate(resolved_scenes):
        print(f"  Scene {idx+1}: {Path(sc).name}")
    print(f"  Hero Scene SHA-256: {asset_sha}")

    # 3. Extract Empirical Video Keyframes
    print(f"\n📸 [3. Frame Extraction (Zero-Blindness)]")
    extracted_frames = []
    for s_idx, sc_path in enumerate(resolved_scenes):
        frame_name = f"scene_{s_idx+1}_frame.jpg"
        frame_path = out_dir / frame_name
        if extract_frame(Path(sc_path), 2.0, frame_path):
            extracted_frames.append(frame_path)
            print(f"  ✅ Extracted scene {s_idx+1} keyframe: {frame_name} ({frame_path.stat().st_size} bytes)")
        elif extract_frame(Path(sc_path), 0.0, frame_path):
            extracted_frames.append(frame_path)
            print(f"  ✅ Extracted scene {s_idx+1} fallback frame: {frame_name}")

    # 4. Generate High-CTR Thumbnail
    print(f"\n🎨 [4. Thumbnail Composition (Portadas Exclusivas)]")
    thumb_engine = ThumbnailEngine()
    thumb_width = 1280 if is_horizontal else 720
    thumb_height = 720 if is_horizontal else 1280
    thumb_path = out_dir / "thumbnail.jpg"

    # Use first extracted frame as visual base for 100% video-thumbnail coherence
    base_frame = extracted_frames[0] if extracted_frames else None

    # Determine channel-adaptive hook text
    topic_low = topic.lower()
    if channel == "moku":
        if "caramelo" in topic_low or "feria" in topic_low:
            hook_text = "¿QUÉ HABÍA EN LA FERIA?"
        elif "cabaña" in topic_low or "bosque" in topic_low:
            hook_text = "NUNCA DEBIERON ENTRAR"
        elif "morgue" in topic_low:
            hook_text = "¿QUÉ HABÍA EN LA CAMILLA?"
        elif "faro" in topic_low or "mar" in topic_low:
            hook_text = "EL FARO NUNCA SE APAGÓ"
        else:
            hook_text = "NO DEBIERON ENTRAR"
    elif channel == "aelithia":
        if "boda" in topic_low or "hermana" in topic_low or "esposo" in topic_low:
            hook_text = "¿SOY LA MALA?"
        else:
            hook_text = "¿ESTUVE MAL?"
    else:
        hook_text = "¿QUÉ ENCONTRARON?"

    thumb_cfg = ThumbnailConfig(
        title=topic.upper(),
        channel_id=channel,
        lane_id=lane,
        hook_text=hook_text,
        output_path=thumb_path,
        width=thumb_width,
        height=thumb_height,
        accent_color="#FF0044" if channel == "moku" else "#FFB300",
        primary_color="#FFE600",
    )

    thumb_res = thumb_engine.generate(
        config=thumb_cfg,
        video_path=hero_scene,
        base_image_path=base_frame,
    )
    print(f"  ✅ High-CTR Thumbnail Generated: {thumb_res.name} ({thumb_res.stat().st_size} bytes, {thumb_width}x{thumb_height})")

    # 5. Copy to Agent Brain Artifacts for User Inspection
    copied_artifacts = {}
    if copy_to_artifacts and ARTIFACTS_DIR.is_dir():
        slug = topic.replace(" ", "_").lower()
        for idx, fpath in enumerate(extracted_frames):
            dest = ARTIFACTS_DIR / f"{slug}_frame_{idx+1}.jpg"
            shutil.copy2(fpath, dest)
            copied_artifacts[f"frame_{idx+1}"] = str(dest)
        if thumb_res.is_file():
            dest_thumb = ARTIFACTS_DIR / f"{slug}_thumbnail.jpg"
            shutil.copy2(thumb_res, dest_thumb)
            copied_artifacts["thumbnail"] = str(dest_thumb)
        print(f"\n📦 [5. Artifacts Persisted to Agent Brain]")
        for k, v in copied_artifacts.items():
            print(f"  - {k}: {v}")

    report = {
        "topic": topic,
        "channel": channel,
        "lane": lane,
        "orientation": orientation,
        "motifs": motifs,
        "resolved_asset": str(hero_scene),
        "asset_name": hero_scene.name,
        "sha256": asset_sha,
        "resolved_scenes": resolved_scenes,
        "frames": [str(p) for p in extracted_frames],
        "thumbnail": str(thumb_res),
        "artifacts": copied_artifacts,
        "subtitles_burned_on_video": False,
    }

    report_path = out_dir / "inspection_report.json"
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\n✅ Report written to: {report_path}")
    print(f"======================================================================\n")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Empirical Visual Inspection Rig")
    parser.add_argument("--topic", type=str, default="Terror con caramelos", help="Story title/topic")
    parser.add_argument("--channel", type=str, default="moku", help="Target channel (moku, aelithia)")
    parser.add_argument("--lane", type=str, default="moku-scp-shorts", help="Target lane ID")
    parser.add_argument("--output-dir", type=str, default=None, help="Custom output directory")
    args = parser.parse_args()

    out_p = Path(args.output_dir) if args.output_dir else None
    inspect_story(
        topic=args.topic,
        channel=args.channel,
        lane=args.lane,
        output_dir=out_p,
    )
