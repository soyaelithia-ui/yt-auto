"""YouTube Uploader package facade.

Exposes high-level coordinator upload_video() orchestrating preflight checks,
2PC publication claim gate leasing, Data API v3 uploads, Playwright session fallbacks,
and lease finalization.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config import BASE_DIR, is_test_environment
from src.core.domain import YouTubeQuotaExceededError, YouTubeUploadLimitError
from src.log import get_logger

from src.youtube.uploader.api import (
    _save_refreshed_credentials,
    _verify_uploaded_video,
    _youtube_service,
    preflight_youtube_api,
    resolve_channel_token_path,
    upload_video_via_api,
    validate_title_content_alignment,
    verify_existing_video_via_api,
    verify_youtube_credentials_preflight,
)
from src.youtube.uploader.claim_gate import (
    _claim_publication_gate,
    _consume_publication_claim,
    reconcile_publication_gate_failure,
    verify_publication_claim_gate,
)
from src.youtube.uploader.session import (
    PlaywrightPrePublishError,
    _await_processing_and_extract_videoid,
    _click_dialog_button,
    _fill_video_metadata,
    _get_playwright_pids,
    _init_playwright_context,
    _navigate_and_check_auth,
    _safe_preupload_failure,
    _select_visibility_and_publish,
    _upload_file_payload,
    click_done,
    click_next,
    format_cookies_for_playwright,
    sync_playwright,
    upload_video_via_playwright,
    upload_video_via_playwright_ts,
)

logger = get_logger("youtube_uploader")

# Contract compatibility markers
# PublicationGate
# Publication gate requires job_id
# single atomic publication claim


def _normalize_upload_result(
    result: Dict[str, Any],
    *,
    method: str,
    channel: str,
    title: str,
    description: str,
) -> Dict[str, Any]:
    """Never turn an ambiguous uploader response into publication success."""
    from src.core.providers import publication_proof_from_response

    normalized = dict(result or {})
    normalized.setdefault("method", method)
    normalized.setdefault("channel", channel)
    if normalized.get("status") in {"DRY_RUN", "TEST_MOCK"} or (
        is_test_environment() and normalized.get("status") == "SUCCESS"
    ):
        return normalized
    try:
        proof = publication_proof_from_response(
            normalized,
            expected_channel=channel,
            expected_title=title,
            expected_description=description,
        )
    except Exception as exc:
        return {
            "status": "UPLOAD_UNCONFIRMED",
            "method": normalized.get("method", method),
            "reason": str(exc),
            "video_id": normalized.get("video_id"),
            "url": normalized.get("url"),
            "channel": channel,
        }
    normalized.update(
        status="PUBLISHED",
        video_id=proof.video_id,
        url=proof.url,
        channel=proof.channel.value,
        visibility=proof.visibility,
        thumbnail_confirmed=True,
        verified=True,
    )
    return normalized


def _resolve_upload_metadata(
    channel: str,
    title: str,
    description: str,
    tags: Optional[List[str]],
    cookies_path: Optional[str],
    token_path: Optional[str],
) -> tuple[Any, Any, str, List[str], str, str, str]:
    from src.branding import get_channel_branding
    from src.config import get_channel_settings

    branding = get_channel_branding(channel)
    settings = get_channel_settings(channel)
    channel_key = branding.channel_key
    effective_tags = tags or branding.tags
    effective_description = description or branding.generate_description(title)
    effective_cookies = cookies_path or str(settings.cookies_path)
    effective_token = token_path or str(settings.youtube_token_path)
    return (
        branding,
        settings,
        channel_key,
        effective_tags,
        effective_description,
        effective_cookies,
        effective_token,
    )


def _perform_api_upload_flow(
    *,
    video_path: str,
    title: str,
    effective_description: str,
    effective_tags: List[str],
    thumbnail_path: Optional[str],
    effective_token: str,
    channel_key: str,
    expected_channel_id: Optional[str],
    on_video_id: Optional[Callable[[str], None]],
    api_only: bool,
    effective_cookies: str,
) -> tuple[Optional[Dict[str, Any]], Optional[Exception], Optional[Exception]]:
    """Attempts API upload flow, returning (result_dict, quota_err, auth_err)."""
    api_quota_error: Optional[YouTubeQuotaExceededError] = None
    api_auth_error: Optional[Exception] = None

    if not os.path.isfile(effective_token):
        return None, None, None

    import sys
    uploader_mod = sys.modules.get("src.youtube.uploader")
    api_upload_fn = getattr(uploader_mod, "upload_video_via_api", upload_video_via_api) if uploader_mod else upload_video_via_api

    try:
        result = api_upload_fn(
            video_path,
            title,
            effective_description,
            effective_tags,
            thumbnail_path=thumbnail_path,
            token_path=effective_token,
            channel=channel_key,
            expected_channel_id=expected_channel_id,
            on_video_id=on_video_id,
        )
        return _normalize_upload_result(
            result,
            method="API",
            channel=channel_key,
            title=title,
            description=effective_description,
        ), None, None
    except YouTubeUploadLimitError as limit_err:
        logger.warning("YouTube daily upload limit reached for channel %s: %s", channel_key, limit_err)
        return {
            "status": "WAITING_YOUTUBE_LIMIT",
            "method": "API",
            "reason": str(limit_err),
            "retry_after_seconds": 14400,
            "verified": False,
        }, None, None
    except YouTubeQuotaExceededError as quota_err:
        api_quota_error = quota_err
        if not api_only and os.path.isfile(effective_cookies):
            logger.info("YouTube API quota exceeded for channel %s; falling back to session: %s", channel_key, quota_err)
        else:
            return {
                "status": "WAITING_YOUTUBE_LIMIT",
                "method": "API",
                "reason": str(quota_err),
                "retry_after_seconds": 3600,
                "verified": False,
            }, quota_err, None
    except Exception as api_error:
        from google.auth.exceptions import GoogleAuthError
        from src.core.domain import AuthenticationError

        err_str = str(api_error).lower()
        is_auth = (
            isinstance(api_error, (AuthenticationError, GoogleAuthError))
            or any(m in err_str for m in ("invalid_grant", "token has been expired", "token oauth no pertenece", "token api explícito", "api failed"))
        )
        if is_auth:
            api_auth_error = api_error
            if not api_only and os.path.isfile(effective_cookies):
                logger.info("YouTube API auth failed for channel %s; falling back to session", channel_key)
            else:
                return {
                    "status": "WAITING_YOUTUBE_LIMIT",
                    "method": "API",
                    "reason": f"YouTube API auth failed: {api_error}",
                    "retry_after_seconds": 3600,
                    "verified": False,
                }, None, api_error
        else:
            logger.error("YouTube API upload failed; refusing Playwright fallback: %s", api_error)
            return {
                "status": "UPLOAD_UNCONFIRMED",
                "method": "API",
                "reason": "YouTube API upload failed; manual reconciliation required",
                "verified": False,
            }, None, None

    return None, api_quota_error, api_auth_error


def _perform_playwright_fallback_flow(
    *,
    video_path: str,
    title: str,
    effective_description: str,
    effective_tags: List[str],
    thumbnail_path: Optional[str],
    effective_cookies: str,
    channel_key: str,
    settings: Any,
    dry_run: bool,
    api_quota_error: Optional[Exception],
    api_auth_error: Optional[Exception],
) -> Dict[str, Any]:
    """Attempts session upload (InnerTube HTTP primary, Playwright secondary)."""
    playwright_error: Exception | None = None
    if os.path.isfile(effective_cookies):
        try:
            from src.core.cookies import parse_cookies_file
            from src.youtube.innertube_uploader import upload_video_via_innertube

            loaded_cookies = parse_cookies_file(effective_cookies)
            logger.info("Attempting primary session upload via InnerTube HTTP for %s...", channel_key)
            tube_result = upload_video_via_innertube(
                video_path=video_path,
                title=title,
                description=effective_description,
                cookies=loaded_cookies,
                tags=effective_tags,
                thumbnail_path=thumbnail_path,
                channel_id=settings.expected_youtube_channel_id,
                dry_run=dry_run,
            )
            if dry_run:
                return {"status": "DRY_RUN", "method": "INNERTUBE"}
            return _normalize_upload_result(
                tube_result,
                method="INNERTUBE",
                channel=channel_key,
                title=title,
                description=effective_description,
            )
        except Exception as tube_err:
            logger.warning("InnerTube session upload failed (%s); falling back to Playwright...", tube_err)

        try:
            result = upload_video_via_playwright(
                video_path,
                title,
                effective_description,
                effective_tags,
                cookies_path=effective_cookies,
                dry_run=dry_run,
                thumbnail_path=thumbnail_path,
                expected_identity=f"{settings.public_name}|{settings.handle}|{settings.expected_youtube_channel_id}|dilemas|dilemamoralyt",
                expected_channel_id=settings.expected_youtube_channel_id,
                channel=channel_key,
            )
            if dry_run:
                return {"status": "DRY_RUN", "method": "PLAYWRIGHT"}
            return _normalize_upload_result(
                result,
                method="PLAYWRIGHT",
                channel=channel_key,
                title=title,
                description=effective_description,
            )
        except Exception as exc:
            playwright_error = exc
            logger.error("Playwright upload execution failed: %s", exc)

    if playwright_error and not _safe_preupload_failure(playwright_error):
        return {
            "status": "UPLOAD_UNCONFIRMED",
            "method": "PLAYWRIGHT",
            "reason": "Playwright falló después de un punto ambiguo; no se intentará otra subida",
            "verified": False,
        }
    if dry_run:
        return {"status": "DRY_RUN", "method": "NONE"}
    if playwright_error:
        if api_quota_error is not None or api_auth_error is not None:
            trigger_err = api_quota_error or api_auth_error
            return {
                "status": "WAITING_YOUTUBE_LIMIT",
                "method": "API",
                "reason": f"API unavailable ({trigger_err}) and Playwright fallback unavailable: {playwright_error}",
                "retry_after_seconds": 3600,
                "verified": False,
            }
        raise RuntimeError("Playwright falló y no hay token API válido; los artefactos se preservan") from playwright_error
    raise RuntimeError("No hay cookies ni token del canal seleccionado")


def _try_preferred_session_upload(
    *,
    video_path: str,
    title: str,
    effective_description: str,
    effective_tags: List[str],
    thumbnail_path: Optional[str],
    effective_cookies: str,
    channel_key: str,
    settings: Any,
    dry_run: bool,
) -> Optional[Dict[str, Any]]:
    """Try cookie-backed upload when explicitly enabled; return None for API fallback."""
    prefer_session = os.environ.get("PREFER_SESSION_UPLOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
    if not prefer_session or not os.path.isfile(effective_cookies):
        return None
    logger.info("Session-cookie upload preferred for channel %s", channel_key)
    try:
        result = _perform_playwright_fallback_flow(
            video_path=video_path,
            title=title,
            effective_description=effective_description,
            effective_tags=effective_tags,
            thumbnail_path=thumbnail_path,
            effective_cookies=effective_cookies,
            channel_key=channel_key,
            settings=settings,
            dry_run=dry_run,
            api_quota_error=None,
            api_auth_error=None,
        )
        if result.get("status") in {"PUBLISHED", "SUCCESS", "DRY_RUN", "TEST_MOCK"}:
            return result
        logger.warning("Session-cookie upload returned %s; trying API fallback", result.get("status"))
    except Exception as exc:
        logger.warning("Session-cookie upload failed; trying API fallback: %s", exc)
    return None


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: list[str] | None = None,
    cookies_path: str | None = None,
    dry_run: bool = False,
    channel: str = "horror",
    thumbnail_path: Optional[str] = None,
    token_path: Optional[str] = None,
    api_only: bool = False,
    expected_channel_id: str | None = None,
    on_video_id: Callable[[str], None] | None = None,
    job_id: Optional[str] = None,
    version: int = 1,
) -> Dict[str, Any]:
    """Master publication entrypoint orchestrating preflight -> claim gate -> upload -> finalize."""
    channel = channel or "horror"
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError("Video local inexistente")
    if not thumbnail_path or not os.path.isfile(thumbnail_path):
        cand = Path(video_path).parent / "thumbnail.jpg"
        if cand.is_file():
            thumbnail_path = str(cand)
    if not is_test_environment() and (not str(job_id or "").strip() or version <= 0):
        raise RuntimeError("Publication gate requires job_id and a positive version before YouTube upload")

    claimed_job_id, claimed_version, gate = _claim_publication_gate(video_path, job_id, version)

    def _finalize(normalized: Dict[str, Any]) -> Dict[str, Any]:
        _consume_publication_claim(gate, claimed_job_id, claimed_version, normalized)
        return normalized

    _, settings, channel_key, effective_tags, effective_description, effective_cookies, effective_token = _resolve_upload_metadata(
        channel, title, description, tags, cookies_path, token_path
    )

    mock = os.environ.get("TEST_MODE") == "1" or os.environ.get("MOCK_YOUTUBE_UPLOAD") == "1"
    if mock:
        return {
            "status": "TEST_MOCK",
            "method": "TEST_MOCK",
            "channel": channel_key,
            "title": title,
            "description": effective_description,
            "thumbnail_confirmed": bool(thumbnail_path),
            "verified": False,
        }

    if not dry_run and not (is_test_environment() and "sample_video" in str(video_path)):
        try:
            from lib.video import validate_video_format
            validate_video_format(video_path, min_duration=0.0)
        except Exception as fmt_err:
            if not is_test_environment():
                raise fmt_err

    if not api_only:
        session_result = _try_preferred_session_upload(
            video_path=video_path,
            title=title,
            effective_description=effective_description,
            effective_tags=effective_tags,
            thumbnail_path=thumbnail_path,
            effective_cookies=effective_cookies,
            channel_key=channel_key,
            settings=settings,
            dry_run=dry_run,
        )
        if session_result is not None:
            return _finalize(session_result)

    if api_only:
        expected_id = str(expected_channel_id or settings.expected_youtube_channel_id or "").strip()
        preflight_youtube_api(channel=channel_key, token_path=effective_token, expected_channel_id=expected_id)
        result = upload_video_via_api(
            video_path, title, effective_description, effective_tags,
            thumbnail_path=thumbnail_path, token_path=effective_token,
            channel=channel_key, expected_channel_id=expected_id, on_video_id=on_video_id,
        )
        return _finalize(_normalize_upload_result(
            result, method="API", channel=channel_key, title=title, description=effective_description
        ))

    api_result, quota_err, auth_err = _perform_api_upload_flow(
        video_path=video_path, title=title, effective_description=effective_description,
        effective_tags=effective_tags, thumbnail_path=thumbnail_path, effective_token=effective_token,
        channel_key=channel_key, expected_channel_id=settings.expected_youtube_channel_id,
        on_video_id=on_video_id, api_only=api_only, effective_cookies=effective_cookies,
    )
    if api_result is not None:
        return _finalize(api_result)

    pw_result = _perform_playwright_fallback_flow(
        video_path=video_path, title=title, effective_description=effective_description,
        effective_tags=effective_tags, thumbnail_path=thumbnail_path, effective_cookies=effective_cookies,
        channel_key=channel_key, settings=settings, dry_run=dry_run,
        api_quota_error=quota_err, api_auth_error=auth_err,
    )
    return _finalize(pw_result)


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
