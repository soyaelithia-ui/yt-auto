"""Typed project configuration for the two canonical YouTube channels."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.core.domain import CanonicalChannel, canonical_channel


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
if ENV_FILE.exists():
    try:
        from dotenv import load_dotenv

        load_dotenv(ENV_FILE)
    except ImportError:
        pass

os.environ.setdefault("FFMPEG_CHUNKED_XFADE", "0")


def _env_path(name: str, default: Path) -> Path:
    return Path(os.environ.get(name, str(default))).expanduser().resolve()


def _env_int(name: str, default: int) -> int:
    value = int(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


def _oauth_token_has_scope(path: Path, required_scope: str) -> bool:
    """Check a token file's declared scopes without printing token contents."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return False
    scopes = data.get("scope") or data.get("scopes") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return required_scope in scopes


def _env_float(name: str, default: float) -> float:
    value = float(os.environ.get(name, str(default)))
    if value <= 0:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


@dataclass(frozen=True)
class SubtitleSettings:
    template: str
    font_name: str
    font_size: int
    primary_colour: str
    outline_colour: str
    play_res_x: int = 1280
    play_res_y: int = 720


@dataclass(frozen=True)
class DesignSettings:
    style: str
    primary_colour: str
    accent_colour: str
    font_bold: str
    font_regular: str
    scene_min_seconds: int = 15
    scene_max_seconds: int = 30


@dataclass(frozen=True)
class ChannelSettings:
    key: CanonicalChannel
    public_name: str
    handle: str
    topic: str
    voice: str
    tts_provider: str
    tone: str
    intro: str
    cta: str
    seo_tags: tuple[str, ...]
    subtitle: SubtitleSettings
    design: DesignSettings
    cookies_path: Path
    youtube_token_path: Path
    expected_youtube_channel_id: str
    source_feed: str
    min_video_seconds: int = 30
    max_parallel_jobs: int = 1
    video_mode: str = "short"

    def public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["key"] = self.key.value
        data["cookies_path"] = str(self.cookies_path)
        data["youtube_token_path"] = str(self.youtube_token_path)
        return data


@dataclass(frozen=True)
class RuntimeSettings:
    database_path: Path
    work_root: Path
    artifact_root: Path
    bot_home: Path
    scheduler_interval_seconds: int
    render_timeout_seconds: int
    max_work_bytes: int
    min_free_bytes: int
    render_crf: int
    drive_folder_id: str
    drive_root_folder_id: str
    drive_use_gcloud: bool
    drive_approved_folder_id: str
    drive_approved_video_folder_id: str
    drive_approved_cover_folder_id: str
    drive_metadata_folder_id: str
    drive_published_folder_id: str
    drive_rejected_folder_id: str
    drive_archive_folder_id: str
    drive_key_path: Path
    channels: dict[CanonicalChannel, ChannelSettings] = field(repr=False)
    short_compositor: str = "loop"
    video_engine: str = "loop"
    enable_subtitles: bool = False

    def channel(self, value: str | CanonicalChannel) -> ChannelSettings:
        return self.channels[canonical_channel(value)]


BOT_HOME_PATH = _env_path("BOT_HOME", BASE_DIR / ".bot_home")
ANTIGRAVITY_AGENTS_APP_DATA_DIR = _env_path(
    "ANTIGRAVITY_AGENTS_APP_DATA_DIR", BOT_HOME_PATH / ".gemini" / "antigravity-cli"
)
SECRETS_DIR = _env_path("SECRETS_DIR", BASE_DIR / "secrets")

