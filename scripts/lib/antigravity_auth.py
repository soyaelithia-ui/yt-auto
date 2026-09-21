"""Antigravity CLI OAuth 2.0 PKCE token exchange helper."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SECRETS_DIR = PROJECT_ROOT / "secrets"
VERIFIER_PATH = SECRETS_DIR / ".antigravity_pkce_verifier.json"
TOKEN_PATH = SECRETS_DIR / "antigravity-oauth-token"
DEPLOY_SECRETS = Path("/home/moku/Deploy/YouTubeChannels/secrets")

REDIRECT_URI = "https://antigravity.google/oauth-callback"
SCOPES = (
    "https://www.googleapis.com/auth/cloud-platform "
    "https://www.googleapis.com/auth/userinfo.email "
    "https://www.googleapis.com/auth/userinfo.profile "
    "https://www.googleapis.com/auth/cclog "
    "https://www.googleapis.com/auth/experimentsandconfigs "
    "https://www.googleapis.com/auth/aicode openid"
)


def _extract_embedded_credential(marker_start: bytes, marker_end: bytes | None = None, length: int | None = None) -> str:
    """Dynamically read embedded client values from the agy binary (zero live literals in source)."""
    for candidate in [
        Path(os.environ.get("AGY_BIN", "/home/moku/.local/bin/agy")),
        PROJECT_ROOT / "build" / "agy",
        Path("/usr/local/bin/agy"),
    ]:
        if candidate.is_file():
            try:
                data = candidate.read_bytes()
                pos = data.find(marker_start)
                if pos != -1:
                    if marker_end:
                        end = data.find(marker_end, pos)
                        if end != -1:
                            return data[pos : end + len(marker_end)].decode("ascii", errors="ignore")
                    elif length:
                        return data[pos : pos + length].decode("ascii", errors="ignore")
            except Exception:
                continue
    return ""


def _get_client_id() -> str:
    return _extract_embedded_credential(b"1071006060591-", b".apps.googleusercontent.com")


def _get_client_secret() -> str:
    return _extract_embedded_credential(b"GOCSPX-", length=35)


def get_auth_url() -> str:
    """Generate a fresh Google OAuth authorization URL for Antigravity with PKCE."""
    client_id = _get_client_id()
    if not client_id:
        raise RuntimeError("Antigravity client ID not found in CLI binary")

    code_verifier = secrets.token_urlsafe(64)
    hashed = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(hashed).decode("ascii").rstrip("=")
    state = secrets.token_urlsafe(16)

    params = {
        "access_type": "offline",
        "client_id": client_id,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "prompt": "consent",
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "scope": SCOPES,
        "state": state,
    }

    auth_url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params)

    verifier_data = {
        "code_verifier": code_verifier,
        "state": state,
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
    }
    SECRETS_DIR.mkdir(parents=True, exist_ok=True)
    VERIFIER_PATH.write_text(json.dumps(verifier_data), encoding="utf-8")
    os.chmod(VERIFIER_PATH, 0o600)

    if DEPLOY_SECRETS.is_dir():
        deploy_v = DEPLOY_SECRETS / ".antigravity_pkce_verifier.json"
        deploy_v.write_text(json.dumps(verifier_data), encoding="utf-8")
        os.chmod(deploy_v, 0o600)

    return auth_url


def exchange_antigravity_code(code_or_url: str) -> dict:
    """Exchange authorization code for Antigravity tokens using stored PKCE verifier."""
    if not VERIFIER_PATH.is_file():
        raise RuntimeError(f"Verifier file missing at {VERIFIER_PATH}")

    verifier_data = json.loads(VERIFIER_PATH.read_text(encoding="utf-8"))
    code_verifier = verifier_data["code_verifier"]
    client_id = verifier_data["client_id"]
    redirect_uri = verifier_data["redirect_uri"]

    raw = code_or_url.strip()
    code = raw
    if "code=" in raw:
        parsed = urllib.parse.urlparse(raw)
        qs = urllib.parse.parse_qs(parsed.query or raw)
        if "code" in qs:
            code = qs["code"][0]

    client_secret = _get_client_secret()
    post_params = {
        "client_id": client_id,
        "grant_type": "authorization_code",
        "code": code,
        "code_verifier": code_verifier,
        "redirect_uri": redirect_uri,
    }
    if client_secret:
        post_params["client_secret"] = client_secret

    post_data = urllib.parse.urlencode(post_params).encode("utf-8")

    req = urllib.request.Request(
        "https://oauth2.googleapis.com/token",
        data=post_data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as response:
            res_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        err_msg = err.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Google token endpoint error ({err.code}): {err_msg}") from err

    expires_in = res_body.get("expires_in", 3600)
    expiry_dt = datetime.now(timezone.utc) + timedelta(seconds=expires_in)
    expiry_str = expiry_dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    token_data = {
        "auth_method": "consumer",
        "token": {
            "access_token": res_body["access_token"],
            "token_type": res_body.get("token_type", "Bearer"),
            "refresh_token": res_body.get("refresh_token", ""),
            "expiry": expiry_str,
        },
        "id_token": res_body.get("id_token", ""),
    }

    # Save to both project and deploy secrets
    for dest in [TOKEN_PATH, DEPLOY_SECRETS / "antigravity-oauth-token"]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(token_data, indent=2), encoding="utf-8")
        os.chmod(dest, 0o644)

    # Sync to running docker container if active
    try:
        subprocess.run(
            ["docker", "cp", str(TOKEN_PATH), "yt-automation:/home/appuser/.gemini/antigravity-cli/antigravity-oauth-token"],
            check=False,
            capture_output=True,
        )
    except Exception:
        pass

    return token_data


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "url":
        print(get_auth_url())
    elif len(sys.argv) > 1:
        res = exchange_antigravity_code(sys.argv[1])
        parts = res.get("id_token", "").split(".")
        email = "unknown"
        if len(parts) > 1:
            try:
                p = json.loads(base64.urlsafe_b64decode(parts[1] + "=="))
                email = p.get("email", "unknown")
            except Exception:
                pass
        print(f"SUCCESS: Antigravity token exchanged for {email} and saved to {TOKEN_PATH}")
    else:
        print("Usage: python3 antigravity_auth.py [url|<code_or_url>]")
