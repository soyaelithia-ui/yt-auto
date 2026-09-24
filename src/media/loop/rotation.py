"""Loop selection from catalog, rotation index persistence, and library scanning."""

from __future__ import annotations

import json
import random
import subprocess
import threading
from pathlib import Path
from typing import Any, Optional, Sequence

from src.config import BASE_DIR
from src.core.catalog import (
    CHANNEL_THEMES,
    LoopCatalogRepository,
    resolve_loop_file_path,
    _LEGACY_CHECKOUT_PREFIXES,
)
from src.core.resolution import LONGFORM_RESOLUTION, SHORT_RESOLUTION
from src.log import get_logger
from src.media.interface import CatalogAssetNotFoundError
from src.media.loop.exceptions import LoopVideoAssetError
from lib.ffmpeg import probe_media

logger = get_logger("loop_rotation")

SHORTS_VIDEOS_DIR = (BASE_DIR / "assets" / "videos" / "shorts").resolve()
LONGS_VIDEOS_DIR = (BASE_DIR / "assets" / "videos" / "longs").resolve()

GREY_PLANE_TECHNOLOGIES = frozenset({"ffmpeg_lavfi", "synthetic_monochrome"})
_OVERLAY_DIR_MARKERS = frozenset({"overlays", "ambient_gifs"})
_OVERLAY_NAME_TOKENS = ("tv_static", "film_grain", "vignette")
_GREY_NAME_TOKENS = ("monochrome", "grey", "gray")

SYNTHETIC_MONOCHROME_IDS: tuple[str, ...] = (
    "loop_maritime_lighthouse_h_544374",
    "loop_arctic_desolation_v_800210",
)

SYNTHETIC_MONOCHROME_CATEGORIES: tuple[str, ...] = (
    "maritime_lighthouse",
    "arctic_desolation",
)

SYNTHETIC_MONOCHROME_FILES: tuple[str, ...] = (
    "loop_maritime_lighthouse_horizontal_544374.mp4",
    "loop_arctic_desolation_vertical_800210.mp4",
)

THEMATIC_CATEGORIES: tuple[str, ...] = (
    "horror",
    "dark_forest",
    "cosmic_horror",
    "drama",
    "cozy_ambient",
    "scifi",
    "space_abyss",
    "monsters",
    "dark_ambient",
)

CATEGORY_ALIASES: dict[str, str] = {
    # Moku / Horror / SCP / Underground / Facility themes
    "tactical_chamber": "horror",
    "bunker": "horror",
    "chamber": "horror",
    "corridor": "horror",
    "asylum": "horror",
    "morgue": "horror",
    "facility": "horror",
    "containment": "horror",
    "scp": "horror",
    "moku": "horror",
    "moku_horror": "horror",
    "haunted_house": "horror",
    "analog_horror": "horror",
    "vhs": "horror",
    "found_footage": "horror",

    # Dark Forest / Outdoor Mystery / Woods
    "creepy_woods": "dark_forest",
    "woods": "dark_forest",
    "forest": "dark_forest",
    "cemetery": "dark_forest",
    "misty_pines": "dark_forest",
    "cabin": "dark_forest",
    "dark_woods": "dark_forest",
    "foggy_road": "dark_forest",

    # Aelithia / Drama / Relationships / Reddit AITA
    "cozy_hearth": "drama",
    "aelithia": "drama",
    "aelithia_drama": "drama",
    "aita": "drama",
    "drama_aita": "drama",
    "reddit_aita": "drama",
    "confession": "drama",
    "relationships": "drama",
    "family_drama": "drama",
    "nostalgia": "drama",
    "moral_dilemma": "drama",

    # Cozy Ambient / Warm Interiors
    "cozy_interior": "cozy_ambient",
    "cozy_interiors": "cozy_ambient",
    "warm_hearth": "cozy_ambient",
    "fireplace": "cozy_ambient",
    "cafe": "cozy_ambient",
    "rainy_cafe": "cozy_ambient",
    "bookstore": "cozy_ambient",
    "art_studio": "cozy_ambient",

    # SciFi / Cyber / Space / Shaders
    "cosmic_singularity": "scifi",
    "singularidad_scifi": "scifi",
    "cyberpunk": "scifi",
    "cyber_infrastructure": "scifi",
    "synaptic_network": "scifi",
    "arcade_vector_flight": "scifi",
    "parkour_runner": "scifi",
    "datacenter": "scifi",

    # Space Abyss / Cosmic / Deep Space
    "deep_space": "space_abyss",
    "space": "space_abyss",
    "abyss": "space_abyss",
    "blackhole": "space_abyss",

    # Procedural / Fallback
    "maritime_lighthouse": "dark_ambient",
    "arctic_desolation": "dark_ambient",
}

