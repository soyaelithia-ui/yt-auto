import os
import re
import sys
import json
import time
import signal
import subprocess
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from src.config import (
    COOKIES_PATH,
    YOUTUBE_TOKEN_PATH,
    TOKEN_CHANNEL2_PATH,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    BASE_DIR,
    is_test_environment
)
try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None
from src.log import get_logger
from src.core.domain import YouTubeQuotaExceededError, YouTubeUploadLimitError

logger = get_logger("youtube_uploader")

_LAST_2FA_ALERT_TIME: float = 0.0
_2FA_ALERT_COOLDOWN_SECONDS: float = 3600.0


def _run_subproc(
    cmd: List[str],
    cwd: Optional[str] = None,
    timeout: float = 300,
    check: bool = False,
    capture_output: bool = True,
    text: bool = True,
    start_new_session: bool = True,
) -> subprocess.CompletedProcess:
    proc = None
    try:
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE if capture_output else None,
            stderr=subprocess.PIPE if capture_output else None,
            text=text,
            start_new_session=start_new_session,
        )
        stdout, stderr = proc.communicate(timeout=timeout)
        res = subprocess.CompletedProcess(cmd, proc.returncode, stdout, stderr)
        if check and res.returncode != 0:
            raise subprocess.CalledProcessError(res.returncode, cmd, output=stdout, stderr=stderr)
        return res
    except subprocess.TimeoutExpired as te:
        if proc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            proc.wait()
        raise


def validate_title_content_alignment(title: str, entity_id: str, script_text: str) -> bool:
    """Validates alignment between YouTube title, entity identifier, and script content."""
    import re
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


def _save_refreshed_credentials(token_path: str, credentials, original_data: dict | None = None) -> None:
    try:
        from src.core.google_auth import save_credentials
        save_credentials(credentials, token_path)
    except Exception as exc:
        logger.warning("Could not persist refreshed OAuth token to %s: %s", token_path, exc)


def _youtube_service(token_path: str):
    if not token_path or not os.path.isfile(token_path):
        raise RuntimeError("El token API explícito del canal no existe")
    from src.core.google_auth import build_youtube_service
    return build_youtube_service(token_path=token_path)


def preflight_youtube_api(
    *,
    channel: str,
    token_path: str,
    expected_channel_id: str,
) -> Dict[str, str]:
    """Read-only proof that the OAuth token belongs to the configured channel."""
    from src.core.domain import canonical_channel

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


def _verify_uploaded_video(
    youtube,
    *,
    video_id: str,
    expected_channel_id: str,
    expected_title: str,
    expected_description: str,
    timeout_seconds: int = 900,
    poll_seconds: int = 10,
) -> Dict[str, Any]:
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
        if upload_status in {"failed", "rejected", "deleted"} or processing_status in {
            "failed",
            "terminated",
        }:
            raise RuntimeError("YouTube informó un fallo definitivo de procesamiento")
        if upload_status == "processed" and processing_status in {"", "succeeded"}:
            return item
        if time.monotonic() >= deadline:
            raise RuntimeError("YouTube no confirmó el procesamiento dentro del plazo")
        time.sleep(max(1, poll_seconds))


def resolve_channel_token_path(channel: str = "terror") -> str:
    from src.core.google_auth import resolve_channel_token_path as _resolve
    return _resolve(channel)


def verify_youtube_credentials_preflight(channel: str) -> tuple[bool, str]:
    """
    Step 0 Pre-Flight Check (< 1 second):
    Validates YouTube OAuth credentials for target channel BEFORE starting LLM, Edge-TTS, or FFmpeg.
    Returns (is_valid: bool, detail_or_auth_url: str).
    """
    if os.environ.get("TEST_MODE") == "1" or os.environ.get(
        "MOCK_YOUTUBE_UPLOAD"
    ) == "1":
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


def format_cookies_for_playwright(cookies: list) -> list:
    """Formats raw cookies for Playwright context.add_cookies()."""
    from src.core.cookies import format_cookies_for_playwright as _fmt
    return _fmt(cookies)


