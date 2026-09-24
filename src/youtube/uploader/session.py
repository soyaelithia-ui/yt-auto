"""Playwright browser-based upload session module.

Decomposes YouTube Studio web uploads into 6 discrete, linear stages
strictly conforming to the <= 100 executable lines per function budget.
Zero-Browser policy: Playwright imports restricted exclusively to src/youtube/.
"""

from __future__ import annotations

import json
import os
import random
import re
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None

from src.config import BASE_DIR, COOKIES_PATH, is_test_environment
from src.log import get_logger

logger = get_logger("youtube_uploader.session")

_LAST_2FA_ALERT_TIME: float = 0.0
_2FA_ALERT_COOLDOWN_SECONDS: float = 3600.0


class PlaywrightPrePublishError(RuntimeError):
    """Raised when Playwright fails before the final publish step (no video published)."""
    pass


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
    except subprocess.TimeoutExpired:
        if proc:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except Exception:
                pass
            proc.wait()
        raise


def format_cookies_for_playwright(cookies: list) -> list:
    """Formats raw cookies for Playwright context.add_cookies()."""
    from src.core.cookies import format_cookies_for_playwright as _fmt
    return _fmt(cookies)


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


def _click_dialog_button(page: Any, selectors: List[str], step_name: str, timeout: int = 15000) -> bool:
    """Helper searching and clicking dialog buttons with fallback."""
    logger.info("Attempting to click button for step: %s...", step_name)
    try:
        page.wait_for_selector(", ".join(selectors), timeout=timeout)
    except Exception as e:
        logger.debug("Wait for selector timeout for %s: %s", step_name, e)

    clicked = False
    for selector in selectors:
        try:
            loc = page.locator(selector)
            cnt = int(loc.count()) if isinstance(loc.count(), (int, float)) else 0
            for i in range(cnt):
                el = loc.nth(i)
                if el.is_visible():
                    el.click(force=True)
                    clicked = True
                    break
            if clicked:
                break
        except Exception as e:
            logger.debug("Click attempt failed on selector '%s': %s", selector, e)

    if not clicked:
        for selector in selectors:
            try:
                loc = page.locator(selector)
                cnt = int(loc.count()) if isinstance(loc.count(), (int, float)) else 0
                if cnt > 0:
                    loc.first.click(force=True)
                    clicked = True
                    break
            except Exception as e:
                logger.debug("Fallback click failed on selector '%s': %s", selector, e)

    if not clicked:
        raise RuntimeError(f"Could not find or click button for step: {step_name}")
    return True


def click_next(page: Any, logger_inst: Any = None, step_name: str = "") -> None:
    selectors = [
        '#next-button button',
        'ytcp-button#next-button',
        '#next-button',
        'ytcp-button:has-text("Siguiente")',
        'button:has-text("Siguiente")',
        'button:has-text("Next")',
    ]
    _click_dialog_button(page, selectors, f"Next ({step_name})")


def click_done(page: Any, logger_inst: Any = None) -> None:
    selectors = [
        '#done-button button',
        'ytcp-button#done-button',
        '#done-button',
        'ytcp-button:has-text("Publicar")',
        'ytcp-button:has-text("Guardar")',
        'button:has-text("Publicar")',
        'button:has-text("Guardar")',
        'button:has-text("Save")',
        'button:has-text("Publish")',
    ]
    _click_dialog_button(page, selectors, "Done/Publish")


