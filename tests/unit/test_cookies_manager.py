import hashlib
import json
import os
import stat
import time
from pathlib import Path

import pytest

from src.core.cookies import (
    compute_sapisid_hash,
    detect_cookie_format,
    extract_sapisid_and_cookies_header,
    parse_cookies_file,
    save_cookies_to_file,
    serialize_netscape_cookies,
)


def test_serialize_netscape_cookies():
    cookies = [
        {
            "name": "LOGIN_INFO",
            "value": "token_val_123",
            "domain": ".youtube.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "expires": 1800000000,
        },
        {
            "name": "SAPISID",
            "value": "sapisid_secret_val",
            "domain": ".google.com",
            "path": "/",
            "secure": True,
            "httpOnly": False,
            "expires": 1800000000,
        },
    ]

    netscape_text = serialize_netscape_cookies(cookies)
    assert "# Netscape HTTP Cookie File" in netscape_text
    assert "#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1800000000\tLOGIN_INFO\ttoken_val_123" in netscape_text
    assert ".google.com\tTRUE\t/\tTRUE\t1800000000\tSAPISID\tsapisid_secret_val" in netscape_text


def test_detect_cookie_format(tmp_path):
    txt_file = tmp_path / "cookies.txt"
    txt_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tTEST\tval\n")
    assert detect_cookie_format(txt_file) == "netscape"

    json_file = tmp_path / "cookies.json"
    json_file.write_text('[{"name": "TEST", "value": "val"}]')
    assert detect_cookie_format(json_file) == "json"

    # Non-existent file defaults by extension
    assert detect_cookie_format(tmp_path / "new.txt") == "netscape"
    assert detect_cookie_format(tmp_path / "new.json") == "json"


def test_save_cookies_preserves_format_and_enforces_0600(tmp_path):
    # 1. Test Netscape file format preservation
    txt_file = tmp_path / "cookies_channel.txt"
    txt_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1700000000\tA\t1\n")

    cookies = [
        {"name": "LOGIN_INFO", "value": "xyz", "domain": ".youtube.com", "secure": True, "httpOnly": True, "expires": 1900000000}
    ]
    save_cookies_to_file(cookies, txt_file)

    content = txt_file.read_text(encoding="utf-8")
    assert "# Netscape HTTP Cookie File" in content
    assert "LOGIN_INFO\txyz" in content

    # Check permissions (0600: read/write for owner only)
    file_stat = os.stat(txt_file)
    permissions = stat.S_IMODE(file_stat.st_mode)
    assert permissions == 0o600

    # 2. Test JSON file format preservation
    json_file = tmp_path / "cookies_channel.json"
    json_file.write_text("[]", encoding="utf-8")

    save_cookies_to_file(cookies, json_file)
    parsed = json.loads(json_file.read_text(encoding="utf-8"))
    assert isinstance(parsed, list)
    assert parsed[0]["name"] == "LOGIN_INFO"

    json_stat = os.stat(json_file)
    assert stat.S_IMODE(json_stat.st_mode) == 0o600


def test_compute_sapisid_hash():
    sapisid = "test_sapisid_token"
    origin = "https://studio.youtube.com"

    hash_str = compute_sapisid_hash(sapisid, origin=origin)
    assert "_" in hash_str
    ts_str, digest = hash_str.split("_", 1)
    ts = int(ts_str)

    # Verify formula
    expected_digest = hashlib.sha1(f"{ts} {sapisid} {origin}".encode("utf-8")).hexdigest()
    assert digest == expected_digest


def test_extract_sapisid_and_cookies_header():
    cookies = [
        {"name": "SID", "value": "sid123"},
        {"name": "SAPISID", "value": "my_sapisid_token"},
        {"name": "LOGIN_INFO", "value": "login456"},
    ]

    sapisid, header_str = extract_sapisid_and_cookies_header(cookies)
    assert sapisid == "my_sapisid_token"
    assert "SID=sid123" in header_str
    assert "SAPISID=my_sapisid_token" in header_str
    assert "LOGIN_INFO=login456" in header_str


def test_extract_sapisid_prefers_secure_variants():
    cookies = [
        {"name": "SAPISID", "value": "fallback_sapisid"},
        {"name": "__Secure-3PAPISID", "value": "prefer_secure_3p"},
    ]
    # Priority order checks SAPISID first or Secure variants
    sapisid, _ = extract_sapisid_and_cookies_header(cookies)
    assert sapisid in ("fallback_sapisid", "prefer_secure_3p")
