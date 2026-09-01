"""Provision and organize complete Google Drive subfolder tree under the root folder."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, Optional

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.core.google_auth import build_drive_service
from src.log import get_logger, setup_logging

logger = get_logger("setup_drive_folders")


def find_or_create_subfolder(service, name: str, parent_id: str) -> str:
    """Find existing subfolder by name or create a new one under parent_id."""
    query = (
        f"'{parent_id}' in parents and name = '{name}' and "
        f"mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    )
    results = service.files().list(
        q=query,
        spaces="drive",
        fields="files(id, name)",
        supportsAllDrives=True,
        includeItemsFromAllDrives=True,
    ).execute()

    files = results.get("files", [])
    if files:
        folder_id = files[0]["id"]
        logger.info("Carpeta existente encontrada: '%s' (ID: %s)", name, folder_id)
        return folder_id

    file_metadata = {
        "name": name,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(
        body=file_metadata,
        fields="id, name",
        supportsAllDrives=True,
    ).execute()
    folder_id = folder.get("id")
    logger.info("Carpeta creada: '%s' (ID: %s)", name, folder_id)
    return folder_id


def setup_drive_structure(root_folder_id: str, sa_key_path: Optional[str] = None, token_path: Optional[str] = None) -> Dict[str, str]:
    """Create complete folder hierarchy under root_folder_id and return folder IDs."""
    service = build_drive_service(sa_key_path=sa_key_path, token_path=token_path)

    # 1. Verify root folder access
    root = service.files().get(
        fileId=root_folder_id,
        fields="id, name, capabilities",
        supportsAllDrives=True,
    ).execute()
    logger.info("Conectado exitosamente a carpeta raíz de Drive: '%s' [%s]", root.get("name"), root_folder_id)

    ids = {
        "DRIVE_ROOT_FOLDER_ID": root_folder_id,
        "DRIVE_FOLDER_ID": root_folder_id,
    }

    # 2. Approved section
    approved_id = find_or_create_subfolder(service, "01_approved", root_folder_id)
    ids["DRIVE_APPROVED_FOLDER_ID"] = approved_id

    video_id = find_or_create_subfolder(service, "videos", approved_id)
    ids["DRIVE_APPROVED_VIDEO_FOLDER_ID"] = video_id

    covers_id = find_or_create_subfolder(service, "covers", approved_id)
    ids["DRIVE_APPROVED_COVER_FOLDER_ID"] = covers_id

    metadata_id = find_or_create_subfolder(service, "metadata", approved_id)
    ids["DRIVE_METADATA_FOLDER_ID"] = metadata_id

    # 3. Lifecycle folders
    ids["DRIVE_PUBLISHED_FOLDER_ID"] = find_or_create_subfolder(service, "02_published", root_folder_id)
    ids["DRIVE_REJECTED_FOLDER_ID"] = find_or_create_subfolder(service, "03_rejected", root_folder_id)
    ids["DRIVE_ARCHIVE_FOLDER_ID"] = find_or_create_subfolder(service, "04_archive", root_folder_id)

    # 4. Channels & Assets
    channels_id = find_or_create_subfolder(service, "channels", root_folder_id)
    find_or_create_subfolder(service, "moku", channels_id)
    find_or_create_subfolder(service, "aelithia", channels_id)
    find_or_create_subfolder(service, "assets", root_folder_id)

    return ids


def update_env_file(folder_ids: Dict[str, str], env_path: Path = ROOT_DIR / ".env") -> None:
    """Update .env with newly provisioned Drive folder IDs."""
    if not env_path.exists():
        return

    content = env_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    new_lines = []

    keys_set = set(folder_ids.keys())
    existing_keys = set()

    for line in lines:
        matched = False
        for k, v in folder_ids.items():
            if line.startswith(f"{k}=") or line.startswith(f'export {k}='):
                new_lines.append(f'{k}="{v}"')
                existing_keys.add(k)
                matched = True
                break
        if not matched:
            new_lines.append(line)

    for k, v in folder_ids.items():
        if k not in existing_keys:
            new_lines.append(f'{k}="{v}"')

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    logger.info("Archivo .env actualizado con los IDs de carpetas de Drive.")


if __name__ == "__main__":
    setup_logging()
    root_id = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DRIVE_ROOT_FOLDER_ID", "")
    if not root_id:
        print("Error: Se requiere DRIVE_ROOT_FOLDER_ID en el entorno o como argumento CLI.", file=sys.stderr)
        sys.exit(1)
    sa_path = "secrets/drive_key.json" if Path("secrets/drive_key.json").exists() else None
    token_p = "secrets/youtube_token.json" if Path("secrets/youtube_token.json").exists() else None

    print(f"Provisioning Drive folders under root: {root_id}...")
    try:
        results = setup_drive_structure(root_id, sa_key_path=sa_path, token_path=token_p)
        update_env_file(results)
        print("\n¡Estructura de Google Drive creada y configurada con éxito!")
        for k, v in results.items():
            print(f"  {k}: {v}")
    except Exception as exc:
        print(f"\nError al provisionar carpetas en Drive: {exc}", file=sys.stderr)
        sys.exit(1)
