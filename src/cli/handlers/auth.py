"""Handler for 'auth' subcommand and YouTube Data API v3 OAuth lifecycle."""
from __future__ import annotations

import argparse
import sys
from typing import Any

def _resolve_channel_key(channel: str | None) -> str:
    import sys

    if "src.branding" in sys.modules:
        br = sys.modules["src.branding"]
    else:
        import src.branding as br

    return br.resolve_channel_key(channel)


def _get_auth_helpers():
    import sys

    if "src.youtube.auth" in sys.modules:
        auth_mod = sys.modules["src.youtube.auth"]
    else:
        import src.youtube.auth as auth_mod

    return auth_mod.exchange_code, auth_mod.get_auth_url


def _get_token_paths():
    import sys

    if "src.config" in sys.modules:
        cfg = sys.modules["src.config"]
    else:
        import src.config as cfg

    return getattr(cfg, "TOKEN_CHANNEL2_PATH", None), getattr(cfg, "YOUTUBE_TOKEN_PATH", None)


def handle_auth(args: argparse.Namespace, parser: argparse.ArgumentParser | None = None) -> int:
    """Generate OAuth authorization URLs or exchange authorization codes for API tokens."""
    action = (getattr(args, "action", None) or "url").lower()
    channel = getattr(args, "channel", "moku") or "moku"

    try:
        target_channel = _resolve_channel_key(channel)
    except (ValueError, KeyError):
        msg = f"Canal desconocido o inválido: {channel!r}. Canales válidos: 'moku', 'aelithia'"
        if parser is not None:
            parser.error(msg)
        else:
            print(f"Error: {msg}", file=sys.stderr)
            return 2

    token_ch2_path, token_moku_path = _get_token_paths()
    exchange_code_fn, get_auth_url_fn = _get_auth_helpers()

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

        target_path = token_ch2_path if target_channel == "aelithia" else token_moku_path
        print(f"Exchanging authorization code for channel '{target_channel}' ({target_path})...")
        try:
            try:
                exchange_code_fn(str(code_val).strip(), "urn:ietf:wg:oauth:2.0:oob", token_path=target_path)
            except Exception:
                exchange_code_fn(str(code_val).strip(), "http://localhost:8585/", token_path=target_path)
            print(f"YouTube OAuth Token successfully saved to {target_path}!")
            return 0
        except Exception as exc:
            print(f"Error al canjear código de autorización OAuth: {exc}", file=sys.stderr)
            return 1

    # Default action: url
    print("=== Google OAuth YouTube API v3 Authorization ===")
    print("Open the following URL in your browser to grant YouTube Upload permissions:")
    print("\n" + get_auth_url_fn("http://localhost:8585/") + "\n")
    print("OOB Authorization URL:")
    print(get_auth_url_fn("urn:ietf:wg:oauth:2.0:oob") + "\n")
    return 0
