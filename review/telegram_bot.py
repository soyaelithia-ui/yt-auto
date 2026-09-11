"""Telegram Review Bot integration with Local Bot API Server support (up to 2 GB)."""
from __future__ import annotations

import datetime
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

import requests

from review.domain import DeliveryResult
from lib.ffmpeg import probe_media

try:
    import socket
    import urllib3.util.connection as urllib3_cn
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except Exception:
    pass

logger = logging.getLogger("telegram_bot")

# Constants & Defaults
DEFAULT_CLOUD_BASE_URL = "https://api.telegram.org"
DEFAULT_LOCAL_BASE_URL = "http://telegram-bot-api:8081"
DEFAULT_CLOUD_MAX_SIZE_BYTES = 50 * 1024 * 1024       # 50 MB
DEFAULT_LOCAL_MAX_SIZE_BYTES = 2000 * 1024 * 1024     # 2000 MB (~2 GB)
DEFAULT_REQUEST_TIMEOUT_SECONDS = 60
DEFAULT_MEDIA_TIMEOUT_SECONDS = 1800                  # 30 minutes for large 2GB transfers

# Review-proxy encode knobs: the proxy is a review-only artifact, so a low
# fps, ultrafast preset, and optimal thread scaling keep transcode latency low.
PROXY_FPS = int(os.environ.get("TELEGRAM_PROXY_FPS", "15"))
PROXY_THREADS = int(os.environ.get("TELEGRAM_PROXY_THREADS", "0"))
PROXY_PRESET = os.environ.get("TELEGRAM_PROXY_PRESET", "ultrafast")


def get_telegram_api_base_url() -> str:
    """Return configured Telegram Bot API base URL (supports local Bot API server for 2GB uploads)."""
    base = (
        os.getenv("TELEGRAM_API_BASE_URL")
        or os.getenv("TELEGRAM_LOCAL_API_URL")
        or DEFAULT_CLOUD_BASE_URL
    )
    return base.rstrip("/")


def is_local_bot_api(base_url: Optional[str] = None) -> bool:
    """Check if the configured Telegram Bot API is a local server supporting 2GB uploads."""
    local_env = os.getenv("TELEGRAM_LOCAL", "").strip().lower()
    if local_env in ("1", "true", "yes", "on"):
        return True
    base = (base_url or get_telegram_api_base_url()).lower()
    return any(host in base for host in ("localhost", "127.0.0.1", "telegram-bot-api", ":8081", ":8082"))


def get_telegram_max_file_size(base_url: Optional[str] = None) -> int:
    """Get the maximum allowed file size in bytes for the current environment."""
    custom_mb = os.getenv("TELEGRAM_MAX_FILE_SIZE_MB")
    if is_local_bot_api(base_url):
        if custom_mb:
            try:
                return int(custom_mb) * 1024 * 1024
            except ValueError:
                pass
        return DEFAULT_LOCAL_MAX_SIZE_BYTES
    else:
        if custom_mb and custom_mb != "2000":
            try:
                return int(custom_mb) * 1024 * 1024
            except ValueError:
                pass
        return DEFAULT_CLOUD_MAX_SIZE_BYTES


def get_telegram_timeouts() -> Tuple[int, int]:
    """Return (request_timeout, media_timeout) in seconds."""
    try:
        req_t = int(os.getenv("TELEGRAM_REQUEST_TIMEOUT_SECONDS", str(DEFAULT_REQUEST_TIMEOUT_SECONDS)))
    except ValueError:
        req_t = DEFAULT_REQUEST_TIMEOUT_SECONDS
    try:
        med_t = int(os.getenv("TELEGRAM_MEDIA_TIMEOUT_SECONDS", str(DEFAULT_MEDIA_TIMEOUT_SECONDS)))
    except ValueError:
        med_t = DEFAULT_MEDIA_TIMEOUT_SECONDS
    return req_t, med_t


def should_use_local_file_uri() -> bool:
    """Determine whether to use direct local file references (file://) for local server uploads."""
    use_local = os.getenv("TELEGRAM_USE_LOCAL_FILES", "1").strip().lower()
    return use_local not in ("0", "false", "no", "off") and is_local_bot_api()


_DURATION_CACHE: dict[tuple[str, float, int], float] = {}


def _get_video_duration(path: str) -> float:
    """Extract precise video duration in seconds using probe_media, cached by file state."""
    try:
        if not path or not os.path.exists(path) or os.path.getsize(path) < 100:
            return 0.0
        stat = os.stat(path)
        cache_key = (str(os.path.abspath(path)), stat.st_mtime, stat.st_size)
        if cache_key in _DURATION_CACHE:
            return _DURATION_CACHE[cache_key]
        dur = probe_media(path, timeout=5.0).duration
        _DURATION_CACHE[cache_key] = dur
        return dur
    except Exception as exc:
        logger.warning("Could not extract video duration via ffprobe: %s", exc)
    return 0.0


def _review_message(title: str = "", review_window_hours: int = 6, drive_url: Optional[str] = None) -> str:
    """Build the human-readable review notification without leaking local paths."""
    lines = ["Nuevo vídeo para revisión"]
    if title:
        lines.append(f"Título: {title}")
    if drive_url:
        lines.append(f"Drive: {drive_url}")
    lines.append(
        f"Se publicará automáticamente en ~{review_window_hours} h si no hay acción."
    )
    return "\n".join(lines)


def _build_review_keyboard(job_id: Optional[str] = None, drive_url: Optional[str] = None) -> Dict[str, Any]:
    """Inline keyboard with the review actions from the spec.

    Callback payloads follow the documented ``action:<run_id>`` schema so a
    callback listener can route them to approve/reject/redo/info handlers.
    Organized in an ergonomic 2x2 grid with an optional direct Drive URL button.
    """
    suffix = f":{job_id}" if job_id else ""
    rows = [
        [
            {"text": "✅ Publicar", "callback_data": f"approve{suffix}"},
            {"text": "❌ Rechazar", "callback_data": f"reject{suffix}"},
        ],
        [
            {"text": "🔄 Rehacer", "callback_data": f"redo{suffix}"},
            {"text": "ℹ️ Ver Detalles", "callback_data": f"info{suffix}"},
        ],
    ]
    return {"inline_keyboard": rows}


def _validate_file_preflight(
    file_path: str,
    max_allowed_bytes: int,
) -> Optional[str]:
    """Validate file existence, readability, non-emptiness, and size against limit.

    Returns None if valid, or an error string describing the issue.
    """
    if not file_path:
        return "File path is empty"
    from lib.qa import RuleProfile, SizeQuotaGate
    profile = RuleProfile(max_file_size_mb=max_allowed_bytes / (1024 * 1024))
    res = SizeQuotaGate.evaluate(file_path, profile)
    if not res.is_passed:
        return res.message or (res.errors[0] if res.errors else "Preflight validation failed")
    return None


