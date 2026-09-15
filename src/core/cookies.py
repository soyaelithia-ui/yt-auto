"""Universal cookie parser, normalizer, and YouTube session health validator."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Union


class SessionStatus(str, Enum):
    HEALTHY = "HEALTHY"
    EXPIRING_SOON = "EXPIRING_SOON"
    EXPIRED = "EXPIRED"
    INCOMPLETE = "INCOMPLETE"
    INVALID = "INVALID"


@dataclass
class SessionHealthResult:
    status: SessionStatus
    min_expiry: Optional[float] = None
    days_left: Optional[float] = None
    missing_tokens: List[str] = field(default_factory=list)
    detail: str = ""
    total_cookies: int = 0


# Essential YouTube / Google session cookies required for authentication
PRIMARY_SESSION_TOKENS = {"LOGIN_INFO"}
SECONDARY_SESSION_TOKENS = {"SID", "__Secure-1PSID", "__Secure-3PSID"}
RECOGNIZED_SESSION_TOKENS = {
    "LOGIN_INFO",
    "SID",
    "HSID",
    "SSID",
    "APISID",
    "SAPISID",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
}


def parse_netscape_cookies(text: str) -> List[Dict[str, Any]]:
    """Parse Netscape HTTP Cookie File format into a list of cookie dicts."""
    cookies = []
    for line in text.splitlines():
        line = line.strip()
        http_only = False
        if line.startswith("#HttpOnly_"):
            line = line[len("#HttpOnly_"):]
            http_only = True
        elif not line or line.startswith("#"):
            continue

        parts = line.split("\t")
        if len(parts) < 7:
            # Fallback for space-delimited formats
            parts = line.split()
            if len(parts) < 7:
                continue

        domain = parts[0]
        # flag = parts[1].upper() == "TRUE"
        path = parts[2]
        secure = parts[3].upper() == "TRUE"
        try:
            expires = float(parts[4])
        except (ValueError, TypeError):
            expires = None
        name = parts[5]
        value = parts[6] if len(parts) > 6 else ""

        cookie = {
            "name": str(name),
            "value": str(value),
            "domain": domain,
            "path": path,
            "secure": secure,
            "httpOnly": http_only,
            "sameSite": "Lax",
        }
        if expires is not None and expires > 0:
            cookie["expires"] = expires
        cookies.append(cookie)

    return cookies


def parse_cookies_file(file_path: Union[str, Path]) -> List[Dict[str, Any]]:
    """Parse either JSON array or Netscape format cookies file seamlessly."""
    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"Cookies file not found: {file_path}")

    text = p.read_text(encoding="utf-8").strip()
    if not text or len(text) < 2:
        raise ValueError(f"Cookies file is empty: {p.name}")

    # 1. Try JSON parsing
    if text.startswith("[") or text.startswith("{"):
        try:
            data = json.loads(text)
            raw_list = data
            if isinstance(data, dict) and "cookies" in data:
                raw_list = data["cookies"]

            if isinstance(raw_list, list):
                if not raw_list:
                    raise ValueError(f"Cookies file is empty: {p.name}")
                normalized = []
                for item in raw_list:
                    if isinstance(item, dict) and "name" in item:
                        c = dict(item)
                        if "expirationDate" in c and "expires" not in c:
                            c["expires"] = c["expirationDate"]
                        normalized.append(c)
                if not normalized:
                    raise ValueError(f"Invalid cookies format in {p.name}: expected list of cookie dicts")
                return normalized
            raise ValueError(f"Invalid cookies format in {p.name}: expected list")
        except json.JSONDecodeError:
            pass  # Fall through to Netscape parsing

    # 2. Try Netscape format parsing
    netscape_cookies = parse_netscape_cookies(text)
    if netscape_cookies:
        return netscape_cookies

    # 3. Try raw semicolon-separated Cookie header string parsing
    if ";" in text and "=" in text:
        raw_header_cookies = parse_raw_cookie_header(text)
        if raw_header_cookies:
            return raw_header_cookies

    raise ValueError(f"Invalid cookies format in {p.name}")


def parse_raw_cookie_header(text: str, default_domain: str = ".youtube.com") -> List[Dict[str, Any]]:
    """Parse HTTP Cookie header string (name=value; name2=value2) into cookie dicts with dual-domain support."""
    cookies = []
    if not text or "=" not in text:
        return cookies

    items = text.strip().split(";")
    future_expiry = time.time() + 86400 * 180  # 180 days default

    google_auth_names = {
        "SID", "HSID", "SSID", "APISID", "SAPISID",
        "__Secure-1PSID", "__Secure-3PSID",
        "__Secure-1PAPISID", "__Secure-3PAPISID",
        "__Secure-1PSIDTS", "__Secure-3PSIDTS",
        "__Secure-1PSIDCC", "__Secure-3PSIDCC",
        "SIDCC", "ACCOUNT_CHOOSER",
    }

    for item in items:
        item = item.strip()
        if not item or "=" not in item:
            continue
        name, val = item.split("=", 1)
        name = name.strip()
        val = val.strip()
        if not name:
            continue

        is_secure = name.startswith("__Secure-") or name in {"SAPISID", "__Secure-3PAPISID", "__Secure-1PAPISID"}
        is_httponly = name in {"SID", "HSID", "SSID", "__Secure-1PSID", "__Secure-3PSID", "LOGIN_INFO"}

        # Base cookie for default domain (.youtube.com)
        cookies.append({
            "name": name,
            "value": val,
            "domain": default_domain,
            "path": "/",
            "secure": is_secure or True,
            "httpOnly": is_httponly,
            "sameSite": "None" if is_secure else "Lax",
            "expires": future_expiry,
        })

        # Dual-domain authentication: Google account cookies must also exist on .google.com
        if name in google_auth_names:
            cookies.append({
                "name": name,
                "value": val,
                "domain": ".google.com",
                "path": "/",
                "secure": is_secure or True,
                "httpOnly": is_httponly,
                "sameSite": "None" if is_secure else "Lax",
                "expires": future_expiry,
            })

    return cookies


def save_cookies_to_file(cookies: List[Dict[str, Any]], file_path: Union[str, Path]) -> None:
    """Save cookie list to JSON file atomically."""
    p = Path(file_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    temp_p = p.with_suffix(".tmp")
    temp_p.write_text(json.dumps(cookies, indent=2), encoding="utf-8")
    temp_p.replace(p)



def format_cookies_for_playwright(cookies: list) -> List[Dict[str, Any]]:
    """Formats raw cookies for Playwright BrowserContext.add_cookies()."""
    formatted = []
    if not isinstance(cookies, list):
        return formatted

    for c in cookies:
        if not isinstance(c, dict) or "name" not in c or "value" not in c:
            continue

        raw_domain = c.get("domain")
        domain = str(raw_domain).strip() if raw_domain else ".youtube.com"
        if domain and not domain.startswith("."):
            domain = "." + domain

        fc: Dict[str, Any] = {
            "name": str(c["name"]),
            "value": str(c["value"]),
            "domain": domain,
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }

        # Expiration (must be strictly positive for persistent cookies; omit for session cookies)
        exp_val = None
        if "expirationDate" in c and c["expirationDate"] is not None:
            try:
                exp_val = float(c["expirationDate"])
            except (ValueError, TypeError):
                pass
        elif "expires" in c and c["expires"] is not None:
            try:
                exp_val = float(c["expires"])
            except (ValueError, TypeError):
                pass

        if exp_val is not None and exp_val > 0:
            fc["expires"] = exp_val

        # SameSite normalization (RFC 6265bis: SameSite=None requires Secure=True)
        same_site = c.get("sameSite")
        if same_site is not None:
            s_str = str(same_site).lower()
            if s_str in ("strict",):
                fc["sameSite"] = "Strict"
            elif s_str in ("none", "no_restriction"):
                fc["sameSite"] = "None"
                fc["secure"] = True
            else:
                fc["sameSite"] = "Lax"

        formatted.append(fc)

    return formatted


def validate_youtube_session_cookies(
    cookies: List[Dict[str, Any]],
    expiring_soon_hours: float = 48.0,
) -> SessionHealthResult:
    """Deep inspection of YouTube/Google session cookies for presence and expiration."""
    if not cookies or not isinstance(cookies, list):
        return SessionHealthResult(
            status=SessionStatus.INVALID,
            detail="Cookies inválidas o vacías",
            total_cookies=0,
        )

    found_names = {str(c.get("name")) for c in cookies if isinstance(c, dict) and "name" in c}

    missing_tokens = []
    for token in PRIMARY_SESSION_TOKENS:
        if token not in found_names:
            missing_tokens.append(token)

    if not any(token in found_names for token in SECONDARY_SESSION_TOKENS):
        missing_tokens.append("SID/__Secure-1PSID")

    if missing_tokens:
        return SessionHealthResult(
            status=SessionStatus.INCOMPLETE,
            missing_tokens=missing_tokens,
            detail=f"Cookies incompletas: falta {', '.join(missing_tokens)}",
            total_cookies=len(cookies),
        )

    now = time.time()
    session_expiries = []

    for c in cookies:
        if not isinstance(c, dict):
            continue
        name = str(c.get("name"))
        if name in RECOGNIZED_SESSION_TOKENS:
            exp = c.get("expires") if "expires" in c else c.get("expirationDate")
            if exp is not None:
                try:
                    exp_val = float(exp)
                    if exp_val > 0:
                        session_expiries.append(exp_val)
                except (ValueError, TypeError):
                    pass

    if not session_expiries:
        return SessionHealthResult(
            status=SessionStatus.HEALTHY,
            detail=f"Cookies OK ({len(cookies)} cookies detectadas)",
            total_cookies=len(cookies),
        )

    min_expiry = min(session_expiries)
    seconds_left = min_expiry - now
    days_left = seconds_left / 86400.0

    if seconds_left <= 0:
        days_ago = abs(seconds_left) / 86400.0
        return SessionHealthResult(
            status=SessionStatus.EXPIRED,
            min_expiry=min_expiry,
            days_left=days_left,
            detail=f"Cookies expiradas (caducaron hace {days_ago:.1f} días)",
            total_cookies=len(cookies),
        )

    if seconds_left <= (expiring_soon_hours * 3600.0):
        hours_left = seconds_left / 3600.0
        return SessionHealthResult(
            status=SessionStatus.EXPIRING_SOON,
            min_expiry=min_expiry,
            days_left=days_left,
            detail=f"Cookies por expirar (restan {hours_left:.1f} horas)",
            total_cookies=len(cookies),
        )

    return SessionHealthResult(
        status=SessionStatus.HEALTHY,
        min_expiry=min_expiry,
        days_left=days_left,
        detail=f"Cookies OK (activas, {days_left:.1f} días restantes)",
        total_cookies=len(cookies),
    )


class SessionHealthValidator:
    """Proactive health checker and expiration monitor for YouTube session cookies."""

    @staticmethod
    def validate(
        cookies: List[Dict[str, Any]],
        expiring_soon_hours: float = 48.0,
    ) -> SessionHealthResult:
        """Validate session cookies list for key authentication tokens and expiration."""
        return validate_youtube_session_cookies(cookies, expiring_soon_hours=expiring_soon_hours)

    @classmethod
    def validate_file(
        cls,
        file_path: Union[str, Path],
        expiring_soon_hours: float = 48.0,
    ) -> SessionHealthResult:
        """Parse cookie file (Netscape or JSON) and validate session health."""
        try:
            cookies = parse_cookies_file(file_path)
            return cls.validate(cookies, expiring_soon_hours=expiring_soon_hours)
        except Exception as exc:
            return SessionHealthResult(
                status=SessionStatus.INVALID,
                detail=f"Error leyendo archivo de cookies: {exc}",
                total_cookies=0,
            )

    @classmethod
    def resolve_cookie_file_for_channel(
        cls,
        channel: str,
        secrets_dir: Optional[Union[str, Path]] = None,
    ) -> Optional[Path]:
        """Locate Netscape or JSON cookie file for the specified channel."""
        ch = str(channel).lower().strip()
        base_dir = Path(secrets_dir) if secrets_dir else Path(__file__).resolve().parent.parent.parent / "secrets"
        candidates = [
            base_dir / f"cookies_{ch}.txt",
            base_dir / f"cookies_{ch}.json",
            base_dir / f"{ch}_cookies.txt",
            base_dir / f"{ch}_cookies.json",
            base_dir / "cookies.txt",
            base_dir / "cookies.json",
        ]
        for c in candidates:
            if c.is_file() and c.stat().st_size > 0:
                return c
        return None

    @classmethod
    def validate_channel(
        cls,
        channel: str,
        secrets_dir: Optional[Union[str, Path]] = None,
        expiring_soon_hours: float = 48.0,
    ) -> SessionHealthResult:
        """Check session health for a named channel."""
        path = cls.resolve_cookie_file_for_channel(channel, secrets_dir=secrets_dir)
        if not path:
            return SessionHealthResult(
                status=SessionStatus.INVALID,
                detail=f"No se encontró archivo de cookies para el canal '{channel}'",
                total_cookies=0,
            )
        return cls.validate_file(path, expiring_soon_hours=expiring_soon_hours)

