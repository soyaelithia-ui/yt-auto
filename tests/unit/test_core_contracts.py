"""Unit tests verifying Phase 3 strict typing and data contracts."""

import os
import sqlite3
from collections.abc import Mapping
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from review.domain import ReviewJob, ReviewStatus
from src.core.contracts import (
    ClaimedLeaseContext,
    PipelineContext,
    RenderSpec,
    ReviewContract,
    RunContext,
    StoryRecord,
)
from src.core.profiling import PipelineProfiler
from src.core.repository import QueueRepository


class TestStoryRecordContract:
    def test_slots_and_mapping(self):
        assert hasattr(StoryRecord, "__slots__")
        record = StoryRecord.from_dict({
            "id": "story_001",
            "channel": "moku",
            "title": "La Criatura del Bosque",
            "content": "Relato escalofriante...",
            "score": 95.5,
            "custom_field": "test_value",
        })
        assert isinstance(record, Mapping)
        assert record.story_id == "story_001"
        assert record.id == "story_001"
        assert record.content == "Relato escalofriante..."
        assert record["channel"] == "moku"
        assert record.get("score") == 95.5
        assert "custom_field" in record
        assert record["custom_field"] == "test_value"
        assert record.custom_field == "test_value"

    def test_dict_conversion_and_unpacking(self):
        record = StoryRecord(
            story_id="s_123",
            channel="aelithia",
            title="Drama Familiar",
            raw_content="Historia de drama",
            score=88.0,
        )
        as_dict = dict(record)
        assert as_dict["story_id"] == "s_123"
        assert as_dict["id"] == "s_123"
        assert as_dict["content"] == "Historia de drama"
        unpacked = {**record}
        assert unpacked["title"] == "Drama Familiar"

    def test_from_sqlite_row(self, tmp_path):
        db_path = str(tmp_path / "test.db")
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "CREATE TABLE stories (story_id TEXT, channel TEXT, title TEXT, raw_content TEXT, score REAL)"
            )
            conn.execute(
                "INSERT INTO stories VALUES ('s_sql', 'scifi', 'Nave Perdida', 'Contenido scifi', 77.5)"
            )
            row = conn.execute("SELECT * FROM stories LIMIT 1").fetchone()
            record = StoryRecord.from_row(row)
            assert record.story_id == "s_sql"
            assert record.channel == "scifi"
            assert record.title == "Nave Perdida"
            assert record.raw_content == "Contenido scifi"
            assert record.score == 77.5

    def test_subscript_assignment(self):
        record = StoryRecord.from_dict({"id": "s_mod", "channel": "moku", "title": "Init Title"})
        record["title"] = "Updated Title"
        assert record.title == "Updated Title"
        assert record["title"] == "Updated Title"
        record["dynamic_attr"] = 42
        assert record["dynamic_attr"] == 42
        assert record.dynamic_attr == 42

    def test_bidirectional_property_alias_mutation(self):
        s = StoryRecord(story_id="s1", channel="moku", title="Title", raw_content="Initial")
        s["content"] = "Mutated via subscript"
        assert s.content == "Mutated via subscript"
        assert s.raw_content == "Mutated via subscript"
        assert s["content"] == "Mutated via subscript"

        s.content = "Mutated via attr"
        assert s.content == "Mutated via attr"
        assert s.raw_content == "Mutated via attr"
        assert s["content"] == "Mutated via attr"

        s["id"] = "s2"
        assert s.id == "s2"
        assert s.story_id == "s2"
        assert s["id"] == "s2"

        s.id = "s3"
        assert s.id == "s3"
        assert s.story_id == "s3"
        assert s["id"] == "s3"

    def test_from_dict_pops_both_primary_and_alias_keys(self):
        d = {"story_id": "orig_id", "id": "orig_id", "raw_content": "orig_text", "content": "orig_text"}
        s = StoryRecord.from_dict(d)
        assert "id" not in s._extra
        assert "content" not in s._extra
        s.raw_content = "UPDATED"
        assert s.to_dict()["content"] == "UPDATED"
        assert s.to_dict()["raw_content"] == "UPDATED"

    def test_robust_numeric_and_empty_string_conversion(self):
        s = StoryRecord.from_dict({"story_id": "1", "score": "", "next_attempt_at": "", "attempt_count": "invalid"})
        assert s.score == 0.0
        assert s.next_attempt_at is None
        assert s.attempt_count == 0

    def test_mapping_protocol_compliance(self):
        s = StoryRecord(story_id="s1", channel="moku", title="Title")
        assert ("to_dict" in s) is False
        assert ("get" in s) is False
        assert ("keys" in s) is False
        assert s.get("last_error", "FALLBACK") is None
        assert s.get("missing_key", "FALLBACK") == "FALLBACK"
        with pytest.raises(KeyError):
            _ = s["to_dict"]