def upload_video_via_api(
    video_path: str,
    title: str,
    description: str,
    tags: List[str] = None,
    thumbnail_path: Optional[str] = None,
    token_path: Optional[str] = None,
    on_video_id: Callable[[str], None] | None = None,
    **kwargs,
) -> Dict[str, Any]:
    """Insert PUBLIC, then attach thumbnail and verify processing.

    YouTube assigns ``video_id`` only after ``videos.insert``. Because PRIVATE is
    forbidden for this route, there is an unavoidable interval where the PUBLIC
    insert exists before thumbnail upload and post-verification. The ID callback
    runs immediately, and every later ambiguity fails closed without reupload.
    """
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

    if not is_spanish_neutral(f"{title}\n{description}", minimum_words=10):
        raise ValueError("La metadata dirigida no está verificada como español")

    from googleapiclient.http import MediaFileUpload
    youtube = _youtube_service(str(token_path))
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
                    # PRIVATE staging is intentionally forbidden by the directed contract.
                    "status": {"privacyStatus": "public"},
                },
                media_body=MediaFileUpload(video_path, chunksize=-1, resumable=True),
            )
            .execute()
        )
    except Exception as exc:
        from src.core.domain import (
            AmbiguousUploadError,
            YouTubeQuotaExceededError,
            YouTubeUploadLimitError,
        )

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
            raise YouTubeUploadLimitError(
                f"YouTube daily upload limit exceeded: {exc_str}"
            ) from exc

        if is_quota:
            raise YouTubeQuotaExceededError(
                f"YouTube API quota exceeded: {exc_str}"
            ) from exc

        raise AmbiguousUploadError(
            "La subida API pudo iniciarse pero no devolvió una respuesta inequívoca; no se reintentará automáticamente"
        ) from exc
    video_id = str(response.get("id") or "")
    if not video_id:
        raise RuntimeError("YouTube API no devolvió video_id")
    actual_channel_id = str((response.get("snippet") or {}).get("channelId") or "")
    if not expected_channel_id and actual_channel_id:
        expected_channel_id = actual_channel_id
    if on_video_id:
        on_video_id(video_id)
    try:
        thumbnail_response = (
            youtube.thumbnails()
            .set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnail_path, resumable=False),
            )
            .execute()
        )
        thumbnail_confirmed = True
    except Exception as exc:
        logger.warning("YouTube custom thumbnail setting failed: %s", exc)
    try:
        item = _verify_uploaded_video(
            youtube,
            video_id=video_id,
            expected_channel_id=expected_channel_id,
            expected_title=title,
            expected_description=description,
        )
    except RuntimeError as verify_err:
        logger.warning(
            "Video %s was uploaded to YouTube, but verification timed out or could not be fully confirmed: %s",
            video_id,
            verify_err,
        )
        return {
            "status": "UPLOAD_UNCONFIRMED",
            "method": "API",
            "video_id": video_id,
            "url": f"https://www.youtube.com/watch?v={video_id}",
            "channel": str(kwargs.get("channel") or ""),
            "thumbnail_confirmed": thumbnail_confirmed,
            "verified": False,
            "reason": str(verify_err),
            "publication_sequence": (
                "videos.insert(public)->persist video_id->verification_timeout"
            ),
        }
    snippet = item.get("snippet") or {}
    status = item.get("status") or {}
    if not thumbnail_confirmed and (snippet.get("thumbnails") or {}).get("default"):
        thumbnail_confirmed = True
    expected_channel = str(kwargs.get("channel") or "")
    return {
        "status": "PUBLISHED",
        "method": "API",
        "video_id": video_id,
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "channel": expected_channel,
        "visibility": status.get("privacyStatus"),
        "title": snippet.get("title"),
        "description": snippet.get("description"),
        "thumbnail_confirmed": thumbnail_confirmed,
        "verified": True,
        "duration": (item.get("contentDetails") or {}).get("duration"),
        "processing_status": "processed",
        "publication_sequence": (
            "videos.insert(public)->persist video_id->thumbnail.set->processing verification"
        ),
    }


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
    """Verify a Playwright upload and set its thumbnail without uploading again."""
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
        token_uri=token_data.get(
            "token_uri", "https://oauth2.googleapis.com/token"
        ),
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
    thumbnail_response = (
        youtube.thumbnails()
        .set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, resumable=False),
        )
        .execute()
    )
    result = (
        youtube.videos()
        .list(part="snippet,status,contentDetails", id=video_id)
        .execute()
    )
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


class PlaywrightPrePublishError(RuntimeError):
    """Raised when Playwright fails before the final publish step (no video published)."""
    pass


def _safe_preupload_failure(error: Exception) -> bool:
    if isinstance(error, PlaywrightPrePublishError):
        return True
    detail = str(error).lower()
    return any(
        marker in detail
        for marker in (
            "cookies are expired",
            "session validation failed",
            "session validation",
            "cookies expiradas",
            "cookies incompletas",
            "cookies inválidas",
            "invalid cookies format",
            "invalid cookies file",
            "cookies file is empty",
            "authentication failed",
            "identity could not be confirmed",
            "no confirmó la identidad",
            "chromium de playwright no está instalado",
            "browsertype.launch",
            "browser failed",
            "cookies file not found",
            "read-only file system",
            "permission denied",
            "browser_data",
            "google identity verification",
            "identity verification",
            "verifica tu identidad",
            "confirmar tu identidad",
            "iron-overlay-backdrop",
            "playwright pre-publish",
        )
    )


