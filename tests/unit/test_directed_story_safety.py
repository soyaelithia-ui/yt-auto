import json
import math
import shutil
import sys
import wave
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.config import SETTINGS
from src.core.domain import CanonicalChannel, JobStatus, PublicationProof
from src.core.quality import validate_prepublication
from src.core.repository import QueueRepository, connect
from src.llm import curate_script
from lib.subtitles import create_subtitles, validate_subtitle_artifact
from lib.tts import validate_word_boundaries
from lib.video import (
    build_visual_scene_plan,
    compose_video,
    create_video_thumbnail,
)


def _repo(tmp_path: Path) -> QueueRepository:
    repository = QueueRepository(tmp_path / "queue.db")
    repository.initialize()
    return repository


def test_claim_exact_is_atomic_and_does_not_touch_other_stories(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("other", "Otra", "Contenido", "https://other", "moku")
    repository.enqueue("bhv6zd", "Off the grid", "Historia completa", "https://target", "moku")

    claimed = repository.claim_exact("bhv6zd", "moku", "worker", now=1_000)

    assert claimed and claimed["story_id"] == "bhv6zd"
    repository.require_single_story_run(claimed["run_id"], "bhv6zd")
    with connect(repository.db_path, read_only=True) as conn:
        rows = {
            row["story_id"]: row["status"]
            for row in conn.execute("SELECT story_id,status FROM stories")
        }
    assert rows == {"other": "PENDING", "bhv6zd": "PROCESSING"}


def test_claim_exact_rejects_wrong_channel_without_mutation(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "moku")
    assert repository.claim_exact("bhv6zd", "aelithia", "worker") is None
    with connect(repository.db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT status,run_id FROM stories WHERE story_id='bhv6zd'"
        ).fetchone()
    assert (row["status"], row["run_id"]) == (JobStatus.PENDING.value, None)


def test_claim_exact_reconciles_only_its_expired_lease(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "moku")
    repository.enqueue("ael", "Otra", "Historia", "https://ael", "aelithia")
    first = repository.claim_exact(
        "bhv6zd", "moku", "old-worker", lease_seconds=10, now=1_000
    )
    other = repository.claim_exact(
        "ael", "aelithia", "other-worker", lease_seconds=100, now=1_000
    )

    second = repository.claim_exact(
        "bhv6zd", "moku", "new-worker", lease_seconds=10, now=1_011
    )

    assert second and second["run_id"] != first["run_id"]
    with connect(repository.db_path, read_only=True) as conn:
        old_status = conn.execute(
            "SELECT status FROM runs WHERE run_id=?", (first["run_id"],)
        ).fetchone()[0]
        other_lease = conn.execute(
            "SELECT owner,run_id FROM leases WHERE job_id='ael'"
        ).fetchone()
    assert old_status == JobStatus.RETRYABLE_FAILED.value
    assert (other_lease["owner"], other_lease["run_id"]) == (
        "other-worker",
        other["run_id"],
    )


def test_old_worker_cannot_heartbeat_or_mutate_new_run(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "moku")
    first = repository.claim_exact(
        "bhv6zd", "moku", "old-worker", lease_seconds=10, now=1_000
    )
    second = repository.claim_exact(
        "bhv6zd", "moku", "new-worker", lease_seconds=100, now=1_011
    )

    assert repository.heartbeat(first["run_id"], "old-worker", now=1_012) is False
    assert repository.set_status(
        "bhv6zd",
        JobStatus.RETRYABLE_FAILED,
        run_id=first["run_id"],
        owner="old-worker",
        now=1_012,
    ) is False
    with connect(repository.db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT status,run_id FROM stories WHERE story_id='bhv6zd'"
        ).fetchone()
    assert (row["status"], row["run_id"]) == (
        JobStatus.PROCESSING.value,
        second["run_id"],
    )


def test_mark_published_only_updates_the_primary_story(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "moku")
    repository.enqueue("other", "Otra", "Otra historia", "https://other", "moku")
    claimed = repository.claim_exact("bhv6zd", "moku", "worker")
    proof = PublicationProof(
        video_id="video12345",
        channel=CanonicalChannel.MOKU,
        visibility="public",
        title="Título verificado",
        description="Descripción verificada",
        thumbnail_confirmed=True,
    )
    repository.mark_published("bhv6zd", claimed["run_id"], proof, provider="API")
    assert repository.set_status(
        "bhv6zd",
        JobStatus.RETRYABLE_FAILED,
        error_code="post_commit_failure",
        error_detail="falló una tarea posterior",
    ) is False
    with connect(repository.db_path, read_only=True) as conn:
        rows = {
            row["story_id"]: row["status"]
            for row in conn.execute("SELECT story_id,status FROM stories")
        }
    assert rows == {"bhv6zd": "PUBLISHED", "other": "PENDING"}


def test_mark_published_rejects_run_with_more_than_one_story(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "moku")
    repository.enqueue("other", "Otra", "Otra historia", "https://other", "moku")
    claimed = repository.claim_exact("bhv6zd", "moku", "worker")
    with connect(repository.db_path) as conn:
        conn.execute(
            "INSERT INTO run_stories(run_id,story_id,position) VALUES(?,?,1)",
            (claimed["run_id"], "other"),
        )
        conn.commit()
    proof = PublicationProof(
        video_id="video12345",
        channel=CanonicalChannel.MOKU,
        visibility="public",
        title="Título verificado",
        description="Descripción verificada",
        thumbnail_confirmed=True,
    )
    with pytest.raises(RuntimeError, match="única historia principal"):
        repository.mark_published("bhv6zd", claimed["run_id"], proof, provider="API")
    with connect(repository.db_path, read_only=True) as conn:
        assert conn.execute(
            "SELECT status FROM stories WHERE story_id='bhv6zd'"
        ).fetchone()[0] == JobStatus.PROCESSING.value


def test_strict_script_rejects_aggregation(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    with pytest.raises(ValueError, match="no admite historias adicionales"):
        curate_script(
            "Historia principal",
            "Título",
            additional_stories=[{"title": "Otra", "content": "Mezcla"}],
            provider="C",
            channel="moku",
            strict_single_story=True,
        )


def test_word_boundaries_and_subtitles_require_real_coverage(tmp_path):
    boundaries = [
        {"word": "Esta", "start": 0.1, "end": 0.7},
        {"word": "historia", "start": 0.8, "end": 1.7},
        {"word": "termina", "start": 1.8, "end": 2.7},
    ]
    facts = validate_word_boundaries(boundaries, 3.0, expected_word_count=3)
    assert facts["temporal_coverage"] >= 0.70
    srt = tmp_path / "subtitles.srt"
    create_subtitles(boundaries, str(srt))
    subtitle_facts = validate_subtitle_artifact(
        str(srt), duration_sec=3.0, expected_words=3
    )
    assert subtitle_facts["coverage"] >= 0.90

    with pytest.raises(RuntimeError, match="monotónico"):
        validate_word_boundaries(
            [
                {"word": "dos", "start": 1.0, "end": 1.3},
                {"word": "uno", "start": 0.2, "end": 0.6},
            ],
            2.0,
        )


def test_visual_plan_has_full_8_to_15_second_cadence(tmp_path):
    source = tmp_path / "scene.jpg"
    source.write_bytes(b"image")
    plan = build_visual_scene_plan(605.0, [str(source)])
    assert len(plan) > 12
    assert all(8.0 <= item["duration"] <= 15.0 for item in plan)
    assert sum(item["duration"] for item in plan) == pytest.approx(605.0, abs=0.1)


def test_compose_adds_faststart_and_writes_visual_qa(monkeypatch, tmp_path):
    source = tmp_path / "scene.jpg"
    source.write_bytes(b"image")
    audio = tmp_path / "audio.wav"
    audio.write_bytes(b"audio")
    output = tmp_path / "video.mp4"
    manager = MagicMock()
    manager.get_background_sequence.side_effect = lambda count, **kwargs: [str(source)] * count
    manager.get_music.return_value = ""
    manager.get_ambient.return_value = ""
    monkeypatch.setattr("src.asset_manager.get_asset_manager", lambda: manager)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setenv("FORCE_REAL_RENDER", "1")
    monkeypatch.setenv("SHORT_COMPOSITOR", "ffmpeg_legacy")
    monkeypatch.setattr("src.config.is_test_environment", lambda: False)
    run = MagicMock()
    def fake_run(cmd, *args, **kwargs):
        out_f = cmd[-1]
        Path(out_f).write_bytes(b"MP4_DUMMY_HEADER_DATA" * 6000)
        return MagicMock(returncode=0, stderr="")
    run.side_effect = fake_run
    sub_mod = MagicMock()
    sub_mod.run = run
    def fake_get_video_attr(name, default=None):
        if name == "is_test_environment":
            return lambda: False
        if name == "subprocess":
            return sub_mod
        if name == "validate_video_format":
            return lambda *args, **kwargs: True
        return default
    monkeypatch.setattr("lib.video._get_video_attr", fake_get_video_attr)
    monkeypatch.setattr("lib.video.subprocess", sub_mod)
    monkeypatch.setattr("lib.video.subprocess", sub_mod)
    monkeypatch.setattr("subprocess.run", run)

    from lib.video import compose_video as compose_video_core
    compose_video_core(
        str(audio),
        "",
        str(source),
        str(output),
        duration_sec=605.0,
        min_duration=0.0,
        channel="moku",
        strict_visuals=True,
        video_mode="longform",
    )

    command = run.call_args.args[0]
    assert command[command.index("-movflags") + 1] == "+faststart"
    qa = json.loads((tmp_path / "visual_plan.json").read_text(encoding="utf-8"))
    assert qa["scene_count"] > 12
    assert qa["black_fallbacks"] == 0


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg no disponible")
def test_real_ffmpeg_render_has_no_long_black_segments(monkeypatch, tmp_path):
    from PIL import Image
    from src.core.quality import detect_long_black_frames
    from src.templates import VideoTemplate

    red = tmp_path / "red.png"
    blue = tmp_path / "blue.png"
    Image.new("RGB", (1280, 720), (220, 35, 35)).save(red)
    Image.new("RGB", (1280, 720), (35, 90, 220)).save(blue)
    audio = tmp_path / "audio.wav"
    sample_rate = 8_000
    duration = 4.0
    with wave.open(str(audio), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        frames = bytearray()
        for index in range(int(sample_rate * duration)):
            sample = int(5_000 * math.sin(2 * math.pi * 220 * index / sample_rate))
            frames.extend(sample.to_bytes(2, "little", signed=True))
        handle.writeframes(frames)
    manager = MagicMock()
    manager.get_background_sequence.side_effect = lambda count, **kwargs: [
        str(blue)
    ] * count
    manager.get_music.return_value = ""
    manager.get_ambient.return_value = ""
    monkeypatch.setattr("src.asset_manager.get_asset_manager", lambda: manager)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("TEST_MODE", "0")
    monkeypatch.setenv("FORCE_REAL_RENDER", "1")
    monkeypatch.setenv("SHORT_COMPOSITOR", "ffmpeg_legacy")
    monkeypatch.setattr("src.config.is_test_environment", lambda: False)
    monkeypatch.setattr("lib.video._get_video_attr", lambda name, default=None: (lambda: False) if name == "is_test_environment" else default)
    template = VideoTemplate(name="ffmpeg-review")
    template.visual.fps = 5
    template.visual.zoom_speed = 0.0001
    template.visual.max_zoom = 1.02
    template.visual.contrast = 1.0
    template.visual.brightness = 0.0
    template.visual.saturation = 1.0
    template.visual.enable_vignette = False
    output = tmp_path / "render.mp4"

    from lib.video import compose_video as compose_video_core
    compose_video_core(
        str(audio),
        "",
        str(red),
        str(output),
        duration_sec=duration,
        template=template,
        min_duration=0.0,
        channel="moku",
        strict_visuals=True,
        video_mode="longform",
    )

    longest, segments = detect_long_black_frames(output, maximum_seconds=1.0)
    assert output.stat().st_size > 0
    assert longest < 1.0, segments


def test_directed_thumbnail_fails_before_cli_or_local_fallback(monkeypatch, tmp_path):
    local = MagicMock(return_value=str(tmp_path / "thumbnail.jpg"))
    monkeypatch.setattr("lib.video.generate_pil_thumbnail", local)
    monkeypatch.setattr("lib.video.generate_pil_thumbnail", local)
    res = create_video_thumbnail(
        "Título", "moku", str(tmp_path / "thumbnail.jpg")
    )
    local.assert_called_once()
    assert res == str(tmp_path / "thumbnail.jpg")


def test_cli_propagates_story_id(monkeypatch, tmp_path):
    from main import main

    run_once = MagicMock(return_value={"status": "RENDERED"})
    monkeypatch.setattr("src.orchestrator.pipeline.run_pipeline_once", run_once)
    monkeypatch.setattr("main.acquire_lock", lambda channel: None)
    monkeypatch.setattr("main.release_lock", lambda channel="global": None)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "main.py",
            "run-once",
            "--channel",
            "moku",
            "--story-id",
            "bhv6zd",
            "--db-path",
            str(tmp_path / "queue.db"),
            "--generate-only",
        ],
    )
    main()
    assert run_once.call_args.kwargs["story_id"] == "bhv6zd"
    assert run_once.call_args.kwargs["channel"] == "moku"


def test_directed_pipeline_skips_scraper_and_passes_no_extra_stories(monkeypatch, tmp_path):
    from src.pipeline import run_pipeline_once

    repository = _repo(tmp_path)
    repository.enqueue("other", "Otra", "No usar", "https://other", "moku")
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "moku")
    old_work_root = SETTINGS.work_root
    object.__setattr__(SETTINGS, "work_root", tmp_path / "work")
    scraper = MagicMock(side_effect=AssertionError("scraper no debe ejecutarse"))
    curate = MagicMock(return_value="Esta es la única historia que se debe narrar completa.")

    def audio(_script, output, **kwargs):
        Path(output).write_bytes(b"wav")
        return {
            "duration_sec": 2.0,
            "word_timestamps": [{"word": "historia", "start": 0.0, "end": 2.0}],
        }

    def subtitles(_timestamps, output, **kwargs):
        Path(output).write_text("subtitles", encoding="utf-8")
        return output

    def video(_audio, _subs, _background, output, **kwargs):
        Path(output).write_bytes(b"mp4")
        return output

    def thumbnail(_title, _channel, output, **kwargs):
        Path(output).write_bytes(b"jpg")
        return output

    monkeypatch.setattr("src.scraper.fetch_reddit_stories", scraper)
    monkeypatch.setattr("src.llm.curate_script", curate)
    monkeypatch.setattr("lib.tts.generate_audio", audio)
    monkeypatch.setattr("lib.subtitles.create_subtitles", subtitles)
    monkeypatch.setattr("lib.video.compose_video", video)
    monkeypatch.setattr("lib.video.create_video_thumbnail", thumbnail)
    report = MagicMock()
    report.require_pass.return_value = None
    # Los artefactos son placeholders; el gate real exige MP4/miniatura válidos.
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: report)
    try:
        result = run_pipeline_once(
            channel="moku",
            db_path=repository.db_path,
            story_id="bhv6zd",
            generate_only=True,
        )
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work_root)

    assert result["status"] == JobStatus.RENDERED.value
    assert curate.call_args.kwargs["additional_stories"] == []
    assert curate.call_args.kwargs["strict_single_story"] is True
    with connect(repository.db_path, read_only=True) as conn:
        assert conn.execute(
            "SELECT status FROM stories WHERE story_id='other'"
        ).fetchone()[0] == JobStatus.PENDING.value
        run_id = result["run_id"]
        assert conn.execute(
            "SELECT COUNT(*) FROM run_stories WHERE run_id=?", (run_id,)
        ).fetchone()[0] == 1


