"""
Asset Manager for cataloging, indexing, and selecting images, videos, music,
and ambient audio files for video generation pipelines.
"""
import os
import random
from pathlib import Path
from typing import List, Dict, Optional, Union
from src.config import BASE_DIR, DEFAULT_BACKGROUND
from src.log import get_logger

logger = get_logger("asset_manager")

# Path segments that must never enter the video background pool.
# Finished title cards / baked-text covers are quarantined here; overlays and
# ambient GIFs are motion/UI layers, not full-frame scenery.
_BACKGROUND_EXCLUDED_DIR_MARKERS = (
    "_quarantine_title_cards",
    "quarantine_title_cards",
    "title_cards",
    "prebaked",
    "ambient_gifs",
    "overlays",
)

# Filename / path tokens for baked Spanish title-card chrome (never index as bg).
_BACKGROUND_EXCLUDED_NAME_TOKENS = (
    "bitácora",
    "bitacora",
    "advertencia",
)

_BACKGROUND_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".mp4", ".webm")  # no .gif
_BACKGROUND_MOTION_EXTS = (".mp4", ".webm")


def _path_has_excluded_background_marker(file_path: str) -> bool:
    """True if path sits under a folder that is not eligible as video background."""
    parts = {p.lower() for p in Path(file_path).parts}
    return any(marker.lower() in parts for marker in _BACKGROUND_EXCLUDED_DIR_MARKERS)


def _path_has_excluded_name_token(file_path: str) -> bool:
    """True if filename stem contains baked title-card tokens (BITÁCORA / ADVERTENCIA)."""
    # Basename only — full paths may include unrelated parent dirs (e.g. pytest node names).
    stem = Path(file_path).stem.lower()
    name = Path(file_path).name.lower()
    hay = f"{stem} {name}"
    return any(tok in hay for tok in _BACKGROUND_EXCLUDED_NAME_TOKENS)


def is_eligible_background_asset(file_path: str) -> bool:
    """Return True if file may be indexed / selected as a video background."""
    if not file_path:
        return False
    ext = os.path.splitext(file_path)[1].lower()
    if ext not in _BACKGROUND_IMAGE_EXTS:
        return False
    if _path_has_excluded_background_marker(file_path):
        return False
    if _path_has_excluded_name_token(file_path):
        return False
    return True


def _prefer_motion_background(pool: List[str]) -> List[str]:
    """Prefer motion loops over stills when selecting video backgrounds."""
    motion = [p for p in pool if os.path.splitext(p)[1].lower() in _BACKGROUND_MOTION_EXTS]
    return motion or pool


LIBRARY_DIR = os.path.join(BASE_DIR, "assets", "library")


