"""Visual provenance and tracking module.

Video generation uses ``LoopVideoEngine`` and the SQLite-backed ``LoopCatalogRepository``
with web-based procedural generation (Three.js, Canvas, WebGL, CSS).
"""
from src.visuals.scene_asset_tracker import SceneAssetTracker

__all__ = ["SceneAssetTracker"]