def _get_playwright_pids(pids_before: set = None) -> set:
    if pids_before is None:
        pids_before = set()
    my_pids = {str(os.getpid()), str(os.getppid())} | pids_before
    try:
        res = _run_subproc(["pgrep", "-f", "chromium|chrome-headless-shell|playwright"], text=True, timeout=10)
        raw_pids = set(res.stdout.strip().split()) - my_pids
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
        except (FileNotFoundError, PermissionError, ProcessLookupError, OSError):
            continue
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
    """Strategy B (TypeScript Native): Invokes Playwright TypeScript uploader service."""
    compiled_path = BASE_DIR / "ts_services" / "dist" / "youtube_studio_uploader.js"
    source_path = BASE_DIR / "ts_services" / "src" / "youtube_studio_uploader.ts"
    ts_services_dir = str(BASE_DIR / "ts_services")
    browser_data_dir = user_data_dir or os.environ.get("PLAYWRIGHT_USER_DATA_DIR", "/tmp/browser_data/session")

    if compiled_path.is_file():
        cmd = ["node", str(compiled_path)]
    else:
        ts_node = BASE_DIR / "ts_services" / "node_modules" / ".bin" / "ts-node"
        if not ts_node.is_file() or not source_path.is_file():
            raise FileNotFoundError("Playwright TypeScript uploader is not built")
        cmd = [str(ts_node), str(source_path)]

    cmd.extend([
        "--video", video_path, "--title", title, "--description", description,
        "--cookies", cookies_path, "--user-data-dir", browser_data_dir,
    ])
    if tags:
        cmd.extend(["--tags", ",".join(tags)])
    if thumbnail_path:
        cmd.extend(["--thumbnail", thumbnail_path])
    if expected_identity:
        cmd.extend(["--expected-identity", expected_identity])
    if dry_run:
        cmd.append("--dry-run")

    logger.info("Executing Playwright TypeScript Uploader for '%s'...", title)
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


# ==============================================================================
# 6 Linear Stage Functions (strictly <= 100 executable lines each)
# ==============================================================================

def _init_playwright_context(
    playwright: Any,
    cookies_path: str,
    channel: str = "default",
    headless: bool = True,
    user_data_dir: Optional[str] = None,
) -> tuple[Any, Any, Any]:
    """Stage 1: Launch Chromium persistent context and add normalized session cookies."""
    if not user_data_dir:
        channel_name = channel or "default"
        if cookies_path:
            cp_str = str(cookies_path).lower()
            if "drama" in cp_str or "aelithia" in cp_str:
                channel_name = "drama"
            elif "horror" in cp_str or "moku" in cp_str or "cookies.json" in cp_str:
                channel_name = "horror"
        browser_profile_dir = os.environ.get(
            "PLAYWRIGHT_USER_DATA_DIR", str(BASE_DIR / "data" / "browser_profiles" / channel_name)
        )
    else:
        browser_profile_dir = user_data_dir
    os.makedirs(browser_profile_dir, exist_ok=True)

    modern_ua = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )
    try:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=browser_profile_dir,
            headless=headless,
            user_agent=modern_ua,
            viewport={"width": 1280, "height": 720},
            args=[
                "--headless=new",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-dev-shm-usage",
            ],
        )
    except Exception as launch_err:
        if "playwright install" in str(launch_err).lower() or "executable" in str(launch_err).lower():
            raise RuntimeError("Chromium de Playwright no está instalado en la imagen") from launch_err
        raise launch_err

    if cookies_path and os.path.isfile(cookies_path):
        from src.core.cookies import parse_cookies_file
        parsed = parse_cookies_file(cookies_path)
        formatted = format_cookies_for_playwright(parsed)
        if formatted:
            try:
                context.add_cookies(formatted)
            except Exception as cookie_err:
                logger.debug("Persistent context cookie seeding: %s", cookie_err)

    page = context.pages[0] if context.pages else context.new_page()
    return None, context, page