DEFAULT_CATEGORY: str = "dark_ambient"

SUPPORTED_VIDEO_EXTENSIONS: tuple[str, ...] = (
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".avi",
)

SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
)

RESOLUTIONS: dict[str, tuple[int, int]] = {
    "vertical": SHORT_RESOLUTION,
    "horizontal": LONGFORM_RESOLUTION,
    "short": SHORT_RESOLUTION,
    "longform": LONGFORM_RESOLUTION,
    "9:16": SHORT_RESOLUTION,
    "16:9": LONGFORM_RESOLUTION,
    "portrait": SHORT_RESOLUTION,
    "landscape": LONGFORM_RESOLUTION,
}

DEFAULT_RESOLUTION: tuple[int, int] = SHORT_RESOLUTION

_ROTATION_STATE_FILE = (BASE_DIR / "data" / "loop_rotation_state.json").resolve()
_ROTATION_STATE_LOCK = threading.RLock()


def is_overlay_not_plane0(path: str | Path | None) -> bool:
    """True when an asset is an overlay/effect layer, never a principal background."""
    if not path:
        return False
    p = Path(path)
    parts = {part.lower() for part in p.parts}
    if parts & _OVERLAY_DIR_MARKERS:
        return True
    name = p.name.lower()
    return any(tok in name for tok in _OVERLAY_NAME_TOKENS)


def is_grey_procedural_plane(
    *,
    technology: str | None = None,
    category: str | None = None,
    loop_id: str | None = None,
    path: str | Path | None = None,
    sha256: str | None = None,
) -> bool:
    """True when a candidate would be a grey lavfi / synthetic-monochrome plane-0."""
    tech = (technology or "").strip().lower()
    if tech == "synthetic_monochrome":
        return True
    if tech == "ffmpeg_lavfi" and (sha256 or "").strip().lower() == "procedural":
        return True
    cat = (category or "").strip().lower()
    if cat in SYNTHETIC_MONOCHROME_CATEGORIES:
        return True
    lid = (loop_id or "").strip()
    if lid in SYNTHETIC_MONOCHROME_IDS:
        return True
    if not path:
        return False
    p = Path(path)
    if p.name in SYNTHETIC_MONOCHROME_FILES:
        return True
    parts = {part.lower() for part in p.parts}
    if parts & set(SYNTHETIC_MONOCHROME_CATEGORIES):
        return True
    stem = p.stem.lower()
    return any(tok in stem for tok in _GREY_NAME_TOKENS)


def _load_rotation_state() -> dict[str, int]:
    try:
        if _ROTATION_STATE_FILE.is_file():
            data = json.loads(_ROTATION_STATE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {k: int(v) for k, v in data.items() if isinstance(v, (int, float))}
    except Exception:
        pass
    return {}


def _save_rotation_state(state: dict[str, int]) -> None:
    try:
        _ROTATION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _ROTATION_STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(state), encoding="utf-8")
        tmp.replace(_ROTATION_STATE_FILE)
    except Exception:
        pass