MOKU = ChannelSettings(
    key=CanonicalChannel.MOKU,
    public_name="Moku",
    handle=os.environ.get("MOKU_HANDLE", "@MokuRedit"),
    topic="terror psicológico, relatos inquietantes y creepypasta",
    voice=os.environ.get("MOKU_TTS_VOICE", "es-MX-JorgeNeural"),
    tts_provider=os.environ.get("MOKU_TTS_PROVIDER", "edge-tts"),
    tone="oscuro, cinematográfico, inmersivo y sobrio",
    intro="Apaga las luces y escucha con atención.",
    cta="Suscríbete a Moku y cuéntanos en comentarios qué parte te inquietó más.",
    seo_tags=(
        "Moku",
        "historias de terror",
        "creepypasta en español",
        "terror psicológico",
        "relatos de miedo",
    ),
    subtitle=SubtitleSettings(
        template="moku",
        font_name="DejaVu Sans",
        font_size=46,
        primary_colour="&H00FFFFFF",
        outline_colour="&H00100B08",
    ),
    design=DesignSettings(
        style="dark_cinematic",
        primary_colour="#0D1117",
        accent_colour="#D43B32",
        font_bold="DejaVuSans-Bold.ttf",
        font_regular="DejaVuSans.ttf",
    ),
    cookies_path=_env_path("MOKU_COOKIES_PATH", SECRETS_DIR / "decrypted_cookies.json"),
    youtube_token_path=_env_path(
        "MOKU_YOUTUBE_TOKEN_PATH", SECRETS_DIR / "youtube_token.json"
    ),
    expected_youtube_channel_id=os.environ.get(
        "MOKU_YOUTUBE_CHANNEL_ID", ""
    ).strip(),
    source_feed=os.environ.get("MOKU_SOURCE_FEED", "nosleep"),
)

AELITHIA = ChannelSettings(
    key=CanonicalChannel.AELITHIA,
    public_name="Aelithia",
    handle=os.environ.get("AELITHIA_HANDLE", "@Aelithia-c1f"),
    topic="historias personales, dilemas morales y relaciones humanas",
    voice=os.environ.get("AELITHIA_TTS_VOICE", "es-MX-DaliaNeural"),
    tts_provider=os.environ.get("AELITHIA_TTS_PROVIDER", "edge-tts"),
    tone="emocional, moderno, empático y reflexivo",
    intro="Bienvenidos a Aelithia. Hoy escucharemos una historia que merece ser debatida.",
    cta="Suscríbete a Aelithia y dinos con respeto qué habrías hecho tú.",
    seo_tags=(
        "Aelithia",
        "historias reales",
        "dilemas morales",
        "relaciones humanas",
        "relatos en español",
    ),
    subtitle=SubtitleSettings(
        template="aelithia",
        font_name="DejaVu Sans",
        font_size=44,
        primary_colour="&H00FFFFFF",
        outline_colour="&H00412623",
    ),
    design=DesignSettings(
        style="emotional_modern",
        primary_colour="#31263E",
        accent_colour="#FF8FA3",
        font_bold="DejaVuSans-Bold.ttf",
        font_regular="DejaVuSans.ttf",
    ),
    cookies_path=_env_path(
        "AELITHIA_COOKIES_PATH", SECRETS_DIR / "cookies_channel2.json"
    ),
    youtube_token_path=_env_path(
        "AELITHIA_YOUTUBE_TOKEN_PATH", SECRETS_DIR / "youtube_token_aelithia.json"
    ),
    expected_youtube_channel_id=os.environ.get(
        "AELITHIA_YOUTUBE_CHANNEL_ID", ""
    ).strip(),
    source_feed=os.environ.get("AELITHIA_SOURCE_FEED", "AmItheAsshole"),
)

# ---------------------------------------------------------------------------
# Runtime profiles (WP1): production vs CLI sandbox isolation.
#   YT_PROFILE=prod  -> canonical roots (data/, work/, artifacts/); daemon/docker
#   YT_PROFILE=cli   -> sandbox roots data/cli/, work/cli/, ...  (default manual)
#   YT_PROFILE=test  -> data/test/, ... (auto under TEST_MODE or pytest)
# Explicit env overrides (YOUTUBE_AUTOMATION_DB, VIDEO_REVIEW_DB_PATH,
# WORK_ROOT, ARTIFACT_ROOT) always win over profile-derived defaults.
RUNTIME_PROFILE = os.environ.get("YT_PROFILE", "").strip().lower()
if RUNTIME_PROFILE in {"prod", "production"}:
    RUNTIME_PROFILE = "prod"
elif RUNTIME_PROFILE == "test":
    RUNTIME_PROFILE = "test"
elif RUNTIME_PROFILE in {"cli", "dev", "sandbox"}:
    RUNTIME_PROFILE = "cli"
else:
    # Sin valor explícito: test bajo TEST_MODE/pytest; cli en manual.
    RUNTIME_PROFILE = (
        "test"
        if (os.environ.get("TEST_MODE") == "1" or "pytest" in sys.modules)
        else "prod" if os.environ.get("YT_DAEMON") == "1" else "cli"
    )

