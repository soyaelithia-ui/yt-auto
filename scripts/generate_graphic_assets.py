#!/usr/bin/env python3
"""
scripts/generate_graphic_assets.py - Deterministic Procedural Graphic Asset Generator.

Generates 8 static atmospheric RGBA overlays (< 200 KB each) using Pillow & NumPy:
- dark_vignette.png
- soft_vignette.png
- film_grain.png
- tv_static.png
- particles.png
- particles_dust.png
- particles_embers.png
- god_rays.png

Synchronizes output to assets/overlays/static/ and assets/overlays/.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
from typing import List, Tuple
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


DEFAULT_WIDTH = 1080
DEFAULT_HEIGHT = 1920
MAX_FILE_SIZE_BYTES = 204800  # 200 KB


def generate_dark_vignette(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """High-order radial falloff (r^2 to r^4) mapping corner alpha 0.75 -> 0.00 at center."""
    y, x = np.ogrid[:height, :width]
    cx, cy = width / 2.0, height / 2.0
    max_dist = np.hypot(cx, cy)
    dist = np.hypot(x - cx, y - cy) / max_dist

    norm = np.clip((dist - 0.25) / 0.75, 0.0, 1.0)
    falloff = norm ** 2.5
    alpha = (falloff * 0.75 * 255.0).astype(np.uint8)

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


def generate_soft_vignette(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """Feathered gentle gaussian radial falloff mapping corner alpha 0.40 -> 0.00 at center."""
    y, x = np.ogrid[:height, :width]
    cx, cy = width / 2.0, height / 2.0
    max_dist = np.hypot(cx, cy)
    dist = np.hypot(x - cx, y - cy) / max_dist

    norm = np.clip((dist - 0.15) / 0.85, 0.0, 1.0)
    falloff = 0.5 * norm + 0.5 * (norm ** 2.0)
    alpha = (falloff * 0.40 * 255.0).astype(np.uint8)

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 3] = alpha
    return Image.fromarray(rgba, mode="RGBA")


def generate_film_grain(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """35mm optical grain texture synthesized via optical silver halide granules with Gaussian noise (mu=128, sigma=18)."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 18,000 fine microscopic silver halide crystal granules
    num_granules = 18000
    xs = rng.integers(0, width, num_granules)
    ys = rng.integers(0, height, num_granules)
    luminances = rng.normal(128.0, 18.0, num_granules).clip(60, 210).astype(int)
    alphas = rng.integers(40, 75, num_granules)  # Alpha 0.16 - 0.30

    for x, y, lum, a in zip(xs, ys, luminances, alphas):
        draw.point((int(x), int(y)), fill=(int(lum), int(lum), int(lum), int(a)))

    # Microscopic grain clusters
    num_clusters = 2400
    c_xs = rng.integers(1, width - 1, num_clusters)
    c_ys = rng.integers(1, height - 1, num_clusters)
    c_lum = rng.normal(128.0, 15.0, num_clusters).clip(80, 190).astype(int)
    c_alp = rng.integers(35, 65, num_clusters)

    for cx, cy, lum, a in zip(c_xs, c_ys, c_lum, c_alp):
        draw.ellipse([cx - 1, cy - 1, cx + 1, cy + 1], fill=(int(lum), int(lum), int(lum), int(a)))

    return img


