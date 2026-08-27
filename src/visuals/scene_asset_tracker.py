"""Scene asset tracker for extracting and persisting storyboard/scene manifest asset lineage."""
import json
from pathlib import Path
from typing import Any, Optional


class SceneAssetTracker:
    """Extracts and records scene asset metadata into repository storage."""

    def __init__(self, repository: Optional[Any] = None, db_path: Optional[str] = None):
        self.repository = repository
        self.db_path = db_path

    def extract_and_record(self, run_id: str, story_id: str, manifest_path: Any) -> int:
        """Extract scene asset lineage from manifest and record in repository."""
        manifest_data = None
        if isinstance(manifest_path, (str, Path)):
            p = Path(manifest_path)
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    manifest_data = json.load(f)
        elif isinstance(manifest_path, dict):
            manifest_data = manifest_path

        if not manifest_data or "scenes" not in manifest_data:
            return 0

        scenes = manifest_data.get("scenes", [])
        scene_assets = []
        for idx, scene in enumerate(scenes):
            asset_dict = {
                "scene_index": scene.get("scene_index", idx),
                "shot_index": scene.get("shot_index", 0),
                "asset_source": scene.get("asset_source", "local_bank"),
                "source_url_or_path": scene.get("source_url_or_path") or scene.get("image_path", ""),
                "framing_type": scene.get("framing_type", "WIDE_ESTABLISHING"),
                "prompt_used": scene.get("prompt_used") or scene.get("prompt"),
                "dhash": scene.get("dhash"),
                "duration_sec": float(scene.get("duration_sec", 0.0)),
            }
            scene_assets.append(asset_dict)

        if self.repository is not None and hasattr(self.repository, "record_scene_assets"):
            return self.repository.record_scene_assets(
                run_id=run_id,
                story_id=story_id,
                scene_assets=scene_assets,
            )
        return len(scene_assets)


__all__ = ["SceneAssetTracker"]