def _navigate_and_check_auth(
    page: Any,
    channel: str = "default",
    expected_channel_id: Optional[str] = None,
    expected_identity: Optional[str] = None,
    screenshot_dir: Optional[str] = None,
) -> None:
    """Stage 2: Navigate to studio upload page and verify authenticated session identity."""
    target_url = "https://youtube.com/upload"
    if expected_channel_id and str(expected_channel_id).strip():
        cid = str(expected_channel_id).strip()
        target_url = f"https://studio.youtube.com/channel/{cid}/videos/upload?d=ud"

    logger.info("Navigating to %s...", target_url)
    page.goto(target_url)
    page.wait_for_timeout(random.randint(3500, 5500))
    if screenshot_dir:
        page.screenshot(path=f"{screenshot_dir}/1_loaded.png")

    if "accounts.google.com" in page.url:
        raise RuntimeError("Authentication failed. Cookies are expired or invalid.")

    body_text = page.locator("body").inner_text().lower()
    if any(p in body_text for p in ("no tienes permiso", "sin permiso", "access denied", "permission denied")):
        if screenshot_dir:
            page.screenshot(path=f"{screenshot_dir}/permission_error.png")
        raise RuntimeError("No tienes permiso para ver esta página en YouTube Studio. Verifica el canal de la cuenta.")

    identity_candidates = [
        value.strip().lower().lstrip("@")
        for value in str(expected_identity or "").split("|")
        if value.strip()
    ]
    if not identity_candidates:
        raise RuntimeError("Falta la identidad pública esperada para Playwright")

    visible_identity = page.locator("body").inner_text().lower() + " " + page.url.lower()
    for selector in ("#avatar-btn", "[aria-label*='Account']", "[aria-label*='Cuenta']"):
        locator = page.locator(selector)
        cnt = int(locator.count()) if isinstance(locator.count(), (int, float)) else 0
        if cnt > 0:
            for attribute in ("aria-label", "title"):
                visible_identity += " " + str(locator.first.get_attribute(attribute) or "").lower()

    if not any(candidate in visible_identity for candidate in identity_candidates):
        raise RuntimeError("Playwright no confirmó la identidad del canal autenticado")


def _upload_file_payload(
    page: Any,
    video_path: str,
    context: Any = None,
    channel: str = "default",
    screenshot_dir: Optional[str] = None,
) -> None:
    logger.info("Uploading video file: %s...", video_path)
    try:
        page.wait_for_selector('input[type="file"]', state="attached", timeout=8000)
    except Exception:
        create_btn = page.locator('#create-icon, button:has-text("Crear"), [aria-label*="Crear"], ytcp-button#create-icon').first
        if int(create_btn.count()) > 0:
            create_btn.click()
            page.wait_for_timeout(1500)
            upload_item = page.locator('text=Subir vídeos, text=Subir videos, #text-item-0').first
            if int(upload_item.count()) > 0:
                upload_item.click()
                page.wait_for_timeout(2000)
        page.wait_for_selector('input[type="file"]', state="attached", timeout=25000)
    file_input = page.locator('input[type="file"]').first
    file_input.set_input_files(video_path)
    page.wait_for_timeout(5000)
    if screenshot_dir:
        page.screenshot(path=f"{screenshot_dir}/2_uploaded.png")

    page.wait_for_timeout(3000)
    loc_v = page.locator('text=Verifica tu identidad')
    loc_c = page.locator('text=Confirmar tu identidad')
    c_v = int(loc_v.count()) if isinstance(loc_v.count(), (int, float)) else 0
    c_c = int(loc_c.count()) if isinstance(loc_c.count(), (int, float)) else 0
    if c_v > 0 or c_c > 0:
        logger.warning("Google Identity Verification (2FA) detected.")
        if screenshot_dir:
            page.screenshot(path=f"{screenshot_dir}/identity_verification_error.png")
        dialog = page.locator('tp-yt-paper-dialog, ytcp-dialog, ytcp-confirmation-dialog, [role="dialog"]').filter(
            has_text=re.compile(r"Verifica tu identidad|Confirmar tu identidad|Verify your identity", re.I)
        )
        modal_btn = dialog.locator('#confirm-button button, ytcp-button:has-text("Siguiente") button, button:has-text("Siguiente"), button:has-text("Next"), #confirm-button')
        btn_count = int(modal_btn.count()) if isinstance(modal_btn.count(), (int, float)) else 0
        if btn_count > 0:
            next_btn = modal_btn.first
        else:
            fb = page.locator('#confirm-button button, ytcp-button:has-text("Siguiente") button, button:has-text("Siguiente"), button:has-text("Next")')
            fb_count = int(fb.count()) if isinstance(fb.count(), (int, float)) else 0
            next_btn = fb.last if fb_count > 0 else None

        if not next_btn:
            raise PlaywrightPrePublishError("Google Identity Verification (2FA) blocked the upload. Please verify on your phone.")

        global _LAST_2FA_ALERT_TIME
        _now = time.time()
        if _now - _LAST_2FA_ALERT_TIME > _2FA_ALERT_COOLDOWN_SECONDS:
            _LAST_2FA_ALERT_TIME = _now
            try:
                from review.telegram_bot import send_telegram_message
                send_telegram_message(f"⚠️ *Subida a YouTube detenida: Google solicita verificación en '{channel}'.*")
            except Exception:
                pass

        next_btn.click()
        page.wait_for_timeout(4000)
        verified = False
        for _wait_iter in range(36):
            page.wait_for_timeout(5000)
            c1 = int(loc_v.count()) if isinstance(loc_v.count(), (int, float)) else 0
            c2 = int(loc_c.count()) if isinstance(loc_c.count(), (int, float)) else 0
            if c1 == 0 and c2 == 0:
                verified = True
                break
        if not verified:
            raise PlaywrightPrePublishError("Google Identity Verification (2FA) blocked the upload. Timeout waiting for confirmation.")