def _click_dialog_button(page, selectors: List[str], step_name: str, timeout: int = 15000) -> bool:
    """Helper unificado para buscar y pulsar botones en el modal de subida de YouTube."""
    logger.info(f"Attempting to click button for step: {step_name}...")
    try:
        page.wait_for_selector(", ".join(selectors), timeout=timeout)
    except Exception as e:
        logger.debug(f"Wait for selector timeout for {step_name}: {e}")

    clicked = False
    for selector in selectors:
        try:
            loc = page.locator(selector)
            for i in range(loc.count()):
                el = loc.nth(i)
                if el.is_visible():
                    el.click(force=True)
                    clicked = True
                    break
            if clicked:
                break
        except Exception as e:
            logger.debug(f"Click attempt failed on selector '{selector}': {e}")
    
    if not clicked:
        for selector in selectors:
            try:
                loc = page.locator(selector)
                if loc.count() > 0:
                    loc.first.click(force=True)
                    clicked = True
                    break
            except Exception as e:
                logger.debug(f"Fallback click failed on selector '{selector}': {e}")

    if not clicked:
        raise RuntimeError(f"Could not find or click button for step: {step_name}")
    return True


def click_next(page, logger_inst, step_name):
    selectors = [
        '#next-button',
        'button:has-text("Siguiente")',
        'button:has-text("Next")',
        '#next-button button'
    ]
    _click_dialog_button(page, selectors, f"Next ({step_name})")


def click_done(page, logger_inst):
    selectors = [
        '#done-button',
        'button:has-text("Guardar")',
        'button:has-text("Publicar")',
        'button:has-text("Save")',
        'button:has-text("Publish")',
        '#done-button button'
    ]
    _click_dialog_button(page, selectors, "Done/Publish")


def _get_playwright_pids(pids_before: set = None) -> set:
    if pids_before is None:
        pids_before = set()
    my_pids = {str(os.getpid()), str(os.getppid())} | pids_before
    try:
        res = _run_subproc(["pgrep", "-f", "chromium|chrome-headless-shell|playwright"], text=True, timeout=10)
        out = res.stdout
        raw_pids = set(out.strip().split()) - my_pids
    except (subprocess.SubprocessError, OSError) as exc:
        logger.debug("pgrep failed during pid scanning: %s", exc)
        return set()

    filtered = set()
    for pid in raw_pids:
        try:
            with open(f"/proc/{pid}/cmdline", "r") as f:
                cmd = f.read()
                if "pytest" in cmd or "python" in cmd:
                    continue
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError) as exc:
            logger.debug("Reading proc cmdline for pid %s failed: %s", pid, exc)
        filtered.add(pid)
    return filtered