def generate_tv_static(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """CRT phosphor noise modulated by periodic horizontal scanlines (y % 3 == 0) and horizontal glitch streaks."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Periodic horizontal CRT scanlines
    for y in range(0, height, 3):
        alpha = int(rng.integers(25, 55))
        draw.line([(0, y), (width, y)], fill=(180, 255, 200, alpha), width=1)

    # Phosphor static horizontal blips / line glitches
    for _ in range(1200):
        y = int(rng.integers(0, height))
        x1 = int(rng.integers(0, width - 50))
        x2 = min(width, x1 + int(rng.integers(10, 140)))
        val = int(rng.integers(180, 255))
        alpha = int(rng.integers(40, 90))
        draw.line([(x1, y), (x2, y)], fill=(val, val, val, alpha), width=1)

    # Phosphor noise points
    num_dots = 7000
    xs = rng.integers(0, width, num_dots)
    ys = rng.integers(0, height, num_dots)
    alphas = rng.integers(30, 80, num_dots)
    for x, y, a in zip(xs, ys, alphas):
        draw.point((int(x), int(y)), fill=(200, 255, 220, int(a)))

    return img


def generate_particles(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """Multi-scale ambient floating dust motes with soft gaussian edge falloff."""
    rng = np.random.default_rng(seed)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    num_motes = 300
    xs = rng.uniform(20, width - 20, num_motes)
    ys = rng.uniform(20, height - 20, num_motes)
    radii = rng.uniform(1.5, 5.0, num_motes)
    alphas = rng.integers(50, 180, num_motes)

    for x, y, r, a in zip(xs, ys, radii, alphas):
        color = (240, 245, 255, int(a))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=color)

    return img.filter(ImageFilter.GaussianBlur(radius=1.2))


def generate_particles_dust(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """Low-velocity directional drifting indoor motes with elongated aspect."""
    rng = np.random.default_rng(seed + 1)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    num_motes = 250
    xs = rng.uniform(30, width - 30, num_motes)
    ys = rng.uniform(30, height - 30, num_motes)
    radii_x = rng.uniform(2.0, 6.0, num_motes)
    radii_y = rng.uniform(1.0, 3.0, num_motes)
    alphas = rng.integers(40, 150, num_motes)

    for x, y, rx, ry, a in zip(xs, ys, radii_x, radii_y, alphas):
        color = (250, 245, 230, int(a))
        draw.ellipse([x - rx, y - ry, x + rx, y + ry], fill=color)

    return img.filter(ImageFilter.GaussianBlur(radius=1.0))


def generate_particles_embers(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """Warm glowing ember specks (3200K, #FF6600, #FFCC33) with luminous halos."""
    rng = np.random.default_rng(seed + 2)
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    num_embers = 160
    xs = rng.uniform(40, width - 40, num_embers)
    ys = rng.uniform(60, height - 40, num_embers)
    radii = rng.uniform(1.8, 5.5, num_embers)

    for x, y, r in zip(xs, ys, radii):
        halo_r = r * 2.8
        draw.ellipse([x - halo_r, y - halo_r, x + halo_r, y + halo_r], fill=(255, 60, 0, 50))
        draw.ellipse([x - r, y - r, x + r, y + r], fill=(255, 170, 20, 180))
        core_r = max(0.8, r * 0.4)
        draw.ellipse([x - core_r, y - core_r, x + core_r, y + core_r], fill=(255, 250, 210, 220))

    return img.filter(ImageFilter.GaussianBlur(radius=0.8))


def generate_god_rays(width: int = DEFAULT_WIDTH, height: int = DEFAULT_HEIGHT, seed: int = 42) -> Image.Image:
    """Diagonal volumetric light shafts projecting from top corner with soft linear attenuation."""
    y, x = np.ogrid[:height, :width]
    proj = (x * 0.8 + y * 0.5) / 100.0

    beams = (
        np.sin(proj * 1.5) * 0.35
        + np.sin(proj * 3.7 + 1.2) * 0.25
        + np.sin(proj * 7.1 + 0.5) * 0.15
        + 0.5
    )
    beams = np.clip(beams, 0.0, 1.0)

    dist_atten = 1.0 - (y / height * 0.7 + x / width * 0.3)
    dist_atten = np.clip(dist_atten, 0.0, 1.0)

    alpha_map = (beams * dist_atten * 0.25 * 255.0).astype(np.uint8)

    rgba = np.zeros((height, width, 4), dtype=np.uint8)
    rgba[:, :, 0] = 255
    rgba[:, :, 1] = 250
    rgba[:, :, 2] = 235
    rgba[:, :, 3] = alpha_map

    img = Image.fromarray(rgba, mode="RGBA")
    return img.filter(ImageFilter.GaussianBlur(radius=6.0))


GENERATOR_REGISTRY = {
    "dark_vignette.png": generate_dark_vignette,
    "soft_vignette.png": generate_soft_vignette,
    "film_grain.png": generate_film_grain,
    "tv_static.png": generate_tv_static,
    "particles.png": generate_particles,
    "particles_dust.png": generate_particles_dust,
    "particles_embers.png": generate_particles_embers,
    "god_rays.png": generate_god_rays,
}


def verify_asset(path: Path) -> Tuple[bool, str]:
    """Verify PNG asset exists, is RGBA, dimensions valid, and strictly < 200 KB."""
    if not path.is_file():
        return False, f"Missing file: {path}"
    size = path.stat().st_size
    if size == 0:
        return False, f"Zero-byte file: {path}"
    if size >= MAX_FILE_SIZE_BYTES:
        return False, f"File {path.name} size {size} >= {MAX_FILE_SIZE_BYTES} bytes"
    try:
        with Image.open(path) as img:
            if img.mode != "RGBA":
                return False, f"Image {path.name} mode '{img.mode}' != RGBA"
            w, h = img.size
            if not ((w >= 1080 and h >= 1920) or (w >= 1920 and h >= 1080)):
                return False, f"Image {path.name} dimensions {img.size} invalid"
            arr = np.array(img)
            if np.min(arr[:, :, 3]) == np.max(arr[:, :, 3]):
                return False, f"Image {path.name} alpha has zero variance"
    except Exception as exc:
        return False, f"Failed reading {path.name}: {exc}"
    return True, "OK"


def verify_svg_templates(svg_dir: Path) -> List[str]:
    """Verify all expected SVG templates exist, have valid XML, and no DOCTYPE/ENTITY."""
    errors: List[str] = []
    expected_svgs = [
        "rec_analog_hud.svg",
        "cinematic_scope_bars.svg",
        "classified_warning_banner.svg",
        "drama_quote_card.svg",
        "cyber_data_stream.svg",
        "hud_tactical_telemetry.svg",
        "scp_classification_stamp.svg",
        "biometric_wave.svg",
    ]
    import xml.etree.ElementTree as ET

    for name in expected_svgs:
        p = svg_dir / name
        if not p.is_file() or p.stat().st_size == 0:
            errors.append(f"Missing or empty SVG template: {p}")
            continue
        try:
            content = p.read_text(encoding="utf-8")
            if "<!DOCTYPE" in content or "<!ENTITY" in content:
                errors.append(f"{name} contains forbidden DOCTYPE or ENTITY")
            root = ET.fromstring(content)
            if not root.tag.endswith("svg"):
                errors.append(f"{name} root tag is not svg")
        except Exception as exc:
            errors.append(f"Error parsing {name}: {exc}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Deterministic Procedural Graphic Asset Generator")
    parser.add_argument("--force", action="store_true", help="Overwrite existing assets")
    parser.add_argument("--verify", action="store_true", help="Run integrity verification only")
    parser.add_argument("--resolution", nargs=2, type=int, default=[DEFAULT_WIDTH, DEFAULT_HEIGHT], metavar=("WIDTH", "HEIGHT"))
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    static_dir = repo_root / "assets" / "overlays" / "static"
    mirrored_dir = repo_root / "assets" / "overlays"
    svg_dir = repo_root / "assets" / "svg_overlays"

    static_dir.mkdir(parents=True, exist_ok=True)
    mirrored_dir.mkdir(parents=True, exist_ok=True)

    width, height = args.resolution

    if args.verify:
        all_ok = True
        print("Verifying static atmospheric overlay assets...")
        for filename in GENERATOR_REGISTRY:
            target_file = static_dir / filename
            ok, msg = verify_asset(target_file)
            if not ok:
                print(f"  [FAIL] {filename}: {msg}", file=sys.stderr)
                all_ok = False
            else:
                print(f"  [PASS] {filename} ({target_file.stat().st_size} bytes)")

        print("Verifying SVG templates...")
        svg_errors = verify_svg_templates(svg_dir)
        for err in svg_errors:
            print(f"  [FAIL] {err}", file=sys.stderr)
            all_ok = False
        if not svg_errors:
            print("  [PASS] All 8 SVG templates verified.")

        return 0 if all_ok else 1

    # Generation mode
    generated_count = 0
    skipped_count = 0

    for filename, generator_fn in GENERATOR_REGISTRY.items():
        target_file = static_dir / filename
        mirror_file = mirrored_dir / filename

        if not args.force and target_file.exists() and mirror_file.exists():
            skipped_count += 1
            continue

        print(f"Generating {filename} ({width}x{height})...")
        img = generator_fn(width=width, height=height)

        target_file.parent.mkdir(parents=True, exist_ok=True)
        img.save(target_file, format="PNG", optimize=True, compress_level=9)
        img.save(mirror_file, format="PNG", optimize=True, compress_level=9)

        size = target_file.stat().st_size
        if size >= MAX_FILE_SIZE_BYTES:
            print(f"ERROR: {filename} exceeded budget: {size} bytes >= {MAX_FILE_SIZE_BYTES}", file=sys.stderr)
            return 1
        print(f"  Saved {filename}: {size} bytes (< 200 KB budget)")
        generated_count += 1

    print(f"Finished: {generated_count} generated, {skipped_count} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