def _fill_video_metadata(
    page: Any,
    title: str,
    description: str,
    thumbnail_path: Optional[str] = None,
    made_for_kids: bool = False,
    screenshot_dir: Optional[str] = None,
) -> None:
    """Stage 4: Fill title, description, thumbnail payload, and select audience radio."""
    logger.info("Filling video metadata...")
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
    thumbnail_input = page.locator('input[type="file"][accept*="image"]')
    cnt_thumb = int(thumbnail_input.count()) if isinstance(thumbnail_input.count(), (int, float)) else 0
    if cnt_thumb < 1:
        raise RuntimeError("YouTube Studio no expuso el control de miniatura")
    thumbnail_input.first.set_input_files(thumbnail_path)
    page.wait_for_timeout(2000)

    logger.info("Selecting Not Made for Kids...")
    kids_selectors = [
        'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"] #radioContainer',
        'tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"]',
        'tp-yt-paper-radio-button:has-text("No, no es contenido") #radioContainer',
        'tp-yt-paper-radio-button:has-text("No, no es contenido")',
        'tp-yt-paper-radio-button:has-text("No, it\'s not made for kids")',
        'text="No, no es contenido creado para niños"',
    ]
    for _k_iter in range(3):
        for sel in kids_selectors:
            try:
                loc = page.locator(sel)
                cnt = int(loc.count()) if isinstance(loc.count(), (int, float)) else 0
                if cnt > 0:
                    loc.first.scroll_into_view_if_needed()
                    loc.first.click()
                    page.wait_for_timeout(500)
                    break
            except Exception:
                pass
        radio = page.locator('tp-yt-paper-radio-button[name="VIDEO_MADE_FOR_KIDS_NOT_MFK"], tp-yt-paper-radio-button:has-text("No, no es contenido")')
        r_cnt = int(radio.count()) if isinstance(radio.count(), (int, float)) else 0
        if r_cnt > 0 and radio.first.get_attribute("aria-checked") == "true":
            break
        if r_cnt > 0:
            radio.first.evaluate("el => { el.click(); const rc = el.querySelector('#radioContainer') || el.querySelector('#offRadio'); if (rc) rc.click(); }")
            page.wait_for_timeout(500)
            if radio.first.get_attribute("aria-checked") == "true":
                break

    page.wait_for_timeout(1000)
    if screenshot_dir:
        page.screenshot(path=f"{screenshot_dir}/3_metadata.png")


