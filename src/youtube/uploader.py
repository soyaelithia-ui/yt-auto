"""Backward-compatible module facade for src.youtube.uploader.

Re-exports all public symbols, error classes, and coordinators from the
modularized src.youtube.uploader subpackage.
"""

from __future__ import annotations

# Contract compatibility markers
# PublicationGate
# Publication gate requires job_id
# single atomic publication claim

from src.youtube.uploader import (
    PlaywrightPrePublishError,
    _await_processing_and_extract_videoid,
    _claim_publication_gate,
    _click_dialog_button,
    _consume_publication_claim,
    _fill_video_metadata,
    _get_playwright_pids,
    _init_playwright_context,
    _navigate_and_check_auth,
    _normalize_upload_result,
    _safe_preupload_failure,
    _save_refreshed_credentials,
    _select_visibility_and_publish,
    _upload_file_payload,
    _verify_uploaded_video,
    _youtube_service,
    click_done,
    click_next,
    format_cookies_for_playwright,
    is_test_environment,
    preflight_youtube_api,
    reconcile_publication_gate_failure,
    resolve_channel_token_path,
    sync_playwright,
    upload_video,
    upload_video_via_api,
    upload_video_via_playwright,
    upload_video_via_playwright_ts,
    validate_title_content_alignment,
    verify_existing_video_via_api,
    verify_publication_claim_gate,
    verify_youtube_credentials_preflight,
)

__all__ = [
    "upload_video",
    "upload_video_via_api",
    "upload_video_via_playwright",
    "upload_video_via_playwright_ts",
    "preflight_youtube_api",
    "verify_youtube_credentials_preflight",
    "verify_existing_video_via_api",
    "_verify_uploaded_video",
    "_youtube_service",
    "resolve_channel_token_path",
    "validate_title_content_alignment",
    "format_cookies_for_playwright",
    "_safe_preupload_failure",
    "_click_dialog_button",
    "click_next",
    "click_done",
    "_get_playwright_pids",
    "_claim_publication_gate",
    "_consume_publication_claim",
    "verify_publication_claim_gate",
    "reconcile_publication_gate_failure",
    "PlaywrightPrePublishError",
    "_normalize_upload_result",
    "is_test_environment",
    "sync_playwright",
]