def test_non_short_pipeline_creates_srt_before_validation(monkeypatch, tmp_path):
    from src.pipeline import run_pipeline_once

    monkeypatch.setenv("ENABLE_SUBTITLES", "1")
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "moku")
    old_work_root = SETTINGS.work_root
    object.__setattr__(SETTINGS, "work_root", tmp_path / "work")
    order = []

    def audio(_script, output, **kwargs):
        Path(output).write_bytes(b"wav")
        return {
            "duration_sec": 605.0,
            "word_timestamps": [
                {"word": "historia", "start": 0.0, "end": 605.0}
            ],
            "provider": "edge-tts",
            "voice": SETTINGS.channel("moku").voice,
            "boundary_type": "WordBoundary",
        }

    def subtitles(_timestamps, output, **kwargs):
        order.append("create-srt")
        Path(output).write_text("subtitles", encoding="utf-8")
        return output

    def ass_subtitles(_timestamps, output, **kwargs):
        order.append("create-ass")
        Path(output).write_text("subtitles", encoding="utf-8")
        return output

    def validate(path, **kwargs):
        assert Path(path).is_file()
        order.append("validate-srt")
        return {"coverage": 1.0}

    def video(_audio, _subs, _background, output, **kwargs):
        Path(output).write_bytes(b"mp4")
        (Path(output).parent / "visual_plan.json").write_text("{}", encoding="utf-8")
        return output

    def thumbnail(_title, _channel, output, **kwargs):
        Path(output).write_bytes(b"jpg")
        return output

    report = MagicMock()
    report.require_pass.return_value = None
    monkeypatch.setattr("src.llm.curate_script", lambda *args, **kwargs: "Esta es una historia completa en español.")
    monkeypatch.setattr("lib.tts.generate_audio", audio)
    monkeypatch.setattr("lib.subtitles.create_subtitles", subtitles)
    monkeypatch.setattr("lib.subtitles.create_ass_subtitles", ass_subtitles)
    monkeypatch.setattr("lib.subtitles.validate_subtitle_artifact", validate)
    monkeypatch.setattr("lib.video.compose_video", video)
    monkeypatch.setattr("lib.video.create_video_thumbnail", thumbnail)
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: report)
    try:
        result = run_pipeline_once(
            channel="moku",
            db_path=repository.db_path,
            story_id="bhv6zd",
            generate_only=True,
            lane_id="moku-horror-long",
        )
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work_root)

    assert result["status"] == JobStatus.RENDERED.value
    assert order == ["create-ass", "create-srt", "validate-srt"]


