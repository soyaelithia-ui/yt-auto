"""Handler for 'auth' subcommand and YouTube Data API v3 / Drive OAuth lifecycle."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.core.google_auth import (
    load_authorized_user_credentials,
    resolve_channel_token_path,
    standardize_token_file,
)
from src.log import get_logger

logger = get_logger("cli_auth")


def _resolve_channel_key(channel: str | None) -> str:
    from src.branding import resolve_channel_key
    return resolve_channel_key(channel)


def _get_auth_helpers():
    import src.youtube.auth as auth_mod
    return auth_mod.exchange_code, auth_mod.get_auth_url, getattr(auth_mod, "run_local_login_flow", None)


def _get_token_paths():
    import src.config as cfg
    return getattr(cfg, "TOKEN_CHANNEL2_PATH", None), getattr(cfg, "YOUTUBE_TOKEN_PATH", None)


def handle_auth(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Generate OAuth authorization URLs, exchange authorization codes, login, or verify API tokens."""
    action = (getattr(args, "action", None) or "url").lower()
    channel = getattr(args, "channel", "moku") or "moku"

    try:
        target_channel = _resolve_channel_key(channel)
    except (ValueError, KeyError):
        from src.core.domain import CanonicalChannel
        valid_channels = ", ".join(repr(c.value) for c in CanonicalChannel)
        msg = f"Canal desconocido o inválido: {channel!r}. Canales válidos: {valid_channels}"
        if parser is not None:
            parser.error(msg)
        else:
            print(f"Error: {msg}", file=sys.stderr)
            return 2

    target_path = resolve_channel_token_path(target_channel)
    exchange_code_fn, get_auth_url_fn, run_local_login_fn = _get_auth_helpers()

    # 1. Login action (interactive local server flow)
    if action == "login":
        port = getattr(args, "port", 8585) or 8585
        print(f"=== Iniciando autenticación interactiva oficial de Google ({target_channel}) ===")
        print(f"Destino de credenciales: {target_path}")
        try:
            if run_local_login_fn:
                run_local_login_fn(token_path=target_path, port=port)
            else:
                from src.youtube.auth import run_local_login_flow
                run_local_login_flow(token_path=target_path, port=port)
            print(f"Autenticación exitosa. Token guardado en formato oficial en: {target_path}")
            return 0
        except Exception as exc:
            print(f"Error durante el login interactivo: {exc}", file=sys.stderr)
            return 1

    # 2. Exchange action
    if action == "exchange" or getattr(args, "auth_code", None) is not None:
        code_val = (
            getattr(args, "code", None)
            or getattr(args, "auth_code", None)
            or getattr(args, "code_flag", None)
        )
        if not code_val or str(code_val).strip() == "" or code_val == "exchange":
            msg = "El subcomando 'auth exchange' requiere un código de autorización (ej. 'auth exchange <código>' o '--code <código>')"
            if parser is not None:
                parser.error(msg)
            else:
                print(f"Error: {msg}", file=sys.stderr)
                return 2

        print(f"Exchanging authorization code for channel '{target_channel}' ({target_path})...")
        try:
            try:
                exchange_code_fn(str(code_val).strip(), "http://localhost:8585/", token_path=target_path)
            except Exception:
                exchange_code_fn(str(code_val).strip(), "urn:ietf:wg:oauth:2.0:oob", token_path=target_path)
            print(f"YouTube OAuth Token successfully saved to {target_path}!")
            return 0
        except Exception as exc:
            print(f"Error al canjear código de autorización OAuth: {exc}", file=sys.stderr)
            return 1

    # 3. Check action (validate token, scopes, channel identity, and drive access)
    if action == "check":
        print(f"=== Diagnóstico de Credenciales de Google para canal '{target_channel}' ===")
        print(f"Ruta de token: {target_path}")
        if not target_path or not Path(target_path).is_file():
            print("ESTADO: Faltan credenciales. El archivo de token no existe.", file=sys.stderr)
            return 1

        try:
            creds = load_authorized_user_credentials(target_path, auto_refresh=True)
            print(f"• Token cargado: Válido={creds.valid}, Expirado={creds.expired}")
            print(f"• Scopes otorgados: {', '.join(creds.scopes or [])}")

            # Verify YouTube channel preflight
            from src.config import SETTINGS
            from src.youtube.uploader import preflight_youtube_api
            expected_id = SETTINGS.channel(target_channel).expected_youtube_channel_id
            if expected_id:
                yt_info = preflight_youtube_api(
                    channel=target_channel,
                    token_path=target_path,
                    expected_channel_id=expected_id,
                )
                print(f"• YouTube API: OK (Canal: {yt_info.get('title')} [{yt_info.get('channel_id')}])")
            else:
                print("• YouTube API: (channel_id no configurado en settings)")

            # Verify Drive preflight
            from src.config import DRIVE_FOLDER_ID
            from src.drive import preflight_drive_access
            if DRIVE_FOLDER_ID:
                drive_info = preflight_drive_access(folder_id=DRIVE_FOLDER_ID, token_path=target_path)
                print(f"• Google Drive API: OK (Carpeta: {drive_info.get('name')} [{drive_info.get('folder_id')}])")

            print("ESTADO: Todas las APIs de Google verificadas correctamente.")
            return 0
        except Exception as exc:
            print(f"ESTADO: Error de verificación: {exc}", file=sys.stderr)
            return 1

    # 4. Standardize action (convert legacy token file to official Google format)
    if action == "standardize":
        print(f"=== Estandarizando credenciales para canal '{target_channel}' ===")
        print(f"Archivo objetivo: {target_path}")
        if not target_path or not Path(target_path).is_file():
            print("Error: El archivo de token especificado no existe.", file=sys.stderr)
            return 1
        ok = standardize_token_file(target_path)
        if ok:
            print(f"Token estandarizado exitosamente al formato oficial de Google en {target_path} (permisos 0600)")
            return 0
        print("Error al estandarizar el token.", file=sys.stderr)
        return 1

    # Default action: url
    print("=== Google OAuth YouTube API v3 Authorization ===")
    print("Open the following URL in your browser to grant YouTube Upload permissions:")
    print("\n" + get_auth_url_fn("http://localhost:8585/") + "\n")
    print("OOB Authorization URL:")
    print(get_auth_url_fn("urn:ietf:wg:oauth:2.0:oob") + "\n")
    return 0