class AssetManager:
    """Manages video composition media assets with category matching and rotation."""

    def __init__(self, root_dir: Optional[str] = None):
        self.root_dir = root_dir or os.path.join(BASE_DIR, "assets")
        self.library_dir = os.path.join(self.root_dir, "library")
        self._index: Dict[str, Dict[str, List[str]]] = {
            "backgrounds": {},
            "music": {},
            "ambient": {}
        }
        self.refresh_index()

    def refresh_index(self):
        """Scans asset directories (worksets, templates, visual_bank, library) and builds in-memory catalog index."""
        self._index = {"backgrounds": {}, "music": {}, "ambient": {}}

        def _add_media(category: str, file_path: str):
            ext = os.path.splitext(file_path)[1].lower()
            if ext in _BACKGROUND_IMAGE_EXTS:
                if is_eligible_background_asset(file_path):
                    self._index["backgrounds"].setdefault(category, []).append(file_path)
            elif ext in (".mp3", ".wav", ".ogg", ".m4a", ".flac"):
                fp_lower = file_path.lower()
                if "ambient" in fp_lower:
                    self._index["ambient"].setdefault(category, []).append(file_path)
                elif "music" in fp_lower or "bgm" in fp_lower or "track" in fp_lower:
                    self._index["music"].setdefault(category, []).append(file_path)
                else:
                    self._index["music"].setdefault(category, []).append(file_path)
                    self._index["ambient"].setdefault(category, []).append(file_path)

        # 1. Scan data/worksets/ directory (canonical & category worksets)
        if self.root_dir != os.path.join(BASE_DIR, "assets"):
            worksets_dir = os.path.join(self.root_dir, "worksets")
            if not os.path.exists(worksets_dir):
                worksets_dir = os.path.join(self.root_dir, "data", "worksets")
        else:
            worksets_dir = os.path.join(BASE_DIR, "data", "worksets")
        if os.path.exists(worksets_dir):
            for root, _, files in os.walk(worksets_dir):
                rel = os.path.relpath(root, worksets_dir)
                category = rel.split(os.sep)[0].lower() if rel != "." else "worksets"
                for f in files:
                    if not f.startswith("."):
                        full_p = os.path.join(root, f)
                        _add_media(category, full_p)
                        _add_media("worksets", full_p)
                        _add_media("default", full_p)

        # 2. Scan assets/templates/ directory
        templates_dir = os.path.join(self.root_dir, "templates")
        if os.path.exists(templates_dir):
            for root, _, files in os.walk(templates_dir):
                rel = os.path.relpath(root, templates_dir)
                category = rel.split(os.sep)[0].lower() if rel != "." else "templates"
                for f in files:
                    if not f.startswith("."):
                        full_p = os.path.join(root, f)
                        _add_media(category, full_p)
                        _add_media("templates", full_p)
                        _add_media("default", full_p)

        # 3. Scan assets/visual_bank/ directory
        visual_bank_dir = os.path.join(self.root_dir, "visual_bank")
        if os.path.exists(visual_bank_dir):
            for root, _, files in os.walk(visual_bank_dir):
                rel = os.path.relpath(root, visual_bank_dir)
                parts = [p.lower() for p in rel.split(os.sep) if p != "."]
                categories = parts + ["visual_bank", "horror", "default"]
                for f in files:
                    if not f.startswith("."):
                        full_p = os.path.join(root, f)
                        for cat in categories:
                            _add_media(cat, full_p)
                        if len(parts) >= 2:
                            _add_media(f"{parts[0]}_{parts[1]}", full_p)

        # 4. Scan legacy folders for fallback compatibility
        bg_dir = os.path.join(self.root_dir, "backgrounds")
        if os.path.exists(bg_dir):
            bgs = [os.path.join(bg_dir, f) for f in os.listdir(bg_dir) if f.lower().endswith((".jpg", ".jpeg", ".png", ".mp4"))]
            if bgs:
                self._index["backgrounds"].setdefault("horror", []).extend(bgs)
                self._index["backgrounds"].setdefault("default", []).extend(bgs)

        music_dir = os.path.join(self.root_dir, "music")
        if os.path.exists(music_dir):
            tracks = [os.path.join(music_dir, f) for f in os.listdir(music_dir) if f.lower().endswith((".mp3", ".wav", ".ogg"))]
            if tracks:
                self._index["music"].setdefault("horror", []).extend(tracks)
                self._index["music"].setdefault("default", []).extend(tracks)

        music_aita_dir = os.path.join(self.root_dir, "music_aita")
        if os.path.exists(music_aita_dir):
            aita_tracks = [os.path.join(music_aita_dir, f) for f in os.listdir(music_aita_dir) if f.lower().endswith((".mp3", ".wav", ".ogg"))]
            if aita_tracks:
                self._index["music"].setdefault("aita", []).extend(aita_tracks)

        def_bg = os.path.join(self.root_dir, "background.jpg")
        if os.path.exists(def_bg):
            self._index["backgrounds"].setdefault("default", []).append(def_bg)

        # 5. Scan structured library_dir if exists
        if os.path.exists(self.library_dir):
            for asset_type in ("backgrounds", "music", "ambient"):
                type_path = os.path.join(self.library_dir, asset_type)
                if not os.path.exists(type_path):
                    continue
                try:
                    categories = os.listdir(type_path)
                except OSError:
                    continue
                for category in categories:
                    cat_path = os.path.join(type_path, category)
                    if os.path.isdir(cat_path):
                        try:
                            files = [
                                os.path.join(cat_path, f)
                                for f in os.listdir(cat_path)
                                if not f.startswith(".")
                            ]
                            if files:
                                for file_p in files:
                                    _add_media(category.lower(), file_p)
                        except OSError:
                            pass

        logger.debug(f"AssetManager indexed: {sum(len(v) for v in self._index['backgrounds'].values())} backgrounds, "
                     f"{sum(len(v) for v in self._index['music'].values())} music tracks, "
                     f"{sum(len(v) for v in self._index['ambient'].values())} ambient tracks.")

    def get_background(self, category: str = "horror", style: str = "creepypasta") -> str:
        """Retrieve a single background image or video path matching category/style."""
        cat_key = category.lower()
        style_key = style.lower()

        raw_pool = (
            self._index["backgrounds"].get(cat_key)
            or self._index["backgrounds"].get(style_key)
            or self._index["backgrounds"].get("default")
            or self._index["backgrounds"].get("horror")
        )
        pool = [p for p in (raw_pool or []) if is_eligible_background_asset(p)]
        pool = _prefer_motion_background(pool)

        if pool:
            return random.choice(pool)

        if os.path.exists(DEFAULT_BACKGROUND):
            return DEFAULT_BACKGROUND

        return ""

    def _generate_procedural_scene_background(self, index: int, category: str = "horror") -> str:
        """Returns real local template/default background image path for scene index fallback."""
        template_bg = os.path.join(self.root_dir, "templates", "horror_shorts", "background.jpg")
        if os.path.exists(template_bg):
            return template_bg
        if os.path.exists(DEFAULT_BACKGROUND):
            return DEFAULT_BACKGROUND
        return ""

    def get_background_sequence(self, category: str = "horror", style: str = "creepypasta", count: int = 3) -> List[str]:
        """Retrieve a sequence of distinct background images/videos for multi-scene rendering."""
        cat_key = category.lower()
        style_key = style.lower()

        raw_pool = (
            self._index["backgrounds"].get(cat_key)
            or self._index["backgrounds"].get(style_key)
            or self._index["backgrounds"].get("default")
            or self._index["backgrounds"].get("horror")
            or []
        )
        pool = [p for p in raw_pool if is_eligible_background_asset(p)]
        pool = _prefer_motion_background(pool)

        # Deduplicate pool while preserving order
        unique_pool = list(dict.fromkeys(pool))

        if len(unique_pool) >= count:
            return random.sample(unique_pool, count)

        res = []
        for i in range(count):
            if i < len(unique_pool):
                res.append(unique_pool[i])
            else:
                proc = self._generate_procedural_scene_background(i, category=category)
                if proc:
                    res.append(proc)
                elif unique_pool:
                    res.append(unique_pool[i % len(unique_pool)])
                else:
                    single = self.get_background(category=category, style=style)
                    res.append(single)

        return res

    def get_music(self, category: str = "horror", style: str = "creepypasta") -> str:
        """Retrieve background music track for specified category/style."""
        cat_key = category.lower()
        style_key = style.lower()
        is_drama = cat_key in ("drama", "aita", "soy_el_malo", "yo_soy_el_malo")

        if is_drama:
            pool = (
                self._index["music"].get(cat_key)
                or self._index["music"].get(style_key)
                or self._index["music"].get("drama")
                or []
            )
        else:
            pool = (
                self._index["music"].get(cat_key)
                or self._index["music"].get(style_key)
                or self._index["music"].get("horror")
                or self._index["music"].get("default")
                or []
            )

        if pool:
            return random.choice(pool)
        return ""

    def get_ambient(self, category: str = "horror", style: str = "creepypasta") -> str:
        """Retrieve ambient background track for specified category/style."""
        cat_key = category.lower()
        style_key = style.lower()
        is_drama = cat_key in ("drama", "aita", "soy_el_malo", "yo_soy_el_malo")

        if is_drama:
            pool = (
                self._index["ambient"].get(cat_key)
                or self._index["ambient"].get(style_key)
                or self._index["ambient"].get("drama")
                or []
            )
            if pool:
                return random.choice(pool)
            fallback_pool = (
                self._index["music"].get(cat_key)
                or self._index["music"].get(style_key)
                or self._index["music"].get("drama")
                or []
            )
        else:
            pool = (
                self._index["ambient"].get(cat_key)
                or self._index["ambient"].get(style_key)
                or self._index["ambient"].get("horror")
                or self._index["ambient"].get("default")
                or []
            )
            if pool:
                return random.choice(pool)
            fallback_pool = (
                self._index["music"].get(cat_key)
                or self._index["music"].get(style_key)
                or self._index["music"].get("horror")
                or self._index["music"].get("default")
                or []
            )

        if fallback_pool:
            return fallback_pool[0]

        return ""

    def resolve_or_create_background_audio(
        self,
        category: str = "horror",
        style: str = "creepypasta",
        duration_sec: float = 30.0,
        work_dir: Optional[Union[str, os.PathLike]] = None,
        mode: str = "auto",
        seed: Optional[int] = None,
    ) -> str:
        """
        Resolves background audio track by choosing from local catalog or synthesizing procedurally.
        - mode 'auto': searches asset bank, falls back to procedural generation if missing.
        - mode 'choose': searches asset bank only.
        - mode 'create': directly synthesizes procedural ambient audio.
        - mode 'off': returns empty string (no background audio).
        """
        mode_clean = str(mode or "auto").lower().strip()
        if mode_clean in ("off", "none", "disabled", "false", "0"):
            return ""

        if mode_clean in ("auto", "choose"):
            track = self.get_music(category=category, style=style) or self.get_ambient(category=category, style=style)
            if track and os.path.exists(track) and os.path.getsize(track) > 0:
                return str(track)
            if mode_clean == "choose":
                return ""

        # Procedural synthesis fallback / mode 'create'
        from src.media.procedural_audio import get_procedural_audio_engine
        engine = get_procedural_audio_engine()

        theme_tag = category or style or "default"
        if work_dir and os.path.exists(work_dir):
            out_path = Path(work_dir) / f"procedural_ambient_{theme_tag}.wav"
        else:
            out_dir = Path(self.root_dir) / "music"
            out_dir.mkdir(parents=True, exist_ok=True)
            out_path = out_dir / f"procedural_ambient_{theme_tag}.wav"

        try:
            res_path = engine.generate_ambient_track(
                output_path=out_path,
                theme=theme_tag,
                duration_sec=min(60.0, max(1.0, duration_sec)),
                seed=seed,
            )
            return str(res_path)
        except Exception as exc:
            logger.warning("Procedural audio generation failed: %s; returning empty background track", exc)
            return ""


# Global singleton instance
_default_asset_manager = AssetManager()


def get_asset_manager() -> AssetManager:
    return _default_asset_manager



