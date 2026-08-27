"""YouTube and Google Drive OAuth 2.0 authentication lifecycle."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Optional

from src.config import BASE_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, YOUTUBE_TOKEN_PATH
from src.core.google_auth import (
    DEFAULT_SCOPES,
    DRIVE_SCOPES,
    YOUTUBE_SCOPES,
    build_client_config,
    create_oauth_flow,
    load_authorized_user_credentials,
    save_credentials,
    standardize_token_file,
)
from src.log import get_logger

logger = get_logger("youtube_auth")

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
TOKEN_PATH = str(BASE_DIR / "secrets" / "youtube_token.json")


def get_auth_url(
    redirect_uri: str = "http://localhost:8585/",
    scopes: Optional[list[str]] = None,
) -> str:
    """Generate the official Google OAuth 2.0 authorization URL."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID no está configurado")

    flow = create_oauth_flow(
        client_id=client_id,
        scopes=scopes or DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, _ = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )
    return auth_url


def exchange_code(
    code: str,
    redirect_uri: str = "urn:ietf:wg:oauth:2.0:oob",
    token_path: Optional[str] = None,
    scopes: Optional[list[str]] = None,
) -> None:
    """Exchange authorization code for tokens and save in official Google format."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET deben proporcionarse por entorno"
        )
    target_path = token_path or TOKEN_PATH

    flow = create_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
    )
    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        logger.warning("fetch_token with redirect_uri=%s failed: %s. Trying fallback uri...", redirect_uri, exc)
        # Try alternate redirect URI if OOB or localhost failed
        alt_uri = "http://localhost:8585/" if redirect_uri != "http://localhost:8585/" else "urn:ietf:wg:oauth:2.0:oob"
        flow = create_oauth_flow(
            client_id=client_id,
            client_secret=client_secret,
            scopes=scopes or DEFAULT_SCOPES,
            redirect_uri=alt_uri,
        )
        flow.fetch_token(code=code)

    save_credentials(flow.credentials, target_path)
    print(f"Credentials saved successfully to {target_path}!")


def run_local_login_flow(
    token_path: Optional[str] = None,
    port: int = 8585,
    scopes: Optional[list[str]] = None,
) -> None:
    """Run official Google InstalledAppFlow local server for 1-click browser login."""
    client_id = os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET deben proporcionarse por entorno"
        )
    target_path = token_path or TOKEN_PATH

    flow = create_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or DEFAULT_SCOPES,
    )
    print(f"Starting local OAuth authentication server on port {port}...")
    credentials = flow.run_local_server(
        port=port,
        prompt="consent",
        access_type="offline",
        open_browser=True,
    )
    save_credentials(credentials, target_path)
    print(f"Official Google credentials successfully saved to {target_path}!")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        exchange_code(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        exchange_code(sys.argv[1])
    else:
        print("Auth URL (localhost):", get_auth_url("http://localhost:8585/"))
        print("Auth URL (OOB):", get_auth_url("urn:ietf:wg:oauth:2.0:oob"))
