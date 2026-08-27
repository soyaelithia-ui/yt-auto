"""Google Drive adapter that reports success only after remote verification."""

from __future__ import annotations

import json
import hashlib
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Callable

from src.config import DRIVE_KEY_PATH, DRIVE_UPLOAD_MAX_RETRIES
from src.core.domain import (
    AmbiguousUploadError,
    AuthenticationError,
    ProviderValidationError,
    QuotaError,
)
from src.core.providers import DriveProof, backoff_with_jitter, classify_provider_failure
from src.log import get_logger


logger = get_logger("drive")
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive"


def _mock_enabled() -> bool:
    return os.environ.get("TEST_MODE") == "1" or os.environ.get(
        "MOCK_DRIVE_UPLOAD"
    ) == "1"


def _gcloud_enabled() -> bool:
    return os.environ.get("DRIVE_USE_GCLOUD", "0").strip() == "1"


def _gcloud_credentials():
    """Build in-memory Drive credentials from the active gcloud account."""
    try:
        completed = subprocess.run(
            ["gcloud", "auth", "print-access-token"],
            shell=False,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise AuthenticationError("gcloud no pudo proporcionar un token de Drive") from exc
    access_token = completed.stdout.strip()
    if not access_token:
        raise AuthenticationError("gcloud no devolvió un token de Drive")
    from google.oauth2.credentials import Credentials

    return Credentials(token=access_token, scopes=[DRIVE_SCOPE])


def _credentials(sa_key_path: str | None, token_path: str | None):
    from src.core.google_auth import load_authorized_user_credentials

    if _gcloud_enabled():
        return _gcloud_credentials()
    if sa_key_path and Path(sa_key_path).is_file():
        data = json.loads(Path(sa_key_path).read_text(encoding="utf-8"))
        if data.get("type") == "service_account":
            from google.oauth2 import service_account

            return service_account.Credentials.from_service_account_file(
                sa_key_path,
                scopes=[DRIVE_SCOPE],
            )
        if data.get("refresh_token") or data.get("token") or data.get("access_token"):
            return load_authorized_user_credentials(sa_key_path, scopes=[DRIVE_SCOPE])
        raise AuthenticationError("DRIVE_KEY_PATH no es ni service account ni token OAuth")
    if token_path and Path(token_path).is_file():
        return load_authorized_user_credentials(token_path, scopes=[DRIVE_SCOPE])
    raise AuthenticationError(
        "Drive requiere DRIVE_KEY_PATH o un token OAuth elegido explícitamente"
    )


def preflight_drive_access(
    *,
    folder_id: str,
    sa_key_path: str = DRIVE_KEY_PATH,
    token_path: str | None = None,
) -> dict[str, Any]:
    """Read-only proof that the configured identity can target the Drive folder."""
    if not str(folder_id or "").strip():
        raise AuthenticationError("DRIVE_FOLDER_ID es obligatorio")
    sa_exists = bool(sa_key_path and Path(sa_key_path).is_file())
    token_exists = bool(token_path and Path(token_path).is_file())
    credentials = _credentials(
        sa_key_path if sa_exists else None,
        token_path if token_exists else None,
    )
    from googleapiclient.discovery import build

    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    try:
        folder = (
            service.files()
            .get(
                fileId=folder_id,
                fields="id,name,mimeType,trashed,capabilities(canAddChildren)",
            )
            .execute()
        )
    except Exception as exc:
        if not sa_exists and not _gcloud_enabled():
            logger.warning(
                "Drive preflight notice: no se pudo verificar la carpeta con el "
                "token OAuth disponible (la clave de servicio no está montada): %s",
                exc,
            )
            return {"folder_id": folder_id, "name": "drive_unreachable", "writable": False}
        error_type = classify_provider_failure(str(exc))
        raise error_type("Drive preflight no confirmó acceso a la carpeta") from exc
    if (
        str(folder.get("id") or "") != folder_id
        or folder.get("mimeType") != "application/vnd.google-apps.folder"
        or bool(folder.get("trashed"))
        or not bool((folder.get("capabilities") or {}).get("canAddChildren"))
    ):
        raise ProviderValidationError(
            "Drive preflight no confirmó carpeta activa con permiso de escritura"
        )
    return {"folder_id": folder_id, "name": str(folder.get("name") or ""), "writable": True}


def upload_to_drive_verified(
    file_path: str,
    folder_id: str,
    sa_key_path: str = DRIVE_KEY_PATH,
    token_path: str | None = None,
    display_name: str | None = None,
    idempotency_key: str | None = None,
    on_file_id: Callable[[str], None] | None = None,
) -> DriveProof:
    target = Path(file_path)
    if not target.is_file() or target.stat().st_size == 0:
        raise FileNotFoundError("El archivo local para Drive no existe o está vacío")
    if not folder_id.strip():
        raise ValueError("folder_id es obligatorio")
    name = display_name or target.name
    if _mock_enabled():
        file_id = f"mock-drive-{target.stat().st_size}"
        if on_file_id:
            on_file_id(file_id)
        return DriveProof(
            file_id=file_id,
            name=name,
            size_bytes=target.stat().st_size,
            folder_id=folder_id,
            exists=True,
        )

    sa_exists = bool(sa_key_path and Path(sa_key_path).is_file())
    token_exists = bool(token_path and Path(token_path).is_file())
    if not _gcloud_enabled() and not sa_exists and not token_exists:
        raise FileNotFoundError(
            f"Neither Drive service account key ({sa_key_path}) nor token path ({token_path}) exists."
        )

    credentials = _credentials(sa_key_path if sa_exists else None, token_path)
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    raw_key = idempotency_key or f"{folder_id}:{name}:{target.stat().st_size}"
    stable_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    property_name = "yt_backup_key"

    def _search_existing() -> list[dict[str, Any]]:
        escaped_folder = folder_id.replace("'", "\\'")
        escaped_key = stable_key.replace("'", "\\'")
        response = (
            service.files()
            .list(
                q=(
                    f"'{escaped_folder}' in parents and trashed = false and "
                    f"appProperties has {{ key='{property_name}' and value='{escaped_key}' }}"
                ),
                spaces="drive",
                fields="files(id,name,size,parents,trashed,appProperties)",
                pageSize=2,
            )
            .execute()
        )
        files = response.get("files") if isinstance(response, dict) else []
        return [item for item in (files or []) if isinstance(item, dict)]

    def _proof(remote: dict[str, Any]) -> DriveProof:
        parents = remote.get("parents") or []
        proof = DriveProof(
            file_id=str(remote.get("id") or ""),
            name=str(remote.get("name") or ""),
            size_bytes=int(remote.get("size") or -1),
            folder_id=folder_id if folder_id in parents else "",
            exists=not bool(remote.get("trashed", False)),
        )
        proof.validate(
            expected_name=name,
            expected_size=target.stat().st_size,
            expected_folder=folder_id,
        )
        return proof

    def _resolve_matches(matches: list[dict[str, Any]]) -> DriveProof | None:
        if len(matches) > 1:
            raise ProviderValidationError(
                "Drive devolvió más de un backup para la misma clave idempotente"
            )
        if not matches:
            return None
        proof = _proof(matches[0])
        if on_file_id:
            on_file_id(proof.file_id)
        return proof

    existing = _resolve_matches(_search_existing())
    if existing:
        return existing

    try:
        uploaded = (
            service.files()
            .create(
                body={
                    "name": name,
                    "parents": [folder_id],
                    "appProperties": {property_name: stable_key},
                },
                media_body=MediaFileUpload(str(target), resumable=True),
                fields="id",
            )
            .execute()
        )
    except Exception as exc:
        error_type = classify_provider_failure(str(exc))
        if error_type is QuotaError:
            raise QuotaError("Cuota de Drive alcanzada; archivo local preservado") from exc
        if error_type is AuthenticationError:
            raise AuthenticationError(
                "Autenticación Drive falló; archivo local preservado"
            ) from exc
        try:
            reconciled = _resolve_matches(_search_existing())
        except Exception as reconcile_exc:
            raise AmbiguousUploadError(
                "Drive create fue ambiguo y la reconciliación idempotente no fue concluyente; no se repetirá files.create"
            ) from reconcile_exc
        if reconciled:
            return reconciled
        raise AmbiguousUploadError(
            "Drive create fue ambiguo y no apareció la clave idempotente; no se repetirá files.create"
        ) from exc

    file_id = str(uploaded.get("id") or "") if isinstance(uploaded, dict) else ""
    if not file_id:
        raise AmbiguousUploadError(
            "Drive create no devolvió file_id; no se repetirá files.create"
        )
    if on_file_id:
        on_file_id(file_id)

    last_error: Exception | None = None
    for attempt in range(1, max(1, DRIVE_UPLOAD_MAX_RETRIES) + 1):
        try:
            remote = (
                service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,size,parents,trashed,appProperties",
                )
                .execute()
            )
            return _proof(remote)
        except Exception as exc:
            last_error = exc
            error_type = classify_provider_failure(str(exc))
            if error_type is QuotaError:
                raise QuotaError("Cuota de Drive alcanzada; archivo local preservado") from exc
            if error_type is AuthenticationError:
                raise AuthenticationError(
                    "Autenticación Drive falló; archivo local preservado"
                ) from exc
            if attempt < max(1, DRIVE_UPLOAD_MAX_RETRIES):
                time.sleep(backoff_with_jitter(attempt, base_seconds=2, cap_seconds=30))
    raise ProviderValidationError(
        "Drive no pudo confirmar el file_id conocido; files.create no se repitió"
    ) from last_error


