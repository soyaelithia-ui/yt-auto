import json
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.api_health import (
    check_all,
    check_cookies,
    check_drive_api,
    check_youtube_api,
    format_status_report,
)


def test_check_youtube_api_reports_ok_when_preflight_passes():
    with patch("src.youtube.uploader.verify_youtube_credentials_preflight", return_value=(True, "token válido")):
        res = check_youtube_api(channel="moku")
    assert res == {"ok": True, "detail": "token válido"}


def test_check_youtube_api_reports_failure_when_preflight_fails():
    with patch("src.youtube.uploader.verify_youtube_credentials_preflight", return_value=(False, "sin token")):
        res = check_youtube_api(channel="moku")
    assert res == {"ok": False, "detail": "sin token"}


def test_check_youtube_api_never_raises_on_unexpected_error():
    with patch("src.youtube.uploader.verify_youtube_credentials_preflight", side_effect=RuntimeError("boom")):
        res = check_youtube_api(channel="moku")
    assert res["ok"] is False
    assert "Error al validar YouTube" in res["detail"]


def test_check_drive_api_gcloud_ok():
    settings = SimpleNamespace(drive_use_gcloud=True, channels={})
    with patch("src.api_health.SETTINGS", settings), \
         patch("src.api_health._gcloud_token_ok", return_value=True):
        res = check_drive_api()
    assert res["ok"] is True


def test_check_drive_api_gcloud_missing():
    settings = SimpleNamespace(drive_use_gcloud=True, channels={})
    with patch("src.api_health.SETTINGS", settings), \
         patch("src.api_health._gcloud_token_ok", return_value=False):
        res = check_drive_api()
    assert res["ok"] is False


def test_check_drive_api_service_account_file(tmp_path):
    settings = SimpleNamespace(drive_use_gcloud=False, channels={})

    key_file = tmp_path / "drive_key.json"
    key_file.write_text(json.dumps({"type": "service_account"}), encoding="utf-8")
    with patch("src.api_health.SETTINGS", settings), \
         patch("src.api_health.DRIVE_KEY_PATH", key_file):
        res = check_drive_api()
    assert res["ok"] is True
    assert "drive_key.json" in res["detail"]


def test_check_drive_api_no_credentials_available(tmp_path):
    settings = SimpleNamespace(drive_use_gcloud=False, channels={})

    with patch("src.api_health.SETTINGS", settings), \
         patch("src.api_health.DRIVE_KEY_PATH", tmp_path / "missing.json"), \
         patch("src.api_health._oauth_token_has_scope", return_value=False):
        res = check_drive_api()
    assert res["ok"] is False


def test_check_cookies_valid_list(tmp_path):
    cookies = tmp_path / "cookies.json"
    future_time = time.time() + 86400 * 10
    sample = [
        {"name": "LOGIN_INFO", "value": "tok", "expires": future_time},
        {"name": "SID", "value": "sid", "expires": future_time},
    ]
    cookies.write_text(json.dumps(sample), encoding="utf-8")
    with patch("src.api_health.get_channel_settings", return_value=SimpleNamespace(cookies_path=cookies)):
        res = check_cookies(channel="moku")
    assert res["ok"] is True
    assert "activas" in res["detail"] or "OK" in res["detail"]


def test_check_cookies_netscape_format(tmp_path):
    cookies = tmp_path / "cookies.txt"
    future_time = int(time.time() + 86400 * 5)
    content = f".youtube.com\tTRUE\t/\tTRUE\t{future_time}\tLOGIN_INFO\ttok_netscape\n.google.com\tTRUE\t/\tTRUE\t{future_time}\tSID\tsid_netscape\n"
    cookies.write_text(content, encoding="utf-8")
    with patch("src.api_health.get_channel_settings", return_value=SimpleNamespace(cookies_path=cookies)):
        res = check_cookies(channel="moku")
    assert res["ok"] is True
    assert "activas" in res["detail"] or "OK" in res["detail"]


def test_check_cookies_expired(tmp_path):
    cookies = tmp_path / "cookies.json"
    past_time = time.time() - 3600 * 24
    sample = [
        {"name": "LOGIN_INFO", "value": "tok", "expires": past_time},
        {"name": "SID", "value": "sid", "expires": past_time},
    ]
    cookies.write_text(json.dumps(sample), encoding="utf-8")
    with patch("src.api_health.get_channel_settings", return_value=SimpleNamespace(cookies_path=cookies)):
        res = check_cookies(channel="moku")
    assert res["ok"] is False
    assert "expiradas" in res["detail"].lower()


def test_check_cookies_missing_tokens(tmp_path):
    cookies = tmp_path / "cookies.json"
    sample = [{"name": "OTHER_COOKIE", "value": "val", "expires": time.time() + 86400}]
    cookies.write_text(json.dumps(sample), encoding="utf-8")
    with patch("src.api_health.get_channel_settings", return_value=SimpleNamespace(cookies_path=cookies)):
        res = check_cookies(channel="moku")
    assert res["ok"] is False
    assert "incompletas" in res["detail"].lower()


def test_check_cookies_missing_file(tmp_path):
    with patch("src.api_health.get_channel_settings", return_value=SimpleNamespace(cookies_path=tmp_path / "nope.json")):
        res = check_cookies(channel="moku")
    assert res["ok"] is False
    assert "Faltan cookies" in res["detail"]


def test_check_cookies_invalid_json(tmp_path):
    cookies = tmp_path / "cookies.json"
    cookies.write_text("not-json-or-netscape-invalid", encoding="utf-8")
    with patch("src.api_health.get_channel_settings", return_value=SimpleNamespace(cookies_path=cookies)):
        res = check_cookies(channel="moku")
    assert res["ok"] is False
    assert "Cookies inválidas" in res["detail"]


def test_check_all_aggregates_all_ok():
    with patch("src.api_health.check_youtube_api", return_value={"ok": True, "detail": "ok"}), \
         patch("src.api_health.check_drive_api", return_value={"ok": True, "detail": "ok"}), \
         patch("src.api_health.check_cookies", return_value={"ok": True, "detail": "ok"}):
        report = check_all(channel="moku")
    assert report["youtube"]["ok"] is True
    assert report["drive"]["ok"] is True
    assert report["cookies"]["ok"] is True
    assert report["all_ok"]["ok"] is True


def test_check_all_aggregates_failure():
    with patch("src.api_health.check_youtube_api", return_value={"ok": False, "detail": "x"}), \
         patch("src.api_health.check_drive_api", return_value={"ok": True, "detail": "ok"}), \
         patch("src.api_health.check_cookies", return_value={"ok": True, "detail": "ok"}):
        report = check_all(channel="moku")
    assert report["all_ok"]["ok"] is False


def test_format_status_report_is_clean_and_readable():
    report = {
        "youtube": {"ok": True, "detail": "token válido"},
        "drive": {"ok": False, "detail": "Falta DRIVE_KEY_PATH"},
        "cookies": {"ok": True, "detail": "Cookies OK (3 dominios)"},
        "all_ok": {"ok": False},
    }
    text = format_status_report(report, channel="moku")
    assert "canal moku" in text
    assert "YouTube: OK" in text
    assert "Drive: FALLO" in text
    assert "Cookies: OK" in text
    assert "requieren atención" in text


def test_format_status_report_all_ok_message():
    report = {
        "youtube": {"ok": True, "detail": "ok"},
        "drive": {"ok": True, "detail": "ok"},
        "cookies": {"ok": True, "detail": "ok"},
        "all_ok": {"ok": True},
    }
    text = format_status_report(report)
    assert "Todas las APIs activas." in text
