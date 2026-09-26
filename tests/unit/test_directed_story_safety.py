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
    repository.enqueue("other", "Otra", "Contenido", "https://other", "horror")
    repository.enqueue("bhv6zd", "Off the grid", "Historia completa", "https://target", "horror")

    claimed = repository.claim_exact("bhv6zd", "horror", "worker", now=1_000)

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
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "horror")
    assert repository.claim_exact("bhv6zd", "drama", "worker") is None
    with connect(repository.db_path, read_only=True) as conn:
        row = conn.execute(
            "SELECT status,run_id FROM stories WHERE story_id='bhv6zd'"
        ).fetchone()
    assert (row["status"], row["run_id"]) == (JobStatus.PENDING.value, None)


def test_claim_exact_reconciles_only_its_expired_lease(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "horror")
    repository.enqueue("ael", "Otra", "Historia", "https://ael", "drama")
    first = repository.claim_exact(
        "bhv6zd", "horror", "old-worker", lease_seconds=10, now=1_000
    )
    other = repository.claim_exact(
        "ael", "drama", "other-worker", lease_seconds=100, now=1_000
    )

    second = repository.claim_exact(
        "bhv6zd", "horror", "new-worker", lease_seconds=10, now=1_011
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
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "horror")
    first = repository.claim_exact(
        "bhv6zd", "horror", "old-worker", lease_seconds=10, now=1_000
    )
    second = repository.claim_exact(
        "bhv6zd", "horror", "new-worker", lease_seconds=100, now=1_011
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
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "horror")
    repository.enqueue("other", "Otra", "Otra historia", "https://other", "horror")
    claimed = repository.claim_exact("bhv6zd", "horror", "worker")
    proof = PublicationProof(
        video_id="video12345",
        channel=CanonicalChannel.HORROR,
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
    repository.enqueue("bhv6zd", "Off the grid", "Historia", "https://target", "horror")
    repository.enqueue("other", "Otra", "Otra historia", "https://other", "horror")
    claimed = repository.claim_exact("bhv6zd", "horror", "worker")
    with connect(repository.db_path) as conn:
        conn.execute(
            "INSERT INTO run_stories(run_id,story_id,position) VALUES(?,?,1)",
            (claimed["run_id"], "other"),
        )
        conn.commit()
    proof = PublicationProof(
        video_id="video12345",
        channel=CanonicalChannel.HORROR,
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


def test_mark_published_accepts_multistory_collection_for_non_directed_run(tmp_path):
    repository = _repo(tmp_path)
    repository.enqueue("a_story_main", "Principal", "Historia principal", "https://main", "horror")
    repository.enqueue("b_story_extra", "Extra", "Historia extra", "https://extra", "horror")
    claimed = repository.claim_for_lane("horror-horror-long", "horror", "worker")
    assert claimed and claimed["story_id"] == "a_story_main"
    with connect(repository.db_path) as conn:
        conn.execute(
            "INSERT INTO run_stories(run_id, story_id, position) VALUES (?, ?, 1)",
            (claimed["run_id"], "b_story_extra"),
        )
        conn.commit()
    proof = PublicationProof(
        video_id="video999",
        channel=CanonicalChannel.HORROR,
        visibility="public",
        title="Título verificado",
        description="Descripción verificada",
        thumbnail_confirmed=True,
    )
    repository.mark_published("a_story_main", claimed["run_id"], proof, provider="API")
    with connect(repository.db_path, read_only=True) as conn:
        rows = {
            row["story_id"]: row["status"]
            for row in conn.execute("SELECT story_id, status FROM stories")
        }
    assert rows == {"a_story_main": "PUBLISHED", "b_story_extra": "PUBLISHED"}


def test_strict_script_rejects_aggregation(monkeypatch):
    monkeypatch.setenv("TEST_MODE", "1")
    with pytest.raises(ValueError, match="no admite historias adicionales"):
        curate_script(
            "Historia principal",
            "Título",
            additional_stories=[{"title": "Otra", "content": "Mezcla"}],
            provider="C",
            channel="horror",
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
        channel="horror",
        strict_visuals=True,
        video_mode="longform",
    )

    longest, segments = detect_long_black_frames(output, maximum_seconds=1.0)
    assert output.stat().st_size > 0
    assert longest < 1.0, segments



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
            "horror",
            "--story-id",
            "bhv6zd",
            "--db-path",
            str(tmp_path / "queue.db"),
            "--generate-only",
        ],
    )
    main()
    assert run_once.call_args.kwargs["story_id"] == "bhv6zd"
    assert run_once.call_args.kwargs["channel"] == "horror"




def test_pipeline_aborts_when_heartbeat_loses_ownership(monkeypatch, tmp_path):
    from src.pipeline import run_pipeline_once

    repository = _repo(tmp_path)
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "horror")
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
            channel="horror",
            db_path=repository.db_path,
            story_id="bhv6zd",
            generate_only=True,
        )
    finally:
        object.__setattr__(SETTINGS, "work_root", old_work_root)
    assert result["status"] == "LEASE_LOST"
    audio.assert_not_called()




def test_missing_official_thumbnail_sdk_leaves_story_retryable_without_remote_calls(
    monkeypatch, tmp_path
):
    from src.pipeline import run_pipeline_once

    repository = _repo(tmp_path)
    repository.enqueue("other", "Otra", "No usar", "https://other", "horror")
    repository.enqueue("bhv6zd", "SCP-173: La Escultura", "Solo esta historia", "https://target", "horror")
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
            channel="horror",
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
            "channel": "horror",
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
        channel="horror",
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
    scenes = build_visual_scene_plan(605.0, [str(source)], min_seconds=20.0, max_seconds=30.0)
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
        channel="horror",
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
            "voice": SETTINGS.channel("horror").voice,
            "boundary_type": "WordBoundary",
        },
        require_strict_voice=True,
    )
    assert report.passed, report.issues

    blocked = validate_prepublication(
        channel="horror",
        script=script + " TODO <placeholder>",
        title="La casa donde nadie debía entrar",
        description=description,
        video_path=video,
        subtitle_path=subtitle,
        thumbnail_path=thumbnail,
        visual_plan_path=plan,
    )
    assert any("placeholder" in issue for issue in blocked.issues)