def upload_to_drive(
    file_path: str,
    folder_id: str,
    sa_key_path: str = DRIVE_KEY_PATH,
    token_path: str | None = None,
    display_name: str | None = None,
    idempotency_key: str | None = None,
    on_file_id: Callable[[str], None] | None = None,
) -> str:
    """Compatibility facade returning only a verified ID."""
    return upload_to_drive_verified(
        file_path,
        folder_id,
        sa_key_path=sa_key_path,
        token_path=token_path,
        display_name=display_name,
        idempotency_key=idempotency_key,
        on_file_id=on_file_id,
    ).file_id


def move_drive_file(
    file_id: str,
    target_folder_id: str,
    sa_key_path: str = DRIVE_KEY_PATH,
    token_path: str | None = None,
) -> bool:
    """Move an existing file in Google Drive to target_folder_id by updating its parents."""
    if not str(file_id or "").strip() or not str(target_folder_id or "").strip():
        return False
    if _mock_enabled():
        logger.info("Mock Drive move: file %s -> folder %s", file_id, target_folder_id)
        return True

    sa_exists = bool(sa_key_path and Path(sa_key_path).is_file())
    token_exists = bool(token_path and Path(token_path).is_file())
    credentials = _credentials(sa_key_path if sa_exists else None, token_path if token_exists else None)
    from googleapiclient.discovery import build

    service = build("drive", "v3", credentials=credentials, cache_discovery=False)
    file_info = service.files().get(fileId=file_id, fields="parents").execute()
    previous_parents = ",".join(file_info.get("parents") or [])
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=previous_parents,
        fields="id, parents",
    ).execute()
    logger.info("Drive file %s moved to folder %s", file_id, target_folder_id)
    return True

