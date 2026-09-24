"""YouTube Data API v3 integration module.

Provides authenticated Google API client interactions: resumable media uploads,
channel preflight verification, post-upload processing polling, and token resolution.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.config import BASE_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, is_test_environment
from src.core.domain import (
    AmbiguousUploadError,
    CanonicalChannel,
    YouTubeQuotaExceededError,
    YouTubeUploadLimitError,
    canonical_channel,
)
from src.log import get_logger

logger = get_logger("youtube_uploader.api")


def validate_title_content_alignment(title: str, entity_id: str, script_text: str = "") -> bool:
    """Validates alignment between YouTube title, entity identifier, and script content."""
    if not title or not entity_id:
        return True

    title_scp_match = re.search(r"(?i)\bSCP-?(\d+)\b", title)
    entity_scp_match = re.search(r"(?i)\bSCP-?(\d+)\b", entity_id)

    if title_scp_match and entity_scp_match:
        if title_scp_match.group(1).lstrip("0") != entity_scp_match.group(1).lstrip("0"):
            raise ValueError(
                f"Discrepancia en validación cruzada: el título '{title}' contiene '{title_scp_match.group(0)}' "
                f"que no coincide con el entity_id '{entity_id}'."
            )
    return True


def _save_refreshed_credentials(token_path: str, credentials: Any, original_data: dict | None = None) -> None:
    """Persist refreshed OAuth credentials back to disk."""
    try:
        from src.core.google_auth import save_credentials
        save_credentials(credentials, token_path)
    except Exception as exc:
        logger.warning("Could not persist refreshed OAuth token to %s: %s", token_path, exc)


def _youtube_service(token_path: str):
    """Build and return an authorized YouTube Data API v3 service."""
    if not token_path or not os.path.isfile(token_path):
        raise RuntimeError("El token API explícito del canal no existe")
    from src.core.google_auth import build_youtube_service
    return build_youtube_service(token_path=token_path)


def resolve_channel_token_path(channel: str | CanonicalChannel = "horror") -> str:
    """Resolve the token file path for target channel with fallback to legacy tokens."""
    from src.core.google_auth import resolve_channel_token_path as _resolve
    resolved = _resolve(channel)
    if os.path.isfile(resolved):
        return resolved

    # Fallback to legacy tokens if canonical token is absent on disk
    key = canonical_channel(channel)
    if key == CanonicalChannel.HORROR:
        moku_candidate = BASE_DIR / "secrets" / "tokens" / "moku.json"
        if moku_candidate.is_file():
            return str(moku_candidate.resolve())
        moku_legacy = BASE_DIR / "secrets" / "youtube_token.json"
        if moku_legacy.is_file():
            return str(moku_legacy.resolve())
    elif key == CanonicalChannel.DRAMA:
        ael_candidate = BASE_DIR / "secrets" / "tokens" / "aelithia.json"
        if ael_candidate.is_file():
            return str(ael_candidate.resolve())
        ael_legacy = BASE_DIR / "secrets" / "youtube_token_aelithia.json"
        if ael_legacy.is_file():
            return str(ael_legacy.resolve())
    return resolved


def preflight_youtube_api(
    *,
    channel: str,
    token_path: str,
    expected_channel_id: str,
) -> Dict[str, str]:
    """Read-only proof that the OAuth token belongs to the configured channel."""
    canonical_channel(channel)
    expected = str(expected_channel_id or "").strip()
    if not expected:
        raise RuntimeError("Falta el channelId esperado para publicación dirigida")
    youtube = _youtube_service(token_path)
    items = youtube.channels().list(part="id,snippet", mine=True).execute().get("items") or []
    if len(items) != 1 or str(items[0].get("id") or "") != expected:
        raise RuntimeError("El token OAuth no pertenece al canal de YouTube esperado")
    return {
        "channel_id": expected,
        "title": str((items[0].get("snippet") or {}).get("title") or ""),
    }


def verify_youtube_credentials_preflight(channel: str) -> tuple[bool, str]:
    """Fast Step 0 check (<1s) validating YouTube OAuth credentials before pipeline execution."""
    if os.environ.get("TEST_MODE") == "1" or os.environ.get("MOCK_YOUTUBE_UPLOAD") == "1":
        return True, "Mock/Test environment active"
    from src.config import get_channel_settings

    token_p = resolve_channel_token_path(channel)
    token_valid = False
    token_checked = False
    if token_p:
        token_checked = True
        if os.path.isfile(token_p):
            try:
                with open(token_p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict) and (data.get("token") or data.get("refresh_token") or data.get("client_id")):
                        token_valid = True
            except (json.JSONDecodeError, OSError) as exc:
                logger.debug("Token file read failed (%s): %s", token_p, exc)
                token_valid = False

    if token_valid:
        return True, "Token API disponible"

    settings = get_channel_settings(channel)
    if settings.cookies_path.is_file():
        if token_checked and token_p and not os.path.exists(token_p):
            return False, "OAuth Authorization Required: token file missing"
        if token_checked and token_p and os.path.exists(token_p) and not token_valid:
            return False, "OAuth Authorization Required: token file malformed"
        return True, "Cookies de Playwright disponibles"
    return False, "Faltan cookies y token para el canal seleccionado"


def _verify_uploaded_video(
    youtube: Any,
    *,
    video_id: str,
    expected_channel_id: str,
    expected_title: str,
    expected_description: str,
    timeout_seconds: int = 900,
    poll_seconds: int = 10,
) -> Dict[str, Any]:
    """Poll video processing details until YouTube confirms publication or terminal error."""
    deadline = time.monotonic() + max(0, timeout_seconds)
    while True:
        response = (
            youtube.videos()
            .list(part="snippet,status,contentDetails,processingDetails", id=video_id)
            .execute()
        )
        items = response.get("items") or []
        if len(items) != 1:
            if time.monotonic() >= deadline:
                raise RuntimeError("La consulta independiente no encontró el video")
            time.sleep(max(1, poll_seconds))
            continue
        item = items[0]
        snippet = item.get("snippet") or {}
        status = item.get("status") or {}
        processing = item.get("processingDetails") or {}
        if snippet.get("channelId") != expected_channel_id:
            raise RuntimeError("El video quedó asociado a otro canal")
        if snippet.get("title") != expected_title or snippet.get("description") != expected_description:
            raise RuntimeError("YouTube confirmó metadata distinta")
        if status.get("privacyStatus") != "public":
            raise RuntimeError("YouTube no confirmó visibility=public")
        upload_status = str(status.get("uploadStatus") or "")
        processing_status = str(processing.get("processingStatus") or "")
        if upload_status in {"failed", "rejected", "deleted"} or processing_status in {"failed", "terminated"}:
            raise RuntimeError("YouTube informó un fallo definitivo de procesamiento")
        if upload_status == "processed" and processing_status in {"", "succeeded"}:
            return item
        if time.monotonic() >= deadline:
            raise RuntimeError("YouTube no confirmó el procesamiento dentro del plazo")
        time.sleep(max(1, poll_seconds))


def _classify_api_upload_error(exc: Exception) -> Exception:
    """Classify Google API error into structured domain exceptions."""
    is_limit = False
    is_quota = False
    status_code = getattr(getattr(exc, "resp", None), "status", None)
    exc_str = str(exc)

    if "uploadLimitExceeded" in exc_str:
        is_limit = True
    elif hasattr(exc, "error_details") and exc.error_details:
        for detail in exc.error_details:
            if isinstance(detail, dict):
                if detail.get("reason") == "uploadLimitExceeded":
                    is_limit = True
                    break
                if detail.get("reason") in ("rateLimitExceeded", "quotaExceeded"):
                    is_quota = True
                    break

    if not is_quota and (
        status_code == 429
        or "rateLimitExceeded" in exc_str
        or "quotaExceeded" in exc_str
        or "RESOURCE_EXHAUSTED" in exc_str
    ):
        is_quota = True

    if is_limit:
        return YouTubeUploadLimitError(f"YouTube daily upload limit exceeded: {exc_str}")
    if is_quota:
        return YouTubeQuotaExceededError(f"YouTube API quota exceeded: {exc_str}")
    return AmbiguousUploadError(
        "La subida API pudo iniciarse pero no devolvió una respuesta inequívoca; no se reintentará automáticamente"
    )


def _validate_api_upload_inputs(
    video_path: str,
    token_path: Optional[str],
    thumbnail_path: Optional[str],
    title: str,
    description: str,
) -> None:
    """Assert invariants on payload, tokens, thumbnail, and localization."""
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError("Video local inexistente")
    if not token_path or not os.path.isfile(token_path):
        raise RuntimeError("El token API explícito del canal no existe")
    if not thumbnail_path or not os.path.isfile(thumbnail_path):
        raise RuntimeError("La miniatura es obligatoria para publicar")
    if not title.strip() or len(title) > 100:
        raise ValueError("El título debe tener entre 1 y 100 caracteres")
    if not description.strip() or len(description) > 5_000:
        raise ValueError("La descripción debe tener entre 1 y 5000 caracteres")
    from src.core.quality import is_spanish_neutral

    if not is_test_environment() and not is_spanish_neutral(f"{title}\n{description}", minimum_words=10):
        raise ValueError("La metadata dirigida no está verificada como español")


def _format_api_success_response(
    video_id: str,
    item: Dict[str, Any],
    thumbnail_confirmed: bool,
    channel: str,
    title: str,
    description: str,
) -> Dict[str, Any]:
    """Package confirmed YouTube video metadata into standard response dictionary."""
    snippet = item.get("snippet") or {}
    status = item.get("status") or {}
    if not thumbnail_confirmed and (snippet.get("thumbnails") or {}).get("default"):
        thumbnail_confirmed = True

    return {
        "status": "PUBLISHED",
        "method": "API",
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": channel,
        "visibility": status.get("privacyStatus"),
        "title": snippet.get("title") or title,
        "description": snippet.get("description") or description,
        "thumbnail_confirmed": thumbnail_confirmed,
        "verified": True,
        "duration": (item.get("contentDetails") or {}).get("duration"),
        "processing_status": "processed",
        "publication_sequence": "videos.insert(public)->persist video_id->thumbnail.set->processing verification",
    }


def upload_video_via_api(
    video_path: str,
    title: str,
    description: str,
    tags: List[str] = None,
    thumbnail_path: Optional[str] = None,
    token_path: Optional[str] = None,
    on_video_id: Callable[[str], None] | None = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Insert PUBLIC video via Data API v3, attach thumbnail, and verify processing."""
    _validate_api_upload_inputs(video_path, token_path, thumbnail_path, title, description)

    import sys
    from googleapiclient.http import MediaFileUpload

    uploader_mod = sys.modules.get("src.youtube.uploader")
    service_fn = getattr(uploader_mod, "_youtube_service", _youtube_service) if uploader_mod else _youtube_service
    verify_fn = getattr(uploader_mod, "_verify_uploaded_video", _verify_uploaded_video) if uploader_mod else _verify_uploaded_video

    youtube = service_fn(str(token_path))
    expected_channel_id = str(kwargs.get("expected_channel_id") or "").strip()
    if expected_channel_id:
        preflight_youtube_api(
            channel=str(kwargs.get("channel") or ""),
            token_path=str(token_path),
            expected_channel_id=expected_channel_id,
        )

    try:
        response = (
            youtube.videos()
            .insert(
                part="snippet,status",
                body={
                    "snippet": {
                        "title": title,
                        "description": description,
                        "tags": tags or [],
                        "categoryId": "24",
                    },
                    "status": {"privacyStatus": "public"},
                },
                media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
            )
            .execute()
        )
    except Exception as exc:
        classified = _classify_api_upload_error(exc)
        raise classified from exc

    video_id = str(response.get("id") or "")
    if not video_id:
        raise RuntimeError("YouTube API no devolvió video_id")
    actual_channel_id = str((response.get("snippet") or {}).get("channelId") or "")
    if not expected_channel_id and actual_channel_id:
        expected_channel_id = actual_channel_id
    if on_video_id:
        on_video_id(video_id)

    thumbnail_confirmed = False
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, resumable=False),
        ).execute()
        thumbnail_confirmed = True
    except Exception as exc:
        logger.warning("YouTube custom thumbnail setting failed: %s", exc)

    try:
        item = verify_fn(
            youtube,
            video_id=video_id,
            expected_channel_id=expected_channel_id,
            expected_title=title,
            expected_description=description,
        )
    except RuntimeError as verify_err:
        logger.warning("Video %s upload unconfirmed: %s", video_id, verify_err)
        return {
            "status": "UPLOAD_UNCONFIRMED",
            "method": "API",
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "channel": str(kwargs.get("channel") or ""),
            "thumbnail_confirmed": thumbnail_confirmed,
            "verified": False,
            "reason": str(verify_err),
            "publication_sequence": "videos.insert(public)->persist video_id->verification_timeout",
        }

    return _format_api_success_response(
        video_id, item, thumbnail_confirmed, str(kwargs.get("channel") or ""), title, description
    )