def _select_visibility_and_publish(
    page: Any,
    visibility: str = "PUBLIC",
    schedule_time: Optional[str] = None,
    screenshot_dir: Optional[str] = None,
    logger_inst: Any = None,
) -> str:
    """Stage 5: Advance through wizard steps, select visibility radio, and click publish."""
    click_next(page, logger_inst, "Video Elements")
    page.wait_for_timeout(2000)
    click_next(page, logger_inst, "Checks")
    page.wait_for_timeout(2000)
    click_next(page, logger_inst, "Visibility")
    page.wait_for_timeout(2000)
    if screenshot_dir:
        page.screenshot(path=f"{screenshot_dir}/6_visibility.png")

    logger.info("Selecting Visibility as PUBLIC...")
    public_selectors = [
        'tp-yt-paper-radio-button[name="PUBLIC"] #radioContainer',
        'tp-yt-paper-radio-button[name="PUBLIC"]',
        'tp-yt-paper-radio-button:has-text("Público") #radioContainer',
        'tp-yt-paper-radio-button:has-text("Público")',
        'tp-yt-paper-radio-button:has-text("Public")',
    ]
    for psel in public_selectors:
        try:
            loc = page.locator(psel)
            cnt = int(loc.count()) if isinstance(loc.count(), (int, float)) else 0
            if cnt > 0:
                loc.first.scroll_into_view_if_needed()
                loc.first.click()
                page.wait_for_timeout(500)
                break
        except Exception:
            pass

    pradio = page.locator('tp-yt-paper-radio-button[name="PUBLIC"], tp-yt-paper-radio-button:has-text("Público")')
    pr_cnt = int(pradio.count()) if isinstance(pradio.count(), (int, float)) else 0
    if pr_cnt > 0 and pradio.first.get_attribute("aria-checked") != "true":
        pradio.first.evaluate("el => { el.click(); const rc = el.querySelector('#radioContainer') || el.querySelector('#offRadio'); if (rc) rc.click(); }")
        page.wait_for_timeout(500)

    video_url = ""
    try:
        link_el = page.locator('a.style-scope.ytcp-video-info')
        l_cnt = int(link_el.count()) if isinstance(link_el.count(), (int, float)) else 0
        if l_cnt > 0:
            video_url = link_el.first.get_attribute("href") or ""
    except Exception:
        pass

    page.wait_for_timeout(2000)
    click_done(page, logger_inst)

    page.wait_for_timeout(3000)
    confirm_selectors = [
        'ytcp-button:has-text("Publicar de todas formas")',
        'ytcp-button:has-text("Publish anyway")',
        'button:has-text("Publicar de todas formas")',
        'button:has-text("Publish anyway")',
        '#dialog-action-button button',
    ]
    for sel in confirm_selectors:
        try:
            loc = page.locator(sel)
            cnt = int(loc.count()) if isinstance(loc.count(), (int, float)) else 0
            if cnt > 0 and loc.first.is_visible():
                loc.first.click(force=True)
                page.wait_for_timeout(2000)
                break
        except Exception:
            pass

    page.wait_for_timeout(7000)
    if screenshot_dir:
        page.screenshot(path=f"{screenshot_dir}/8_published.png")
    return video_url


