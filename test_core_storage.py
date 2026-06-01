from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from core.paths import (
    GENERATED_DOCS_DIR_NAME,
    SOURCE_HTML_DIR_NAME,
    build_unique_path,
    ensure_html_suffix,
    ensure_workspace_dirs,
)
from storage.html_files import read_html_file, write_html_file


class CoreStorageTests(unittest.TestCase):
    def test_ensure_workspace_dirs_creates_official_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_dir, generated_dir = ensure_workspace_dirs(Path(temp_dir))

            self.assertEqual(source_dir.name, SOURCE_HTML_DIR_NAME)
            self.assertEqual(generated_dir.name, GENERATED_DOCS_DIR_NAME)
            self.assertTrue(source_dir.is_dir())
            self.assertTrue(generated_dir.is_dir())

    def test_ensure_html_suffix_keeps_existing_html_extension(self) -> None:
        self.assertEqual(ensure_html_suffix("documento.htm"), "documento.htm")
        self.assertEqual(ensure_html_suffix("documento.html"), "documento.html")
        self.assertEqual(ensure_html_suffix("documento"), "documento.html")

    def test_build_unique_path_adds_counter_when_file_exists(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "documento.html"
            path.write_text("base", encoding="utf-8")

            self.assertEqual(build_unique_path(path), Path(temp_dir) / "documento-2.html")

    def test_read_and_write_html_file_uses_utf8(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "documento.html"

            write_html_file(path, "<p>Ola</p>")

            self.assertEqual(read_html_file(path), "<p>Ola</p>")


if __name__ == "__main__":
    unittest.main()
