from __future__ import annotations

import shutil
from pathlib import Path

from storage.document_metadata import utc_now


HISTORY_DIR_NAME = ".historico"


def history_dir_for(document_path: Path) -> Path:
    return document_path.parent / HISTORY_DIR_NAME / document_path.stem


def create_document_snapshot(document_path: Path, reason: str = "manual") -> Path | None:
    if not document_path.is_file():
        return None

    timestamp = utc_now().replace(":", "-")
    safe_reason = "".join(
        char if char.isalnum() or char in {"-", "_"} else "-"
        for char in reason.strip().lower()
    ).strip("-") or "manual"
    snapshot_dir = history_dir_for(document_path)
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"{timestamp}-{safe_reason}{document_path.suffix}"
    shutil.copy2(document_path, snapshot_path)
    return snapshot_path


def list_document_snapshots(document_path: Path) -> list[Path]:
    snapshot_dir = history_dir_for(document_path)
    if not snapshot_dir.is_dir():
        return []
    return sorted(
        (path for path in snapshot_dir.iterdir() if path.is_file()),
        key=lambda path: path.name,
    )