PROFILE_DATA_ROOT = (
    BASE_DIR / "data" if RUNTIME_PROFILE == "prod" else BASE_DIR / "data" / RUNTIME_PROFILE
)
PROFILE_WORK_ROOT = (
    BASE_DIR / "work" if RUNTIME_PROFILE == "prod" else BASE_DIR / "work" / RUNTIME_PROFILE
)
PROFILE_ARTIFACT_ROOT = (
    BASE_DIR / "artifacts"
    if RUNTIME_PROFILE == "prod"
    else BASE_DIR / "artifacts" / RUNTIME_PROFILE
)
try:
    PROFILE_DATA_ROOT.mkdir(parents=True, exist_ok=True)
except OSError:
    pass


def default_review_db_path() -> Path:
    """Review-state DB default honoring runtime profiles (explicit env wins)."""
    return Path(
        os.environ.get(
            "VIDEO_REVIEW_DB_PATH", str(PROFILE_DATA_ROOT / "review_state.db")
        )
    ).expanduser()


SETTING_DB_PATH = PROFILE_DATA_ROOT / "shorts_queue.db"
SETTINGS = RuntimeSettings(
    database_path=_env_path("YOUTUBE_AUTOMATION_DB", SETTING_DB_PATH),
    work_root=_env_path("WORK_ROOT", PROFILE_WORK_ROOT),
    artifact_root=_env_path("ARTIFACT_ROOT", PROFILE_ARTIFACT_ROOT),
    bot_home=BOT_HOME_PATH,
    scheduler_interval_seconds=_env_int("SCHEDULER_INTERVAL_SECONDS", 1800),
    render_timeout_seconds=_env_int("RENDER_TIMEOUT_SECONDS", 10_800),
    max_work_bytes=_env_int("MAX_WORK_BYTES", 20 * 1024**3),
    min_free_bytes=_env_int("MIN_FREE_BYTES", 15 * 1024**3),
    render_crf=_env_int("RENDER_CRF", 21),
    drive_folder_id=os.environ.get("DRIVE_FOLDER_ID", "").strip(),
    drive_root_folder_id=os.environ.get("DRIVE_ROOT_FOLDER_ID", "").strip(),
    drive_use_gcloud=os.environ.get("DRIVE_USE_GCLOUD", "0").strip() == "1",
    drive_approved_folder_id=os.environ.get("DRIVE_APPROVED_FOLDER_ID", "").strip(),
    drive_approved_video_folder_id=os.environ.get("DRIVE_APPROVED_VIDEO_FOLDER_ID", "").strip(),
    drive_approved_cover_folder_id=os.environ.get("DRIVE_APPROVED_COVER_FOLDER_ID", "").strip(),
    drive_metadata_folder_id=os.environ.get("DRIVE_METADATA_FOLDER_ID", "").strip(),
    drive_published_folder_id=os.environ.get("DRIVE_PUBLISHED_FOLDER_ID", "").strip(),
    drive_rejected_folder_id=os.environ.get("DRIVE_REJECTED_FOLDER_ID", "").strip(),
    drive_archive_folder_id=os.environ.get("DRIVE_ARCHIVE_FOLDER_ID", "").strip(),
    drive_key_path=_env_path("DRIVE_KEY_PATH", SECRETS_DIR / "drive_key.json"),
    channels={CanonicalChannel.MOKU: MOKU, CanonicalChannel.AELITHIA: AELITHIA},
    short_compositor=os.environ.get("SHORT_COMPOSITOR", os.environ.get("VIDEO_ENGINE", os.environ.get("COMPOSITOR", "loop"))),
    video_engine=os.environ.get("VIDEO_ENGINE", os.environ.get("COMPOSITION_ENGINE", "loop")),
    enable_subtitles=os.environ.get("ENABLE_SUBTITLES", "0").strip().lower() in ("1", "true", "yes"),
)


