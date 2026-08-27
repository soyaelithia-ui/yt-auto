import urllib.parse
import urllib.request
import json
import os

from pathlib import Path
from src.config import BASE_DIR, GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID") or GOOGLE_CLIENT_ID
CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET") or GOOGLE_CLIENT_SECRET
TOKEN_PATH = str(BASE_DIR / "secrets" / "youtube_token.json")

def get_auth_url(redirect_uri="http://localhost:8585/"):
    if not CLIENT_ID:
        raise RuntimeError("GOOGLE_CLIENT_ID no está configurado")
    scopes = [
        "https://www.googleapis.com/auth/youtube.upload",
        "https://www.googleapis.com/auth/youtube",
        "https://www.googleapis.com/auth/youtube.readonly",
        "https://www.googleapis.com/auth/drive"
    ]
    params = {
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent"
    }
    url = "https://accounts.google.com/o/oauth2/auth?" + urllib.parse.urlencode(params, quote_via=urllib.parse.quote)
    return url

def exchange_code(code, redirect_uri="urn:ietf:wg:oauth:2.0:oob", token_path=None):
    if not CLIENT_ID or not CLIENT_SECRET:
        raise RuntimeError(
            "GOOGLE_CLIENT_ID y GOOGLE_CLIENT_SECRET deben proporcionarse por entorno"
        )
    if token_path is None:
        token_path = TOKEN_PATH

    data = urllib.parse.urlencode({
        "code": code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }).encode("utf-8")
    
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=data)
    with urllib.request.urlopen(req, timeout=30) as response:
        res_data = json.loads(response.read().decode("utf-8"))
        
    res_data["client_id"] = CLIENT_ID
    res_data["client_secret"] = CLIENT_SECRET
    
    os.makedirs(os.path.dirname(token_path), exist_ok=True)
    with open(token_path, "w") as f:
        json.dump(res_data, f, indent=2)
    os.chmod(token_path, 0o600)
    print(f"Credentials saved successfully to {token_path}!")

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 2:
        exchange_code(sys.argv[1], sys.argv[2])
    elif len(sys.argv) > 1:
        exchange_code(sys.argv[1])
    else:
        print("Auth URL (localhost):", get_auth_url("http://localhost:8585/"))
        print("Auth URL (OOB):", get_auth_url("urn:ietf:wg:oauth:2.0:oob"))