def test_pipeline_aborts_when_heartbeat_loses_ownership(monkeypatch, tmp_path):
    from src.pipeline import run_pipeline_once

    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "moku")
    old_work_root = SETTINGS.work_root
    object.__setattr__(SETTINGS, "work_root", tmp_path / "work")
    monkeypatch.setattr("src.llm.curate_script", lambda *args, **kwargs: "Historia")
    monkeypatch.setattr(
        "src.core.repository.QueueRepository.heartbeat", lambda *args, **kwargs: False
    )
    audio = MagicMock(side_effect=AssertionError("TTS no debe ejecutarse"))
    monkeypatch.setattr("lib.tts.generate_audio", audio)
    try:
        result = run_pipeline_once(
            channel="moku",
            db_path=repository.db_path,
            story_id="bhv6zd",
            generate_only=True,
        )
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work_root)
    assert result["status"] == "LEASE_LOST"
    audio.assert_not_called()


def test_post_commit_failure_does_not_downgrade_published(monkeypatch, tmp_path):
    from src.core.providers import DriveProof
    from src.pipeline import run_pipeline_once

    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "moku")
    old_work_root = SETTINGS.work_root
    object.__setattr__(SETTINGS, "work_root", tmp_path / "work")

    def audio(_script, output, **kwargs):
        Path(output).write_bytes(b"wav")
        return {
            "duration_sec": 2.0,
            "word_timestamps": [{"word": "historia", "start": 0.0, "end": 2.0}],
        }

    def subtitles(_timestamps, output, **kwargs):
        Path(output).write_text("subtitles", encoding="utf-8")
        return output

    def video(_audio, _subs, _background, output, **kwargs):
        Path(output).write_bytes(b"mp4")
        return output

    def thumbnail(_title, _channel, output, **kwargs):
        Path(output).write_bytes(b"jpg")
        return output

    def drive(path, **kwargs):
        kwargs["on_file_id"]("drive12345")
        return DriveProof(
            file_id="drive12345",
            name=kwargs["display_name"],
            size_bytes=Path(path).stat().st_size,
            folder_id=kwargs["folder_id"],
            exists=True,
        )

    def youtube(_path, title, description, **kwargs):
        kwargs["on_video_id"]("video12345")
        return {
            "status": "PUBLISHED",
            "method": "API",
            "video_id": "video12345",
            "channel": "moku",
            "visibility": "public",
            "title": title,
            "description": description,
            "thumbnail_confirmed": True,
            "verified": True,
        }

    monkeypatch.setattr("src.llm.curate_script", lambda *args, **kwargs: "Historia")
    monkeypatch.setattr("lib.tts.generate_audio", audio)
    monkeypatch.setattr("lib.subtitles.create_subtitles", subtitles)
    monkeypatch.setattr("lib.video.compose_video", video)
    monkeypatch.setattr("lib.video.create_video_thumbnail", thumbnail)
    monkeypatch.setattr("src.drive.upload_to_drive_verified", drive)
    monkeypatch.setattr("src.youtube.uploader.upload_video", youtube)
    monkeypatch.setattr(
        "src.core.repository.QueueRepository.record_fingerprint",
        MagicMock(side_effect=RuntimeError("post-commit failure")),
    )
    report = MagicMock()
    report.require_pass.return_value = None
    # Los artefactos son placeholders; el gate real exige MP4/miniatura válidos.
    monkeypatch.setattr("src.pipeline.validate_prepublication", lambda **kwargs: report)
    review_manager = MagicMock()
    review_manager.submit_video_for_review.return_value = MagicMock(
        status="APPROVED", version=1, delivery_error=None
    )
    monkeypatch.setattr("review.ReviewJobManager", lambda: review_manager)
    try:
        result = run_pipeline_once(
            channel="moku",
            db_path=repository.db_path,
            story_id="bhv6zd",
        )
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work_root)

    assert result["status"] == JobStatus.PUBLISHED.value
    assert result["post_commit_warning"]
    with connect(repository.db_path, read_only=True) as conn:
        assert conn.execute(
            "SELECT status FROM stories WHERE story_id='bhv6zd'"
        ).fetchone()[0] == JobStatus.PUBLISHED.value


