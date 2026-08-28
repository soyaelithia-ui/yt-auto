#!/usr/bin/env python3
"""
dev/render_iconic_thematic_loops.py - Render the 8 story-accurate iconic procedural loops with retry logic.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.media.web_renderer import WebVideoRenderer, RenderSpec

def main():
    renderer = WebVideoRenderer()
    loops_dir = ROOT_DIR / "assets" / "loops" / "thematic_iconic"
    loops_dir.mkdir(parents=True, exist_ok=True)

    templates_h = [
        ("act1_suit", "scp5000_suit_blueprint.html", "horizontal"),
        ("act2_pneuma", "scp5000_pneuma_brain.html", "horizontal"),
        ("act3_o5", "scp5000_o5_council.html", "horizontal"),
        ("act4_monsters", "scp5000_monsters_rampage.html", "horizontal"),
        ("act5_ganzir", "scp5000_ganzir_collapse.html", "horizontal"),
        ("act6_desert", "scp5000_pietro_desert.html", "horizontal"),
        ("act7_vortex", "scp5000_vortex_579.html", "horizontal"),
        ("act8_helmet", "scp5000_helmet_why.html", "horizontal"),
    ]

    templates_v = [
        ("short1_suit", "scp5000_suit_blueprint.html", "vertical"),
        ("short2_monsters", "scp5000_monsters_rampage.html", "vertical"),
        ("short3_vortex", "scp5000_vortex_579.html", "vertical"),
    ]

    print("🚀 RENDERIZANDO BUCLES HORIZONTALES ICÓNICOS (1080P)...")
    for name, tmpl, orient in templates_h:
        out_file = loops_dir / f"{name}_1920x1080_6s.mp4"
        if out_file.is_file() and out_file.stat().st_size > 100000:
            print(f"⏩ Ya existe: {out_file.name} ({out_file.stat().st_size / 1024:.1f} KB)")
            continue

        for attempt in range(3):
            try:
                spec = RenderSpec(
                    category="thematic",
                    orientation=orient,
                    duration_sec=6.0,
                    fps=30,
                    template_name=tmpl,
                    output_path=out_file,
                )
                rec = renderer.render_loop(spec)
                print(f"✅ Renderizado {name}: {out_file.name} ({out_file.stat().st_size / 1024:.1f} KB)")
                break
            except Exception as e:
                print(f"⚠️ Error renderizando {name} (intento {attempt+1}): {e}")
                time.sleep(2)

    print("\n🚀 RENDERIZANDO BUCLES VERTICALES ICÓNICOS (1080x1920)...")
    for name, tmpl, orient in templates_v:
        out_file = loops_dir / f"{name}_1080x1920_6s.mp4"
        if out_file.is_file() and out_file.stat().st_size > 100000:
            print(f"⏩ Ya existe: {out_file.name} ({out_file.stat().st_size / 1024:.1f} KB)")
            continue

        for attempt in range(3):
            try:
                spec = RenderSpec(
                    category="thematic",
                    orientation=orient,
                    duration_sec=6.0,
                    fps=30,
                    template_name=tmpl,
                    output_path=out_file,
                )
                rec = renderer.render_loop(spec)
                print(f"✅ Renderizado {name}: {out_file.name} ({out_file.stat().st_size / 1024:.1f} KB)")
                break
            except Exception as e:
                print(f"⚠️ Error renderizando {name} (intento {attempt+1}): {e}")
                time.sleep(2)

    print("\n🎉 TODOS LOS BUCLES ICÓNICOS FUERON RENDERIZADOS CON ÉXITO!")

if __name__ == "__main__":
    main()
