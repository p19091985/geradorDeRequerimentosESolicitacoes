from __future__ import annotations

import json
import shutil
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_STATUS = "rascunho"
VALID_STATUSES = ("rascunho", "revisado", "finalizado", "arquivado")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class DocumentMetadata:
    titulo: str = ""
    tipo: str = ""
    interessado: str = ""
    tags: list[str] = field(default_factory=list)
    status: str = DEFAULT_STATUS
    template_origem: str = ""
    criado_em: str = ""
    modificado_em: str = ""

    @classmethod
    def for_document(
        cls,
        document_path: Path,
        *,
        status: str = DEFAULT_STATUS,
        template_origem: str = "",
        titulo: str = "",
    ) -> "DocumentMetadata":
        now = utc_now()
        return cls(
            titulo=titulo or document_path.stem,
            status=normalize_status(status),
            template_origem=template_origem,
            criado_em=now,
            modificado_em=now,
        )


def normalize_status(status: str) -> str:
    normalized = status.strip().lower()
    return normalized if normalized in VALID_STATUSES else DEFAULT_STATUS


def metadata_path_for(document_path: Path) -> Path:
    return document_path.with_name(f"{document_path.name}.meta.json")


def load_document_metadata(document_path: Path) -> DocumentMetadata:
    metadata_path = metadata_path_for(document_path)
    if not metadata_path.is_file():
        return DocumentMetadata.for_document(document_path)

    try:
        raw_data: dict[str, Any] = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return DocumentMetadata.for_document(document_path)

    metadata = DocumentMetadata.for_document(document_path)
    for field_name in asdict(metadata):
        if field_name in raw_data:
            setattr(metadata, field_name, raw_data[field_name])
    metadata.status = normalize_status(metadata.status)
    if not metadata.titulo:
        metadata.titulo = document_path.stem
    return metadata


def save_document_metadata(document_path: Path, metadata: DocumentMetadata) -> Path:
    metadata_path = metadata_path_for(document_path)
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    data = asdict(metadata)
    data["status"] = normalize_status(metadata.status)
    metadata_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return metadata_path


def upsert_document_metadata(document_path: Path, **updates: Any) -> DocumentMetadata:
    metadata = load_document_metadata(document_path)
    for key, value in updates.items():
        if hasattr(metadata, key):
            setattr(metadata, key, value)
    metadata.status = normalize_status(metadata.status)
    metadata.modificado_em = utc_now()
    save_document_metadata(document_path, metadata)
    return metadata


def touch_document_metadata(document_path: Path) -> None:
    upsert_document_metadata(document_path)


def rename_document_metadata(source_path: Path, target_path: Path) -> None:
    source_metadata = metadata_path_for(source_path)
    if source_metadata.exists():
        source_metadata.rename(metadata_path_for(target_path))


def copy_document_metadata(source_path: Path, target_path: Path) -> None:
    source_metadata = metadata_path_for(source_path)
    if source_metadata.exists():
        shutil.copy2(source_metadata, metadata_path_for(target_path))
        upsert_document_metadata(target_path, titulo=target_path.stem)


def delete_document_metadata(document_path: Path) -> None:
    metadata_path_for(document_path).unlink(missing_ok=True)


def metadata_search_blob(document_path: Path) -> str:
    metadata = load_document_metadata(document_path)
    values = [
        metadata.titulo,
        metadata.tipo,
        metadata.interessado,
        metadata.status,
        metadata.template_origem,
        " ".join(metadata.tags),
    ]
    return " ".join(values).lower()
