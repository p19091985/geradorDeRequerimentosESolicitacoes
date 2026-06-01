from __future__ import annotations

from pathlib import Path


def read_html_file(path: Path) -> str:
    """Read an HTML file, auto-detecting UTF-16 BOM or falling back to UTF-8."""
    raw = path.read_bytes()
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return raw.decode("utf-16")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("utf-16-le", errors="replace")


def write_html_file(path: Path, content: str) -> None:
    """Write HTML content as UTF-8."""
    path.write_text(content, encoding="utf-8")
