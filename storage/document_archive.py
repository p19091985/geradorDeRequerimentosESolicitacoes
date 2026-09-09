from __future__ import annotations

import shutil
from pathlib import Path

from core.paths import build_unique_path
from storage.document_metadata import (
    metadata_path_for,
    rename_document_metadata,
    upsert_document_metadata,
)


ARCHIVE_DIR_NAME = "arquivados"


def archive_document(document_path: Path, workspace_root: Path) -> Path:
    workspace_root = workspace_root.resolve()
    document_path = document_path.resolve()
    try:
        relative_path = document_path.relative_to(workspace_root)
    except ValueError as exc:
        raise ValueError("Documento precisa estar dentro da pasta gerenciada.") from exc

    target_path = build_unique_path(workspace_root / ARCHIVE_DIR_NAME / relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    document_path.rename(target_path)
    rename_document_metadata(document_path, target_path)
    upsert_document_metadata(target_path, status="arquivado")
    return target_path


def restore_archived_document(archived_path: Path, workspace_root: Path) -> Path:
    workspace_root = workspace_root.resolve()
    archived_path = archived_path.resolve()
    archive_root = workspace_root / ARCHIVE_DIR_NAME
    try:
        relative_path = archived_path.relative_to(archive_root)
    except ValueError as exc:
        raise ValueError("Documento precisa estar dentro da pasta de arquivados.") from exc

    target_path = build_unique_path(workspace_root / relative_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    archived_path.rename(target_path)
    rename_document_metadata(archived_path, target_path)
    upsert_document_metadata(target_path, status="rascunho")
    return target_path


def delete_document_with_metadata(document_path: Path) -> None:
    metadata_path = metadata_path_for(document_path)
    document_path.unlink(missing_ok=False)
    metadata_path.unlink(missing_ok=True)


def copy_document_with_metadata(source_path: Path, target_path: Path) -> None:
    shutil.copy2(source_path, target_path)
    source_metadata = metadata_path_for(source_path)
    if source_metadata.exists():
        shutil.copy2(source_metadata, metadata_path_for(target_path))