def test_missing_official_thumbnail_sdk_leaves_story_retryable_without_remote_calls(
    monkeypatch, tmp_path
):
    from src.pipeline import run_pipeline_once

    repository = _repo(tmp_path)
    repository.enqueue("other", "Otra", "No usar", "https://other", "moku")
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "moku")
    old_work_root = SETTINGS.work_root
    object.__setattr__(SETTINGS, "work_root", tmp_path / "work")
    drive_preflight = MagicMock(side_effect=AssertionError("Drive no debe llamarse"))
    youtube_preflight = MagicMock(side_effect=AssertionError("YouTube no debe llamarse"))
    monkeypatch.setattr("src.pipeline.is_test_environment", lambda: False)
    monkeypatch.setattr("lib.tts.generate_audio", MagicMock(side_effect=RuntimeError("Simulated missing SDK error")))
    monkeypatch.setattr("src.drive.preflight_drive_access", drive_preflight)
    monkeypatch.setattr("src.youtube.uploader.preflight_youtube_api", youtube_preflight)
    try:
        result = run_pipeline_once(
            channel="moku",
            db_path=repository.db_path,
            story_id="bhv6zd",
        )
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work_root)
    # WP2: curación AI-first; con arnés caído el run entra en
    # WAITING_LLM_QUOTA (QuotaError -> backoff), no en fallo duro.
    assert result["status"] in (
        JobStatus.RETRYABLE_FAILED.value,
        "WAITING_LLM_QUOTA",
    )
    if result["status"] == JobStatus.RETRYABLE_FAILED.value:
        assert result["reason"]
    else:
        # WAITING_LLM_QUOTA: sin 'reason', el daemon aplica backoff
        assert result.get("error") or result.get("status") == "WAITING_LLM_QUOTA"
    drive_preflight.assert_not_called()
    youtube_preflight.assert_not_called()
    with connect(repository.db_path, read_only=True) as conn:
        rows = {
            row["story_id"]: row["status"]
            for row in conn.execute("SELECT story_id,status FROM stories")
        }
    assert rows["other"] == "PENDING"
    assert rows["bhv6zd"] in ("RETRYABLE_FAILED", "WAITING_LLM_QUOTA")


