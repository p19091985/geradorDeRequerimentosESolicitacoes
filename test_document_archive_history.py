from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.document_archive import ARCHIVE_DIR_NAME, archive_document, restore_archived_document
from storage.document_history import create_document_snapshot, list_document_snapshots
from storage.document_metadata import load_document_metadata, metadata_path_for, save_document_metadata
from storage.document_metadata import DocumentMetadata


class DocumentArchiveHistoryTests(unittest.TestCase):
    def test_archive_and_restore_document_moves_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            document_path = root / "documento.html"
            document_path.write_text("<h1>Documento</h1>", encoding="utf-8")
            save_document_metadata(
                document_path,
                DocumentMetadata.for_document(document_path, titulo="Documento"),
            )

            archived_path = archive_document(document_path, root)

            self.assertFalse(document_path.exists())
            self.assertEqual(archived_path.parts[-2], ARCHIVE_DIR_NAME)
            self.assertTrue(metadata_path_for(archived_path).exists())
            self.assertEqual(load_document_metadata(archived_path).status, "arquivado")

            restored_path = restore_archived_document(archived_path, root)

            self.assertTrue(restored_path.exists())
            self.assertEqual(load_document_metadata(restored_path).status, "rascunho")

    def test_create_document_snapshot_records_versions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            document_path = Path(temp_dir) / "documento.html"
            document_path.write_text("<h1>v1</h1>", encoding="utf-8")

            snapshot_path = create_document_snapshot(document_path, "salvar")

            self.assertIsNotNone(snapshot_path)
            self.assertTrue(snapshot_path.is_file())
            self.assertEqual(snapshot_path.read_text(encoding="utf-8"), "<h1>v1</h1>")
            self.assertEqual(list_document_snapshots(document_path), [snapshot_path])


if __name__ == "__main__":
    unittest.main()
