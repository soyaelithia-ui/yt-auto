"""
src/media/graphics_bank.py - Declarative Local Video Graphics Bank Subsystem.

Provides typed models, manifest parsing, conjunction querying, preflight integrity probe,
path confinement, and opacity clamping for video graphic overlays.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple, Union

ID_REGEX = re.compile(r"^[a-z0-9_]+$")


class GraphicCategory(str, Enum):
    ATMOSPHERIC = "atmospheric"
    VECTOR_HUD = "vector_hud"
    FRAMING = "framing"
    TYPOGRAPHY = "typography"


class GraphicChannelAffinity(str, Enum):
    HORROR = "horror"
    DRAMA = "drama"
    SCIFI = "scifi"
    ALL = "all"


@dataclass(frozen=True)
class GraphicAsset:
    id: str
    name: str
    category: GraphicCategory
    channel_affinity: GraphicChannelAffinity
    aspect_ratios: Tuple[str, ...]
    relative_path: str
    safe_zone_compliant: bool
    default_opacity: float
    dynamic_params: Dict[str, str] = field(default_factory=dict)
    tags: Tuple[str, ...] = field(default_factory=tuple)

    def resolve_path(self, base_dir: Path) -> Path:
        return (base_dir / self.relative_path).resolve()


@dataclass(frozen=True)
class BankValidationReport:
    valid: bool
    total_assets: int
    verified_assets: int
    missing_assets: Tuple[str, ...]
    corrupted_assets: Tuple[str, ...]
    oversized_assets: Tuple[str, ...]
    errors: Tuple[str, ...]


class GraphicsBank:
    """Declarative registry and query provider for local video graphics."""

    def __init__(
        self,
        base_dir: Optional[Path] = None,
        manifest_path: Optional[Path] = None,
    ) -> None:
        if base_dir:
            self.base_dir = Path(base_dir).resolve()
        else:
            self.base_dir = Path(__file__).resolve().parents[2]
        self._assets: Dict[str, GraphicAsset] = {}
        target_manifest = manifest_path or (self.base_dir / "assets" / "graphics_manifest.json")
        if target_manifest.exists():
            self.load_manifest(target_manifest)

    @property
    def assets(self) -> Dict[str, GraphicAsset]:
        return dict(self._assets)

    def load_manifest(self, manifest_path: Optional[Path] = None) -> None:
        """Parse JSON manifest, validating schema, enumerations, duplicates, and path confinement (TM-01)."""
        target = Path(manifest_path) if manifest_path else (self.base_dir / "assets" / "graphics_manifest.json")
        if not target.exists():
            raise FileNotFoundError(f"Manifest not found: {target}")

        content = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(content, dict) or "assets" not in content:
            raise ValueError(f"Invalid manifest structure in {target}: missing 'assets' key")

        loaded_assets: Dict[str, GraphicAsset] = {}
        for entry in content["assets"]:
            if not isinstance(entry, dict):
                raise ValueError("Manifest asset entry must be an object")

            # Required fields validation
            asset_id = entry.get("id")
            if not asset_id or not isinstance(asset_id, str):
                raise ValueError("Asset entry missing valid 'id'")
            if not ID_REGEX.match(asset_id):
                raise ValueError(f"Asset id '{asset_id}' contains invalid characters (must match ^[a-z0-9_]+$)")

            if asset_id in loaded_assets:
                raise ValueError(f"Duplicate asset id '{asset_id}' found in manifest")

            if "category" not in entry or not entry["category"]:
                raise ValueError(f"Asset '{asset_id}' missing required field 'category'")
            if "relative_path" not in entry or not entry["relative_path"]:
                raise ValueError(f"Asset '{asset_id}' missing required field 'relative_path'")

            rel_path_str = str(entry["relative_path"]).strip()
            rel_path = Path(rel_path_str)
            if rel_path.is_absolute() or ".." in rel_path.parts:
                raise ValueError(f"Path traversal or absolute path rejected for '{asset_id}': {rel_path_str}")

            resolved_path = (self.base_dir / rel_path).resolve()
            try:
                resolved_path.relative_to(self.base_dir)
            except ValueError:
                raise ValueError(f"Path traversal rejected: {rel_path_str} resolves outside base_dir {self.base_dir}")

            try:
                cat = GraphicCategory(entry["category"])
            except ValueError:
                raise ValueError(f"Unsupported category '{entry['category']}' for asset '{asset_id}'")

            aff_raw = entry.get("channel_affinity", "all")
            try:
                affinity = GraphicChannelAffinity(aff_raw)
            except ValueError:
                raise ValueError(f"Unsupported channel_affinity '{aff_raw}' for asset '{asset_id}'")

            aspect_ratios = tuple(entry.get("aspect_ratios", ["9:16", "16:9"]))
            safe_zone = bool(entry.get("safe_zone_compliant", True))
            default_opacity = float(entry.get("default_opacity", 0.25))
            dynamic_params = dict(entry.get("dynamic_params", {}))
            tags = tuple(entry.get("tags", []))
            name = str(entry.get("name", asset_id))

            loaded_assets[asset_id] = GraphicAsset(
                id=asset_id,
                name=name,
                category=cat,
                channel_affinity=affinity,
                aspect_ratios=aspect_ratios,
                relative_path=rel_path_str,
                safe_zone_compliant=safe_zone,
                default_opacity=default_opacity,
                dynamic_params=dynamic_params,
                tags=tags,
            )

        self._assets = loaded_assets

    def get_asset(self, asset_id: str) -> Optional[GraphicAsset]:
        return self._assets.get(asset_id)

    def query(
        self,
        category: Optional[Union[GraphicCategory, str]] = None,
        channel: Optional[str] = None,
        aspect_ratio: Optional[str] = None,
        tag: Optional[str] = None,
    ) -> List[GraphicAsset]:
        """Conjunction filtering across category, channel affinity, aspect ratio, and tags."""
        matches: List[GraphicAsset] = []
        cat_filter = category.value if isinstance(category, GraphicCategory) else category
        chan_filter = channel.lower() if channel else None

        # Transparent channel alias mapping
        if chan_filter in ("moku", "horror"):
            chan_filter = "horror"
        elif chan_filter in ("aelithia", "drama", "aita"):
            chan_filter = "drama"
        elif chan_filter in ("singularidad", "scifi", "space"):
            chan_filter = "scifi"

        for asset in self._assets.values():
            if cat_filter and asset.category.value != cat_filter and asset.category != cat_filter:
                continue

            if chan_filter:
                if asset.channel_affinity != GraphicChannelAffinity.ALL:
                    if asset.channel_affinity.value != chan_filter:
                        continue

            if aspect_ratio:
                if aspect_ratio not in asset.aspect_ratios:
                    continue

            if tag:
                tag_lower = tag.lower()
                if not any(tag_lower == t.lower() or tag_lower in t.lower() for t in asset.tags):
                    continue

            matches.append(asset)
        return matches

    def resolve_atmospheric_path(
        self,
        kind: str,
        particle_type: Optional[str] = None,
    ) -> Optional[Path]:
        """Resolve absolute on-disk path for atmospheric overlay textures."""
        kind_norm = (kind or "").strip().lower()

        candidates: List[str] = []
        if kind_norm == "particles":
            ptype = (particle_type or "none").strip().lower()
            if ptype and ptype != "none":
                candidates.append(f"particles_{ptype}")
            candidates.append("particles")
        elif kind_norm in ("vignette", "dark_vignette"):
            candidates.extend(["dark_vignette", "soft_vignette"])
        elif kind_norm in ("soft_vignette",):
            candidates.append("soft_vignette")
        elif kind_norm in ("film_grain", "grain"):
            candidates.append("film_grain")
        elif kind_norm in ("tv_static", "tv-static", "static"):
            candidates.append("tv_static")
        elif kind_norm in ("god_rays", "god-rays", "rays"):
            candidates.append("god_rays")
        else:
            candidates.append(kind_norm)

        for cand_id in candidates:
            asset = self.get_asset(cand_id)
            if asset:
                p = asset.resolve_path(self.base_dir)
                if p.is_file() and p.stat().st_size > 0:
                    return p

        # Fallback to direct file checks if not in manifest
        for cand_id in candidates:
            direct = self.base_dir / "assets" / "overlays" / "static" / f"{cand_id}.png"
            if direct.is_file() and direct.stat().st_size > 0:
                return direct.resolve()
            mirrored = self.base_dir / "assets" / "overlays" / f"{cand_id}.png"
            if mirrored.is_file() and mirrored.stat().st_size > 0:
                return mirrored.resolve()

        return None

    def clamp_asset_opacity(self, asset_id: str, requested: Optional[float] = None) -> float:
        """Clamp overlay opacity based on category constraints."""
        asset = self.get_asset(asset_id)
        if asset and asset.category == GraphicCategory.ATMOSPHERIC:
            if requested is None:
                return asset.default_opacity
            r = float(requested)
            if r == 0.0:
                return 0.0
            return max(0.15, min(0.35, r))

        # Non-atmospheric assets
        if requested is None:
            return asset.default_opacity if asset else 1.0
        return max(0.0, min(1.0, float(requested)))

    def validate_bank(self) -> BankValidationReport:
        """Preflight integrity probe verifying files, sizes, modes, and XML safety."""
        missing: List[str] = []
        corrupted: List[str] = []
        oversized: List[str] = []
        errors: List[str] = []
        verified = 0

        for asset in self._assets.values():
            p = asset.resolve_path(self.base_dir)
            if not p.is_file() or p.stat().st_size == 0:
                missing.append(asset.id)
                errors.append(f"Asset '{asset.id}' file missing or empty: {p}")
                continue

            size = p.stat().st_size
            suffix = p.suffix.lower()

            if suffix == ".png":
                if size > 204800:
                    oversized.append(asset.id)
                    errors.append(f"Asset '{asset.id}' PNG size {size} > 204,800 bytes")
                try:
                    from PIL import Image

                    with Image.open(p) as img:
                        if img.mode != "RGBA":
                            corrupted.append(asset.id)
                            errors.append(f"Asset '{asset.id}' mode '{img.mode}' != RGBA")
                        elif not (
                            (img.width >= 1080 and img.height >= 1920)
                            or (img.width >= 1920 and img.height >= 1080)
                        ):
                            corrupted.append(asset.id)
                            errors.append(f"Asset '{asset.id}' dimensions {img.size} invalid")
                        else:
                            verified += 1
                except Exception as exc:
                    corrupted.append(asset.id)
                    errors.append(f"Asset '{asset.id}' image open failure: {exc}")

            elif suffix == ".svg":
                if size > 512000:
                    oversized.append(asset.id)
                    errors.append(f"Asset '{asset.id}' SVG size {size} > 512,000 bytes")
                try:
                    import xml.etree.ElementTree as ET

                    content = p.read_text(encoding="utf-8")
                    if "<!DOCTYPE" in content or "<!ENTITY" in content:
                        corrupted.append(asset.id)
                        errors.append(f"Asset '{asset.id}' contains forbidden DOCTYPE or ENTITY")
                    else:
                        root = ET.fromstring(content)
                        if not root.tag.endswith("svg"):
                            corrupted.append(asset.id)
                            errors.append(f"Asset '{asset.id}' root tag is not svg")
                        else:
                            verified += 1
                except Exception as exc:
                    corrupted.append(asset.id)
                    errors.append(f"Asset '{asset.id}' XML parse failure: {exc}")
            else:
                verified += 1

        valid = len(missing) == 0 and len(corrupted) == 0 and len(oversized) == 0
        return BankValidationReport(
            valid=valid,
            total_assets=len(self._assets),
            verified_assets=verified,
            missing_assets=tuple(missing),
            corrupted_assets=tuple(corrupted),
            oversized_assets=tuple(oversized),
            errors=tuple(errors),
        )


_GLOBAL_BANK: Optional[GraphicsBank] = None


def get_graphics_bank() -> GraphicsBank:
    """Singleton provider for GraphicsBank."""
    global _GLOBAL_BANK
    if _GLOBAL_BANK is None:
        _GLOBAL_BANK = GraphicsBank()
    return _GLOBAL_BANK
