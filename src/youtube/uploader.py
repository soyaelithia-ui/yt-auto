import os
import sys
import json
import time
import signal
import subprocess
from typing import Optional, List, Dict, Any, Callable
from pathlib import Path
from src.config import (
    DECRYPTED_COOKIES_PATH,
    COOKIES_CHANNEL2_PATH,
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

logger = get_logger("youtube_uploader")


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


def _save_refreshed_credentials(token_path: str, credentials, original_data: dict) -> None:
    try:
        updated = dict(original_data)
        if credentials.token:
            updated["access_token"] = credentials.token
            updated["token"] = credentials.token
        if credentials.refresh_token:
            updated["refresh_token"] = credentials.refresh_token
        if credentials.expiry:
            updated["expiry"] = credentials.expiry.isoformat()
        Path(token_path).write_text(json.dumps(updated, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.warning("Could not persist refreshed OAuth token to %s: %s", token_path, exc)


def _youtube_service(token_path: str):
    if not token_path or not os.path.isfile(token_path):
        raise RuntimeError("El token API explícito del canal no existe")
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

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
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


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
            raise RuntimeError("La consulta independiente no encontró el video")
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
    from src.branding import resolve_channel_key
    c_key = resolve_channel_key(channel)
    if c_key == "aelithia":
        env_override = os.environ.get("TOKEN_CHANNEL2_PATH") or os.environ.get("YOUTUBE_TOKEN_CHANNEL2_PATH")
        if env_override:
            return env_override

        if TOKEN_CHANNEL2_PATH and not os.path.exists(TOKEN_CHANNEL2_PATH):
            return TOKEN_CHANNEL2_PATH

        t_ael = str(BASE_DIR / "secrets" / "youtube_token_aelithia.json")
        if os.path.exists(t_ael):
            return t_ael

        t_malo = str(BASE_DIR / "secrets" / "youtube_token_soy_el_malo.json")
        if os.path.exists(t_malo):
            return t_malo

        return TOKEN_CHANNEL2_PATH or t_ael
    return YOUTUBE_TOKEN_PATH


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
    """
    Formats raw cookies (e.g. from Chrome extension or decrypted_cookies.json)
    for Playwright context.add_cookies().
    """
    formatted = []
    if not isinstance(cookies, list):
        return formatted

    for c in cookies:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            continue

        domain = c.get("domain", ".youtube.com")
        if domain and not domain.startswith("."):
            domain = "." + domain

        fc = {
            "name": str(c["name"]),
            "value": str(c["value"]),
            "domain": domain,
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }

        if "expirationDate" in c and c["expirationDate"] is not None:
            try:
                fc["expires"] = float(c["expirationDate"])
            except (ValueError, TypeError):
                pass
        elif "expires" in c and c["expires"] is not None:
            try:
                fc["expires"] = float(c["expires"])
            except (ValueError, TypeError):
                pass

        same_site = c.get("sameSite")
        if same_site is not None:
            s_str = str(same_site).lower()
            if s_str in ("strict",):
                fc["sameSite"] = "Strict"
            elif s_str in ("none", "no_restriction"):
                fc["sameSite"] = "None"
            else:
                fc["sameSite"] = "Lax"

        formatted.append(fc)

    return formatted


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
        from src.core.domain import AmbiguousUploadError

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
        thumbnail_confirmed = False
    item = _verify_uploaded_video(
        youtube,
        video_id=video_id,
        expected_channel_id=expected_channel_id,
        expected_title=title,
        expected_description=description,
    )
    snippet = item.get("snippet") or {}
    status = item.get("status") or {}
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


def _safe_preupload_failure(error: Exception) -> bool:
    detail = str(error).lower()
    return any(
        marker in detail
        for marker in (
            "cookies are expired",
            "authentication failed",
            "identity could not be confirmed",
            "no confirmó la identidad",
            "chromium de playwright no está instalado",
            "browsertype.launch",
            "browser failed",
            "cookies file not found",
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
    cookies_path: str = DECRYPTED_COOKIES_PATH,
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

    browser_data_dir = user_data_dir or str(BASE_DIR / "browser_data" / "session")

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
    cookies_path: str = DECRYPTED_COOKIES_PATH,
    dry_run: bool = False,
    thumbnail_path: Optional[str] = None,
    expected_identity: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Strategy B: Automation upload via Playwright using decrypted cookies.
    Tries native TypeScript Playwright uploader first, falls back to Python sync_playwright if needed.
    """
    if cookies_path and not Path(cookies_path).is_file():
        raise FileNotFoundError(f"Cookies file not found: {cookies_path}")

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
        with open(cookies_path, "r", encoding="utf-8") as f:
            cookies = json.load(f)
    except Exception as e:
        raise ValueError(f"Invalid JSON in cookies file: {e}")

    if not cookies or not isinstance(cookies, list):
        raise ValueError("Invalid cookies format in decrypted_cookies.json")

    formatted_cookies = format_cookies_for_playwright(cookies)

    mock_env = os.environ.get("MOCK_YOUTUBE_UPLOAD") == "1"

    if (mock_env or is_test_environment()) and not dry_run:
        return {
            "status": "TEST_MOCK",
            "method": "PLAYWRIGHT",
            "verified": False,
        }

    logger.info("Launching headless browser for YouTube upload via Playwright...")
    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed or available.")
    
    screenshot_dir = str(BASE_DIR / "logs" / "debug")
    os.makedirs(screenshot_dir, exist_ok=True)
    
    pids_before = _get_playwright_pids()

    try:
        with sync_playwright() as p:
            browser = None
            context = None
            page = None
            try:
                try:
                    browser = p.chromium.launch(headless=True)
                except Exception as launch_err:
                    if "playwright install" in str(launch_err).lower() or "executable" in str(launch_err).lower():
                        raise RuntimeError(
                            "Chromium de Playwright no está instalado en la imagen"
                        ) from launch_err
                    else:
                        raise launch_err
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 720}
                )
                context.add_cookies(formatted_cookies)
                
                page = context.new_page()
                
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
                visible_identity = page.locator("body").inner_text().lower()
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
                    page.screenshot(path=f"{screenshot_dir}/identity_verification_error.png")
                    raise RuntimeError("Google Identity Verification (2FA) blocked the upload. Please verify on your phone or try again later.")

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
            finally:
                if page:
                    try:
                        page.close()
                    except Exception as page_err:
                        logger.warning(f"Error closing page: {page_err}")
                if context:
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
        from src.video import validate_video_format

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
                expected_identity=f"{settings.public_name}|{settings.handle}",
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

    if playwright_error and not _safe_preupload_failure(playwright_error):
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
        raise RuntimeError(
            "Playwright falló y no hay token API válido; los artefactos se preservan"
        ) from playwright_error
    raise RuntimeError("No hay cookies ni token del canal seleccionado")
