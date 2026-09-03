"""
src/media/thumbnails/subject_extractor.py - Intelligent Thematic Setting & Subject Compositor.

Renders contextually accurate, anatomical silhouettes and environmental focal elements matching
the exact narrative setting archetype:
- maritime_lighthouse: Solitary observer/keeper silhouette standing on the coastal cliff edge in the path of the sweeping beacon beam over dark ocean waters.
- tactical_chamber / subway: Arched concrete tunnel portal with descending steps and explorer silhouette.
- dark_forest: Whispering pine tree silhouettes and eerie glowing-eyed watcher.
- arctic_desolation: Jagged snow ridge with emaciated humanoid anomaly (SCP-096).
- cosmic_singularity: Deep space event horizon with solitary astronaut / explorer.
- arcade_vector_flight: Retro vector spaceship firing laser pulses at wireframe asteroids.
- parkour_runner: Isometric neon voxel blocks with jumping platformer character.
- cozy_hearth / drama: Elegant solitary trench coat figure by soft rainy ambient window.
- synaptic_network: Neural soma network with contemplative figure.
"""
from __future__ import annotations

from typing import Tuple, Optional
import math
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps, ImageChops


class AdaptiveSubjectCompositor:
    """
    Composites a subtle, atmospheric thematic subject silhouette in the central focal area
    of the thumbnail (underneath the title hook) with chiaroscuro depth and accent rim lighting.
    """

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        h = hex_str.lstrip("#")
        if len(h) == 6:
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0, 255, 102)

    @classmethod
    def composite_thematic_subject(
        cls,
        base_img: Image.Image,
        channel_id: str = "moku",
        archetype: str = "tactical_chamber",
        accent_color_hex: str = "#00FF66",
        intensity: float = 0.90,
    ) -> Image.Image:
        w, h = base_img.size
        r_col, g_col, b_col = cls.hex_to_rgb(accent_color_hex)
        
        # High-resolution super-sampled mask (4x) for ultra-smooth anti-aliasing
        scale_factor = 4
        sw, sh = w * scale_factor, h * scale_factor
        mask_img = Image.new("L", (sw, sh), 0)
        draw = ImageDraw.Draw(mask_img)

        cx = sw * 0.50
        base_y = sh * 0.77  # Ground / horizon baseline
        subject_h = sh * 0.34

        channel_norm = str(channel_id or "").lower()
        arch_norm = str(archetype or "").lower()

        # 1. MARITIME LIGHTHOUSE / COASTAL OBSERVER
        if any(k in arch_norm for k in ("maritime", "lighthouse", "faro", "mar", "ocean", "costa", "acantilado", "naufragio")):
            # Solitary coastal observer / keeper standing on the cliff ledge gazing at the sea
            char_h = subject_h * 0.65
            char_cx = cx - subject_h * 0.15
            char_base_y = base_y
            
            # Head & Rainhood / Cap
            head_r = char_h * 0.085
            head_y = char_base_y - char_h + head_r * 1.5
            draw.ellipse([char_cx - head_r, head_y - head_r, char_cx + head_r * 1.2, head_y + head_r], fill=255)
            # Neck
            draw.polygon([
                (char_cx - head_r * 0.4, head_y + head_r * 0.7),
                (char_cx + head_r * 0.4, head_y + head_r * 0.7),
                (char_cx + head_r * 0.5, head_y + head_r * 1.7),
                (char_cx - head_r * 0.5, head_y + head_r * 1.7),
            ], fill=255)
            
            # Oilskin Heavy Coat (Torso & Flared Hem)
            sh_w = char_h * 0.15
            w_w = char_h * 0.11
            torso_top_y = head_y + head_r * 1.6
            draw.polygon([
                (char_cx - sh_w, torso_top_y + char_h * 0.03),
                (char_cx + sh_w, torso_top_y + char_h * 0.03),
                (char_cx + w_w, char_base_y - char_h * 0.42),
                (char_cx - w_w, char_base_y - char_h * 0.42),
            ], fill=255)
            
            # Long Flared Raincoat Body
            coat_bot_y = char_base_y - char_h * 0.10
            draw.polygon([
                (char_cx - w_w, char_base_y - char_h * 0.42),
                (char_cx + w_w, char_base_y - char_h * 0.42),
                (char_cx + w_w * 1.4, coat_bot_y),
                (char_cx - w_w * 1.4, coat_bot_y),
            ], fill=255)
            
            # Boots
            draw.line([(char_cx - w_w * 0.5, coat_bot_y), (char_cx - w_w * 0.55, char_base_y)], fill=255, width=max(4, int(char_h * 0.045)))
            draw.line([(char_cx + w_w * 0.5, coat_bot_y), (char_cx + w_w * 0.55, char_base_y)], fill=255, width=max(4, int(char_h * 0.045)))

            # Extended arm holding lantern
            draw.line([(char_cx + sh_w * 0.9, torso_top_y + char_h * 0.05), (char_cx + sh_w * 1.8, char_base_y - char_h * 0.45)], fill=255, width=max(4, int(char_h * 0.035)))
            lantern_cx = char_cx + sh_w * 1.85
            lantern_cy = char_base_y - char_h * 0.40
            draw.rectangle([lantern_cx - 10, lantern_cy - 16, lantern_cx + 10, lantern_cy + 16], fill=255)

        # 2. UNDERGROUND SUBWAY / METRO / BUNKER / TACTICAL CHAMBER
        elif any(k in arch_norm for k in ("tactical", "chamber", "metro", "subway", "estacion", "estación", "tunel", "túnel", "escalera", "bunker", "búnker")):
            arch_w = subject_h * 0.40
            arch_top_y = base_y - subject_h * 1.18
            
            draw.ellipse([cx - arch_w, arch_top_y, cx + arch_w, arch_top_y + arch_w * 1.8], fill=255)
            draw.rectangle([cx - arch_w, arch_top_y + arch_w * 0.9, cx + arch_w, base_y], fill=255)
            
            inner_w = arch_w * 0.76
            inner_top_y = arch_top_y + arch_w * 0.24
            draw.ellipse([cx - inner_w, inner_top_y, cx + inner_w, inner_top_y + inner_w * 1.8], fill=0)
            draw.rectangle([cx - inner_w, inner_top_y + inner_w * 0.9, cx + inner_w, base_y], fill=0)
            
            for step_idx in range(4):
                sy = base_y - step_idx * (subject_h * 0.05)
                swidth = arch_w * (0.80 + step_idx * 0.10)
                draw.rectangle([cx - swidth * 0.5, sy, cx + swidth * 0.5, sy + 6], fill=255)
            
            char_h = subject_h * 0.58
            char_base_y = base_y - subject_h * 0.16
            head_r = char_h * 0.08
            head_y = char_base_y - char_h + head_r * 1.4
            draw.ellipse([cx - head_r * 0.85, head_y - head_r, cx + head_r * 0.85, head_y + head_r], fill=255)
            draw.polygon([(cx - head_r * 0.3, head_y + head_r * 0.7), (cx + head_r * 0.3, head_y + head_r * 0.7), (cx + head_r * 0.4, head_y + head_r * 1.6), (cx - head_r * 0.4, head_y + head_r * 1.6)], fill=255)
            
            sh_w = char_h * 0.14
            w_w = char_h * 0.10
            torso_top_y = head_y + head_r * 1.5
            draw.polygon([
                (cx - sh_w, torso_top_y + char_h * 0.04),
                (cx + sh_w, torso_top_y + char_h * 0.04),
                (cx + w_w, char_base_y - char_h * 0.40),
                (cx - w_w, char_base_y - char_h * 0.40),
            ], fill=255)
            draw.polygon([
                (cx - w_w, char_base_y - char_h * 0.40),
                (cx + w_w, char_base_y - char_h * 0.40),
                (cx + w_w * 1.25, char_base_y - char_h * 0.10),
                (cx - w_w * 1.25, char_base_y - char_h * 0.10),
            ], fill=255)
            draw.line([(cx - w_w * 0.5, char_base_y - char_h * 0.10), (cx - w_w * 0.55, char_base_y)], fill=255, width=max(4, int(char_h * 0.04)))
            draw.line([(cx + w_w * 0.5, char_base_y - char_h * 0.10), (cx + w_w * 0.55, char_base_y)], fill=255, width=max(4, int(char_h * 0.04)))

        # 3. RETRO ARCADE VECTOR SHOOTER
        elif any(k in arch_norm for k in ("arcade", "vector", "flight", "shooter")):
            s_nose = (cx, base_y - subject_h * 0.55)
            s_left = (cx - subject_h * 0.25, base_y - subject_h * 0.10)
            s_right = (cx + subject_h * 0.25, base_y - subject_h * 0.10)
            s_notch = (cx, base_y - subject_h * 0.22)
            draw.polygon([s_nose, s_left, s_notch, s_right], fill=255)
            
            for lx_off in (-subject_h * 0.08, subject_h * 0.08):
                draw.line([(cx + lx_off, base_y - subject_h * 0.65), (cx + lx_off, base_y - subject_h * 1.1)], fill=255, width=8)
            
            ast_cx, ast_cy = cx + subject_h * 0.35, base_y - subject_h * 0.95
            ast_r = subject_h * 0.16
            draw.polygon([
                (ast_cx, ast_cy - ast_r),
                (ast_cx + ast_r * 0.86, ast_cy - ast_r * 0.5),
                (ast_cx + ast_r * 0.86, ast_cy + ast_r * 0.5),
                (ast_cx, ast_cy + ast_r),
                (ast_cx - ast_r * 0.86, ast_cy + ast_r * 0.5),
                (ast_cx - ast_r * 0.86, ast_cy - ast_r * 0.5),
            ], fill=255)

        # 4. ISOMETRIC PARKOUR RUNNER
        elif any(k in arch_norm for k in ("parkour", "runner", "roblox")):
            p_w, p_h = subject_h * 0.35, subject_h * 0.08
            draw.rectangle([cx - p_w, base_y - p_h, cx + p_w, base_y], fill=255)
            draw.rectangle([cx - p_w * 1.4, base_y - subject_h * 0.45, cx - p_w * 0.4, base_y - subject_h * 0.37], fill=255)
            draw.rectangle([cx + p_w * 0.4, base_y - subject_h * 0.85, cx + p_w * 1.4, base_y - subject_h * 0.77], fill=255)
            bx, by = cx, base_y - p_h - subject_h * 0.15
            draw.rectangle([bx - 20, by - 40, bx + 20, by], fill=255)
            draw.rectangle([bx - 16, by - 75, bx + 16, by - 43], fill=255)
            draw.line([(bx - 10, by), (bx - 15, by + 30)], fill=255, width=12)
            draw.line([(bx + 10, by), (bx + 15, by + 30)], fill=255, width=12)

        # 5. COZY HEARTH / DOMESTIC DRAMA / AITA
        elif any(k in arch_norm for k in ("cozy", "hearth", "confession", "drama", "aelithia", "aita")):
            head_r = subject_h * 0.055
            head_y = base_y - subject_h + head_r * 1.6
            draw.ellipse([cx - head_r * 0.9, head_y - head_r, cx + head_r * 0.9, head_y + head_r * 0.95], fill=255)
            neck_w = head_r * 0.4
            draw.polygon([(cx - neck_w, head_y + head_r * 0.7), (cx + neck_w, head_y + head_r * 0.7), (cx + neck_w * 1.3, head_y + head_r * 1.7), (cx - neck_w * 1.3, head_y + head_r * 1.7)], fill=255)
            shoulder_w = subject_h * 0.08
            waist_w = subject_h * 0.06
            waist_y = base_y - subject_h * 0.48
            coat_bottom_y = base_y - subject_h * 0.12
            draw.polygon([(cx - shoulder_w, head_y + head_r * 1.5 + subject_h * 0.03), (cx + shoulder_w, head_y + head_r * 1.5 + subject_h * 0.03), (cx + waist_w, waist_y), (cx - waist_w, waist_y)], fill=255)
            draw.polygon([(cx - waist_w, waist_y), (cx + waist_w, waist_y), (cx + subject_h * 0.105, coat_bottom_y), (cx - subject_h * 0.105, coat_bottom_y)], fill=255)
            draw.line([(cx - waist_w * 0.5, coat_bottom_y), (cx - waist_w * 0.55, base_y)], fill=255, width=max(4, int(subject_h * 0.022)))
            draw.line([(cx + waist_w * 0.5, coat_bottom_y), (cx + waist_w * 0.55, base_y)], fill=255, width=max(4, int(subject_h * 0.022)))

        # 6. SCI-FI / COSMIC SINGULARITY
        elif any(k in arch_norm for k in ("cosmic", "singularity", "scifi", "space")):
            helmet_r = subject_h * 0.065
            head_y = base_y - subject_h + helmet_r * 1.5
            draw.ellipse([cx - helmet_r, head_y - helmet_r, cx + helmet_r, head_y + helmet_r], fill=255)
            suit_w = subject_h * 0.085
            draw.polygon([(cx - suit_w, head_y + helmet_r * 0.8), (cx + suit_w, head_y + helmet_r * 0.8), (cx + suit_w * 0.9, base_y - subject_h * 0.45), (cx - suit_w * 0.9, base_y - subject_h * 0.45)], fill=255)
            draw.line([(cx - suit_w * 0.5, base_y - subject_h * 0.45), (cx - suit_w * 0.6, base_y)], fill=255, width=max(6, int(subject_h * 0.035)))
            draw.line([(cx + suit_w * 0.5, base_y - subject_h * 0.45), (cx + suit_w * 0.6, base_y)], fill=255, width=max(6, int(subject_h * 0.035)))

        # 7. DARK FOREST / WOODS
        elif any(k in arch_norm for k in ("dark_forest", "forest", "wood", "woods")):
            head_r = subject_h * 0.05
            head_y = base_y - subject_h * 0.85
            draw.ellipse([cx - head_r, head_y - head_r, cx + head_r, head_y + head_r], fill=255)
            draw.polygon([
                (cx - subject_h * 0.06, head_y + head_r),
                (cx + subject_h * 0.06, head_y + head_r),
                (cx + subject_h * 0.09, base_y),
                (cx - subject_h * 0.09, base_y),
            ], fill=255)

        # 8. ARCTIC DESOLATION / SCP-096 SHY GUY
        else:
            head_r = subject_h * 0.042
            head_y = base_y - subject_h + head_r * 1.5
            draw.ellipse([cx - head_r * 0.85, head_y - head_r * 1.2, cx + head_r * 0.85, head_y + head_r * 1.2], fill=255)
            torso_top_y = head_y + head_r * 2.0
            torso_bottom_y = base_y - subject_h * 0.44
            draw.polygon([(cx - subject_h * 0.045, torso_top_y), (cx + subject_h * 0.045, torso_top_y), (cx + subject_h * 0.042, torso_bottom_y), (cx - subject_h * 0.042, torso_bottom_y)], fill=255)
            arm_w = max(4, int(subject_h * 0.016))
            draw.line([(cx - subject_h * 0.045, torso_top_y), (cx - subject_h * 0.065, base_y - subject_h * 0.12)], fill=255, width=arm_w)
            draw.line([(cx + subject_h * 0.045, torso_top_y), (cx + subject_h * 0.065, base_y - subject_h * 0.12)], fill=255, width=arm_w)
            leg_w = max(4, int(subject_h * 0.019))
            draw.line([(cx - subject_h * 0.028, torso_bottom_y), (cx - subject_h * 0.042, base_y)], fill=255, width=leg_w)
            draw.line([(cx + subject_h * 0.028, torso_bottom_y), (cx + subject_h * 0.042, base_y)], fill=255, width=leg_w)

        # Downsample mask with smooth anti-aliasing
        mask_img = mask_img.resize((w, h), Image.Resampling.LANCZOS)
        soft_mask = mask_img.filter(ImageFilter.GaussianBlur(radius=2.5))

        # Ground mist falloff over feet
        mist_gradient = Image.new("L", (w, h), 255)
        mist_draw = ImageDraw.Draw(mist_gradient)
        mist_start = int(h * 0.67)
        mist_end = int(h * 0.78)
        for y_coord in range(mist_start, min(h, mist_end + 1)):
            alpha_val = int(255 * (1.0 - (y_coord - mist_start) / max(1, (mist_end - mist_start)) * 0.7))
            mist_draw.line([(0, y_coord), (w, y_coord)], fill=alpha_val)
        
        soft_mask = ImageChops.multiply(soft_mask, mist_gradient)

        # Dark chiaroscuro charcoal body
        body_col = (10, 14, 20)
        body_layer = Image.new("RGBA", (w, h), (*body_col, int(230 * intensity)))

        # Multi-layer Rim Light Edge Glow
        edges_sharp = soft_mask.filter(ImageFilter.FIND_EDGES)
        edges_halo = edges_sharp.filter(ImageFilter.GaussianBlur(radius=6))
        
        rim_glow = Image.new("RGBA", (w, h), (r_col, g_col, b_col, 0))
        rim_alpha_sharp = edges_sharp.point(lambda p: int(p * 0.85 * intensity))
        rim_alpha_halo = edges_halo.point(lambda p: int(p * 0.45 * intensity))
        combined_rim_alpha = ImageChops.add(rim_alpha_sharp, rim_alpha_halo)
        rim_glow.putalpha(combined_rim_alpha)

        # Composite onto base image
        base_rgba = base_img.convert("RGBA")
        body_alpha = soft_mask.point(lambda p: int(p * 0.92 * intensity))
        body_layer.putalpha(body_alpha)
        
        composite = Image.alpha_composite(base_rgba, body_layer)
        composite = Image.alpha_composite(composite, rim_glow)
        return composite.convert("RGB")


class RimLightCompositor:
    """Legacy wrapper delegating to AdaptiveSubjectCompositor."""

    @staticmethod
    def hex_to_rgb(hex_str: str) -> Tuple[int, int, int]:
        return AdaptiveSubjectCompositor.hex_to_rgb(hex_str)

    @classmethod
    def apply_rim_light_to_frame(
        cls,
        base_img: Image.Image,
        accent_color_hex: str = "#00FF66",
        intensity: float = 1.0,
    ) -> Image.Image:
        r_col, g_col, b_col = cls.hex_to_rgb(accent_color_hex)
        w, h = base_img.size

        gray = base_img.convert("L")
        edges = gray.filter(ImageFilter.FIND_EDGES)
        edges = ImageOps.autocontrast(edges, cutoff=15)

        edge_glow = edges.filter(ImageFilter.GaussianBlur(radius=8))

        glow_rgba = Image.new("RGBA", (w, h), (r_col, g_col, b_col, 0))
        glow_mask = edge_glow.point(lambda p: int(p * 0.45 * intensity))
        glow_rgba.putalpha(glow_mask)

        base_rgba = base_img.convert("RGBA")
        return Image.alpha_composite(base_rgba, glow_rgba).convert("RGB")