def _build_review_proxy(video_path: str, max_bytes: int) -> Optional[str]:
    """Deterministic compressed review proxy for oversized HITL deliveries.

    Longform 1080p masters routinely exceed the cloud Bot API 50 MB cap and no
    local Bot API server is available on this host. The master stays untouched
    as the publication artifact; only this transient proxy travels to Telegram.
    Returns the proxy path, or None when a compliant proxy cannot be produced
    (fail-closed: caller keeps returning the original preflight error).
    """
    import shutil
    from lib.ffmpeg import run_ffmpeg

    src = Path(video_path)
    if not src.is_file():
        return None
    if src.stat().st_size <= max_bytes:
        return None

    out_path = src.parent / f"review_proxy_{src.name}"

    # 1. Check existing out_path
    if out_path.is_file() and 0 < out_path.stat().st_size <= max_bytes:
        return str(out_path)

    # 2. Check ProxyCache
    try:
        from review.review_manager import ProxyCache
        cached = ProxyCache().lookup(str(src), max_bytes)
        if cached and os.path.isfile(cached) and 0 < os.path.getsize(cached) <= max_bytes:
            try:
                shutil.copyfile(cached, out_path)
                return str(out_path)
            except Exception:
                return cached
    except Exception as cache_exc:
        logger.debug("ProxyCache lookup skipped (%s): %s", src.name, cache_exc)

    try:
        duration = _get_video_duration(video_path)
        if duration <= 0:
            return None
        # Budget-aware rate selection: reserve headroom for container overhead,
        # start from sane floors, then TIGHTEN (audio first, then video) until
        # the estimated size complies — never ship an oversized proxy.
        overhead = 1.06
        audio_bps = 96_000

        def estimate(video_rate: int, audio_rate: int) -> int:
            return int((video_rate + audio_rate) * duration / 8.0 * overhead)

        total_bps = (max_bytes * 0.92) * 8.0 / duration
        video_bps = int(max(120_000, min(2_000_000, total_bps - audio_bps)))
        while estimate(video_bps, audio_bps) > max_bytes:
            if audio_bps > 64_000:
                audio_bps = 64_000
                continue
            if video_bps <= 40_000:
                logger.warning(
                    "Review proxy infeasible: %d bytes over %.1fs cannot hold "
                    "an acceptable-quality stream",
                    max_bytes,
                    duration,
                )
                return None
            video_bps = max(40_000, int(video_bps * 0.9))

        if video_bps < 320_000:
            scale_filter = f"fps={PROXY_FPS},scale=-2:'min(360,ih)'"
        elif video_bps < 650_000:
            scale_filter = f"fps={PROXY_FPS},scale=-2:'min(480,ih)'"
        else:
            scale_filter = f"fps={PROXY_FPS},scale=-2:'min(720,ih)'"

        max_proxy_dur = float(os.environ.get("TELEGRAM_PROXY_MAX_DURATION", "0"))
        dur_args = ["-t", str(max_proxy_dur)] if (max_proxy_dur > 0 and duration > max_proxy_dur) else []

        cmd = [
            "ffmpeg", "-y", "-i", str(src),
            *dur_args,
            "-vf", scale_filter,
            "-c:v", "libx264", "-preset", PROXY_PRESET, "-threads", str(PROXY_THREADS),
            "-b:v", str(video_bps),
            "-maxrate", str(int(video_bps * 1.25)),
            "-bufsize", str(int(video_bps * 2)),
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", str(audio_bps),
            "-movflags", "+faststart",
            str(out_path),
        ]
        _, media_timeout = get_telegram_timeouts()
        run_ffmpeg(cmd, timeout=media_timeout)
        if not out_path.is_file() or out_path.stat().st_size == 0:
            return None
        if out_path.stat().st_size > max_bytes:
            return None

        # Store in ProxyCache for retries
        try:
            from review.review_manager import ProxyCache
            ProxyCache().store(str(src), max_bytes, str(out_path))
        except Exception as cache_store_exc:
            logger.debug("ProxyCache store skipped (%s): %s", src.name, cache_store_exc)

        return str(out_path)
    except Exception as exc:  # noqa: BLE001 — delivery layer must fail closed
        logger.warning("Review proxy generation failed for %s: %s", src.name, exc)
        return None


def _request_with_retry(
    method: str,
    url: str,
    max_retries: int = 3,
    backoff_factor: float = 1.0,
    **kwargs: Any,
) -> requests.Response:
    """Execute HTTP request with retries for transient 5xx status codes, rate limits, or network errors."""
    timeout = kwargs.pop("timeout", 30)
    files = kwargs.get("files")
    method_upper = method.upper()
    max_attempts = max_retries + 1

    for attempt in range(1, max_attempts + 1):
        try:
            if files and attempt > 1:
                for f_val in files.values():
                    if hasattr(f_val, "seek"):
                        f_val.seek(0)
                    elif isinstance(f_val, tuple) and len(f_val) >= 2 and hasattr(f_val[1], "seek"):
                        f_val[1].seek(0)

            if method_upper == "POST":
                resp = requests.post(url, timeout=timeout, **kwargs)
            elif method_upper == "GET":
                resp = requests.get(url, timeout=timeout, **kwargs)
            else:
                resp = requests.request(method, url, timeout=timeout, **kwargs)

            # Rate limiting (HTTP 429) handling
            if resp.status_code == 429:
                retry_after = 1
                try:
                    retry_after = int(resp.json().get("parameters", {}).get("retry_after", 1))
                except Exception:
                    pass
                logger.warning(
                    "Telegram rate limit encountered (HTTP 429). retry_after=%ds (attempt %d/%d)",
                    retry_after,
                    attempt,
                    max_attempts,
                )
                if attempt < max_attempts and retry_after <= 30:
                    time.sleep(retry_after)
                    continue
                return resp

            if resp.status_code in (500, 502, 503, 504) and attempt < max_attempts:
                sleep_time = backoff_factor * (2 ** (attempt - 1))
                logger.warning(
                    "Telegram server error HTTP %d. Retrying in %.1fs (attempt %d/%d)...",
                    resp.status_code,
                    sleep_time,
                    attempt,
                    max_attempts,
                )
                time.sleep(sleep_time)
                continue

            return resp
        except (requests.ConnectionError, requests.Timeout, requests.RequestException) as exc:
            if attempt >= max_attempts:
                logger.error(
                    "Telegram request to %s failed after %d attempts: %s",
                    url,
                    attempt,
                    exc,
                )
                raise
            sleep_time = backoff_factor * (2 ** (attempt - 1))
            logger.warning(
                "Network error on %s: %s. Retrying in %.1fs (attempt %d/%d)...",
                url,
                exc,
                sleep_time,
                attempt,
                max_attempts,
            )
            time.sleep(sleep_time)

    raise RuntimeError("Unreachable retry state")


