"""Critical: Drive uses google_auth SSOT; OOB redirect removed."""
from pathlib import Path

from src.core import google_auth
import src.drive as drive


def test_default_redirect_uris_have_no_oob():
    assert "urn:ietf:wg:oauth:2.0:oob" not in google_auth.DEFAULT_REDIRECT_URIS
    joined = "\n".join(google_auth.DEFAULT_REDIRECT_URIS)
    assert "oob" not in joined.lower()


def test_drive_module_has_no_local_credential_builders():
    src = Path("src/drive.py").read_text(encoding="utf-8")
    assert "def _credentials(" not in src
    assert "def _gcloud_credentials(" not in src
    assert "get_drive_credentials" in src
    assert "build_drive_service" in src
    assert hasattr(drive, "_drive_service")


def test_youtube_auth_exchange_default_is_loopback():
    import inspect
    from src.youtube.auth import exchange_code

    default = inspect.signature(exchange_code).parameters["redirect_uri"].default
    assert default.startswith("http://localhost")
    assert "oob" not in default