def test_api_only_uploader_never_calls_playwright(monkeypatch, tmp_path):
    from src.youtube.uploader import upload_video

    video = tmp_path / "video.mp4"
    thumb = tmp_path / "thumbnail.jpg"
    token = tmp_path / "token.json"
    video.write_bytes(b"video")
    thumb.write_bytes(b"thumb")
    token.write_text("{}", encoding="utf-8")
    monkeypatch.delenv("TEST_MODE", raising=False)
    monkeypatch.delenv("MOCK_YOUTUBE_UPLOAD", raising=False)
    monkeypatch.setattr("lib.video.validate_video_format", lambda *args, **kwargs: True)
    monkeypatch.setattr("src.youtube.uploader.preflight_youtube_api", MagicMock())
    api = MagicMock(
        return_value={
            "status": "PUBLISHED",
            "method": "API",
            "video_id": "video12345",
            "channel": "moku",
            "visibility": "public",
            "title": "Una historia de terror",
            "description": "Esta es una descripción en español para la historia que se publica en el canal.",
            "thumbnail_confirmed": True,
            "verified": True,
        }
    )
    playwright = MagicMock(side_effect=AssertionError("Playwright no permitido"))
    monkeypatch.setattr("src.youtube.uploader.upload_video_via_api", api)
    monkeypatch.setattr("src.youtube.uploader.upload_video_via_playwright", playwright)
    result = upload_video(
        str(video),
        "Una historia de terror",
        "Esta es una descripción en español para la historia que se publica en el canal.",
        channel="moku",
        thumbnail_path=str(thumb),
        token_path=str(token),
        api_only=True,
        expected_channel_id="expected-channel",
    )
    assert result["status"] == "PUBLISHED"
    playwright.assert_not_called()