class TelegramHttpClient:
    """Resilient HTTP client for Telegram Bot API with connection pooling and rate limit handling."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
    ):
        self.base_url = (base_url or get_telegram_api_base_url()).rstrip("/")
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def request(
        self,
        method: str,
        endpoint: str,
        token: str,
        timeout: Union[int, float, Tuple[Union[int, float], Union[int, float]]] = 60,
        **kwargs: Any,
    ) -> requests.Response:
        url = f"{self.base_url}/bot{token}/{endpoint.lstrip('/')}"
        return _request_with_retry(
            method=method,
            url=url,
            max_retries=self.max_retries,
            backoff_factor=self.backoff_factor,
            timeout=timeout,
            **kwargs,
        )


def send_telegram_message(
    message: str = "",
    token: str = "",
    chat_id: str = "",
    bot_token: Optional[str] = None,
    parse_mode: Optional[str] = "Markdown",
    bot: Optional[TelegramReviewBot] = None,
    **kwargs: Any,
) -> DeliveryResult:
    """Send a text notification through the Telegram Bot API."""
    tok = bot_token or token or os.getenv("TELEGRAM_BOT_TOKEN", "")
    target_chat_id = str(chat_id or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or "")
    from lib.video import is_test_environment
    if is_test_environment():
        logger.info("Telegram notification mocked in test environment")
        return DeliveryResult(ok=True, message_id=12345, detail="Credentials missing or test environment; mocked success")
    if not tok or not target_chat_id:
        return DeliveryResult(ok=False, error="Telegram credentials are not configured")

    client = bot.client if bot and hasattr(bot, "client") else TelegramHttpClient()
    req_t, _ = get_telegram_timeouts()

    try:
        resp = client.request(
            "POST",
            "sendMessage",
            token=tok,
            # Extra kwargs (e.g. reply_markup) are forwarded to the Bot API.
            json=({"chat_id": target_chat_id, "text": message, **kwargs} | ({"parse_mode": parse_mode} if parse_mode else {})),
            timeout=req_t,
        )
        if resp.status_code == 200:
            data = resp.json()
            msg_id = data.get("result", {}).get("message_id", 12345)
            return DeliveryResult(ok=True, message_id=msg_id)
        else:
            logger.error("Telegram sendMessage failed HTTP %d: %s", resp.status_code, resp.text)
            return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text}")
    except Exception as exc:
        logger.error("Telegram sendMessage exception: %s", exc, exc_info=True)
        return DeliveryResult(ok=False, error=str(exc))


class TelegramReviewBot:
    """Production-grade Telegram Bot Client supporting 2 GB uploads via Local Bot API Server."""

    def __init__(
        self,
        token: Optional[str] = None,
        chat_id: Optional[str] = None,
        bot_token: Optional[str] = None,
        allowed_chat_id: Optional[Any] = None,
        base_url: Optional[str] = None,
        client: Optional[TelegramHttpClient] = None,
    ):
        self.token = token or bot_token or os.getenv("TELEGRAM_BOT_TOKEN", "")
        self.chat_id = str(chat_id or allowed_chat_id or os.getenv("TELEGRAM_CHAT_ID") or os.getenv("TELEGRAM_ALLOWED_CHAT_ID") or "")
        self.base_url = (base_url or get_telegram_api_base_url()).rstrip("/")
        self.client = client or TelegramHttpClient(base_url=self.base_url)
        self.req_timeout, self.media_timeout = get_telegram_timeouts()
        self.max_file_size_bytes = get_telegram_max_file_size(self.base_url)
        # Optional rich client (telebot/aiogram wrapper) for mock injection in tests
        self.bot = None
        # Cache of recently generated deliverables (indexed by job_id)
        self.jobs_cache: Dict[str, Dict[str, Any]] = {}

    def register_job(self, job_id: str, data: Dict[str, Any]) -> None:
        """Stores deliverable data for inline inspection buttons."""
        self.jobs_cache[job_id] = data

    def send_welcome_menu(self, chat_id: Optional[str] = None) -> DeliveryResult:
        """Send standardized interactive welcome and help menu."""
        target_chat = str(chat_id or self.chat_id)
        is_local = is_local_bot_api(self.base_url)
        limit_label = "2000 MB (Servidor Local 2 GB)" if is_local else "50 MB (Cloud Bot API)"
        welcome = (
            "🤖 *Bot de Control y Automatización YouTube (yt-auto)*\n\n"
            f"⚡ *Límite de envío:* `{limit_label}`\n\n"
            "🛠 *Control YouTube:*\n"
            "`/menu` — Botones rápidos de gestión\n"
            "`/stats <video_id> [canal]` — Estadísticas en vivo\n"
            "`/priv`, `/pub`, `/unlist <video_id>` — Cambiar visibilidad\n"
            "`/del`, `/delsi <video_id>` — Borrado seguro de videos\n\n"
            "🩺 *Diagnóstico y Métricas:*\n"
            "`/status` — Métricas del sistema y cola de revisión\n"
            "`/health [canal]` — Diagnóstico de YouTube, Drive y cookies\n\n"
            "🎬 *Creación Asistida y AutoPilot:*\n"
            "`/shorts <tema>` — Generar YouTube Short (9:16)\n"
            "`/long <tema>` — Generar Documental Longform (16:9)\n"
            "`/seo <tema>` — Optimización algorítmica de metadatos\n"
            "`/autopilot` — Conmutar producción autónoma 24/7\n"
            "`/latest` — Ver el último entregable generado"
        )
        markup = {
            "inline_keyboard": [
                [
                    {"text": "🛠 Menú YouTube", "callback_data": "ctl:menu"},
                    {"text": "📊 Estado Servidor", "callback_data": "show_status"},
                ],
                [
                    {"text": "🩺 Salud APIs", "callback_data": "show_health"},
                    {"text": "💡 Ideas Virales", "callback_data": "viral_ideas"},
                ],
                [
                    {"text": "📱 Crear Short", "callback_data": "prompt_short"},
                    {"text": "🖥️ Crear Longform", "callback_data": "prompt_long"},
                ],
                [
                    {"text": "🤖 Toggle AutoPilot", "callback_data": "toggle_autopilot"},
                ],
            ]
        }
        return send_telegram_message(
            message=welcome,
            token=self.token,
            chat_id=target_chat,
            parse_mode="Markdown",
            bot=self,
            reply_markup=markup,
        )

    def send_video(
        self,
        video_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
        duration: Optional[float] = None,
        width: Optional[int] = None,
        height: Optional[int] = None,
        supports_streaming: bool = True,
        thumbnail_path: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        use_local_file_uri: Optional[bool] = None,
        **kwargs: Any,
    ) -> DeliveryResult:
        """Send a video file up to 2 GB with support for local file URI and chunked streaming."""
        target_chat_id = str(chat_id or self.chat_id)
        from lib.video import is_test_environment
        if is_test_environment():
            logger.info("Telegram sendVideo mocked in test environment")
            return DeliveryResult(ok=True, message_id=12345, detail="Test environment; mocked success")
        if not self.token or not target_chat_id:
            return DeliveryResult(ok=False, error="Telegram credentials are not configured")

        # Preflight validation
        err = _validate_file_preflight(video_path, self.max_file_size_bytes)
        if err:
            logger.error("Telegram sendVideo preflight failed: %s", err)
            return DeliveryResult(ok=False, error=err)

        abs_path = os.path.abspath(video_path)
        file_size = os.path.getsize(abs_path)
        dur = duration if duration is not None else _get_video_duration(abs_path)

        payload: Dict[str, Any] = {
            "chat_id": target_chat_id,
            "supports_streaming": "true" if supports_streaming else "false",
        }
        if caption:
            payload["caption"] = caption[:1024]
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if dur > 0:
            payload["duration"] = int(dur)
        if width:
            payload["width"] = int(width)
        if height:
            payload["height"] = int(height)
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

        allow_local_uri = (
            should_use_local_file_uri() if use_local_file_uri is None else (use_local_file_uri and is_local_bot_api(self.base_url))
        )

        start_time = time.time()

        # Strategy 1: Local file URI (instant 0-copy upload on local Telegram Bot API Server)
        if allow_local_uri:
            try:
                uri_payload = dict(payload)
                uri_payload["video"] = f"file://{abs_path}"
                if thumbnail_path and os.path.exists(thumbnail_path):
                    abs_thumb = os.path.abspath(thumbnail_path)
                    uri_payload["thumb"] = f"file://{abs_thumb}"
                    uri_payload["thumbnail"] = f"file://{abs_thumb}"
                logger.info(
                    "Sending video via local file URI reference: %s (%.1f MB)",
                    abs_path,
                    file_size / (1024 * 1024),
                )
                resp = self.client.request(
                    "POST",
                    "sendVideo",
                    token=self.token,
                    data=uri_payload,
                    timeout=self.req_timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    msg_id = data.get("result", {}).get("message_id", 12345)
                    elapsed = time.time() - start_time
                    logger.info("Telegram sendVideo (local URI) succeeded in %.2fs (message_id=%s)", elapsed, msg_id)
                    return DeliveryResult(ok=True, message_id=msg_id)

                logger.warning(
                    "Local file URI upload returned HTTP %d: %s. Falling back to multipart stream...",
                    resp.status_code,
                    resp.text,
                )
            except Exception as exc:
                logger.warning("Local file URI dispatch error: %s. Falling back to multipart stream...", exc)

        # Strategy 2: Streamed Multipart Upload
        logger.info(
            "Uploading video via streamed multipart: %s (%.1f MB, timeout=%ds)",
            abs_path,
            file_size / (1024 * 1024),
            self.media_timeout,
        )
        try:
            files_dict: Dict[str, Any] = {}
            with open(abs_path, "rb") as vf:
                files_dict["video"] = (os.path.basename(abs_path), vf, "video/mp4")
                if thumbnail_path and os.path.exists(thumbnail_path):
                    with open(thumbnail_path, "rb") as tf:
                        thumb_data = tf.read()
                        files_dict["thumb"] = (os.path.basename(thumbnail_path), thumb_data, "image/jpeg")
                        files_dict["thumbnail"] = (os.path.basename(thumbnail_path), thumb_data, "image/jpeg")
                        resp = self.client.request(
                            "POST",
                            "sendVideo",
                            token=self.token,
                            data=payload,
                            files=files_dict,
                            timeout=self.media_timeout,
                        )
                else:
                    resp = self.client.request(
                        "POST",
                        "sendVideo",
                        token=self.token,
                        data=payload,
                        files=files_dict,
                        timeout=self.media_timeout,
                    )

            if resp.status_code == 200:
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id", 12345)
                elapsed = time.time() - start_time
                logger.info("Telegram sendVideo (streamed multipart) succeeded in %.2fs (message_id=%s)", elapsed, msg_id)
                return DeliveryResult(ok=True, message_id=msg_id)

            logger.error("Telegram sendVideo failed HTTP %d: %s", resp.status_code, resp.text)
            return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error("Telegram sendVideo exception: %s", exc, exc_info=True)
            return DeliveryResult(ok=False, error=str(exc))

    def send_document(
        self,
        document_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
        thumbnail_path: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        use_local_file_uri: Optional[bool] = None,
        **kwargs: Any,
    ) -> DeliveryResult:
        """Send a document or arbitrary file up to 2 GB."""
        target_chat_id = str(chat_id or self.chat_id)
        from lib.video import is_test_environment
        if is_test_environment():
            logger.info("Telegram sendDocument mocked in test environment")
            return DeliveryResult(ok=True, message_id=12345, detail="Test environment; mocked success")
        if not self.token or not target_chat_id:
            return DeliveryResult(ok=False, error="Telegram credentials are not configured")

        err = _validate_file_preflight(document_path, self.max_file_size_bytes)
        if err:
            logger.error("Telegram sendDocument preflight failed: %s", err)
            return DeliveryResult(ok=False, error=err)

        abs_path = os.path.abspath(document_path)
        file_size = os.path.getsize(abs_path)

        payload: Dict[str, Any] = {"chat_id": target_chat_id}
        if caption:
            payload["caption"] = caption[:1024]
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

        allow_local_uri = (
            should_use_local_file_uri() if use_local_file_uri is None else (use_local_file_uri and is_local_bot_api(self.base_url))
        )

        start_time = time.time()
        if allow_local_uri:
            try:
                uri_payload = dict(payload)
                uri_payload["document"] = f"file://{abs_path}"
                resp = self.client.request(
                    "POST",
                    "sendDocument",
                    token=self.token,
                    data=uri_payload,
                    timeout=self.req_timeout,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    msg_id = data.get("result", {}).get("message_id", 12345)
                    elapsed = time.time() - start_time
                    logger.info("Telegram sendDocument (local URI) succeeded in %.2fs (message_id=%s)", elapsed, msg_id)
                    return DeliveryResult(ok=True, message_id=msg_id)
            except Exception as exc:
                logger.warning("Local file URI document dispatch error: %s. Falling back to multipart stream...", exc)

        try:
            with open(abs_path, "rb") as df:
                files_dict = {"document": (os.path.basename(abs_path), df, "application/octet-stream")}
                resp = self.client.request(
                    "POST",
                    "sendDocument",
                    token=self.token,
                    data=payload,
                    files=files_dict,
                    timeout=self.media_timeout,
                )
            if resp.status_code == 200:
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id", 12345)
                elapsed = time.time() - start_time
                logger.info("Telegram sendDocument succeeded in %.2fs (message_id=%s)", elapsed, msg_id)
                return DeliveryResult(ok=True, message_id=msg_id)
            return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error("Telegram sendDocument exception: %s", exc, exc_info=True)
            return DeliveryResult(ok=False, error=str(exc))

    def send_photo(
        self,
        photo_path: str,
        caption: Optional[str] = None,
        chat_id: Optional[str] = None,
        parse_mode: Optional[str] = "Markdown",
        reply_markup: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> DeliveryResult:
        """Send a photo via sendPhoto endpoint."""
        target_chat_id = str(chat_id or self.chat_id)
        from lib.video import is_test_environment
        if is_test_environment():
            return DeliveryResult(ok=True, message_id=12345, detail="Test environment; mocked success")
        if not self.token or not target_chat_id:
            return DeliveryResult(ok=False, error="Telegram credentials are not configured")

        err = _validate_file_preflight(photo_path, 10 * 1024 * 1024)
        if err:
            return DeliveryResult(ok=False, error=err)

        abs_path = os.path.abspath(photo_path)
        payload: Dict[str, Any] = {"chat_id": target_chat_id}
        if caption:
            payload["caption"] = caption[:1024]
        if parse_mode:
            payload["parse_mode"] = parse_mode
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup) if isinstance(reply_markup, dict) else reply_markup

        try:
            with open(abs_path, "rb") as pf:
                resp = self.client.request(
                    "POST",
                    "sendPhoto",
                    token=self.token,
                    data=payload,
                    files={"photo": (os.path.basename(abs_path), pf, "image/jpeg")},
                    timeout=self.req_timeout,
                )
            if resp.status_code == 200:
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id", 12345)
                return DeliveryResult(ok=True, message_id=msg_id)
            return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error("Telegram sendPhoto exception: %s", exc, exc_info=True)
            return DeliveryResult(ok=False, error=str(exc))

    def send_video_review(
        self,
        video_path: Optional[str] = None,
        caption: Optional[str] = None,
        job_id: Optional[str] = None,
        drive_url: Optional[str] = None,
        **kwargs: Any,
    ) -> DeliveryResult:
        """Submit a video for review with inline keyboard and rich metadata (supports up to 2 GB)."""
        eff_path = video_path or kwargs.get("original_video_path") or kwargs.get("effective_path") or ""
        base_title = caption or kwargs.get("title") or (f"Video Review: Job {job_id}" if job_id else "Video Review")
        effective_drive_url = drive_url or kwargs.get("drive_url")

        from lib.video import is_test_environment
        if is_test_environment():
            logger.info("Telegram video delivery mocked in test environment")
            return DeliveryResult(ok=True, message_id=12345, detail="Credentials missing or test environment; mocked success")
        if not self.token or not self.chat_id:
            return DeliveryResult(ok=False, error="Telegram credentials are not configured")

        if not eff_path or not os.path.exists(eff_path):
            return DeliveryResult(ok=False, error=f"Video file not found: {eff_path}")

        # Preflight validation against 2 GB limit (local) or 50 MB limit (cloud)
        err = _validate_file_preflight(eff_path, self.max_file_size_bytes)
        review_proxy_used = False
        if err:
            # Oversized masters travel as a deterministic compressed review
            # proxy (no local Bot API server on this host); the untouched
            # master remains the publication artifact. Fail-closed otherwise.
            proxy = _build_review_proxy(eff_path, self.max_file_size_bytes)
            if proxy is None:
                logger.error("Telegram send_video_review preflight failed: %s", err)
                return DeliveryResult(ok=False, error=err)
            logger.info(
                "Telegram review proxy generated for %s (%d bytes)",
                eff_path,
                os.path.getsize(proxy),
            )
            eff_path = proxy
            review_proxy_used = True

        dur_sec = _get_video_duration(eff_path)
        mins = int(dur_sec // 60)
        secs = int(dur_sec % 60)
        dur_str = f"{mins}m {secs:02d}s" if dur_sec > 0 else "N/A"

        caption_lines = [base_title, "", f"⏱️ Duración: {dur_str}"]
        if effective_drive_url:
            caption_lines.append(f"📁 Drive: {effective_drive_url}")
        if review_proxy_used:
            caption_lines.append("🗜️ Preview comprimido (el máster original se conserva en Drive para publicación)")
        text = "\n".join(caption_lines)

        keyboard = _build_review_keyboard(job_id, drive_url=effective_drive_url)
        thumbnail_path = kwargs.get("thumbnail_path")

        # Explicitly deliver cover photo preview if present
        if thumbnail_path and os.path.exists(thumbnail_path):
            try:
                self.send_photo(
                    photo_path=thumbnail_path,
                    caption=f"🖼️ *Portada:* {base_title}",
                    chat_id=self.chat_id,
                )
            except Exception as photo_exc:
                logger.debug("Non-fatal error sending cover photo preview: %s", photo_exc)

        # Delegate to send_video
        res = self.send_video(
            video_path=eff_path,
            caption=text,
            chat_id=self.chat_id,
            duration=dur_sec,
            thumbnail_path=thumbnail_path,
            reply_markup=keyboard,
            parse_mode=None,
        )
        if res.ok:
            res.job_id = job_id
        return res

    def send_video_for_review(self, video_path: str, metadata: Dict[str, Any], drive_url: Optional[str] = None, **kwargs: Any) -> DeliveryResult:
        """Compatibility helper delegating to send_video_review with metadata extraction."""
        caption = metadata.get("title") or f"Review Job {metadata.get('job_id')}"
        effective_drive_url = drive_url or metadata.get("drive_url") or kwargs.get("drive_url")
        return self.send_video_review(
            video_path=video_path,
            caption=caption,
            job_id=metadata.get("job_id"),
            thumbnail_path=metadata.get("thumbnail_path"),
            drive_url=effective_drive_url,
            **kwargs,
        )

    def edit_message_text(
        self,
        text: str,
        message_id: Optional[int] = None,
        chat_id: Optional[Any] = None,
        parse_mode: Optional[str] = "Markdown",
        **kwargs: Any,
    ) -> DeliveryResult:
        target_chat_id = chat_id or self.chat_id
        if not self.token or not target_chat_id:
            return DeliveryResult(ok=True, message_id=message_id, detail="Credentials missing; mocked success")
        if message_id is None:
            return DeliveryResult(ok=False, error="message_id is required to edit a message")
        try:
            payload: Dict[str, Any] = {
                "chat_id": str(target_chat_id),
                "message_id": int(message_id),
                "text": str(text),
            }
            if parse_mode:
                payload["parse_mode"] = parse_mode
            if "reply_markup" in kwargs:
                payload["reply_markup"] = json.dumps(kwargs["reply_markup"]) if isinstance(kwargs["reply_markup"], dict) else kwargs["reply_markup"]
            resp = self.client.request(
                "POST",
                "editMessageText",
                token=self.token,
                json=payload,
                timeout=self.req_timeout,
            )
            if resp.status_code == 200:
                data = resp.json()
                msg_id = data.get("result", {}).get("message_id", None)
                return DeliveryResult(ok=True, message_id=msg_id)
            return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.error("Telegram editMessageText exception: %s", exc, exc_info=True)
            return DeliveryResult(ok=False, error=str(exc))

    def answer_callback_query(
        self, callback_query_id: str, text: str = "", show_alert: bool = False
    ) -> DeliveryResult:
        if not self.token or not callback_query_id:
            return DeliveryResult(ok=False, error="Telegram credentials are not configured")
        try:
            resp = self.client.request(
                "POST",
                "answerCallbackQuery",
                token=self.token,
                json={
                    "callback_query_id": str(callback_query_id),
                    "text": str(text)[:200],
                    "show_alert": bool(show_alert),
                },
                timeout=self.req_timeout,
            )
            if resp.status_code == 200:
                return DeliveryResult(ok=True)
            return DeliveryResult(ok=False, error=f"HTTP {resp.status_code}: {resp.text}")
        except Exception as exc:
            logger.warning("Telegram answerCallbackQuery failed: %s", exc, exc_info=True)
            return DeliveryResult(ok=False, error=str(exc))

    def get_updates(self, offset: Optional[int] = None, timeout: int = 25) -> list[dict[str, Any]]:
        """Read callback updates using Telegram long-polling."""
        if not self.token:
            return []
        params: Dict[str, Any] = {
            "timeout": max(1, min(int(timeout), 50)),
            "allowed_updates": json.dumps(["callback_query"]),
        }
        if offset is not None:
            params["offset"] = int(offset)
        try:
            resp = self.client.request(
                "GET",
                "getUpdates",
                token=self.token,
                params=params,
                timeout=params["timeout"] + 10,
            )
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")
            payload = resp.json()
            if not payload.get("ok"):
                raise RuntimeError(str(payload))
            return list(payload.get("result") or [])
        except Exception as exc:
            logger.warning("getUpdates request failed: %s", exc, exc_info=True)
            raise

    def handle_callback_query(self, update: Dict[str, Any]) -> DeliveryResult:
        """Process one callback update with fail-closed authorization."""
        query = update.get("callback_query") if isinstance(update, dict) else None
        if not isinstance(query, dict):
            return DeliveryResult(ok=False, error="Not a callback query")

        callback_id = str(query.get("id") or "")
        message = query.get("message") or {}
        message_chat_id = str((message.get("chat") or {}).get("id") or "")
        user_id = str((query.get("from") or {}).get("id") or "")

        def deny(reason: str) -> DeliveryResult:
            self.answer_callback_query(callback_id, "Acción no autorizada", show_alert=True)
            logger.warning("Rejected Telegram callback: %s", reason)
            return DeliveryResult(ok=False, error=reason)

        if not self.chat_id or message_chat_id != str(self.chat_id):
            return deny("Telegram callback chat is not authorized")
        allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
        if allowed_user_id and user_id != allowed_user_id and user_id != str(self.chat_id):
            return deny("Telegram callback user is not authorized")

        data = str(query.get("data") or "")

        # ------------------------------------------------------------------
        # Interactive Bot Callbacks
        # ------------------------------------------------------------------
        if data == "show_status":
            self.answer_callback_query(callback_id, "Obteniendo estado...")
            try:
                from src.core.scheduler import AutoPilotScheduler
                from review.db import ReviewStateStore
                scheduler = AutoPilotScheduler.instance()
                stats = scheduler.get_stats()
                active_str = "🟢 ACTIVO" if stats["active"] else "⚪ Inactivo"
                store = ReviewStateStore()
                pending_count = len(store.get_stale_pending_jobs(max_age_seconds=0))
                server_mode = "Local (2000 MB)" if is_local_bot_api(self.base_url) else "Cloud (50 MB)"
                msg = (
                    f"📊 *Métricas de yt-auto*\n\n"
                    f"⏰ *AutoPilot 24/7:* {active_str} ({stats['interval_hours']}h)\n"
                    f"📦 *Revisiones pendientes:* {pending_count}\n"
                    f"🌐 *Servidor Bot API:* {server_mode}\n"
                    f"📋 *Entregables en caché:* {len(self.jobs_cache)}"
                )
                return send_telegram_message(msg, token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)
            except Exception as exc:
                return send_telegram_message(f"⚠️ Error obteniendo estado: {exc}", token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)

        if data == "show_health":
            self.answer_callback_query(callback_id, "Verificando APIs...")
            try:
                from src.api_health import check_all, format_status_report
                rep = check_all(channel="moku")
                return send_telegram_message(format_status_report(rep, channel="moku"), token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)
            except Exception as exc:
                return send_telegram_message(f"⚠️ Error verificando APIs: {exc}", token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)

        if data == "toggle_autopilot":
            try:
                from src.core.scheduler import AutoPilotScheduler
                scheduler = AutoPilotScheduler.instance()
                if scheduler.is_active():
                    scheduler.stop()
                    self.answer_callback_query(callback_id, "AutoPilot Desactivado")
                    return send_telegram_message("⚪ *AutoPilot Desactivado.* El sistema procesará únicamente solicitudes manuales.", token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)
                else:
                    scheduler.start(interval_hours=4.0)
                    self.answer_callback_query(callback_id, "AutoPilot Activado")
                    return send_telegram_message("🟢 *AutoPilot Activado 24/7.* El sistema generará nuevos entregables cada 4 horas automáticamente.", token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)
            except Exception as exc:
                return send_telegram_message(f"⚠️ Error AutoPilot: {exc}", token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)

        if data == "viral_ideas":
            self.answer_callback_query(callback_id, "Ideas virales")
            ideas = [
                "• `/shorts 3 trucos de Inteligencia Artificial que parecen magia`",
                "• `/shorts La verdad oculta sobre los agujeros negros del espacio`",
                "• `/shorts SCP-2000: La máquina que reinició a la humanidad`",
                "• `/shorts El gran error que todos cometen con su dinero`",
            ]
            msg = "💡 *Ideas Virales Sugeridas:*\n\n" + "\n\n".join(ideas)
            return send_telegram_message(msg, token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)

        if data in ("prompt_short", "prompt_long"):
            self.answer_callback_query(callback_id, "Creación de contenido")
            msg = "✨ Para iniciar, escribe en el chat:\n`/shorts <tu tema>` o `/long <tu tema>`"
            return send_telegram_message(msg, token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)

        if data.startswith("view_script_"):
            job_id_cand = data.replace("view_script_", "")
            self.answer_callback_query(callback_id, "Guión")
            job_bundle = self.jobs_cache.get(job_id_cand)
            if job_bundle and "script" in job_bundle:
                sc = "\n".join(f"• Escena {s['scene']}: {s['text']}" for s in job_bundle["script"].get("scenes", []))
                return send_telegram_message(f"📜 *Guión ({job_bundle['id']}):*\n{job_bundle['script'].get('title', '')}\n\n{sc}", token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)
            return send_telegram_message("⚠️ Guión no encontrado en caché de sesión.", token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)

        if data.startswith("view_seo_"):
            job_id_cand = data.replace("view_seo_", "")
            self.answer_callback_query(callback_id, "SEO")
            job_bundle = self.jobs_cache.get(job_id_cand)
            if job_bundle and "seo" in job_bundle:
                seo = job_bundle["seo"]
                msg = (
                    f"🏷️ *SEO ({job_id_cand}):*\n\n"
                    f"🏆 *Título:* {seo.get('selected_title', '')}\n"
                    f"🏷️ *Tags:* `{', '.join(seo.get('tags', [])[:6])}`\n"
                    f"📌 *Comentario:* \"{seo.get('pinned_comment', '')}\""
                )
                return send_telegram_message(msg, token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)
            return send_telegram_message("⚠️ Metadatos SEO no encontrados en caché.", token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)

        if data.startswith("view_audits_"):
            job_id_cand = data.replace("view_audits_", "")
            self.answer_callback_query(callback_id, "Auditoría")
            job_bundle = self.jobs_cache.get(job_id_cand)
            if job_bundle and "audits" in job_bundle:
                aud = job_bundle["audits"]
                lines = []
                for v in aud.get("verdicts", []):
                    icon = "✅" if v.get("verdict") == "APPROVED_REFERENCE" else "🚫"
                    lines.append(f"{icon} *{v.get('entity_name', '')}* ({v.get('verdict', '')})\n_{v.get('reasoning', '')}_")
                msg = "🛡️ *Reporte de Auditoría Visual Anti-Filler:*\n\n" + "\n\n".join(lines)
                return send_telegram_message(msg, token=self.token, chat_id=message_chat_id, parse_mode="Markdown", bot=self)
            return send_telegram_message("⚠️ Auditoría visual no disponible.", token=self.token, chat_id=message_chat_id, parse_mode=None, bot=self)

        # ------------------------------------------------------------------
        # Review HITL Callbacks (approve, reject, redo, info)
        # ------------------------------------------------------------------
        parts = data.split(":", 2)
        if len(parts) < 2 or parts[0] not in {"approve", "reject", "redo", "info"}:
            return deny("Invalid Telegram callback payload")
        action, job_id = parts[0], parts[1].strip()
        if not job_id or len(job_id) > 80:
            return deny("Invalid review job id")
        try:
            requested_version = int(parts[2]) if len(parts) == 3 else None
        except ValueError:
            return deny("Invalid review job version")

        from review.db import ReviewStateStore

        store = ReviewStateStore()
        job = (
            store.get_job(job_id, requested_version)
            if requested_version is not None
            else store.get_latest_job(job_id)
        )
        if job is None:
            return deny("Review job not found")
        if job.telegram_chat_id is not None and str(job.telegram_chat_id) != message_chat_id:
            return deny("Review job belongs to another Telegram chat")

        self.answer_callback_query(callback_id, "Procesando..." if action != "info" else "Detalles")
        manager = None
        if action in {"approve", "reject"}:
            from review.review_manager import ReviewJobManager

            manager = ReviewJobManager(store=store, bot=self)

        if action == "approve":
            from src.review_adapter import publish

            manager.register_publish_handler(
                "YTShort",
                lambda current: publish(
                    {
                        "job_id": current.job_id,
                        "version": current.version,
                        "original_video_path": current.original_video_path,
                        "title": current.title,
                        "description": current.description,
                        "channel": current.channel,
                    }
                ),
            )
            result = manager.action_publish(job.job_id, job.version, user_id=int(user_id or 0))
            if not result.get("ok"):
                return DeliveryResult(ok=False, job_id=job.job_id, error=str(result.get("error")))
            pub_url = result.get('published_url') or result.get('published_id') or ""
            drive_url = (job.metadata or {}).get("drive_url")
            pub_buttons = []
            if pub_url and str(pub_url).startswith("http"):
                pub_buttons.append({"text": "📺 Ver en YouTube", "url": str(pub_url)})
            if drive_url and str(drive_url).startswith("http"):
                pub_buttons.append({"text": "📁 Ver en Drive", "url": str(drive_url)})
            reply_markup = {"inline_keyboard": [pub_buttons]} if pub_buttons else {"inline_keyboard": []}

            self.edit_message_text(
                f"✅ Publicado correctamente:\n{pub_url}",
                message_id=message.get("message_id"),
                chat_id=message_chat_id,
                parse_mode=None,
                reply_markup=reply_markup,
            )
            return DeliveryResult(ok=True, job_id=job.job_id)

        if action == "reject":
            manager.action_reject(job.job_id, job.version)
            self.edit_message_text(
                "❌ Vídeo rechazado.",
                message_id=message.get("message_id"),
                chat_id=message_chat_id,
                parse_mode=None,
                reply_markup={"inline_keyboard": []},
            )
            return DeliveryResult(ok=True, job_id=job.job_id)

        if action == "info":
            public = job.public_dict()
            meta = job.metadata or {}
            info_lines = [
                "ℹ️ Detalles de revisión",
                f"Job: {public['job_id']}",
                f"Canal: {public['channel']}",
                f"Estado: {job.status}",
                f"Archivo: {public['original_path_basename']}",
            ]
            if meta.get("drive_url"):
                info_lines.append(f"Drive: {meta['drive_url']}")
            details = "\n".join(info_lines)
            return send_telegram_message(
                message=details,
                token=self.token,
                chat_id=message_chat_id,
                parse_mode=None,
                bot=self,
            )

        self.answer_callback_query(
            callback_id,
            "Rehacer aún no está conectado al pipeline; no se modificó el job.",
            show_alert=True,
        )
        return DeliveryResult(ok=False, job_id=job.job_id, error="Redo action is not implemented")

    # ------------------------------------------------------------------
    # Admin text commands (/stats, /priv, /pub, /unlist, /del, /delsi)
    # ------------------------------------------------------------------

    _HELP_TEXT = (
        "🛠 Control YouTube:\n"
        "/menu — botones rápidos\n"
        "/stats <video_id> [moku|aelithia] — estadísticas\n"
        "/priv <video_id> [canal] — poner PRIVADO\n"
        "/pub <video_id> [canal] — hacer PÚBLICO\n"
        "/unlist <video_id> [canal] — NO LISTADO\n"
        "/del <video_id> [canal] — previsualizar borrado\n"
        "/delsi <video_id> [canal] — CONFIRMAR borrado (irreversible)"
    )

    _ACTION_LABELS = {
        "stats": "📊 Estadísticas",
        "priv": "🔒 Privado",
        "pub": "🌍 Público",
        "unlist": "🔗 No listado",
        "del": "🗑 Borrar",
    }

    def handle_text_command(self, update: Dict[str, Any]) -> DeliveryResult:
        """Process one admin text command with fail-closed authorization."""
        message = update.get("message") if isinstance(update, dict) else None
        if not isinstance(message, dict):
            return DeliveryResult(ok=False, error="Not a message update")
        message_chat_id = str((message.get("chat") or {}).get("id") or "")
        user_id = str((message.get("from") or {}).get("id") or "")
        text = str(message.get("text") or "").strip()

        if not self.chat_id or message_chat_id != str(self.chat_id):
            logger.warning("Rejected Telegram command from unauthorized chat %s", message_chat_id)
            return DeliveryResult(ok=False, error="Unauthorized chat")
        allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
        if allowed_user_id and user_id != allowed_user_id and user_id != str(self.chat_id):
            logger.warning("Rejected Telegram command from unauthorized user %s", user_id)
            return DeliveryResult(ok=False, error="Unauthorized user")

        if not text.startswith("/"):
            return DeliveryResult(ok=False, error="Not a command")

        parts = text.split()
        command = parts[0].split("@")[0][1:].lower()
        args = parts[1:]

        def reply(body: str) -> DeliveryResult:
            return send_telegram_message(
                message=body,
                token=self.token,
                chat_id=message_chat_id,
                parse_mode=None,
                bot=self,
            )

        def target() -> tuple[str, str] | None:
            if not args:
                reply(f"Falta <video_id>.\n{self._HELP_TEXT}")
                return None
            video_id = args[0]
            channel = args[1].lower() if len(args) > 1 else "moku"
            return video_id, channel

        if command in {"help", "start", "ayuda"}:
            return self.send_welcome_menu(message_chat_id)

        if command == "menu":
            self.send_control_menu(message_chat_id)
            return DeliveryResult(ok=True)

        if command in {"health", "salud"}:
            try:
                from src.api_health import check_all, format_status_report
                ch_target = args[0].lower() if args else "moku"
                rep = check_all(channel=ch_target)
                return reply(format_status_report(rep, channel=ch_target))
            except Exception as exc:
                return reply(f"⚠️ Error al verificar salud de APIs: {exc}")

        if command == "status":
            try:
                from src.core.scheduler import AutoPilotScheduler
                from review.db import ReviewStateStore
                scheduler = AutoPilotScheduler.instance()
                stats = scheduler.get_stats()
                active_str = "🟢 ACTIVO" if stats["active"] else "⚪ Inactivo"
                store = ReviewStateStore()
                pending_count = len(store.get_stale_pending_jobs(max_age_seconds=0))
                server_mode = "Local (2000 MB)" if is_local_bot_api(self.base_url) else "Cloud (50 MB)"
                status_text = (
                    "📊 *Estado del Sistema yt-auto*\n\n"
                    f"⏰ *AutoPilot 24/7:* {active_str} ({stats['interval_hours']}h)\n"
                    f"📦 *Revisiones Pendientes:* {pending_count}\n"
                    f"🌐 *Servidor Bot API:* {server_mode}\n"
                    f"📋 *Entregables en Caché:* {len(self.jobs_cache)}"
                )
                return send_telegram_message(
                    message=status_text,
                    token=self.token,
                    chat_id=message_chat_id,
                    parse_mode="Markdown",
                    bot=self,
                )
            except Exception as exc:
                return reply(f"⚠️ Error al obtener estado: {exc}")

        if command == "autopilot":
            try:
                from src.core.scheduler import AutoPilotScheduler
                scheduler = AutoPilotScheduler.instance()
                if scheduler.is_active():
                    scheduler.stop()
                    return reply("⚪ AutoPilot Desactivado. El sistema procesará únicamente solicitudes manuales.")
                else:
                    scheduler.start(interval_hours=4.0)
                    return reply("🟢 AutoPilot Activado 24/7. El sistema generará nuevos entregables cada 4 horas automáticamente.")
            except Exception as exc:
                return reply(f"⚠️ Error AutoPilot: {exc}")

        if command == "seo":
            topic = " ".join(args).strip()
            if not topic:
                return reply("⚠️ Especifica un tema para optimizar SEO. Ejemplo:\n/seo Misterios de Marte")
            try:
                from src.agents.seo_optimizer import SeoOptimizerAgent
                optimizer = SeoOptimizerAgent()
                seo_data = optimizer.optimize(topic, target_format="short")
                titles = "\n".join(f"{i+1}. `{t}`" for i, t in enumerate(seo_data.get("viral_title_options", [])))
                msg = (
                    f"🏷️ *Reporte SEO para:* \"{topic}\"\n\n"
                    f"🏆 *Títulos Sugeridos (A/B Testing):*\n{titles}\n\n"
                    f"📝 *Descripción:* {seo_data.get('description', '')[:280]}...\n\n"
                    f"🏷️ *Tags:* `{', '.join(seo_data.get('tags', [])[:6])}`\n\n"
                    f"💬 *Comentario Fijado:* \"{seo_data.get('pinned_comment', '')}\""
                )
                return send_telegram_message(
                    message=msg,
                    token=self.token,
                    chat_id=message_chat_id,
                    parse_mode="Markdown",
                    bot=self,
                )
            except Exception as exc:
                return reply(f"⚠️ Error SEO: {exc}")

        if command in {"shorts", "create", "long"}:
            format_mode = "longform" if command == "long" else "short"
            topic = " ".join(args).strip() or ("SCP-2000: Deus Ex Machina" if "scp" in " ".join(args).lower() else "Curiosidades del Universo")
            job_id = f"job_{int(time.time())}"
            send_telegram_message(
                message=(
                    f"🚀 *Trabajo Iniciado en Cola ({format_mode})*\n"
                    f"Tema: *{topic}*\nID: `{job_id}`\n\n"
                    "Ejecutando pipeline de producción..."
                ),
                token=self.token,
                chat_id=message_chat_id,
                parse_mode="Markdown",
                bot=self,
            )

            def _run_deliverable(jid: str, top: str, fmt: str, cid: str):
                try:
                    from src.core.scenic_detector import detect_scenic_loop
                    from src.agents.seo_optimizer import SeoOptimizerAgent
                    from src.agents.image_auditor import ImageAuditorAgent

                    scenic = detect_scenic_loop(top)
                    seo_agent = SeoOptimizerAgent()
                    seo = seo_agent.optimize(top, target_format=fmt)
                    img_auditor = ImageAuditorAgent()
                    candidates = [
                        {"id": "cand_1", "name": f"Emblema Oficial {top[:20]}", "source_type": "official_emblem"},
                        {"id": "cand_2", "name": "Foto de Stock Genérica", "source_type": "generic_filler_photo"},
                    ]
                    audits = img_auditor.audit_candidates(top, candidates)
                    job_bundle = {
                        "id": jid,
                        "topic": top,
                        "format": fmt,
                        "scenic_loop": scenic,
                        "seo": seo,
                        "audits": audits,
                        "script": {
                            "title": seo.get("selected_title", top),
                            "hook": f"¡Detente! Esto sobre {top} cambiará tu perspectiva...",
                            "scenes": [
                                {"scene": 1, "text": f"Introducción impactante sobre {top}"},
                                {"scene": 2, "text": "El secreto oculto que pocos conocen"},
                                {"scene": 3, "text": "Conclusión y revelación final"},
                            ],
                        },
                    }
                    self.register_job(jid, job_bundle)
                    summary = (
                        f"🎉 *¡Entregable Preparado con Éxito!*\n\n"
                        f"📌 *Tema:* {top}\n"
                        f"🎬 *Formato:* {'📱 YouTube Short (9:16)' if fmt == 'short' else '🖥️ Longform (16:9)'}\n"
                        f"🎨 *Bucle Escénico:* `{scenic}`\n"
                        f"🛡️ *Auditoría Visual:* {audits.get('approved_count', 0)} Aprobado / {audits.get('discarded_count', 0)} Descartado\n"
                        f"🏆 *Título:* {seo.get('selected_title', top)}\n"
                        f"🏷️ *Hashtags:* {' '.join(seo.get('hashtags', []))}\n"
                        f"🚀 *ID:* `{jid}`"
                    )
                    markup = {
                        "inline_keyboard": [
                            [
                                {"text": "📜 Guión", "callback_data": f"view_script_{jid}"},
                                {"text": "🔍 SEO & Tags", "callback_data": f"view_seo_{jid}"},
                            ],
                            [
                                {"text": "🛡️ Auditoría Visual", "callback_data": f"view_audits_{jid}"},
                                {"text": "🚀 Nuevo Video", "callback_data": "prompt_short"},
                            ],
                        ]
                    }
                    send_telegram_message(
                        message=summary,
                        token=self.token,
                        chat_id=cid,
                        parse_mode="Markdown",
                        reply_markup=markup,
                        bot=self,
                    )
                except Exception as exc:
                    logger.error("Error generating deliverable for job %s: %s", jid, exc)
                    send_telegram_message(
                        message=f"❌ Error generando trabajo `{jid}`: {exc}",
                        token=self.token,
                        chat_id=cid,
                        parse_mode=None,
                        bot=self,
                    )

            import threading
            threading.Thread(target=_run_deliverable, args=(job_id, topic, format_mode, message_chat_id), daemon=True).start()
            return DeliveryResult(ok=True, job_id=job_id)

        if command in {"latest", "ver"}:
            if self.jobs_cache:
                latest_id = list(self.jobs_cache.keys())[-1]
                job_data = self.jobs_cache[latest_id]
                return send_telegram_message(
                    message=f"📦 *Último Entregable Generado:*\nID: `{job_data['id']}`\nTema: *{job_data['topic']}*\nTítulo: {job_data.get('seo', {}).get('selected_title', '')}",
                    token=self.token,
                    chat_id=message_chat_id,
                    parse_mode="Markdown",
                    bot=self,
                )
            try:
                from review.db import ReviewStateStore
                store = ReviewStateStore()
                pending = store.get_stale_pending_jobs(max_age_seconds=0)
                if pending:
                    latest_p = pending[0]
                    return send_telegram_message(
                        message=f"📦 *Última Revisión en Cola:*\nJob: `{latest_p.job_id}`\nCanal: *{latest_p.channel}*\nTítulo: {latest_p.title}\nEstado: {latest_p.status}",
                        token=self.token,
                        chat_id=message_chat_id,
                        parse_mode="Markdown",
                        bot=self,
                    )
            except Exception:
                pass
            return reply("📭 No hay entregables en caché. Usa /shorts <tema> para crear uno o /menu para control.")

        if command not in {"stats", "priv", "pub", "unlist", "del", "delsi"}:
            return reply(f"Comando desconocido: /{command}\n{self._HELP_TEXT}")

        parsed = target()
        if parsed is None:
            return DeliveryResult(ok=False, error="Missing video_id argument")
        video_id, channel = parsed

        from src.youtube import control as ctl

        if command == "stats":
            result = ctl.get_video_stats(video_id, channel)
            if not result.get("ok"):
                return reply(f"⚠️ {result.get('error')}")
            return reply(
                f"📊 {result['title']}\n"
                f"ID: {result['video_id']} · canal {channel}\n"
                f"👁 {result['views']:,} · 👍 {result['likes']:,} · 💬 {result['comments']:,}\n"
                f"Visibilidad: {result['privacyStatus']} · Estado: {result['uploadStatus']}"
            )

        if command in {"priv", "pub", "unlist"}:
            wanted = {"priv": "private", "pub": "public", "unlist": "unlisted"}[command]
            result = ctl.set_video_privacy(video_id, wanted, channel)
            if not result.get("ok"):
                return reply(f"⚠️ {result.get('error')}")
            if result.get("action") == "noop":
                return reply(f"ℹ️ Ya estaba en '{wanted}': {video_id}")
            return reply(
                f"✅ Visibilidad {result['previous']} → {result['privacyStatus']}\n{video_id}"
            )

        if command == "del":
            stats = ctl.get_video_stats(video_id, channel)
            title = stats.get("title") if stats.get("ok") else "(no verificable)"
            return reply(
                f"🗑 ¿Borrar definitivamente?\n"
                f"'{title}' ({video_id}, canal {channel})\n\n"
                f"Confirma con:\n/delsi {video_id} {channel}"
            )

        # delsi — confirmed destructive action
        result = ctl.delete_video(video_id, channel)
        if not result.get("ok"):
            return reply(f"⚠️ No se pudo borrar: {result.get('error')}")
        logger.warning("Video deleted via Telegram command by user %s", user_id)
        return reply(f"🗑 Video borrado de YouTube:\n{video_id}")

    # ------------------------------------------------------------------
    # Button-driven control flow (inline keyboards)
    # ------------------------------------------------------------------

    @staticmethod
    def _recent_publications(limit: int = 8) -> list[dict]:
        """Latest published videos from the queue DB for the picker menu."""
        try:
            from src.config import DEFAULT_DB_PATH
            from src.core.repository import connect

            with connect(DEFAULT_DB_PATH, read_only=True) as conn:
                rows = conn.execute(
                    """
                    SELECT story_id, video_id, channel, title
                    FROM publications ORDER BY verified_at DESC LIMIT ?
                    """,
                    (limit,),
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception:
            logger.warning("Could not load recent publications for the menu", exc_info=True)
            return []

    def send_control_menu(self, chat_id: str) -> None:
        def btn(op: str) -> Dict[str, str]:
            return {"text": self._ACTION_LABELS[op], "callback_data": f"ctl:act:{op}"}

        keyboard = {
            "inline_keyboard": [
                [btn("stats"), btn("priv")],
                [btn("pub"), btn("unlist")],
                [btn("del")],
            ]
        }
        send_telegram_message(
            message="🛠 ¿Qué quieres hacer?",
            token=self.token,
            chat_id=chat_id,
            parse_mode=None,
            bot=self,
            reply_markup=keyboard,
        )

    def _videos_keyboard(self, op: str) -> Dict[str, Any] | None:
        videos = self._recent_publications()
        if not videos:
            return None
        rows = []
        for item in videos:
            title = str(item.get("title") or item.get("story_id") or "")[:40]
            vid = str(item.get("video_id") or "")
            if not vid:
                continue
            channel = str(item.get("channel") or "moku")
            rows.append([
                {
                    "text": f"{self._ACTION_LABELS[op].split(' ', 1)[0]} {title} ({channel})",
                    "callback_data": f"ctl:go:{op}:{vid}:{channel}",
                }
            ])
        rows.append([{"text": "↩️ Menú", "callback_data": "ctl:menu"}])
        return {"inline_keyboard": rows}

    def handle_control_callback(self, update: Dict[str, Any]) -> DeliveryResult:
        """Route `ctl:*` button taps through the same fail-closed authorization."""
        query = update.get("callback_query") if isinstance(update, dict) else None
        if not isinstance(query, dict):
            return DeliveryResult(ok=False, error="Not a callback query")

        callback_id = str(query.get("id") or "")
        message = query.get("message") or {}
        message_chat_id = str((message.get("chat") or {}).get("id") or "")
        message_id = message.get("message_id")
        user_id = str((query.get("from") or {}).get("id") or "")

        def deny(reason: str) -> DeliveryResult:
            self.answer_callback_query(callback_id, "Acción no autorizada", show_alert=True)
            logger.warning("Rejected control callback: %s", reason)
            return DeliveryResult(ok=False, error=reason)

        if not self.chat_id or message_chat_id != str(self.chat_id):
            return deny("Unauthorized chat")
        allowed_user_id = os.getenv("TELEGRAM_ALLOWED_USER_ID", "").strip()
        if allowed_user_id and user_id != allowed_user_id:
            return deny("Unauthorized user")

        data = str(query.get("data") or "")
        parts = data.split(":")
        if parts[0] != "ctl" or len(parts) < 2:
            return deny("Invalid control payload")
        step = parts[1]

        def edit(body: str, markup: Dict[str, Any] | None = None) -> DeliveryResult:
            self.edit_message_text(
                body,
                message_id=message_id,
                chat_id=message_chat_id,
                parse_mode=None,
                reply_markup=markup or {"inline_keyboard": []},
            )
            return DeliveryResult(ok=True)

        from src.youtube import control as ctl

        if step == "menu":
            self.answer_callback_query(callback_id, "Menú")
            self.send_control_menu(message_chat_id)
            return DeliveryResult(ok=True)

        if step == "cancel":
            self.answer_callback_query(callback_id, "Cancelado")
            return edit("❌ Cancelado.")

        if step == "act":
            op = parts[2]
            if op not in self._ACTION_LABELS:
                return deny("Unknown control action")
            self.answer_callback_query(callback_id, "Elige un video")
            markup = self._videos_keyboard(op)
            if markup is None:
                return edit("No hay videos publicados todavía.")
            return edit(f"{self._ACTION_LABELS[op]} — elige el video:", markup)

        if step == "go":
            if len(parts) < 5:
                return deny("Invalid control target")
            _, _, op, video_id, channel = parts[:5]
            if op not in self._ACTION_LABELS:
                return deny("Unknown control action")
            self.answer_callback_query(callback_id, "Procesando…")
            if op == "del":
                stats = ctl.get_video_stats(video_id, channel)
                title = stats.get("title") if stats.get("ok") else "(no verificable)"
                confirm_markup = {
                    "inline_keyboard": [
                        [
                            {"text": "✅ Sí, borrar", "callback_data": f"ctl:yes:{video_id}:{channel}"},
                            {"text": "✖️ Cancelar", "callback_data": "ctl:cancel"},
                        ]
                    ]
                }
                return edit(
                    f"🗑 ¿Borrar definitivamente?\n'{title}'\n({video_id}, canal {channel})",
                    confirm_markup,
                )
            return edit(self._control_run(op, video_id, channel))

        if step == "yes":
            if len(parts) < 4:
                return deny("Invalid delete confirmation")
            video_id, channel = parts[2], parts[3]
            self.answer_callback_query(callback_id, "Borrando…")
            result = ctl.delete_video(video_id, channel)
            if not result.get("ok"):
                return edit(f"⚠️ No se pudo borrar: {result.get('error')}")
            logger.warning("Video deleted via Telegram button by user %s", user_id)
            return edit(f"🗑 Video borrado de YouTube:\n{video_id}")

        return deny("Unknown control step")

    def _control_run(self, op: str, video_id: str, channel: str) -> str:
        """Execute a non-destructive control action and format the reply."""
        from src.youtube import control as ctl

        if op == "stats":
            res = ctl.get_video_stats(video_id, channel)
            if not res.get("ok"):
                return f"⚠️ {res.get('error')}"
            return (
                f"📊 {res['title']}\n"
                f"ID: {res['video_id']} · canal {channel}\n"
                f"👁 {res['views']:,} · 👍 {res['likes']:,} · 💬 {res['comments']:,}\n"
                f"Visibilidad: {res['privacyStatus']} · Estado: {res['uploadStatus']}"
            )
        wanted = {"priv": "private", "pub": "public", "unlist": "unlisted"}[op]
        res = ctl.set_video_privacy(video_id, wanted, channel)
        if not res.get("ok"):
            return f"⚠️ {res.get('error')}"
        if res.get("action") == "noop":
            return f"ℹ️ Ya estaba en '{wanted}': {video_id}"
        return f"✅ Visibilidad {res['previous']} → {res['privacyStatus']}\n{video_id}"