class TestRenderSpecContract:
    def test_slots_and_validation(self):
        assert hasattr(RenderSpec, "__slots__")
        spec = RenderSpec(
            duration_sec=25.0,
            orientation="vertical",
            threads=2,
            crf=21,
            preset="fast",
        )
        assert isinstance(spec, Mapping)
        spec.validate()

    def test_validation_failure_on_guardrail_breach(self):
        spec_negative_dur = RenderSpec(duration_sec=-5.0)
        with pytest.raises(ValueError, match="cannot be negative"):
            spec_negative_dur.validate()

        spec_excessive_threads = RenderSpec(threads=6)
        with pytest.raises(ValueError, match="cannot exceed 4"):
            spec_excessive_threads.validate()

        spec_bad_orientation = RenderSpec(orientation="diagonal")
        with pytest.raises(ValueError, match="orientation must be vertical or horizontal"):
            spec_bad_orientation.validate()

    def test_video_path_alias_mutation(self):
        spec = RenderSpec(output_video_path=Path("/tmp/vid1.mp4"))
        assert spec.video_path == Path("/tmp/vid1.mp4")
        assert spec["video_path"] == Path("/tmp/vid1.mp4")

        spec["video_path"] = Path("/tmp/vid2.mp4")
        assert spec.video_path == Path("/tmp/vid2.mp4")
        assert spec.output_video_path == Path("/tmp/vid2.mp4")

        spec.video_path = Path("/tmp/vid3.mp4")
        assert spec.video_path == Path("/tmp/vid3.mp4")
        assert spec.output_video_path == Path("/tmp/vid3.mp4")

    def test_from_dict_pops_video_path_alias(self):
        spec = RenderSpec.from_dict({"output_video_path": "/tmp/a.mp4", "video_path": "/tmp/a.mp4"})
        assert "video_path" not in spec._extra

    def test_from_pipeline_context(self, tmp_path):
        lane_mock = MagicMock()
        lane_mock.orientation = "horizontal"
        lane_mock.id = "long-documentary"
        lane_mock.duration_min_sec = 600
        lane_mock.fps = 60
        lane_mock.expected_resolution = (1920, 1080)
        lane_mock.visual_pipeline = "director"

        ctx = MagicMock()
        ctx.audio = {"duration_sec": 45.2}
        ctx.lane = lane_mock
        ctx.manifest_payload = {"scenes": [{"director_role": "establishing"}, {"director_role": "action"}]}
        ctx.mux_subtitles = True
        dummy_sub = tmp_path / "subs.ass"
        dummy_sub.write_text("[Script Info]", encoding="utf-8")
        ctx.ass_path = dummy_sub
        ctx.video_path = tmp_path / "out.mp4"
        ctx.audio_path = tmp_path / "audio.mp3"
        ctx.manifest_path = tmp_path / "manifest.json"
        ctx.resolved_loop_path = "/assets/loop.mp4"
        ctx.music_track_path = "/assets/music.mp3"
        ctx.bg_volume = 0.05
        ctx.target_category = "space"
        ctx.stream_copy_mode = False
        ctx.scene_bg_list = ["img1.jpg", "img2.jpg"]
        ctx.shot_durations = [10.0, 35.2]
        ctx.is_long_lane = True

        spec = RenderSpec.from_pipeline_context(ctx)
        assert spec.duration_sec == 45.2
        assert spec.orientation == "horizontal"
        assert spec.shot_roles == ["establishing", "action"]
        assert spec.threads == 4  # Long lane gets 4 threads budget
        assert spec.subtitle_path == dummy_sub
        assert spec.fps == 60
        assert spec.width == 1920
        assert spec.height == 1080
        spec.validate()

    def test_mapping_protocol_compliance(self):
        spec = RenderSpec(duration_sec=10.0)
        assert ("validate" in spec) is False
        assert ("to_dict" in spec) is False
        assert spec.get("background_path", "FALLBACK") is None
        assert spec.get("missing", "FALLBACK") == "FALLBACK"