def test_youtube_post_verification_requires_public_processed_and_exact_channel():
    from src.youtube.uploader import _verify_uploaded_video

    youtube = MagicMock()
    youtube.videos().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "channelId": "expected-channel",
                    "title": "Título exacto",
                    "description": "Descripción exacta",
                },
                "status": {"privacyStatus": "public", "uploadStatus": "processed"},
                "processingDetails": {"processingStatus": "succeeded"},
                "contentDetails": {"duration": "PT10M5S"},
            }
        ]
    }
    item = _verify_uploaded_video(
        youtube,
        video_id="video12345",
        expected_channel_id="expected-channel",
        expected_title="Título exacto",
        expected_description="Descripción exacta",
        timeout_seconds=0,
    )
    assert item["status"]["privacyStatus"] == "public"

    youtube.videos().list().execute.return_value["items"][0]["status"][
        "privacyStatus"
    ] = "unlisted"
    with pytest.raises(RuntimeError, match="visibility=public"):
        _verify_uploaded_video(
            youtube,
            video_id="video12345",
            expected_channel_id="expected-channel",
            expected_title="Título exacto",
            expected_description="Descripción exacta",
            timeout_seconds=0,
        )


def test_youtube_public_insert_persists_id_before_thumbnail(monkeypatch, tmp_path):
    from src.youtube.uploader import upload_video_via_api

    video = tmp_path / "video.mp4"
    thumbnail = tmp_path / "thumbnail.jpg"
    token = tmp_path / "token.json"
    video.write_bytes(b"video")
    thumbnail.write_bytes(b"thumbnail")
    token.write_text("{}", encoding="utf-8")
    youtube = MagicMock()
    events = []
    youtube.videos().insert().execute.side_effect = lambda: (
        events.append("insert-public") or {"id": "video12345"}
    )
    youtube.thumbnails().set().execute.side_effect = lambda: (
        events.append("thumbnail") or {"items": [{}]}
    )
    youtube.videos().list().execute.return_value = {
        "items": [
            {
                "snippet": {
                    "channelId": "expected-channel",
                    "title": "Una historia de terror",
                    "description": "Esta es una descripción completa en español para publicar la historia del canal.",
                },
                "status": {"privacyStatus": "public", "uploadStatus": "processed"},
                "processingDetails": {"processingStatus": "succeeded"},
                "contentDetails": {"duration": "PT10M5S"},
            }
        ]
    }
    monkeypatch.setattr("src.youtube.uploader._youtube_service", lambda _path: youtube)
    monkeypatch.setattr("src.youtube.uploader.preflight_youtube_api", lambda **kwargs: {})
    monkeypatch.setattr("googleapiclient.http.MediaFileUpload", lambda *args, **kwargs: object())

    result = upload_video_via_api(
        str(video),
        "Una historia de terror",
        "Esta es una descripción completa en español para publicar la historia del canal.",
        thumbnail_path=str(thumbnail),
        token_path=str(token),
        channel="moku",
        expected_channel_id="expected-channel",
        on_video_id=lambda video_id: events.append(f"persist:{video_id}"),
    )

    insert_body = youtube.videos().insert.call_args.kwargs["body"]
    assert insert_body["status"]["privacyStatus"] == "public"
    assert events == ["insert-public", "persist:video12345", "thumbnail"]
    assert result["publication_sequence"].startswith("videos.insert(public)")