def upload_video_via_playwright_ts(
    video_path: str,
    title: str,
    description: str,
    tags: List[str] = None,
    cookies_path: str = COOKIES_PATH,
    dry_run: bool = False,
    thumbnail_path: Optional[str] = None,
    expected_identity: Optional[str] = None,
    user_data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Strategy B (TypeScript Native): Invokes Playwright TypeScript uploader service via subprocessing.
    """
    compiled_path = BASE_DIR / "ts_services" / "dist" / "youtube_studio_uploader.js"
    source_path = BASE_DIR / "ts_services" / "src" / "youtube_studio_uploader.ts"
    ts_services_dir = str(BASE_DIR / "ts_services")

    browser_data_dir = user_data_dir or os.environ.get(
        "PLAYWRIGHT_USER_DATA_DIR", "/tmp/browser_data/session"
    )

    if compiled_path.is_file():
        cmd = ["node", str(compiled_path)]
    else:
        ts_node = BASE_DIR / "ts_services" / "node_modules" / ".bin" / "ts-node"
        if not ts_node.is_file() or not source_path.is_file():
            raise FileNotFoundError("Playwright TypeScript uploader is not built")
        cmd = [str(ts_node), str(source_path)]
    cmd.extend([
        "--video", video_path,
        "--title", title,
        "--description", description,
        "--cookies", cookies_path,
        "--user-data-dir", browser_data_dir
    ])
    if tags:
        cmd.extend(["--tags", ",".join(tags)])
    if thumbnail_path:
        cmd.extend(["--thumbnail", thumbnail_path])
    if expected_identity:
        cmd.extend(["--expected-identity", expected_identity])
    if dry_run:
        cmd.append("--dry-run")

    logger.info(f"Executing Playwright TypeScript Uploader for '{title}'...")
    res = _run_subproc(cmd, cwd=ts_services_dir, capture_output=True, text=True, timeout=300, start_new_session=True)

    if res.returncode != 0 and not res.stdout:
        err_msg = res.stderr.strip() or f"TypeScript process exited with code {res.returncode}"
        raise RuntimeError(f"TypeScript Uploader execution failed: {err_msg}")

    try:
        data = json.loads(res.stdout.strip())
        if data.get("status") == "ERROR":
            raise RuntimeError(f"TypeScript Uploader reported error: {data.get('error')}")
        return data
    except json.JSONDecodeError:
        raise RuntimeError(f"Failed to parse stdout from TypeScript Uploader: {res.stdout}")


def upload_video_via_playwright(
    video_path: str,
    title: str,
    description: str,
    tags: List[str] = None,
    cookies_path: str = COOKIES_PATH,
    dry_run: bool = False,
    thumbnail_path: Optional[str] = None,
    expected_identity: Optional[str] = None,
    user_data_dir: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Strategy B: Automation upload via Playwright using channel session cookies.
    Tries native TypeScript Playwright uploader first, falls back to Python sync_playwright if needed.
    """
    if cookies_path and not Path(cookies_path).is_file():
        raise FileNotFoundError(f"Cookies file not found: {cookies_path}")

    if (BASE_DIR / "ts_services").is_dir():
        try:
            return upload_video_via_playwright_ts(
                video_path,
                title,
                description,
                tags=tags,
                cookies_path=cookies_path,
                dry_run=dry_run,
                thumbnail_path=thumbnail_path,
                expected_identity=expected_identity,
                user_data_dir=user_data_dir,
            )
        except FileNotFoundError as ts_err:
            logger.warning(
                "TypeScript Playwright uploader is unavailable (%s); using Python",
                ts_err,
            )
        except Exception:
            # The TypeScript flow may already have selected a file or created a draft.
            # Retrying in another browser would risk a duplicate.
            raise


    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")

    if not os.path.exists(cookies_path):
        raise FileNotFoundError(f"Cookies file not found: {cookies_path}")

    try:
        from src.core.cookies import (
            SessionStatus,
            parse_cookies_file,
            validate_youtube_session_cookies,
        )

        cookies = parse_cookies_file(cookies_path)
    except (FileNotFoundError, OSError):
        raise
    except Exception as e:
        raise ValueError(f"Invalid cookies format in {cookies_path}: {e}") from e

    formatted_cookies = format_cookies_for_playwright(cookies)

    mock_env = os.environ.get("MOCK_YOUTUBE_UPLOAD") == "1"

    if (mock_env or is_test_environment()) and not dry_run:
        return {
            "status": "TEST_MOCK",
            "method": "PLAYWRIGHT",
            "verified": False,
        }

    # Preflight cookie session check to fail fast before launching Chromium
    session_health = validate_youtube_session_cookies(cookies)
    if session_health.status in (SessionStatus.EXPIRED, SessionStatus.INCOMPLETE, SessionStatus.INVALID):
        raise RuntimeError(f"Playwright session validation failed: {session_health.detail}")

    logger.info("Launching headless browser for YouTube upload via Playwright...")
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed or available.")
    
    screenshot_dir = os.environ.get(
        "PLAYWRIGHT_DEBUG_DIR", str(BASE_DIR / "logs" / "debug")
    )
    try:
        os.makedirs(screenshot_dir, exist_ok=True)
    except OSError:
        screenshot_dir = "/tmp/debug"
        os.makedirs(screenshot_dir, exist_ok=True)
    
    pids_before = _get_playwright_pids()

    if not user_data_dir:
        channel_name = "default"
        if cookies_path:
            cp_str = str(cookies_path).lower()
            if "aelithia" in cp_str:
                channel_name = "aelithia"
            elif "moku" in cp_str or "cookies.json" in cp_str:
                channel_name = "moku"
        browser_profile_dir = os.environ.get(
            "PLAYWRIGHT_USER_DATA_DIR", str(BASE_DIR / "data" / "browser_profiles" / channel_name)
        )
    else:
        browser_profile_dir = user_data_dir
    os.makedirs(browser_profile_dir, exist_ok=True)

    try:
        with sync_playwright() as p:
            browser = None
            context = None
            page = None
            video_published = False
            try:
                try:
                    modern_ua = (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/131.0.0.0 Safari/537.36"
                    )
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=browser_profile_dir,
                        headless=True,
                        user_agent=modern_ua,
                        viewport={"width": 1280, "height": 720},
                        args=[
                            "--disable-blink-features=AutomationControlled",
                            "--no-sandbox",
                            "--disable-dev-shm-usage",
                        ],
                    )
                    context.add_init_script("""
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """)
                except Exception as launch_err:
                    if "playwright install" in str(launch_err).lower() or "executable" in str(launch_err).lower():
                        raise RuntimeError(
                            "Chromium de Playwright no está instalado en la imagen"
                        ) from launch_err
                    else:
                        raise launch_err

                if formatted_cookies:
                    try:
                        context.add_cookies(formatted_cookies)
                    except Exception as cookie_err:
                        logger.debug("Persistent context cookie seeding: %s", cookie_err)

                page = context.pages[0] if context.pages else context.new_page()
                
                # 1. Navigate to upload page
                logger.info("Navigating to https://youtube.com/upload...")
                page.goto("https://youtube.com/upload")
                page.wait_for_timeout(5000)
                
                page.screenshot(path=f"{screenshot_dir}/1_loaded.png")
                
                if "accounts.google.com" in page.url:
                    raise RuntimeError("Authentication failed. Cookies are expired or invalid.")
                identity_candidates = [
                    value.strip().lower().lstrip("@")
                    for value in str(expected_identity or "").split("|")
                    if value.strip()
                ]
                if not identity_candidates:
                    raise RuntimeError(
                        "Falta la identidad pública esperada para Playwright"
                    )
                visible_identity = (
                    page.locator("body").inner_text().lower()
                    + " "
                    + page.url.lower()
                )
                for selector in ("#avatar-btn", "[aria-label*='Account']", "[aria-label*='Cuenta']"):
                    locator = page.locator(selector)
                    if locator.count() > 0:
                        for attribute in ("aria-label", "title"):
                            visible_identity += " " + str(
                                locator.first.get_attribute(attribute) or ""
                            ).lower()
                if not any(
                    candidate in visible_identity for candidate in identity_candidates
                ):
                    raise RuntimeError(
                        "Playwright no confirmó la identidad del canal autenticado"
                    )
                    
                if dry_run:
                    return {
                        "status": "DRY_RUN",
                        "method": "PLAYWRIGHT",
                    }
                    
                # 2. Upload video
                logger.info("Uploading video file...")
                page.wait_for_selector('input[type="file"]', state="attached", timeout=30000)
                file_input = page.locator('input[type="file"]')
                file_input.set_input_files(video_path)
                page.wait_for_timeout(5000)
                page.screenshot(path=f"{screenshot_dir}/2_uploaded.png")
                
                # Check if Google Identity Verification modal appeared
                page.wait_for_timeout(3000)
                if page.locator('text=Verifica tu identidad').count() > 0 or page.locator('text=Confirmar tu identidad').count() > 0:
                    logger.warning("Google Identity Verification (2FA) detected.")
                    page.screenshot(path=f"{screenshot_dir}/identity_verification_error.png")
                    dialog = page.locator(
                        'tp-yt-paper-dialog, ytcp-dialog, ytcp-confirmation-dialog, [role="dialog"]'
                    ).filter(has_text=re.compile(r"Verifica tu identidad|Confirmar tu identidad|Verify your identity", re.I))
                    modal_btn = dialog.locator('#confirm-button button, ytcp-button:has-text("Siguiente") button, button:has-text("Siguiente"), button:has-text("Next"), #confirm-button')
                    if modal_btn.count() > 0:
                        next_btn = modal_btn.first
                    else:
                        next_btn = page.locator('#confirm-button button, ytcp-button:has-text("Siguiente") button, button:has-text("Siguiente"), button:has-text("Next")').last

                    if next_btn.count() > 0:
                        logger.info("Clicking 'Siguiente' on Identity Verification modal to trigger 2FA notification...")
                        global _LAST_2FA_ALERT_TIME
                        _now = time.time()
                        if _now - _LAST_2FA_ALERT_TIME > _2FA_ALERT_COOLDOWN_SECONDS:
                            _LAST_2FA_ALERT_TIME = _now
                            try:
                                from review.telegram_bot import send_telegram_message
                                send_telegram_message(
                                    "⚠️ *Google solicita verificación 2FA para publicar vía sesión web (Playwright).* "
                                    "Por favor confirma en tu teléfono ahora."
                                )
                            except Exception:
                                pass
                        
                        popup_holder = []
                        context.on("page", lambda new_p: popup_holder.append(new_p))
                        next_btn.click()
                        page.wait_for_timeout(4000)
                        page.screenshot(path=f"{screenshot_dir}/identity_verification_challenge.png")
                        
                        # Check if popup was opened
                        popup_page = popup_holder[0] if popup_holder else (context.pages[1] if len(context.pages) > 1 else None)
                        if popup_page:
                            try:
                                popup_page.wait_for_load_state("domcontentloaded", timeout=10000)
                                popup_page.screenshot(path=f"{screenshot_dir}/popup_auth_challenge.png")
                            except Exception:
                                pass

                        # Wait up to 180s (3 minutes) for user to verify on phone
                        verified = False
                        for wait_iter in range(36):
                            page.wait_for_timeout(5000)
                            # Check if modal is gone or if any dialog is closed
                            if page.locator('text=Verifica tu identidad').count() == 0 and page.locator('text=Confirmar tu identidad').count() == 0:
                                verified = True
                                logger.info("2FA Verification passed successfully! Proceeding with upload...")
                                break
                            if popup_page and popup_page.is_closed():
                                page.wait_for_timeout(3000)
                                if page.locator('text=Verifica tu identidad').count() == 0 and page.locator('text=Confirmar tu identidad').count() == 0:
                                    verified = True
                                    logger.info("2FA Popup closed and modal cleared! Proceeding with upload...")
                                    break
                            if wait_iter % 6 == 0:
                                logger.info("Still waiting for 2FA phone confirmation... (%d/180s elapsed)", wait_iter * 5)
                        if not verified:
                            raise PlaywrightPrePublishError("Google Identity Verification (2FA) blocked the upload. Timeout waiting for phone confirmation.")
                    else:
                        raise PlaywrightPrePublishError("Google Identity Verification (2FA) blocked the upload. Please verify on your phone or try again later.")

                # 3. Fill Metadata
                logger.info("Filling metadata...")
                page.wait_for_selector('#textbox', timeout=60000)
                
                title_box = page.locator('#textbox').first
                title_box.click(force=True)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                title_box.fill(title[:100])
                
                desc_box = page.locator('#textbox').nth(1)
                desc_box.click(force=True)
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                desc_box.fill(description[:5000])

                if not thumbnail_path or not os.path.isfile(thumbnail_path):
                    raise RuntimeError("La miniatura es obligatoria para publicar")
                thumbnail_input = page.locator(
                    'input[type="file"][accept*="image"]'
                )
                if thumbnail_input.count() < 1:
                    raise RuntimeError(
                        "YouTube Studio no expuso el control de miniatura"
                    )
                thumbnail_input.first.set_input_files(thumbnail_path)
                page.wait_for_timeout(2000)
                
                # 4. Select Not Made for Kids
                logger.info("Selecting Not Made for Kids...")
                kids_radio = None
                selectors = [
                    'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
                    'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MADE_FOR_KIDS"]',
                    'tp-yt-paper-radio-button:has-text("No, no es contenido")',
                    'tp-yt-paper-radio-button:has-text("No, it\'s not made for kids")'
                ]
                for sel in selectors:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            kids_radio = loc.first
                            break
                    except Exception as e:
                        logger.debug(f"Radio button selector '{sel}' failed: {e}")
                if not kids_radio:
                    kids_radio = page.locator('tp-yt-paper-radio-button').nth(1)
                    
                kids_radio.scroll_into_view_if_needed()
                kids_radio.click(force=True)
                page.wait_for_timeout(1000)
                page.screenshot(path=f"{screenshot_dir}/3_metadata.png")
                
                # 5. Next -> Video Elements
                click_next(page, logger, "Video Elements")
                page.wait_for_timeout(2000)
                page.screenshot(path=f"{screenshot_dir}/4_elements.png")
                
                # 6. Next -> Checks
                click_next(page, logger, "Checks")
                page.wait_for_timeout(2000)
                page.screenshot(path=f"{screenshot_dir}/5_checks.png")
                
                # 7. Next -> Visibility
                click_next(page, logger, "Visibility")
                page.wait_for_timeout(2000)
                page.screenshot(path=f"{screenshot_dir}/6_visibility.png")
                
                # 8. Select PUBLIC
                logger.info("Selecting Visibility as PUBLIC...")
                public_radio = None
                selectors = [
                    'tp-yt-paper-radio-button[name="PUBLIC"]',
                    'tp-yt-paper-radio-button:has-text("Público")',
                    'tp-yt-paper-radio-button:has-text("Public")'
                ]
                for sel in selectors:
                    try:
                        loc = page.locator(sel)
                        if loc.count() > 0:
                            public_radio = loc.first
                            break
                    except Exception as e:
                        logger.debug(f"Public radio selector '{sel}' failed: {e}")
                if not public_radio:
                    public_radio = page.locator('tp-yt-paper-radio-button').first
                    
                public_radio.click(force=True)
                page.wait_for_timeout(1000)
                page.screenshot(path=f"{screenshot_dir}/7_public_selected.png")
                
                video_url = ""
                try:
                    link_element = page.locator('a.style-scope.ytcp-video-info')
                    if link_element.count() > 0:
                        video_url = link_element.first.get_attribute("href")
                except Exception as e:
                    logger.debug(f"Failed to get video URL element: {e}")
                    
                # 9. Click done
                click_done(page, logger)
                video_published = True
                page.wait_for_timeout(10000)
                page.screenshot(path=f"{screenshot_dir}/8_published.png")
                
                if not video_url:
                    return {
                        "status": "UPLOAD_UNCONFIRMED",
                        "method": "PLAYWRIGHT",
                        "reason": "YouTube Studio no expuso una URL verificable",
                        "verified": False,
                    }
                from urllib.parse import parse_qs, urlparse

                video_id = parse_qs(urlparse(video_url).query).get("v", [""])[0]
                return {
                    "status": "UPLOAD_UNCONFIRMED",
                    "method": "PLAYWRIGHT",
                    "video_id": video_id or None,
                    "url": video_url,
                    "verified": False,
                }
            except Exception as upload_exc:
                if not video_published:
                    logger.warning(
                        "Playwright upload error occurred before publish confirmation: %s",
                        upload_exc,
                    )
                    if not isinstance(upload_exc, PlaywrightPrePublishError):
                        raise PlaywrightPrePublishError(
                            f"Playwright pre-publish failed: {upload_exc}"
                        ) from upload_exc
                raise
            finally:
                if page:
                    try:
                        page.close()
                    except Exception as page_err:
                        logger.warning(f"Error closing page: {page_err}")
                if context:
                    try:
                        if cookies_path and os.path.exists(cookies_path):
                            rotated = context.cookies()
                            if rotated:
                                from src.core.cookies import save_cookies_to_file
                                save_cookies_to_file(rotated, cookies_path)
                                logger.info(
                                    "Persisted %d rotated session cookies back to %s",
                                    len(rotated),
                                    cookies_path,
                                )
                    except Exception as save_err:
                        logger.debug("Failed to persist rotated cookies: %s", save_err)
                    try:
                        context.close()
                    except Exception as ctx_err:
                        logger.warning(f"Error closing browser context: {ctx_err}")
                if browser:
                    try:
                        browser.close()
                    except Exception as close_err:
                        logger.warning(f"Error closing browser: {close_err}")
    finally:
        # Process teardown synchronization AFTER sync_playwright() context manager exits
        deadline = time.time() + 3.0
        while time.time() < deadline:
            try:
                while True:
                    wpid, _ = os.waitpid(-1, os.WNOHANG)
                    if wpid == 0:
                        break
            except (ChildProcessError, OSError) as exc:
                logger.debug("waitpid child process clean: %s", exc)

            current_pids = _get_playwright_pids(pids_before)
            if not current_pids:
                break
            time.sleep(0.05)

        lingering = _get_playwright_pids(pids_before)
        if lingering:
            logger.warning(
                "Playwright dejó procesos hijos etiquetados; no se aplicó un kill amplio"
            )


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
    if normalized.get("status") in {"DRY_RUN", "TEST_MOCK"}:
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


