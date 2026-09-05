"""WIP loop compositor: new plate + moving 2D elements. No catalog, no visual_bank.

Clouds, stick flocks (V birds), four-leg animal shadows. Never detailed humans.
Noise-as-motion is forbidden; elements must travel.
"""
from __future__ import annotations

import argparse
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

W, H = 1080, 1920
FPS = 30
DUR = 8


def fit_plate(im: Image.Image, width: int = W, height: int = H) -> Image.Image:
    src_w, src_h = im.size
    scale = max(width / src_w, height / src_h)
    nw, nh = int(src_w * scale), int(src_h * scale)
    im = im.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - width) // 2
    top = (nh - height) // 2
    return im.crop((left, top, left + width, top + height))


def draw_cloud(draw: ImageDraw.ImageDraw, cx: float, cy: float, rw: float, rh: float, a: int) -> None:
    draw.ellipse(
        [int(cx - rw), int(cy - rh), int(cx + rw), int(cy + rh)],
        fill=(220, 228, 235, a),
    )


def draw_vee(draw: ImageDraw.ImageDraw, x: float, y: float, s: float, a: int = 200) -> None:
    col = (18, 22, 28, a)
    draw.line(
        [(x - s, y - s * 0.35), (x, y), (x + s, y - s * 0.35)],
        fill=col,
        width=max(2, int(s * 0.18)),
    )


def draw_stick_walker(draw: ImageDraw.ImageDraw, x: float, y: float, phase: float) -> None:
    col = (8, 10, 12, 210)
    draw.line([(x - 16, y - 10), (x + 18, y - 10)], fill=col, width=4)
    draw.ellipse([x + 14, y - 16, x + 24, y - 6], fill=col)
    step = math.sin(phase) * 6
    for dx, dy in ((-10, 1), (-2, -1), (6, 1), (14, -1)):
        draw.line([(x + dx, y - 10), (x + dx + 2, y + 8 + step * dy)], fill=col, width=3)
    draw.ellipse([x - 22, y + 6, x + 26, y + 14], fill=(0, 0, 0, 90))


def overlay_clouds(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    clouds = [
        (200, 220, 260, 70, 18.0, 55),
        (700, 180, 300, 80, 12.0, 45),
        (400, 520, 340, 90, 8.0, 35),
        (900, 640, 280, 70, 10.0, 30),
        (150, 780, 220, 55, 7.0, 28),
        (620, 860, 260, 60, 9.0, 26),
    ]
    for x0, y0, rw, rh, spd, a in clouds:
        x = (x0 + spd * t) % (W + rw * 2) - rw
        draw_cloud(d, x, y0 + 8 * math.sin(t * 0.4 + x0), rw, rh, a)
        draw_cloud(d, x + rw * 0.45, y0 + 10, rw * 0.7, rh * 0.75, max(18, a - 10))
    return layer.filter(ImageFilter.GaussianBlur(18))


def overlay_flocks(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    base = -80 + t * 55
    for i, (dx, dy, s) in enumerate(((-40, 0, 11), (-18, 8, 9), (0, -4, 12), (22, 6, 8), (44, -2, 10), (68, 10, 7))):
        x = (base + dx) % (W + 120) - 60
        y = 210 + dy + 6 * math.sin(t * 1.2 + i)
        draw_vee(d, x, y, s)
    base2 = W + 40 - t * 42
    for i, (dx, dy, s) in enumerate(((-30, 4, 9), (-8, -6, 11), (16, 2, 8), (38, -5, 10))):
        x = (base2 + dx) % (W + 140) - 70
        y = 640 + dy + 5 * math.sin(t * 0.9 + i)
        draw_vee(d, x, y, s)
    return layer


def overlay_ground(t: float) -> Image.Image:
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    sway = math.sin(t * 0.6) * 3
    d.line([(820, 1480), (828 + sway, 1620)], fill=(6, 8, 10, 200), width=5)
    d.line([(860, 1500), (868 + sway, 1655)], fill=(6, 8, 10, 180), width=4)
    d.line([(250, 1520), (246 - sway, 1660)], fill=(6, 8, 10, 160), width=4)
    for i, x0 in enumerate((80, 220, 390)):
        x = (x0 + t * (22 + i * 4)) % (W + 80) - 40
        y = 1780 + (i % 2) * 18
        draw_stick_walker(d, x, y, t * 6 + i)
    return layer


def composite_frame(plate: Image.Image, t: float) -> Image.Image:
    frame = plate.convert("RGBA")
    frame = Image.alpha_composite(frame, overlay_clouds(t))
    frame = Image.alpha_composite(frame, overlay_flocks(t))
    frame = Image.alpha_composite(frame, overlay_ground(t))
    return frame.convert("RGB")


def render(plate_path: Path, out_path: Path, duration: float = DUR, fps: int = FPS) -> None:
    plate = fit_plate(Image.open(plate_path).convert("RGB"))
    n = int(duration * fps)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "ffmpeg", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps),
        "-i", "-",
        "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
        "-pix_fmt", "yuv420p", "-an", "-movflags", "+faststart",
        str(out_path),
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    for i in range(n):
        proc.stdin.write(composite_frame(plate, i / fps).tobytes())
    proc.stdin.close()
    rc = proc.wait()
    if rc != 0:
        raise SystemExit(rc)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("plate", type=Path)
    p.add_argument("-o", "--output", type=Path, required=True)
    p.add_argument("--duration", type=float, default=DUR)
    args = p.parse_args()
    render(args.plate, args.output, duration=args.duration)


if __name__ == "__main__":
    main()