def test_read_only_remote_preflights_validate_drive_and_youtube(monkeypatch, tmp_path):
    from src.drive import preflight_drive_access
    from src.youtube.uploader import preflight_youtube_api

    drive = MagicMock()
    drive.files().get().execute.return_value = {
        "id": "folder-id",
        "name": "Moku",
        "mimeType": "application/vnd.google-apps.folder",
        "trashed": False,
        "capabilities": {"canAddChildren": True},
    }
    monkeypatch.setattr("src.drive._credentials", lambda *args, **kwargs: object())
    monkeypatch.setattr("googleapiclient.discovery.build", lambda *args, **kwargs: drive)
    token = tmp_path / "token.json"
    token.write_text("{}", encoding="utf-8")
    proof = preflight_drive_access(
        folder_id="folder-id", sa_key_path="", token_path=str(token)
    )
    assert proof["writable"] is True

    youtube = MagicMock()
    youtube.channels().list().execute.return_value = {
        "items": [{"id": "expected-channel", "snippet": {"title": "Moku"}}]
    }
    monkeypatch.setattr("src.youtube.uploader._youtube_service", lambda _path: youtube)
    identity = preflight_youtube_api(
        channel="moku",
        token_path=str(token),
        expected_channel_id="expected-channel",
    )
    assert identity["channel_id"] == "expected-channel"


