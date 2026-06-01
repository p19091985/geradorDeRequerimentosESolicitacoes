from __future__ import annotations

from pathlib import Path


SOURCE_HTML_DIR_NAME = "documentos_em_elaboracao"
GENERATED_DOCS_DIR_NAME = "documentos_finalizados"
HTML_SUFFIXES = {".html", ".htm"}
FINISHED_DOC_SUFFIXES = {
    ".html",
    ".htm",
    ".pdf",
    ".png",
    ".jpg",
    ".jpeg",
}


def project_root() -> Path:
    return Path.cwd()


def source_html_dir(root_dir: Path | None = None) -> Path:
    source_dir = (root_dir or project_root()) / SOURCE_HTML_DIR_NAME
    source_dir.mkdir(parents=True, exist_ok=True)
    return source_dir


def generated_docs_dir(root_dir: Path | None = None) -> Path:
    generated_dir = (root_dir or project_root()) / GENERATED_DOCS_DIR_NAME
    generated_dir.mkdir(parents=True, exist_ok=True)
    return generated_dir


def ensure_workspace_dirs(root_dir: Path | None = None) -> tuple[Path, Path]:
    return source_html_dir(root_dir), generated_docs_dir(root_dir)


def ensure_html_suffix(name: str) -> str:
    if Path(name).suffix.lower() in HTML_SUFFIXES:
        return name
    return f"{name}.html"


def build_unique_path(path: Path) -> Path:
    if not path.exists():
        return path

    counter = 2
    while True:
        candidate = path.with_name(f"{path.stem}-{counter}{path.suffix}")
        if not candidate.exists():
            return candidate
        counter += 1
