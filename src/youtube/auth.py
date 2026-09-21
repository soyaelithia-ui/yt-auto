"""YouTube and Google Drive OAuth 2.0 authentication lifecycle."""

from __future__ import annotations

import json
import os
import sys
from typing import Optional

from src.config import BASE_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET
from src.core.google_auth import (
    DEFAULT_SCOPES,
    create_oauth_flow,
    save_credentials,
)
from src.log import get_logger

logger = get_logger("youtube_auth")

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
TOKEN_PATH = str(BASE_DIR / "secrets" / "youtube_token.json")

# Loopback redirects only (Google deprecated OOB).
_DEFAULT_REDIRECT = "http://localhost:8585/"
_ALT_REDIRECT = "http://localhost:8080/"


def get_auth_url(
    redirect_uri: str = _DEFAULT_REDIRECT,
    scopes: Optional[list[str]] = None,
) -> str:
    """Generate the official Google OAuth 2.0 authorization URL."""
    client_id = CLIENT_ID or os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    if not client_id:
        raise RuntimeError("GOOGLE_CLIENT_ID no está configurado")

    flow = create_oauth_flow(
        client_id=client_id,
        scopes=scopes or DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
    )
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        include_granted_scopes="true",
    )
    if getattr(flow, "code_verifier", None):
        verifier_path = BASE_DIR / "secrets" / ".oauth_pkce_verifier.json"
        try:
            verifiers = {}
            if verifier_path.is_file():
                try:
                    verifiers = json.loads(verifier_path.read_text(encoding="utf-8"))
                except Exception:
                    verifiers = {}
            verifiers[redirect_uri] = flow.code_verifier
            if state:
                verifiers[state] = flow.code_verifier
            verifier_path.write_text(json.dumps(verifiers), encoding="utf-8")
            os.chmod(verifier_path, 0o600)
        except Exception:
            pass
    return auth_url


def exchange_code(
    code: str,
    redirect_uri: str = _DEFAULT_REDIRECT,
    token_path: Optional[str] = None,
    scopes: Optional[list[str]] = None,
) -> None:
    """Exchange authorization code for tokens and save in official Google format."""
    client_id = CLIENT_ID or os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    client_secret = CLIENT_SECRET or os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
    if not client_id or not client_secret:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET deben proporcionarse por entorno"
        )
    target_path = token_path or TOKEN_PATH

    code = code.strip()
    extracted_state = None
    if "code=" in code:
        from urllib.parse import parse_qs, urlparse
        query = urlparse(code).query or code
        parsed = parse_qs(query)
        if "code" in parsed:
            code = parsed["code"][0]
        if "state" in parsed:
            extracted_state = parsed["state"][0]

    verifier_path = BASE_DIR / "secrets" / ".oauth_pkce_verifier.json"
    verifiers = {}
    if verifier_path.is_file():
        try:
            verifiers = json.loads(verifier_path.read_text(encoding="utf-8"))
        except Exception:
            pass

    code_verifier = (
        (verifiers.get(extracted_state) if extracted_state else None)
        or verifiers.get(redirect_uri)
        or verifiers.get(_DEFAULT_REDIRECT)
    )

    flow = create_oauth_flow(
        client_id=client_id,
        client_secret=client_secret,
        scopes=scopes or DEFAULT_SCOPES,
        redirect_uri=redirect_uri,
    )
    if code_verifier:
        flow.code_verifier = code_verifier

    try:
        flow.fetch_token(code=code)
    except Exception as exc:
        if "verifier" in str(exc).lower():
            flow.code_verifier = None
            try:
                flow.fetch_token(code=code)
            except Exception:
                pass
        if not getattr(flow, "credentials", None):
            logger.warning(
                "fetch_token with redirect_uri=%s failed: %s. Trying fallback uri...",
                redirect_uri,
                exc,
            )
            alt_uri = _ALT_REDIRECT if redirect_uri != _ALT_REDIRECT else _DEFAULT_REDIRECT
            flow = create_oauth_flow(
                client_id=client_id,
                client_secret=client_secret,
                scopes=scopes or DEFAULT_SCOPES,
                redirect_uri=alt_uri,
            )
            try:
                flow.fetch_token(code=code)
            except Exception:
                flow.code_verifier = None
                flow.fetch_token(code=code)

    save_credentials(flow.credentials, target_path)
    if verifier_path.is_file():
        try:
            current_verifiers = {}
            try:
                current_verifiers = json.loads(verifier_path.read_text(encoding="utf-8"))
            except Exception:
                pass
            if extracted_state and extracted_state in current_verifiers:
                del current_verifiers[extracted_state]
            if redirect_uri and redirect_uri in current_verifiers:
                del current_verifiers[redirect_uri]
            if current_verifiers:
                verifier_path.write_text(json.dumps(current_verifiers), encoding="utf-8")
                os.chmod(verifier_path, 0o600)
            else:
                verifier_path.unlink()
        except Exception:
            pass
    print(f"Credentials saved successfully to {target_path}!")


def run_local_login_flow(
    token_path: Optional[str] = None,
    port: int = 8585,
    scopes: Optional[list[str]] = None,
) -> None:
    """Run official Google InstalledAppFlow local server for 1-click browser login."""
    client_id = CLIENT_ID or os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
    client_secret = CLIENT_SECRET or os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
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
        print("Auth URL (localhost:8585):", get_auth_url(_DEFAULT_REDIRECT))
        print("Auth URL (localhost:8080):", get_auth_url(_ALT_REDIRECT))