class TestReviewContract:
    def test_slots_and_validation(self):
        assert hasattr(ReviewContract, "__slots__")
        rc = ReviewContract(job_id="job_001", channel="moku", title="Video Review Title")
        assert isinstance(rc, Mapping)
        rc.validate()
        assert rc.is_pending is True
        assert rc.is_approved is False

    def test_validation_errors(self):
        with pytest.raises(ValueError, match="job_id cannot be empty"):
            ReviewContract(job_id="", channel="moku", title="T").validate()

        with pytest.raises(ValueError, match="channel cannot be empty"):
            ReviewContract(job_id="j1", channel="", title="T").validate()

        with pytest.raises(ValueError, match="title cannot be empty"):
            ReviewContract(job_id="j1", channel="moku", title="").validate()

    def test_from_review_job_conversion(self):
        job = ReviewJob(
            job_id="rev_100",
            channel="aelithia",
            title="AITA Story Video",
            original_video_path="/tmp/video.mp4",
            status=ReviewStatus.APPROVED.value,
        )
        contract = ReviewContract.from_job(job)
        assert contract.job_id == "rev_100"
        assert contract.channel == "aelithia"
        assert contract.video_path == "/tmp/video.mp4"
        assert contract.is_approved is True
        kwargs = contract.to_job_kwargs()
        assert kwargs["job_id"] == "rev_100"
        assert kwargs["status"] == ReviewStatus.APPROVED.value

    def test_alias_mutations_and_from_dict_cleanup(self):
        rc = ReviewContract.from_dict({
            "job_id": "j1",
            "id": "j1",
            "original_video_path": "/v1.mp4",
            "video_path": "/v1.mp4",
        })
        assert "id" not in rc._extra
        assert "video_path" not in rc._extra

        rc["video_path"] = "/v2.mp4"
        assert rc.video_path == "/v2.mp4"
        assert rc.original_video_path == "/v2.mp4"

        rc["id"] = "j2"
        assert rc.id == "j2"
        assert rc.job_id == "j2"

    def test_mapping_protocol_compliance(self):
        rc = ReviewContract(job_id="j1", channel="moku", title="Title")
        assert ("validate" in rc) is False
        assert ("to_dict" in rc) is False
        assert rc.get("delivery_error", "FALLBACK") is None
        assert rc.get("missing", "FALLBACK") == "FALLBACK"


