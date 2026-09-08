"""Cookie files and constants must be branded per channel, not generic leftovers."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

LEGACY_COOKIE_MARKERS = (
    "decrypted_cookies",
    "cookies_channel2",
    "COOKIES_CHANNEL2_PATH",
    "DECRYPTED_COOKIES_PATH",
)


def _channel_auth(channel: str) -> dict:
    return json.loads((ROOT / "config" / "channels" / f"{channel}.json").read_text(encoding="utf-8"))["auth"]


def test_moku_cookie_path_is_branded():
    path = _channel_auth("moku")["cookies_path"]
    assert path == "secrets/cookies_moku.json"


def test_aelithia_cookie_path_is_branded():
    path = _channel_auth("aelithia")["cookies_path"]
    assert path == "secrets/cookies_aelithia.json"


def test_scifi_cookie_path_stays_channel_branded():
    path = _channel_auth("scifi")["cookies_path"]
    name = Path(path).name
    assert name.startswith("cookies_scifi.")
    assert "channel2" not in path
    assert "decrypted" not in path


def test_config_exports_branded_cookie_constants():
    import src.config as cfg

    assert hasattr(cfg, "COOKIES_MOKU_PATH")
    assert hasattr(cfg, "COOKIES_AELITHIA_PATH")
    assert not hasattr(cfg, "DECRYPTED_COOKIES_PATH")
    assert not hasattr(cfg, "COOKIES_CHANNEL2_PATH")
    assert Path(cfg.COOKIES_MOKU_PATH).name == "cookies_moku.json" or "cookies_moku" in str(cfg.COOKIES_MOKU_PATH)
    assert "cookies_aelithia" in str(cfg.COOKIES_AELITHIA_PATH)


def test_env_example_and_compose_use_branded_cookie_filenames():
    example = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    blob = example + "\n" + compose
    for marker in ("decrypted_cookies", "cookies_channel2"):
        assert marker not in blob
    assert "cookies_moku.json" in example
    assert "cookies_aelithia.json" in example
    assert "cookies_moku.json" in compose
    assert "cookies_aelithia.json" in compose


def test_src_has_no_legacy_cookie_filenames():
    hits = []
    for path in (ROOT / "src").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for marker in LEGACY_COOKIE_MARKERS:
            if marker in text:
                hits.append(f"{path.relative_to(ROOT)}:{marker}")
    assert hits == []