def upload_video(
    video_path: str,
    title: str,
    description: str,
    tags: List[str] = None,
    cookies_path: str | None = None,
    dry_run: bool = False,
    channel: str = "terror",
    thumbnail_path: Optional[str] = None,
    token_path: Optional[str] = None,
    api_only: bool = False,
    expected_channel_id: str | None = None,
    on_video_id: Callable[[str], None] | None = None,
    job_id: Optional[str] = None,
    version: int = 1,
) -> Dict[str, Any]:
    """Try Playwright cookies first, then the explicitly selected channel API token."""
    channel = channel or "terror"
    if not video_path or not os.path.isfile(video_path):
        raise FileNotFoundError("Video local inexistente")
    if not thumbnail_path or not os.path.isfile(thumbnail_path):
        cand = Path(video_path).parent / "thumbnail.jpg"
        if cand.is_file():
            thumbnail_path = str(cand)
    if not is_test_environment() and (not str(job_id or "").strip() or version <= 0):
        raise RuntimeError(
            "Publication gate requires job_id and a positive version before YouTube upload"
        )

    # The canonical ReviewJobManager owns the single atomic publication claim.
    # Direct pipeline calls may claim APPROVED jobs; the review daemon invokes
    # this function only after the core has already moved the job to PUBLISHING.
    claimed_job_id: Optional[str] = None
    claimed_version: Optional[int] = None
    unsafe_gate_bypass = bool(os.environ.get("SKIP_PUBLICATION_GATE_FOR_TESTS"))
    if unsafe_gate_bypass and not is_test_environment():
        raise RuntimeError(
            "SKIP_PUBLICATION_GATE_FOR_TESTS is rejected outside a test environment"
        )
    if unsafe_gate_bypass:
        logger.critical(
            "Publication gate BYPASSED via SKIP_PUBLICATION_GATE_FOR_TESTS "
            "(test environment detected)"
        )
    if not unsafe_gate_bypass:
        from review import PublicationGate, ReviewStateStore
        from review.db import get_db_connection
        from review.review_manager import ReviewStatus

        _store = ReviewStateStore()
        target_job_id = job_id
        if not target_job_id:
            if not is_test_environment():
                raise RuntimeError(
                    "Publication gate requires job_id and version; path lookup is disabled"
                )
            with get_db_connection(_store.db_path) as _conn:
                _cur = _conn.execute(
                    "SELECT job_id, version FROM review_jobs "
                    "WHERE original_video_path = ? ORDER BY version DESC LIMIT 1",
                    (os.path.realpath(video_path),),
                )
                _row = _cur.fetchone()
                if _row:
                    target_job_id, version = _row["job_id"], _row["version"]

        if target_job_id:
            _gate = PublicationGate(_store)
            _job = _store.get_job(target_job_id, version)
            if not _job:
                raise RuntimeError(
                    f"Publication gate job not found: {target_job_id} v{version}"
                )
            if _job.status == ReviewStatus.APPROVED.value:
                _gate.verify_and_claim_publication(
                    target_job_id, version, video_path
                )
                claimed_job_id, claimed_version = target_job_id, version
            elif _job.status != ReviewStatus.PUBLISHING.value:
                raise RuntimeError(
                    f"Publication gate is not approved for {target_job_id} v{version}: "
                    f"{_job.status}"
                )

    def _finalize_result(normalized: Dict[str, Any]) -> Dict[str, Any]:
        """Consume a direct pipeline claim after verified publication."""
        if (
            claimed_job_id
            and str(normalized.get("status") or "").upper() == "PUBLISHED"
            and normalized.get("verified") is True
        ):
            try:
                _gate.confirm_publication_success(
                    claimed_job_id,
                    claimed_version or 1,
                    published_id=normalized.get("video_id"),
                    published_url=normalized.get("url"),
                )
            except Exception as exc:
                logger.error(
                    "Publication claim could not be consumed for %s: %s",
                    claimed_job_id,
                    exc,
                )
        return normalized

    from src.branding import get_channel_branding
    from src.config import get_channel_settings

    branding = get_channel_branding(channel)
    settings = get_channel_settings(channel)
    channel_key = branding.channel_key
    effective_tags = tags or branding.tags
    effective_description = description or branding.generate_description(title)
    effective_cookies = cookies_path or str(settings.cookies_path)
    effective_token = token_path or str(settings.youtube_token_path)

    mock = os.environ.get("TEST_MODE") == "1" or os.environ.get(
        "MOCK_YOUTUBE_UPLOAD"
    ) == "1"
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
    if not dry_run:
        from lib.video import validate_video_format

        validate_video_format(video_path, min_duration=0.0)

    if api_only:
        expected_id = str(
            expected_channel_id or settings.expected_youtube_channel_id or ""
        ).strip()
        preflight_youtube_api(
            channel=channel_key,
            token_path=effective_token,
            expected_channel_id=expected_id,
        )
        result = upload_video_via_api(
            video_path,
            title,
            effective_description,
            effective_tags,
            thumbnail_path=thumbnail_path,
            token_path=effective_token,
            channel=channel_key,
            expected_channel_id=expected_id,
            on_video_id=on_video_id,
        )
        return _finalize_result(
            _normalize_upload_result(
                result,
                method="API",
                channel=channel_key,
                title=title,
                description=effective_description,
            )
        )

    api_quota_error: Optional[YouTubeQuotaExceededError] = None
    if not dry_run and os.path.isfile(effective_token):
        try:
            result = upload_video_via_api(
                video_path,
                title,
                effective_description,
                effective_tags,
                thumbnail_path=thumbnail_path,
                token_path=effective_token,
                channel=channel_key,
                expected_channel_id=settings.expected_youtube_channel_id,
                on_video_id=on_video_id,
            )
            return _finalize_result(
                _normalize_upload_result(
                    result,
                    method="API",
                    channel=channel_key,
                    title=title,
                    description=effective_description,
                )
            )
        except YouTubeUploadLimitError as limit_err:
            logger.warning(
                "YouTube daily upload limit reached for channel %s: %s",
                channel_key,
                limit_err,
            )
            return {
                "status": "WAITING_YOUTUBE_LIMIT",
                "method": "API",
                "reason": str(limit_err),
                "retry_after_seconds": 14400,
                "verified": False,
            }
        except YouTubeQuotaExceededError as quota_err:
            api_quota_error = quota_err
            if not api_only and os.path.isfile(effective_cookies):
                logger.info(
                    "YouTube API quota exceeded for channel %s; falling back to Playwright session upload: %s",
                    channel_key,
                    quota_err,
                )
            else:
                logger.warning(
                    "YouTube API quota exceeded for channel %s and Playwright fallback unavailable (api_only=%s, cookies=%s): %s",
                    channel_key,
                    api_only,
                    os.path.isfile(effective_cookies),
                    quota_err,
                )
                return {
                    "status": "WAITING_YOUTUBE_LIMIT",
                    "method": "API",
                    "reason": str(quota_err),
                    "retry_after_seconds": 3600,
                    "verified": False,
                }
        except Exception as api_error:
            logger.error(
                "YouTube API upload failed; refusing Playwright fallback to avoid duplicates: %s",
                api_error,
            )
            return {
                "status": "UPLOAD_UNCONFIRMED",
                "method": "API",
                "reason": "YouTube API upload failed; manual reconciliation required",
                "verified": False,
            }

    playwright_error: Exception | None = None
    if os.path.isfile(effective_cookies):
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
            )
            if dry_run:
                return {"status": "DRY_RUN", "method": "PLAYWRIGHT"}
            return _finalize_result(
                _normalize_upload_result(
                    result,
                    method="PLAYWRIGHT",
                    channel=channel_key,
                    title=title,
                    description=effective_description,
                )
            )
        except Exception as exc:
            playwright_error = exc
            logger.error("Playwright upload execution failed: %s", exc, exc_info=True)

    if playwright_error and not _safe_preupload_failure(playwright_error):
        logger.error(
            "Playwright failure considered unconfirmed/ambiguous: %s",
            playwright_error,
        )
        return {
            "status": "UPLOAD_UNCONFIRMED",
            "method": "PLAYWRIGHT",
            "reason": (
                "Playwright falló después de un punto ambiguo; no se intentará "
                "otra subida automáticamente"
            ),
            "verified": False,
        }
    if dry_run:
        return {"status": "DRY_RUN", "method": "NONE"}
    if playwright_error:
        if api_quota_error is not None:
            logger.warning(
                "YouTube API quota was exceeded and Playwright fallback failed before upload for channel %s (%s); deferring until quota reset",
                channel_key,
                playwright_error,
            )
            return {
                "status": "WAITING_YOUTUBE_LIMIT",
                "method": "API",
                "reason": f"Quota exceeded and Playwright fallback unavailable: {playwright_error}",
                "retry_after_seconds": 3600,
                "verified": False,
            }
        raise RuntimeError(
            "Playwright falló y no hay token API válido; los artefactos se preservan"
        ) from playwright_error
    raise RuntimeError("No hay cookies ni token del canal seleccionado")
