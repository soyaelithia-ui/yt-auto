"""Visual provenance and tracking module.

Video generation uses ``LoopVideoEngine`` and the SQLite-backed ``LoopCatalogRepository``
with pre-rendered video loops and FFmpeg stream-copy composition.
"""
from src.visuals.scene_asset_tracker import SceneAssetTracker

__all__ = ["SceneAssetTracker"]
