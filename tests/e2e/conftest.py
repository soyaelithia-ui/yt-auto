"""Fixtures for End-to-End (E2E) tests."""
from __future__ import annotations

import json
import os
from pathlib import Path
import pytest

from lib.qa_gatekeeper import QAGatekeeper, ffprobe


@pytest.fixture
def temp_e2e_workspace(tmp_path: Path) -> Path:
    """Fixture creating isolated temporary directory for test output artifacts."""
    workspace = tmp_path / "e2e_workspace"
    workspace.mkdir(parents=True, exist_ok=True)
    return workspace


@pytest.fixture
def e2e_workset() -> dict:
    """Fixture that loads canonical workset story (e.g. data/worksets/canonical/MOKU-STORY-001)."""
    project_root = Path(__file__).resolve().parents[2]
    canonical_dir = project_root / "data" / "worksets" / "canonical" / "MOKU-STORY-001"
    story_json = canonical_dir / "story.json"

    if story_json.exists():
        with open(story_json, "r", encoding="utf-8") as f:
            data = json.load(f)
            data["workset_dir"] = str(canonical_dir)
            return data

    return {
        "id": "MOKU-STORY-001",
        "title": "El misterio de la frecuencia de medianoche",
        "content": "A las tres de la madrugada, la radio del viejo camión comenzó a emitir una frecuencia desconocida.",
        "url": "https://www.reddit.com/r/nosleep/comments/moku001",
        "workset_dir": str(canonical_dir),
    }


class E2EVideoVerifier:
    """Probes and audits generated MP4 videos using ffprobe and the QAGatekeeper.

    The legacy per-scene ``VisualIntegrityVerifier`` has been removed: the
    active pipeline renders a continuous loop and its visual gate is the
    loop-level ``validate_prepublication`` in ``src.core.quality``.
    """

    def __init__(self, strict_mode: bool = False):
        self.qa_gatekeeper = QAGatekeeper(strict_mode=strict_mode)

    def probe(self, video_path: str | Path) -> dict:
        """Probes video using ffprobe."""
        return ffprobe(str(video_path))

    def verify_video(
        self,
        video_path: str | Path,
        expected_resolution: tuple[int, int] = (1080, 1920),
        allow_dark_scene: bool = False,
        channel: str = "moku",
        subtitle_path: str | None = None,
    ) -> dict:
        """Probes generated MP4 video verifying dimensions, audio, LUFS, subtitles, no freezes."""
        path_str = str(video_path)
        if not os.path.exists(path_str):
            return {
                "passed": False,
                "errors": [f"File does not exist: {path_str}"],
                "error": f"File does not exist: {path_str}",
            }

        try:
            probe_data = self.probe(path_str)
        except Exception as e:
            return {
                "passed": False,
                "errors": [f"Probing failed: {e}"],
                "error": str(e),
                "ffprobe": {},
                "qa_report": None,
                "dimensions": None,
                "audio_codec": None,
            }

        streams = probe_data.get("streams", [])
        v_stream = next((s for s in streams if s.get("codec_type") == "video"), None)
        a_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)

        errors = []

        if v_stream:
            width = int(v_stream.get("width", 0))
            height = int(v_stream.get("height", 0))
            exp_w, exp_h = expected_resolution
            if (width, height) != (exp_w, exp_h):
                errors.append(f"Dimension mismatch: expected {exp_w}x{exp_h}, got {width}x{height}")
        else:
            errors.append("No video stream found")

        if a_stream:
            audio_codec = a_stream.get("codec_name", "").lower()
            if audio_codec != "aac":
                errors.append(f"Audio codec mismatch: expected aac, got {audio_codec}")
        else:
            errors.append("No audio stream found")

        try:
            qa_report = self.qa_gatekeeper.audit_video(
                video_path=path_str,
                channel=channel,
                subtitle_path=subtitle_path,
            )
        except Exception as e:
            errors.append(f"QAGatekeeper audit failed: {e}")
            qa_report = None

        qa_passed = qa_report.passed if qa_report is not None else False

        passed = (len(errors) == 0) and qa_passed

        res = {
            "passed": passed,
            "errors": errors,
            "ffprobe": probe_data,
            "qa_report": qa_report,
            "dimensions": (int(v_stream.get("width", 0)), int(v_stream.get("height", 0))) if v_stream else None,
            "audio_codec": a_stream.get("codec_name") if a_stream else None,
        }
        if not passed and errors:
            res["error"] = errors[0]

        return res


@pytest.fixture
def e2e_video_verifier() -> E2EVideoVerifier:
    """Fixture providing E2EVideoVerifier instance."""
    return E2EVideoVerifier()