class LoopRotationMixin:
    """Methods for loop asset resolution, round-robin rotation, and library scanning."""

    THEMATIC_CATEGORIES: tuple[str, ...] = THEMATIC_CATEGORIES
    CATEGORY_ALIASES: dict[str, str] = CATEGORY_ALIASES
    SYNTHETIC_MONOCHROME_IDS: tuple[str, ...] = SYNTHETIC_MONOCHROME_IDS
    SYNTHETIC_MONOCHROME_CATEGORIES: tuple[str, ...] = SYNTHETIC_MONOCHROME_CATEGORIES
    SYNTHETIC_MONOCHROME_FILES: tuple[str, ...] = SYNTHETIC_MONOCHROME_FILES
    DEFAULT_CATEGORY: str = DEFAULT_CATEGORY
    SUPPORTED_VIDEO_EXTENSIONS: tuple[str, ...] = SUPPORTED_VIDEO_EXTENSIONS
    SUPPORTED_IMAGE_EXTENSIONS: tuple[str, ...] = SUPPORTED_IMAGE_EXTENSIONS
    RESOLUTIONS: dict[str, tuple[int, int]] = RESOLUTIONS
    DEFAULT_RESOLUTION: tuple[int, int] = DEFAULT_RESOLUTION

    loops_root_dir: Path
    default_fallback_dir: Path
    default_fallback_image: Path
    db_path: str
    _custom_catalog: bool
    catalog: Optional[LoopCatalogRepository]
    enable_live_synth: bool
    shorts_videos_dir: Path
    longs_videos_dir: Path

    _rotation_indices: dict[str, int] = {"shorts": 0, "longs": 0}

    @classmethod
    def get_rotation_index(cls, mode: str, total_files: int, *, persist: bool | None = None) -> int:
        """Determines next rotation index, using disk-backed state in production or in-memory in tests."""
        from src.config import is_test_environment
        should_persist = (not is_test_environment()) if persist is None else bool(persist)
        with _ROTATION_STATE_LOCK:
            if should_persist:
                state = _load_rotation_state()
                curr = state.get(mode, cls._rotation_indices.get(mode, 0))
                idx = curr % total_files
                next_idx = idx + 1
                cls._rotation_indices[mode] = next_idx
                state[mode] = next_idx
                _save_rotation_state(state)
                return idx
            else:
                idx = cls._rotation_indices.get(mode, 0) % total_files
                cls._rotation_indices[mode] = idx + 1
                return idx

    @classmethod
    def reset_rotation_state(cls, mode: str | None = None) -> None:
        """Resets rotation indices in memory and on disk."""
        if mode:
            cls._rotation_indices[mode] = 0
        else:
            cls._rotation_indices = {"shorts": 0, "longs": 0}
        try:
            if _ROTATION_STATE_FILE.is_file():
                if mode:
                    state = _load_rotation_state()
                    state[mode] = 0
                    _save_rotation_state(state)
                else:
                    _save_rotation_state({"shorts": 0, "longs": 0})
        except Exception:
            pass

    def resolve_continuous_loop(
        self,
        orientation: str | tuple[int, int] = "vertical",
        *,
        category: str | None = None,
        channel: str | None = None,
        allow_test_mock: bool = False,
        persist: bool | None = None,
    ) -> Path:
        """
        Resolves a single continuous loop clip from assets/videos/shorts/ (vertical)
        or assets/videos/longs/ (horizontal) using round-robin rotation, optionally
        filtered by thematic category or channel context.
        Raises CatalogAssetNotFoundError if directory is empty (fail-fast safeguard).
        """
        is_vert = (
            orientation in ("vertical", "9:16", (1080, 1920), (720, 1280))
            or "short" in str(orientation).lower()
            or (isinstance(orientation, (tuple, list)) and len(orientation) == 2 and orientation[1] > orientation[0])
        )
        folder = self.shorts_videos_dir if is_vert else self.longs_videos_dir
        mode = "shorts" if is_vert else "longs"
        spec = "10s vertical 9:16" if is_vert else "30s horizontal 16:9"

        mp4_files: list[Path] = []
        if folder.exists():
            mp4_files = sorted([
                p for p in folder.iterdir()
                if p.is_file() and p.suffix.lower() == ".mp4" and p.stat().st_size > 0 and not p.name.startswith(".")
            ])

        if not mp4_files:
            from src.config import is_test_environment
            if allow_test_mock and is_test_environment():
                return self._get_or_create_test_fixture_loop(orientation=orientation)
            raise CatalogAssetNotFoundError(
                f"No video loops found in '{folder}'. Please place at least one .mp4 loop clip "
                f"({spec}) in '{folder}' to enable video composition."
            )

        # Context-aware candidate filtering (Horror vs Drama vs Scifi)
        candidates = mp4_files
        from src.core.domain import CanonicalChannel, canonical_channel
        canon = None
        if channel:
            try:
                canon = canonical_channel(channel)
            except Exception:
                pass

        norm_ctx = f"{category or ''} {channel or ''}".lower()
        if canon == CanonicalChannel.DRAMA or (canon is None and any(k in norm_ctx for k in ("drama", "aita", "aelithia", "interior", "romance", "family", "confession"))):
            drama_matches = [
                p for p in mp4_files
                if not any(k in p.name.lower() for k in ("horror", "scp", "dark", "cosmic", "abyss", "terror", "creepy", "monsters"))
                and any(k in p.name.lower() for k in ("drama", "interior", "cozy", "rain", "window", "hearth", "ambient"))
            ]
            if drama_matches:
                candidates = drama_matches
        elif canon == CanonicalChannel.HORROR or (canon is None and any(k in norm_ctx for k in ("horror", "scp", "moku", "creepy", "dark", "cosmic", "abyss"))):
            horror_matches = [
                p for p in mp4_files
                if not any(k in p.name.lower() for k in ("drama", "aita", "aelithia", "romance", "family"))
                and any(k in p.name.lower() for k in ("horror", "scp", "dark", "cosmic", "abyss", "terror", "creepy", "ambient"))
            ]
            if horror_matches:
                candidates = horror_matches

        rotation_key = f"{mode}_{candidates[0].stem.split('_')[0]}" if len(candidates) < len(mp4_files) else mode
        idx = self.get_rotation_index(rotation_key, len(candidates), persist=persist)
        chosen = candidates[idx]
        logger.info(
            "Resolved continuous single-loop [%s] (ctx: '%s') (%d/%d): %s",
            rotation_key, norm_ctx.strip(), idx + 1, len(candidates), chosen.name,
        )
        return chosen

    @classmethod
    def _get_or_create_test_fixture_loop(cls, orientation: str | tuple[int, int] = "vertical") -> Path:
        """Provides a lightweight 10s (vertical) or 30s (horizontal) mock fixture mp4 loop for unit/integration tests with Main profile."""
        is_vert = (
            orientation in ("vertical", "9:16", (1080, 1920), (720, 1280))
            or "short" in str(orientation).lower()
            or (isinstance(orientation, (tuple, list)) and len(orientation) == 2 and orientation[1] > orientation[0])
        )
        w, h = (1080, 1920) if is_vert else (1920, 1080)
        dur = 10 if is_vert else 30
        fixtures_dir = BASE_DIR / "tests" / "fixtures" / "loops"
        fixtures_dir.mkdir(parents=True, exist_ok=True)
        fixture_path = fixtures_dir / f"mock_loop_{w}x{h}.mp4"
        regenerate = False
        if not fixture_path.exists() or fixture_path.stat().st_size == 0:
            regenerate = True
        else:
            try:
                probe = probe_media(fixture_path)
                prof = (probe.video_streams[0].profile if probe.video_streams else "").lower()
                if "main" not in prof and "baseline" not in prof:
                    regenerate = True
            except Exception:
                regenerate = True

        if regenerate:
            cmd = [
                "ffmpeg", "-y",
                "-f", "lavfi", "-i", f"color=c=0x454545:s={w}x{h}:r=30",
                "-t", str(dur),
                "-c:v", "libx264", "-profile:v", "main", "-level", "4.0", "-pix_fmt", "yuv420p",
                str(fixture_path),
            ]
            subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True, timeout=30)
        return fixture_path

    def _is_unusable_plane0(
        self,
        path: Path | None,
        *,
        technology: str | None = None,
        category: str | None = None,
        loop_id: str | None = None,
    ) -> bool:
        """Grey lavfi / overlay assets cannot be the principal visual plane."""
        if path is None:
            return True
        if is_overlay_not_plane0(path):
            return True
        return is_grey_procedural_plane(
            technology=technology,
            category=category,
            loop_id=loop_id,
            path=path,
            sha256=None,
        )

    def _find_scenery_still(self, seed: Any = None, channel: str | None = None) -> Path | None:
        """Clean scenery still fallback (never overlays / grey lavfi)."""
        still_dirs: list[Path] = []
        if channel:
            chan_scenery = BASE_DIR / "assets" / "visual_bank" / channel.lower().strip() / "scenery"
            if chan_scenery.is_dir():
                still_dirs.append(chan_scenery)
        if self.default_fallback_dir.is_dir():
            still_dirs.append(self.default_fallback_dir)
        using_prod_loops = self.loops_root_dir == (BASE_DIR / "assets" / "loops").resolve()
        if using_prod_loops:
            vb = BASE_DIR / "assets" / "visual_bank"
            if vb.is_dir():
                try:
                    for chan in sorted(p for p in vb.iterdir() if p.is_dir() and not p.name.startswith("_")):
                        scenery = chan / "scenery"
                        if scenery.is_dir() and scenery not in still_dirs:
                            still_dirs.append(scenery)
                except OSError:
                    pass
        for d in still_dirs:
            picked = self._pick_media_file(
                d,
                self.SUPPORTED_IMAGE_EXTENSIONS,
                seed=seed,
                max_scan=32,
                recursive=True,
            )
            if picked is not None and not self._is_unusable_plane0(picked):
                return picked
        img = self.default_fallback_image
        if img.is_file() and img.stat().st_size > 0 and not self._is_unusable_plane0(img):
            return img
        return None

    def normalize_category(self, category: str | None) -> str:
        """
        Normalizes category string into canonical snake_case format
        and resolves semantic pipeline aliases to catalog categories.
        """
        if not category:
            return self.DEFAULT_CATEGORY
        normalized = str(category).strip().lower().replace("-", "_").replace(" ", "_")
        if not normalized:
            return self.DEFAULT_CATEGORY
        return self.CATEGORY_ALIASES.get(normalized, normalized)

    def scan_libraries(self, asset_root: str | Path | None = None) -> dict[str, list[Path]]:
        """
        Scans loop directory tree for available video files grouped by thematic category.
        Returns a dictionary mapping category names to lists of existing video file Paths.
        """
        root = Path(asset_root).expanduser().resolve() if asset_root else self.loops_root_dir
        library: dict[str, list[Path]] = {cat: [] for cat in self.THEMATIC_CATEGORIES}

        if not root.exists() or not root.is_dir():
            return library

        for cat in self.THEMATIC_CATEGORIES:
            for cat_dir in (root / cat, root / "vertical" / cat, root / "horizontal" / cat):
                if cat_dir.is_dir():
                    for f in self._iter_media_files(cat_dir, self.SUPPORTED_VIDEO_EXTENSIONS, max_scan=128, recursive=True):
                        if f not in library[cat]:
                            library[cat].append(f)

        scan_dirs = [root]
        if (root / "vertical").is_dir():
            scan_dirs.append(root / "vertical")
        if (root / "horizontal").is_dir():
            scan_dirs.append(root / "horizontal")

        for parent_dir in scan_dirs:
            for entry in sorted(parent_dir.iterdir()):
                if entry.is_dir() and entry.name not in ("vertical", "horizontal"):
                    c_name = entry.name
                    if c_name not in library:
                        library[c_name] = []
                    for f in self._iter_media_files(entry, self.SUPPORTED_VIDEO_EXTENSIONS, max_scan=128, recursive=True):
                        if f not in library[c_name]:
                            library[c_name].append(f)

        return library

    @staticmethod
    def _live_rss_checkpoint(stage: str) -> dict:
        """Cheap stdlib RSS sample for live select/create (stages 8–9)."""
        try:
            from src.core.guard import memory_checkpoint, read_vm_rss_bytes

            info = memory_checkpoint(stage)
            if "observed_bytes" not in info:
                info["observed_bytes"] = read_vm_rss_bytes()
            logger.debug(
                "live_rss_checkpoint stage=%s rss_bytes=%s",
                stage,
                info.get("observed_bytes"),
            )
            return info
        except Exception as exc:
            logger.debug("live_rss_checkpoint skipped (%s): %s", stage, exc)
            return {"stage": stage, "disabled": True}

    def _iter_media_files(
        self,
        directory: Path,
        extensions: tuple[str, ...],
        *,
        max_scan: int = 64,
        recursive: bool = True,
    ):
        """Yield valid media files lazily with a hard scan cap (near-zero RAM)."""
        if not directory.is_dir():
            return
        try:
            entries = sorted(directory.iterdir())
        except OSError:
            return

        yielded = 0
        subdirs: list[Path] = []
        for f in entries:
            if yielded >= max_scan:
                return
            try:
                if (
                    f.is_file()
                    and f.suffix.lower() in extensions
                    and f.stat().st_size > 0
                ):
                    yielded += 1
                    yield f
                elif recursive and f.is_dir() and f.name not in (".git", "__pycache__"):
                    subdirs.append(f)
            except OSError:
                continue

        if recursive:
            for sdir in subdirs:
                if yielded >= max_scan:
                    return
                for f in self._iter_media_files(
                    sdir,
                    extensions,
                    max_scan=max_scan - yielded,
                    recursive=True,
                ):
                    yielded += 1
                    yield f
                    if yielded >= max_scan:
                        return

    def _pick_media_file(
        self,
        directory: Path,
        extensions: tuple[str, ...],
        *,
        seed: Any = None,
        name_substrs: Sequence[str] | None = None,
        max_scan: int = 64,
        recursive: bool = True,
        exclude_loop_ids: Sequence[str] | None = None,
    ) -> Path | None:
        """Pick one media file without materializing huge directory listings."""
        collected: list[Path] = []
        exclude_set = {str(e).strip() for e in (exclude_loop_ids or []) if e}
        exclude_stems = {Path(e).stem for e in exclude_set}

        for f in self._iter_media_files(directory, extensions, max_scan=max_scan, recursive=recursive):
            if exclude_set and (f.stem in exclude_stems or f.name in exclude_set or str(f) in exclude_set):
                continue
            if is_overlay_not_plane0(f) or is_grey_procedural_plane(path=f):
                continue
            if name_substrs:
                if any(s in f.name for s in name_substrs):
                    collected.append(f)
            else:
                collected.append(f)
            if seed is None and collected and not name_substrs:
                return collected[0]

        if name_substrs and not collected:
            for f in self._iter_media_files(directory, extensions, max_scan=max_scan, recursive=recursive):
                if exclude_set and (f.stem in exclude_stems or f.name in exclude_set or str(f) in exclude_set):
                    continue
                if is_overlay_not_plane0(f) or is_grey_procedural_plane(path=f):
                    continue
                collected.append(f)
                if seed is None:
                    return f

        if not collected:
            return None
        if seed is not None:
            return random.Random(seed).choice(collected)
        return collected[0]

    def _find_fallback_in_other_categories(
        self,
        root: Path,
        norm_cat: str,
        seed: Any,
        orientation: str | None = None,
        exclude_loop_ids: Sequence[str] | None = None,
        channel: str | None = None,
    ) -> Path | None:
        """Lazy cross-category fallback: stop at first usable video (bounded and channel-constrained)."""
        ignored_names = {
            "vertical", "horizontal", norm_cat,
            *self.SYNTHETIC_MONOCHROME_CATEGORIES
        }
        eff_channel = (channel or "").lower().strip()
        if eff_channel and eff_channel in CHANNEL_THEMES:
            candidates: list[str] = [c for c in CHANNEL_THEMES[eff_channel] if c not in ignored_names]
        else:
            candidates: list[str] = [c for c in self.THEMATIC_CATEGORIES if c not in ignored_names]
            try:
                if root.is_dir():
                    for entry in sorted(root.iterdir()):
                        if (
                            entry.is_dir()
                            and entry.name not in ignored_names
                            and entry.name not in candidates
                        ):
                            candidates.append(entry.name)
                            if len(candidates) >= 32:
                                break
            except OSError:
                pass

        orient_name = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical" if orientation else None

        for cat_name in candidates:
            dirs_to_check = []
            if orient_name:
                dirs_to_check.append(root / orient_name / cat_name)
            dirs_to_check.extend([
                root / cat_name,
                root / "vertical" / cat_name,
                root / "horizontal" / cat_name,
            ])
            for cat_dir in dirs_to_check:
                picked = self._pick_media_file(
                    cat_dir,
                    self.SUPPORTED_VIDEO_EXTENSIONS,
                    seed=seed,
                    max_scan=32,
                    recursive=True,
                    exclude_loop_ids=exclude_loop_ids,
                )
                if picked is not None:
                    if self._is_unusable_plane0(picked, category=cat_name):
                        continue
                    logger.info("Found fallback loop video in category '%s': %s", cat_name, picked.name)
                    return picked
        return None

    def _resolve_loop_from_catalog(
        self,
        norm_cat: str,
        asset_root: str | Path | None,
        allow_fallback: bool,
        seed: Any,
        orientation: str | None,
        exclude_loop_ids: Sequence[str] | None,
        channel: str | None,
        motifs: Sequence[str] | None,
    ) -> Path | None:
        can_query_catalog = self.catalog is not None and asset_root is None and (
            self.loops_root_dir == (BASE_DIR / "assets" / "loops").resolve() or self._custom_catalog
        )
        if not can_query_catalog:
            return None
        try:
            exclude_list = list(exclude_loop_ids) if exclude_loop_ids else None
            try:
                best_loop = self.catalog.get_best_loop(
                    category=norm_cat,
                    orientation=orientation or "vertical",
                    requested_tags=[channel] if channel else None,
                    seed=seed,
                    exclude_loop_ids=exclude_list,
                    channel=channel,
                    motifs=motifs,
                )
            except TypeError:
                best_loop = self.catalog.get_best_loop(
                    category=norm_cat,
                    orientation=orientation or "vertical",
                )

            if best_loop and not allow_fallback and getattr(best_loop, "category", "").strip().lower() != norm_cat.strip().lower():
                best_loop = None
            if not best_loop:
                return None

            loop_fp = Path(best_loop.file_path)
            if ".." in loop_fp.parts:
                raise LoopVideoAssetError(
                    f"Path traversal detected in catalog loop asset: {best_loop.file_path}"
                )
            resolved_p = resolve_loop_file_path(best_loop.file_path).resolve()
            allowed_roots = [
                (BASE_DIR / "assets").resolve(),
                self.loops_root_dir.resolve(),
            ]
            for prefix in _LEGACY_CHECKOUT_PREFIXES:
                allowed_roots.append((Path(prefix) / "assets").resolve())

            is_safe = any(resolved_p.is_relative_to(root) for root in allowed_roots)
            if not is_safe:
                raise LoopVideoAssetError(
                    f"Path traversal detected: loop asset {best_loop.file_path} is outside assets directory"
                )

            if resolved_p.is_file() and resolved_p.stat().st_size > 0:
                if self._is_unusable_plane0(
                    resolved_p,
                    technology=getattr(best_loop, "technology", None),
                    category=getattr(best_loop, "category", None),
                    loop_id=getattr(best_loop, "loop_id", None),
                ) or is_grey_procedural_plane(
                    technology=getattr(best_loop, "technology", None),
                    category=getattr(best_loop, "category", None),
                    loop_id=getattr(best_loop, "loop_id", None),
                    path=resolved_p,
                    sha256=getattr(best_loop, "sha256", None),
                ):
                    logger.info(
                        "Skipping grey/overlay catalog loop '%s' for requested category '%s'",
                        best_loop.loop_id,
                        norm_cat,
                    )
                else:
                    self.catalog.record_loop_usage(best_loop.loop_id)
                    logger.info("Resolved loop from SQLite catalog: %s (%s)", best_loop.loop_id, resolved_p)
                    self._live_rss_checkpoint("8_loop_scene_live_select_hit")
                    return resolved_p
        except CatalogAssetNotFoundError:
            raise
        except Exception as e:
            logger.warning("Could not query SQLite loop catalog: %s", e)
        return None

    def _resolve_loop_from_filesystem(
        self,
        root: Path,
        norm_cat: str,
        orientation: str | None,
        seed: Any,
        exclude_loop_ids: Sequence[str] | None,
    ) -> Path | None:
        if orientation:
            orient_name = "horizontal" if orientation in ("horizontal", "16:9", "longform", (1920, 1080)) else "vertical"
            name_keys = (orient_name, f"_{orient_name[:1]}_")
            for orient_cat_dir in (root / orient_name / norm_cat, root / norm_cat):
                use_name_keys = None if orient_cat_dir == (root / orient_name / norm_cat) else name_keys
                picked = self._pick_media_file(
                    orient_cat_dir,
                    self.SUPPORTED_VIDEO_EXTENSIONS,
                    seed=seed,
                    name_substrs=use_name_keys,
                    max_scan=64,
                    recursive=True,
                    exclude_loop_ids=exclude_loop_ids,
                )
                if picked is not None and not self._is_unusable_plane0(picked, category=norm_cat):
                    return picked

        cat_dir = root / norm_cat
        picked = self._pick_media_file(
            cat_dir,
            self.SUPPORTED_VIDEO_EXTENSIONS,
            seed=seed,
            max_scan=64,
            recursive=True,
            exclude_loop_ids=exclude_loop_ids,
        )
        if picked is not None and not self._is_unusable_plane0(picked, category=norm_cat):
            return picked
        return None

    def _resolve_loop_fallback(
        self,
        root: Path,
        norm_cat: str,
        seed: Any,
        orientation: str | None,
        exclude_loop_ids: Sequence[str] | None,
        channel: str | None,
    ) -> Path:
        logger.info(
            "Category '%s' is empty or missing in %s. "
            "Searching color loops, then scenery stills (never grey lavfi as plane-0).",
            norm_cat,
            root,
        )
        other = self._find_fallback_in_other_categories(
            root,
            norm_cat,
            seed,
            orientation=orientation,
            exclude_loop_ids=exclude_loop_ids,
            channel=channel,
        )
        if other is not None and not self._is_unusable_plane0(other):
            return other

        if channel:
            chan_still = self._find_scenery_still(seed=seed, channel=channel)
            if chan_still is not None:
                logger.info("Using channel scenery still as plane-0: %s", chan_still.name)
                return chan_still

        if root.is_dir() and not channel:
            root_hit = self._pick_media_file(
                root,
                self.SUPPORTED_VIDEO_EXTENSIONS,
                seed=None,
                max_scan=32,
                recursive=False,
                exclude_loop_ids=exclude_loop_ids,
            )
            if root_hit is not None and not self._is_unusable_plane0(root_hit):
                logger.info("Found fallback loop video in root loops directory: %s", root_hit.name)
                return root_hit

        if self.default_fallback_dir.is_dir() and not channel:
            fb_vid = self._pick_media_file(
                self.default_fallback_dir,
                self.SUPPORTED_VIDEO_EXTENSIONS,
                max_scan=32,
                recursive=True,
                exclude_loop_ids=exclude_loop_ids,
            )
            if fb_vid is not None and not self._is_unusable_plane0(fb_vid):
                logger.info("Found fallback video in backgrounds directory: %s", fb_vid.name)
                return fb_vid
            fb_img = self._pick_media_file(
                self.default_fallback_dir,
                self.SUPPORTED_IMAGE_EXTENSIONS,
                max_scan=32,
                recursive=True,
            )
            if fb_img is not None and not self._is_unusable_plane0(fb_img):
                logger.info("Found fallback background image: %s", fb_img.name)
                return fb_img

        still = self._find_scenery_still(seed=seed, channel=channel)
        if still is not None:
            logger.info("Using multi-crop scenery still as plane-0: %s", still.name)
            return still

        if self.default_fallback_image.is_file() and self.default_fallback_image.stat().st_size > 0:
            if not self._is_unusable_plane0(self.default_fallback_image):
                logger.info("Using default fallback image: %s", self.default_fallback_image.name)
                return self.default_fallback_image

        raise LoopVideoAssetError(
            f"No catalog loop video or certified fallback asset found for category '{norm_cat}' in {root}"
        )

    def resolve_loop_video(
        self,
        category: str | None = None,
        asset_root: str | Path | None = None,
        allow_fallback: bool = True,
        seed: Any = None,
        orientation: str | None = None,
        exclude_loop_ids: Sequence[str] | None = None,
        channel: str | None = None,
        motifs: Sequence[str] | None = None,
        topic: str | None = None,
        **kwargs: Any,
    ) -> Path:
        """
        Resolves a loop/background asset with live-first priority:
        1) catalog get_best_loop (live select) with seed, exclude_loop_ids, channel, motifs, and monochrome guards
        2) exact category filesystem hit (searching recursive atomic/ folders)
        3) filesystem / backgrounds fallback (avoiding synthetic monochrome latching)
        """
        if category and (".." in str(category) or "/" in str(category) or "\\" in str(category)):
            raise LoopVideoAssetError(f"Path traversal detected in category parameter: {category}")

        norm_cat = self.normalize_category(category)
        self._live_rss_checkpoint("8_loop_scene_live_select")

        if not motifs and topic:
            try:
                from src.core.scenic_detector import extract_story_motifs
                motifs = extract_story_motifs(topic)
            except Exception:
                pass

        catalog_hit = self._resolve_loop_from_catalog(
            norm_cat=norm_cat,
            asset_root=asset_root,
            allow_fallback=allow_fallback,
            seed=seed,
            orientation=orientation,
            exclude_loop_ids=exclude_loop_ids,
            channel=channel,
            motifs=motifs,
        )
        if catalog_hit is not None:
            return catalog_hit

        root = Path(asset_root).expanduser().resolve() if asset_root else self.loops_root_dir
        fs_hit = self._resolve_loop_from_filesystem(
            root=root,
            norm_cat=norm_cat,
            orientation=orientation,
            seed=seed,
            exclude_loop_ids=exclude_loop_ids,
        )
        if fs_hit is not None:
            return fs_hit

        if not allow_fallback:
            cat_dir = root / norm_cat
            raise LoopVideoAssetError(
                f"No video loops found in category '{norm_cat}' at {cat_dir}"
            )

        return self._resolve_loop_fallback(
            root=root,
            norm_cat=norm_cat,
            seed=seed,
            orientation=orientation,
            exclude_loop_ids=exclude_loop_ids,
            channel=channel,
        )

    def resolve_background(
        self,
        category: str | None = None,
        *,
        allow_fallback: bool = True,
        asset_root: str | Path | None = None,
        seed: Any = None,
        orientation: str | None = None,
        exclude_loop_ids: Sequence[str] | None = None,
        channel: str | None = None,
        **kwargs: Any,
    ) -> Path:
        """Convenience alias for resolve_loop_video."""
        return self.resolve_loop_video(
            category=category,
            asset_root=asset_root,
            allow_fallback=allow_fallback,
            seed=seed,
            orientation=orientation,
            exclude_loop_ids=exclude_loop_ids,
            channel=channel,
            **kwargs,
        )