def validate_runtime_config(
    *,
    require_drive: bool = False,
    require_publish: bool = False,
    require_review: bool = False,
) -> None:
    errors: list[str] = []
    if require_drive:
        if not SETTINGS.drive_folder_id:
            errors.append("DRIVE_FOLDER_ID es obligatorio para respaldar")
        if not SETTINGS.drive_approved_video_folder_id:
            errors.append("DRIVE_APPROVED_VIDEO_FOLDER_ID es obligatorio para respaldar")
        drive_scope = "https://www.googleapis.com/auth/drive"
        has_oauth_drive = any(
            channel.youtube_token_path.is_file()
            and _oauth_token_has_scope(channel.youtube_token_path, drive_scope)
            for channel in SETTINGS.channels.values()
        )
        if not SETTINGS.drive_use_gcloud and not SETTINGS.drive_key_path.exists() and not has_oauth_drive:
            errors.append(
                "Falta DRIVE_KEY_PATH y no hay un token OAuth de canal con scope Drive"
            )
    if require_publish:
        for channel in SETTINGS.channels.values():
            if not channel.cookies_path.exists() or not channel.youtube_token_path.exists():
                errors.append(
                    f"{channel.key.value}: faltan cookies o token de YouTube"
                )
            if not channel.expected_youtube_channel_id:
                errors.append(f"{channel.key.value}: falta el channel ID de YouTube")
    if require_review:
        if os.environ.get("TEST_MODE") == "1":
            errors.append("TEST_MODE=1 no está permitido en producción")
        if os.environ.get("AUTO_APPROVE") == "1":
            errors.append("AUTO_APPROVE=1 no está permitido en producción")
        if os.environ.get("ENABLE_AUTO_PUBLISH_SWEEP") == "1":
            errors.append("ENABLE_AUTO_PUBLISH_SWEEP=1 requiere una activación explícita posterior")
        token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
        chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
        allowed_user = os.environ.get("TELEGRAM_ALLOWED_USER_ID", "").strip()
        allowed_chat = os.environ.get("TELEGRAM_ALLOWED_CHAT_ID", "").strip()
        if not token:
            errors.append("TELEGRAM_BOT_TOKEN es obligatorio")
        if not chat_id or not chat_id.lstrip("-").isdigit():
            errors.append("TELEGRAM_CHAT_ID debe ser numérico")
        if not allowed_user or not allowed_user.isdigit():
            errors.append("TELEGRAM_ALLOWED_USER_ID debe ser numérico")
        if not allowed_chat or not allowed_chat.lstrip("-").isdigit():
            errors.append("TELEGRAM_ALLOWED_CHAT_ID debe ser numérico")
        review_path = default_review_db_path()
        if not review_path.parent.exists():
            errors.append(f"No existe el directorio de VIDEO_REVIEW_DB_PATH: {review_path.parent}")
        elif not os.access(review_path.parent, os.W_OK):
            errors.append(f"No se puede escribir en el directorio de revisión: {review_path.parent}")
    if errors:
        raise RuntimeError("; ".join(errors))


def get_channel_config(channel: str | CanonicalChannel) -> dict[str, Any]:
    """Compatibility facade; aliases are accepted only as input."""
    return SETTINGS.channel(channel).public_dict()


def get_channel_settings(channel: str | CanonicalChannel) -> ChannelSettings:
    return SETTINGS.channel(channel)


def is_test_environment() -> bool:
    return os.environ.get("TEST_MODE") == "1" or "pytest" in sys.modules


# Compatibility constants used by existing modules while the pipeline is migrated.
BOT_HOME = str(SETTINGS.bot_home)
PLAYWRIGHT_BROWSERS_PATH = os.environ.get(
    "PLAYWRIGHT_BROWSERS_PATH",
    str(SETTINGS.bot_home / ".cache" / "ms-playwright"),
)
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = PLAYWRIGHT_BROWSERS_PATH
DEFAULT_DB_PATH = str(SETTINGS.database_path)

# R6: bound FFmpeg thread pools inside the cgroup (cpus=4) unless overridden.
FFMPEG_THREADS = int(os.environ.get("FFMPEG_THREADS", "2"))

PYTHON_BIN = os.environ.get("PYTHON_BIN", sys.executable)