class TestPipelineContextContract:
    def test_slots_and_aliases(self, tmp_path):
        assert hasattr(PipelineContext, "__slots__")
        assert hasattr(ClaimedLeaseContext, "__slots__")
        assert RunContext is PipelineContext

        story_rec = StoryRecord(story_id="s_ctx", channel="moku", title="Ctx Title", raw_content="Contenido")
        repo = MagicMock(spec=QueueRepository)
        profiler = PipelineProfiler("run_1")

        ctx = PipelineContext(
            story=story_rec,
            story_id="s_ctx",
            run_id="run_1",
            channel_name="moku",
            channel_key="moku",
            lane=MagicMock(duration_min_sec=400, orientation="horizontal"),
            repository=repo,
            database=":memory:",
            owner="worker_1",
            lease_seconds=300,
            settings=MagicMock(),
            branding=MagicMock(),
            profiler=profiler,
            directed=False,
            generate_only=False,
            engine_mode="loop",
            is_loop_mode=True,
            is_multiscene_mode=False,
            subtitles_active=True,
            work_dir=tmp_path,
            audio_path=tmp_path / "audio.mp3",
            ass_path=tmp_path / "subs.ass",
            srt_path=tmp_path / "subs.srt",
            video_path=tmp_path / "video.mp4",
            thumbnail_path=tmp_path / "thumb.jpg",
            script_path=tmp_path / "script.txt",
            visual_plan_path=tmp_path / "plan.json",
            metadata_path=tmp_path / "meta.json",
            scene_manifest_path=tmp_path / "manifest.json",
        )
        assert isinstance(ctx, Mapping)
        assert ctx.is_long_lane is True
        assert ctx["story_id"] == "s_ctx"
        assert ctx.get("channel_name") == "moku"

        # Mapping keys coverage
        assert "audio_path" in ctx
        assert "script" in ctx
        assert ("heartbeat" in ctx) is False
        assert ("require_heartbeat" in ctx) is False
        assert ctx.get("script", "FALLBACK") == ""
        assert ctx.get("missing_key", "FALLBACK") == "FALLBACK"
        assert "audio_path" in list(ctx.keys())
        assert len(ctx) >= 60

        # Dynamic attribute assignment via _extra
        ctx["runtime_flag"] = True
        assert ctx["runtime_flag"] is True
        assert ctx.runtime_flag is True

        # Serialization to dict
        summary = ctx.to_dict()
        assert summary["story_id"] == "s_ctx"
        assert summary["channel_name"] == "moku"
        assert summary["is_long_lane"] is True
        assert summary["runtime_flag"] is True


class TestContractsSubsystemIntegration:
    def test_repository_get_story_record(self, tmp_path):
        db_path = str(tmp_path / "queue_test.db")
        repo = QueueRepository(db_path)
        repo.initialize()
        repo.enqueue("story_repo_test", "Repo Title", "Repo Content", "https://reddit.com/r/test/1", channel="moku")

        record = repo.get_story_record("story_repo_test")
        assert record is not None
        assert isinstance(record, StoryRecord)
        assert record.story_id == "story_repo_test"
        assert record.title == "Repo Title"
        assert record.channel in ("moku", "horror")

    def test_mcp_manage_queue_uses_story_record(self, tmp_path):
        import asyncio
        from src.mcp.server import create_mcp_server

        db_path = str(tmp_path / "mcp_test.db")
        repo = QueueRepository(db_path)
        repo.initialize()
        repo.enqueue("mcp_s1", "MCP Story Title", "MCP Content", "https://reddit.com/r/test/2", channel="moku")

        server = create_mcp_server()
        result = asyncio.run(
            server.call_tool("manage_queue", {"action": "list", "db_path": db_path})
        )
        import json
        text = result.content[0].text if hasattr(result, "content") else result[0].text
        payload = json.loads(text)
        assert payload["ok"] is True
        assert payload["count"] == 1
        assert payload["items"][0]["story_id"] == "mcp_s1"
        assert payload["items"][0]["title"] == "MCP Story Title"

    def test_mcp_get_lane_info_includes_render_spec(self):
        import asyncio
        from src.mcp.server import create_mcp_server

        server = create_mcp_server()
        result = asyncio.run(server.call_tool("get_lane_info", {"lane_id": "moku-scp-shorts"}))
        import json
        text = result.content[0].text if hasattr(result, "content") else result[0].text
        payload = json.loads(text)
        assert "render_spec" in payload
        assert payload["render_spec"]["orientation"] == "vertical"
        assert payload["render_spec"]["width"] == 1080
        assert payload["render_spec"]["height"] == 1920