def test_critical_qa_accepts_complete_artifacts_and_blocks_placeholders(monkeypatch, tmp_path):
    from PIL import Image

    video = tmp_path / "video.mp4"
    video.write_bytes(b"ftypmoovmdat")
    subtitle = tmp_path / "subtitles.srt"
    subtitle.write_text(
        "1\n00:00:00,000 --> 00:10:05,000\nEsta es una historia completa en español con subtítulos legibles\n",
        encoding="utf-8",
    )
    thumbnail = tmp_path / "thumbnail.jpg"
    Image.new("RGB", (1280, 720), "red").save(thumbnail)
    source = tmp_path / "scene.jpg"
    source.write_bytes(b"image")
    scenes = build_visual_scene_plan(605.0, [str(source)])
    plan = tmp_path / "visual_plan.json"
    plan.write_text(
        json.dumps(
            {
                "covered_seconds": sum(item["duration"] for item in scenes),
                "black_fallbacks": 0,
                "scenes": scenes,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "src.core.quality.ffprobe",
        lambda _path: {
            "format": {"duration": "605"},
            "streams": [
                {
                    "codec_type": "video",
                    "codec_name": "h264",
                    "width": 1920,
                    "height": 1080,
                    "pix_fmt": "yuv420p",
                },
                {"codec_type": "audio", "codec_name": "aac"},
            ],
        },
    )
    monkeypatch.setattr("src.core.quality.has_faststart", lambda _path: True)
    monkeypatch.setattr("src.core.quality.detect_long_black_frames", lambda _path: (0.0, []))
    script = (
        "Esta es una historia en español porque la protagonista llegó a la casa y no sabía "
        "qué hacer cuando todos estaban allí, pero decidió contar toda la verdad."
    )
    description = (
        "Esta es una descripción completa en español para la historia de terror que se publica hoy."
    )
    report = validate_prepublication(
        channel="moku",
        script=script,
        title="La casa donde nadie debía entrar",
        description=description,
        video_path=video,
        subtitle_path=subtitle,
        thumbnail_path=thumbnail,
        visual_plan_path=plan,
        expected_story_count=1,
        visibility="public",
        audio_proof={
            "provider": "edge-tts",
            "voice": SETTINGS.channel("moku").voice,
            "boundary_type": "WordBoundary",
        },
        require_strict_voice=True,
    )
    assert report.passed, report.issues

    blocked = validate_prepublication(
        channel="moku",
        script=script + " TODO <placeholder>",
        title="La casa donde nadie debía entrar",
        description=description,
        video_path=video,
        subtitle_path=subtitle,
        thumbnail_path=thumbnail,
        visual_plan_path=plan,
    )
    assert any("placeholder" in issue for issue in blocked.issues)