LOCK_FILE_PATH = os.environ.get(
    "LOCK_FILE_PATH", str(BASE_DIR / "scratch" / "youtube_automation.lock")
)
DRIVE_FOLDER_ID = SETTINGS.drive_folder_id
DRIVE_KEY_PATH = str(SETTINGS.drive_key_path)
DRIVE_UPLOAD_MAX_RETRIES = _env_int("DRIVE_UPLOAD_MAX_RETRIES", 3)
DECRYPTED_COOKIES_PATH = str(MOKU.cookies_path)
COOKIES_CHANNEL2_PATH = str(AELITHIA.cookies_path)
YOUTUBE_TOKEN_PATH = str(MOKU.youtube_token_path)
TOKEN_AELITHIA_PATH = str(AELITHIA.youtube_token_path)
TOKEN_CHANNEL2_PATH = os.environ.get(
    "TOKEN_CHANNEL2_PATH",
    os.environ.get("YOUTUBE_TOKEN_CHANNEL2_PATH", TOKEN_AELITHIA_PATH),
)
CHANNELS_CONFIG = {
    channel.value: settings.public_dict()
    for channel, settings in SETTINGS.channels.items()
}
DEFAULT_SUBREDDIT = MOKU.source_feed
SHORT_MIN_DURATION_SEC = _env_float("SHORT_MIN_DURATION_SEC", 60.0)
SHORT_MAX_DURATION_SEC = _env_float("SHORT_MAX_DURATION_SEC", 180.0)
SHORT_TARGET_DURATION_SEC = _env_float("SHORT_TARGET_DURATION_SEC", 150.0)

LONG_MIN_DURATION_SEC = _env_float("LONG_MIN_DURATION_SEC", 600.0)
LONG_MAX_DURATION_SEC = _env_float("LONG_MAX_DURATION_SEC", 1800.0)
LONG_TARGET_DURATION_SEC = _env_float("LONG_TARGET_DURATION_SEC", 600.0)
LONG_MIN_WORDS = _env_int("LONG_MIN_WORDS", 2400)

SHORT_MIN_DURATION = SHORT_MIN_DURATION_SEC
SHORT_MAX_DURATION = SHORT_MAX_DURATION_SEC
SHORT_TARGET_DURATION = SHORT_TARGET_DURATION_SEC
LONG_MIN_DURATION = LONG_MIN_DURATION_SEC
LONG_MAX_DURATION = LONG_MAX_DURATION_SEC
LONG_TARGET_DURATION = LONG_TARGET_DURATION_SEC

VERTICAL_DOC_MIN_DURATION_SEC = _env_float("VERTICAL_DOC_MIN_DURATION_SEC", 180.0)
VERTICAL_DOC_MAX_DURATION_SEC = _env_float("VERTICAL_DOC_MAX_DURATION_SEC", 300.0)
VERTICAL_DOC_TARGET_DURATION_SEC = _env_float("VERTICAL_DOC_TARGET_DURATION_SEC", 240.0)

MIN_VIDEO_DURATION_SEC = LONG_MIN_DURATION_SEC
BACKGROUNDS_DIR = os.environ.get(
    "BACKGROUNDS_DIR", str(BASE_DIR / "assets" / "backgrounds")
)
MUSIC_DIR = os.environ.get("MUSIC_DIR", str(BASE_DIR / "assets" / "music"))
ASSETS_LIBRARY_DIR = os.environ.get(
    "ASSETS_LIBRARY_DIR", str(BASE_DIR / "assets" / "library")
)
TEMPLATES_DIR = os.environ.get("TEMPLATES_DIR", str(BASE_DIR / "assets" / "templates"))
DEFAULT_BACKGROUND = os.environ.get(
    "DEFAULT_BACKGROUND", str(BASE_DIR / "assets" / "background.jpg")
)
DEFAULT_LANG = "es"
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")


def resolve_channel2_token_path() -> str:
    override = os.environ.get("TOKEN_CHANNEL2_PATH") or os.environ.get(
        "YOUTUBE_TOKEN_CHANNEL2_PATH"
    )
    if override:
        return str(Path(override).expanduser().resolve())
    return str(TOKEN_AELITHIA_PATH)


def resolve_google_credentials(sa_key_path: str | None = None) -> Any:
    path = Path(sa_key_path or YOUTUBE_TOKEN_PATH)
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return SimpleNamespace(
                    token=data.get("access_token", ""),
                    refresh_token=data.get("refresh_token", ""),
                    client_id=data.get("client_id", ""),
                    client_secret=data.get("client_secret", ""),
                    token_uri=data.get(
                        "token_uri", "https://oauth2.googleapis.com/token"
                    ),
                )
        except (OSError, ValueError):
            pass
    return SimpleNamespace(token="", refresh_token="")
