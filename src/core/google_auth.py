"""Official Google OAuth 2.0 and API Client Service Manager.

Provides standard Google-recommended patterns for authenticating, loading,
refreshing, and serializing credentials for YouTube Data API v3 and Google Drive API v3.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import Resource, build
import google_auth_oauthlib.flow

from src.config import (
    BASE_DIR,
    DRIVE_KEY_PATH,
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    YOUTUBE_TOKEN_PATH,
    get_channel_settings,
    resolve_channel2_token_path,
)
from src.core.domain import AuthenticationError, CanonicalChannel, canonical_channel
from src.log import get_logger

logger = get_logger("google_auth")

YOUTUBE_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/youtube",
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]

DRIVE_SCOPES: List[str] = [
    "https://www.googleapis.com/auth/drive",
]

DEFAULT_SCOPES: List[str] = list(dict.fromkeys(YOUTUBE_SCOPES + DRIVE_SCOPES))

# Loopback only — Google deprecated urn:ietf:wg:oauth:2.0:oob (RFC 8252).
DEFAULT_REDIRECT_URIS: List[str] = [
    "http://localhost:8585/",
    "http://localhost:8080/",
    "http://127.0.0.1:8585/",
    "http://127.0.0.1:8080/",
]


def resolve_client_id(client_id: Optional[str] = None) -> str:
    """Resolve OAuth client ID from arg, environment, or config."""
    cid = (client_id or os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID or "").strip()
    if not cid:
        raise AuthenticationError("GOOGLE_CLIENT_ID no está configurado")
    return cid


def resolve_client_secret(client_secret: Optional[str] = None) -> str:
    """Resolve OAuth client secret from arg, environment, or config."""
    csec = (client_secret or os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET or "").strip()
    if not csec:
        raise AuthenticationError("GOOGLE_CLIENT_SECRET no está configurado")
    return csec


def build_client_config(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    redirect_uris: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate official Google client secrets dictionary in 'installed' format."""
    cid = resolve_client_id(client_id)
    csec = resolve_client_secret(client_secret)
    return {
        "installed": {
            "client_id": cid,
            "client_secret": csec,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
            "redirect_uris": redirect_uris or list(DEFAULT_REDIRECT_URIS),
        }
    }


def create_oauth_flow(
    client_id: Optional[str] = None,
    client_secret: Optional[str] = None,
    client_secrets_file: Optional[str | Path] = None,
    scopes: Optional[List[str]] = None,
    redirect_uri: Optional[str] = None,
) -> google_auth_oauthlib.flow.InstalledAppFlow:
    """Create an official InstalledAppFlow instance for Google OAuth 2.0."""
    effective_scopes = scopes or DEFAULT_SCOPES
    if client_secrets_file and Path(client_secrets_file).is_file():
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            str(client_secrets_file),
            scopes=effective_scopes,
        )
    else:
        config = build_client_config(client_id=client_id, client_secret=client_secret)
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_config(
            config,
            scopes=effective_scopes,
        )
    if redirect_uri:
        flow.redirect_uri = redirect_uri
    return flow


def save_credentials(credentials: Credentials, token_path: str | Path) -> None:
    """Save credentials to disk in official Google authorized user format with chmod 0600."""
    target = Path(token_path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)

    json_data = credentials.to_json()
    temp_file = target.with_suffix(f".tmp.{os.getpid()}")
    try:
        temp_file.write_text(json_data, encoding="utf-8")
        os.chmod(temp_file, 0o600)
        temp_file.replace(target)
        os.chmod(target, 0o600)
        logger.info("Saved standardized Google credentials to %s", target)
    finally:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except OSError:
                pass


def load_authorized_user_credentials(
    token_path: str | Path,
    scopes: Optional[List[str]] = None,
    auto_refresh: bool = True,
) -> Credentials:
    """Load, normalize (if legacy format), and optionally refresh Google OAuth 2.0 credentials."""
    path = Path(token_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"El archivo de credenciales no existe: {path}")

    raw_text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise AuthenticationError(f"Archivo de credenciales malformado ({path}): {exc}") from exc

    if not isinstance(data, dict):
        raise AuthenticationError(f"El contenido de credenciales debe ser un objeto JSON ({path})")

    # Normalize scopes
    raw_scopes = data.get("scopes") or data.get("scope") or scopes or DEFAULT_SCOPES
    if isinstance(raw_scopes, str):
        parsed_scopes = raw_scopes.split()
    elif isinstance(raw_scopes, list):
        parsed_scopes = [str(s) for s in raw_scopes]
    else:
        parsed_scopes = list(scopes or DEFAULT_SCOPES)

    client_id = data.get("client_id") or os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    client_secret = data.get("client_secret") or os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET

    normalized_info: Dict[str, Any] = {
        "token": data.get("token") or data.get("access_token") or "",
        "refresh_token": data.get("refresh_token") or "",
        "token_uri": data.get("token_uri") or "https://oauth2.googleapis.com/token",
        "client_id": client_id,
        "client_secret": client_secret,
        "scopes": parsed_scopes,
        "universe_domain": data.get("universe_domain", "googleapis.com"),
    }
    if data.get("expiry"):
        normalized_info["expiry"] = data.get("expiry")

    credentials = Credentials.from_authorized_user_info(normalized_info, scopes=parsed_scopes)

    # Refresh if expired and refresh_token is present
    if auto_refresh and credentials.expired and credentials.refresh_token:
        try:
            logger.info("Refreshing expired Google credentials for %s", path.name)
            credentials.refresh(Request())
            try:
                save_credentials(credentials, path)
            except OSError as save_err:
                logger.debug("Could not persist refreshed credentials to %s (read-only filesystem): %s", path, save_err)
        except Exception as exc:
            logger.warning("No se pudo refrescar el token de Google (%s): %s", path, exc)

    return credentials