def _await_processing_and_extract_videoid(
    page: Any,
    timeout_sec: int = 60,
    initial_video_url: str = "",
    screenshot_dir: Optional[str] = None,
) -> tuple[Optional[str], str]:
    """Stage 6: Capture post-publish video URL and extract videoId."""
    video_url = initial_video_url
    if not video_url:
        post_selectors = [
            'ytcp-video-share-dialog a', 'a.ytcp-video-share-dialog', '#share-url',
            'a[href*="/shorts/"]', 'a[href*="youtu.be"]', 'a[href*="youtube.com/watch"]',
            'a.style-scope.ytcp-video-info',
        ]
        for psel in post_selectors:
            try:
                loc = page.locator(psel)
                cnt = int(loc.count()) if isinstance(loc.count(), (int, float)) else 0
                if cnt > 0:
                    val = loc.first.get_attribute("href") or loc.first.inner_text()
                    if val and ("youtu.be" in val or "youtube.com" in val):
                        video_url = val.strip()
                        break
            except Exception:
                pass

    if not video_url:
        try:
            body_text = page.locator("body").inner_text()
            match = re.search(r"https?://(?:www\.)?(?:youtu\.be/|youtube\.com/(?:shorts/|watch\?v=))([a-zA-Z0-9_-]+)", body_text)
            if match:
                video_url = match.group(0)
        except Exception:
            pass

    try:
        close_btn = page.locator('ytcp-button:has-text("Cerrar"), button:has-text("Cerrar"), button:has-text("Close")')
        c_cnt = int(close_btn.count()) if isinstance(close_btn.count(), (int, float)) else 0
        if c_cnt > 0 and close_btn.first.is_visible():
            close_btn.first.click(force=True)
            page.wait_for_timeout(1000)
    except Exception:
        pass

    if not video_url:
        return None, ""

    from urllib.parse import parse_qs, urlparse
    video_id = parse_qs(urlparse(video_url).query).get("v", [""])[0]
    if not video_id and "youtu.be" in video_url:
        video_id = urlparse(video_url).path.strip("/").split("/")[0]
    if not video_id and "/shorts/" in video_url:
        video_id = urlparse(video_url).path.split("/shorts/")[-1].split("/")[0].split("?")[0]

    return (video_id or None), video_url


# ==============================================================================
# Helper routines for orchestrator
# ==============================================================================

def _validate_and_load_session_cookies(video_path: str, cookies_path: str, dry_run: bool) -> tuple[Optional[Dict[str, Any]], list]:
    """Validate files, preflight check session health, and handle mock returns."""
    if not video_path or not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(cookies_path):
        raise FileNotFoundError(f"Cookies file not found: {cookies_path}")

    from src.core.cookies import SessionStatus, parse_cookies_file, validate_youtube_session_cookies
    try:
        cookies = parse_cookies_file(cookies_path)
    except (FileNotFoundError, OSError):
        raise
    except Exception as e:
        raise ValueError(f"Invalid cookies format in {cookies_path}: {e}") from e

    if (os.environ.get("MOCK_YOUTUBE_UPLOAD") == "1" or is_test_environment()) and not dry_run:
        return {"status": "TEST_MOCK", "method": "PLAYWRIGHT", "verified": False}, cookies

    session_health = validate_youtube_session_cookies(cookies)
    if session_health.status in (SessionStatus.EXPIRED, SessionStatus.INCOMPLETE, SessionStatus.INVALID):
        raise RuntimeError(f"Playwright session validation failed: {session_health.detail}")

    return None, cookies


def _cleanup_playwright_resources(page: Any, context: Any, browser: Any, cookies_path: str) -> None:
    """Safely close page, rotate cookies, close context and browser."""
    if page:
        try: page.close()
        except Exception: pass
    if context:
        try:
            if cookies_path and os.path.exists(cookies_path):
                rotated = context.cookies()
                if rotated:
                    from src.core.cookies import save_cookies_to_file
                    save_cookies_to_file(rotated, cookies_path)
        except Exception: pass
        try: context.close()
        except Exception: pass
    if browser:
        try: browser.close()
        except Exception: pass