def verify_existing_video_via_api(
    *,
    video_id: str,
    title: str,
    description: str,
    thumbnail_path: str,
    token_path: str,
    expected_channel_id: str,
    channel: str,
) -> Dict[str, Any]:
    """Verify a Playwright upload and attach thumbnail without reuploading video payload."""
    if not video_id.strip():
        raise RuntimeError("Falta video_id para verificar la publicación")
    if not expected_channel_id.strip():
        raise RuntimeError("Falta el channel_id esperado")
    if not os.path.isfile(token_path) or not os.path.isfile(thumbnail_path):
        raise RuntimeError("Faltan token o miniatura para la verificación")

    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    token_data = json.loads(Path(token_path).read_text(encoding="utf-8"))
    credentials = Credentials(
        token=token_data.get("access_token") or token_data.get("token"),
        refresh_token=token_data.get("refresh_token"),
        token_uri=token_data.get("token_uri", "https://oauth2.googleapis.com/token"),
        client_id=token_data.get("client_id") or GOOGLE_CLIENT_ID,
        client_secret=token_data.get("client_secret") or GOOGLE_CLIENT_SECRET,
    )
    if credentials.expired and credentials.refresh_token:
        credentials.refresh(Request())
        _save_refreshed_credentials(token_path, credentials, token_data)
    youtube = build("youtube", "v3", credentials=credentials, cache_discovery=False)
    mine = youtube.channels().list(part="id", mine=True).execute().get("items") or []
    if len(mine) != 1 or str(mine[0].get("id") or "") != expected_channel_id:
        raise RuntimeError("El token de verificación pertenece a otro canal")

    thumbnail_response = youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumbnail_path, resumable=False),
    ).execute()

    result = youtube.videos().list(part="snippet,status,contentDetails", id=video_id).execute()
    items = result.get("items") or []
    if len(items) != 1:
        raise RuntimeError("La API no confirmó el video publicado")

    item = items[0]
    snippet = item.get("snippet") or {}
    status = item.get("status") or {}
    if snippet.get("channelId") != expected_channel_id:
        raise RuntimeError("La publicación pertenece a otro canal")

    return {
        "status": "PUBLISHED",
        "method": "PLAYWRIGHT+API_VERIFY",
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": channel,
        "visibility": status.get("privacyStatus"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "thumbnail_confirmed": bool(thumbnail_response),
        "verified": True,
        "duration": (item.get("contentDetails") or {}).get("duration"),
    }
