"""Regression tests: longform QA resolution gate must expect 1920x1080.

Production incident 2026-08-23 (run 8a30d658): a correct 1920x1080 longform
render was rejected with 'resolución de video distinta de 1280x720' because
src/core/quality.validate_prepublication hardcoded the legacy 720p constant
instead of LONGFORM_RESOLUTION from src/core/resolution.py (1080p default
since commit c60effa).
"""

import os
import subprocess

from src.core.quality import validate_prepublication


def _render_probe(width: int, height: int, tmp_path) -> str:
    video_p = tmp_path / f"probe_{width}x{height}.mp4"
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi", "-i", f"testsrc=size={width}x{height}:rate=30:duration=3",
        "-f", "lavfi", "-i", "sine=frequency=1000:duration=3",
        "-c:v", "libx264", "-profile:v", "main", "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "44100", "-ac", "2",
        "-movflags", "+faststart",
        str(video_p),
    ]
    subprocess.run(cmd, capture_output=True, text=True, check=True)
    return str(video_p)


def _audit(tmp_path, width: int, height: int):
    ass_p = tmp_path / f"sub_{width}x{height}.ass"
    ass_p.write_text(
        "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n",
        encoding="utf-8",
    )
    thumb_p = tmp_path / f"thumb_{width}x{height}.jpg"
    thumb_p.write_bytes(b"\xff\xd8\xff\xe0" + b"0" * 2000)
    return validate_prepublication(
        channel="moku",
        script="Narración de prueba suficientemente larga para el gate de español neutro. "
               * 3,
        title="Historia de prueba del gate longform",
        description="Descripción de prueba.",
        video_path=_render_probe(width, height, tmp_path),
        subtitle_path=str(ass_p),
        thumbnail_path=str(thumb_p),
        video_mode="longform",
    )


def _messages(report) -> list[str]:
    out = []
    for issue in report.issues:
        out.append(issue if isinstance(issue, str) else str(getattr(issue, "message", issue)))
    return out


def test_longform_1080p_passes_resolution_gate(tmp_path):
    report = _audit(tmp_path, 1920, 1080)
    bad = [m for m in _messages(report) if "resolución de video" in m]
    assert bad == [], (
        "1920x1080 longform must satisfy the QA resolution gate; got "
        f"{bad}"
    )


def test_longform_legacy_720p_still_rejected(tmp_path):
    report = _audit(tmp_path, 1280, 720)
    assert any("resolución de video distinta de 1920x1080" in m for m in _messages(report)), (
        "1280x720 must keep failing the longform resolution gate"
    )