def standardize_token_file(token_path: str | Path) -> bool:
    """Standardize an existing token file to the official Google format."""
    try:
        creds = load_authorized_user_credentials(token_path, auto_refresh=True)
        save_credentials(creds, token_path)
        return True
    except Exception as exc:
        logger.error("Failed to standardize token file %s: %s", token_path, exc)
        return False


def resolve_channel_token_path(channel: str | CanonicalChannel) -> str:
    """Resolve the token file path for any canonical channel dynamically."""
    key = canonical_channel(channel)
    cid = key.value if hasattr(key, "value") else str(key)
    prefix = cid.upper()

    # 1. Environment variable overrides (highest precedence)
    override = os.environ.get(f"{prefix}_YOUTUBE_TOKEN_PATH")
    if override:
        return str(Path(override).expanduser().resolve())

    # Legacy environment overrides for backwards compatibility
    if key == CanonicalChannel.AELITHIA:
        override = os.environ.get("TOKEN_CHANNEL2_PATH") or os.environ.get("YOUTUBE_TOKEN_CHANNEL2_PATH")
        if override:
            return str(Path(override).expanduser().resolve())
    elif key == CanonicalChannel.MOKU:
        override = os.environ.get("YOUTUBE_TOKEN_PATH")
        if override:
            return str(Path(override).expanduser().resolve())

    # 2. Dynamic profile configuration (e.g. secrets/tokens/<channel>.json)
    configured_path = None
    try:
        settings = get_channel_settings(key)
        configured_path = Path(settings.youtube_token_path)
        if configured_path.is_file():
            return str(configured_path.resolve())
    except Exception:
        pass

    # 3. Fallback candidates (modular secrets/tokens/<channel>.json or legacy paths)
    modular_candidate = BASE_DIR / "secrets" / "tokens" / f"{cid}.json"
    if modular_candidate.is_file():
        return str(modular_candidate.resolve())

    legacy_named = BASE_DIR / "secrets" / f"youtube_token_{cid}.json"
    if legacy_named.is_file():
        return str(legacy_named.resolve())

    if key == CanonicalChannel.MOKU:
        legacy_moku = BASE_DIR / "secrets" / "youtube_token.json"
        if legacy_moku.is_file():
            return str(legacy_moku.resolve())

    if configured_path:
        return str(configured_path.resolve())

    return str(modular_candidate.resolve())


def build_youtube_service(
    token_path: Optional[str | Path] = None,
    channel: Optional[str | CanonicalChannel] = None,
) -> Resource:
    """Build and return an official YouTube Data API v3 client Resource."""
    if token_path is None:
        if channel is None:
            channel = CanonicalChannel.MOKU
        token_path = resolve_channel_token_path(channel)

    credentials = load_authorized_user_credentials(
        token_path,
        scopes=YOUTUBE_SCOPES,
        auto_refresh=True,
    )
    return build("youtube", "v3", credentials=credentials, cache_discovery=False)


def _gcloud_credentials() -> Credentials:
    """Build in-memory credentials using the active gcloud CLI account."""
    try:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthenticationError("gcloud no pudo proporcionar un token de Google") from exc

    access_token = completed.stdout.strip()
    if not access_token:
        raise AuthenticationError("gcloud no devolvió un token de acceso válido")

    return Credentials(token=access_token, scopes=DRIVE_SCOPES)


def get_drive_credentials(
    sa_key_path: Optional[str | Path] = None,
    token_path: Optional[str | Path] = None,
    use_gcloud: bool = False,
) -> Any:
    """Resolve Drive credentials from gcloud, service account file, or authorized OAuth token."""
    if use_gcloud or os.environ.get("DRIVE_USE_GCLOUD", "0").strip() == "1":
        return _gcloud_credentials()

    if token_path and Path(token_path).is_file():
        try:
            return load_authorized_user_credentials(token_path, scopes=DRIVE_SCOPES)
        except Exception as exc:
            logger.warning("No se pudo cargar token OAuth para Drive (%s): %s", token_path, exc)

    if sa_key_path and Path(sa_key_path).is_file():
        sa_path = Path(sa_key_path)
        try:
            data = json.loads(sa_path.read_text(encoding="utf-8"))
            if data.get("type") == "service_account":
                from google.oauth2 import service_account

                return service_account.Credentials.from_service_account_file(
                    str(sa_path),
                    scopes=DRIVE_SCOPES,
                )
            if data.get("refresh_token"):
                return load_authorized_user_credentials(sa_path, scopes=DRIVE_SCOPES)
        except Exception as exc:
            raise AuthenticationError(f"Error al leer clave de Drive ({sa_key_path}): {exc}") from exc
        raise AuthenticationError("DRIVE_KEY_PATH no es ni service account ni token OAuth válido")

    # Fallback to default channel tokens if available
    for ch_token in [YOUTUBE_TOKEN_PATH, resolve_channel2_token_path()]:
        if ch_token and Path(ch_token).is_file():
            try:
                return load_authorized_user_credentials(ch_token, scopes=DRIVE_SCOPES)
            except Exception:
                continue

    raise AuthenticationError("Drive requiere DRIVE_KEY_PATH, gcloud o un token OAuth válido")


def build_drive_service(
    sa_key_path: Optional[str | Path] = None,
    token_path: Optional[str | Path] = None,
    use_gcloud: bool = False,
) -> Resource:
    """Build and return an official Google Drive API v3 client Resource."""
    credentials = get_drive_credentials(
        sa_key_path=sa_key_path,
        token_path=token_path,
        use_gcloud=use_gcloud,
    )
    return build("drive", "v3", credentials=credentials, cache_discovery=False)