def _reap_lingering_playwright_pids(pids_before: set) -> None:
    """Synchronize process teardown and avoid orphan chromium zombies."""
    deadline = time.time() + 3.0
    while time.time() < deadline:
        try:
            while True:
                wpid, _ = os.waitpid(-1, os.WNOHANG)
                if wpid == 0: break
        except (ChildProcessError, OSError): pass
        if not _get_playwright_pids(pids_before): break
        time.sleep(0.05)


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
    expected_channel_id: Optional[str] = None,
    channel: str = "default",
    **kwargs: Any,
) -> Dict[str, Any]:
    """Strategy B: Browser automation upload via Playwright running 6 discrete linear stages."""
    if cookies_path and not Path(cookies_path).is_file():
        raise FileNotFoundError(f"Cookies file not found: {cookies_path}")
    if (BASE_DIR / "ts_services").is_dir():
        try:
            return upload_video_via_playwright_ts(
                video_path, title, description, tags=tags, cookies_path=cookies_path,
                dry_run=dry_run, thumbnail_path=thumbnail_path, expected_identity=expected_identity,
                user_data_dir=user_data_dir,
            )
        except FileNotFoundError: pass
        except Exception: raise

    early_mock, _cookies = _validate_and_load_session_cookies(video_path, cookies_path, dry_run)
    if early_mock:
        return early_mock

    if sync_playwright is None:
        raise RuntimeError("Playwright is not installed or available.")

    screenshot_dir = os.environ.get("PLAYWRIGHT_DEBUG_DIR", "/tmp/debug")
    os.makedirs(screenshot_dir, exist_ok=True)
    pids_before = _get_playwright_pids()

    try:
        with sync_playwright() as p:
            browser, context, page = None, None, None
            video_published = False
            try:
                browser, context, page = _init_playwright_context(
                    p, cookies_path, channel=channel, headless=True, user_data_dir=user_data_dir
                )
                _navigate_and_check_auth(
                    page, channel=channel, expected_channel_id=expected_channel_id,
                    expected_identity=expected_identity, screenshot_dir=screenshot_dir,
                )
                if dry_run:
                    return {"status": "DRY_RUN", "method": "PLAYWRIGHT"}

                _upload_file_payload(page, video_path, context=context, channel=channel, screenshot_dir=screenshot_dir)
                _fill_video_metadata(page, title, description, thumbnail_path=thumbnail_path, screenshot_dir=screenshot_dir)
                pre_url = _select_visibility_and_publish(page, visibility="PUBLIC", screenshot_dir=screenshot_dir, logger_inst=logger)
                video_published = True

                video_id, final_url = _await_processing_and_extract_videoid(page, initial_video_url=pre_url, screenshot_dir=screenshot_dir)
                if not final_url:
                    return {"status": "UPLOAD_UNCONFIRMED", "method": "PLAYWRIGHT", "reason": "YouTube Studio no expuso una URL verificable", "verified": False}

                return {
                    "status": "PUBLISHED" if video_id else "UPLOAD_UNCONFIRMED",
                    "method": "PLAYWRIGHT",
                    "video_id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}" if video_id else final_url,
                    "title": title,
                    "description": description,
                    "visibility": "public",
                    "thumbnail_confirmed": bool(thumbnail_path),
                    "verified": bool(video_id),
                }
            except Exception as upload_exc:
                err_img = f"{screenshot_dir}/upload_failure_{int(time.time())}.png"
                try:
                    if page and not page.is_closed():
                        page.screenshot(path=err_img)
                except Exception:
                    err_img = None

                if err_img and os.path.isfile(err_img):
                    try:
                        from src.observability.alerts import send_operational_alert
                        send_operational_alert(
                            f"Fallo de Subida YouTube ({channel})",
                            f"Error: {upload_exc}\nCanal: {channel}\nURL: {getattr(page, 'url', 'desconocida')}",
                            photo_path=err_img,
                            force=True,
                        )
                    except Exception as alert_err:
                        logger.warning("No se pudo despachar captura a Telegram: %s", alert_err)

                if not video_published and not isinstance(upload_exc, PlaywrightPrePublishError):
                    raise PlaywrightPrePublishError(f"Playwright pre-publish failed: {upload_exc}") from upload_exc
                raise
            finally:
                _cleanup_playwright_resources(page, context, browser, cookies_path)
    finally:
        _reap_lingering_playwright_pids(pids_before)
