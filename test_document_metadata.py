from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from storage.document_metadata import (
    DocumentMetadata,
    copy_document_metadata,
    delete_document_metadata,
    load_document_metadata,
    metadata_path_for,
    metadata_search_blob,
    rename_document_metadata,
    save_document_metadata,
    upsert_document_metadata,
)


class DocumentMetadataTests(unittest.TestCase):
    def test_save_and_load_document_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            document_path = Path(temp_dir) / "documento.html"
            document_path.write_text("<h1>Documento</h1>", encoding="utf-8")
            metadata = DocumentMetadata.for_document(
                document_path,
                status="rascunho",
                template_origem="solicitacao",
                titulo="Pedido teste",
            )

            save_document_metadata(document_path, metadata)
            loaded = load_document_metadata(document_path)

            self.assertEqual(loaded.titulo, "Pedido teste")
            self.assertEqual(loaded.status, "rascunho")
            self.assertEqual(loaded.template_origem, "solicitacao")
            self.assertTrue(metadata_path_for(document_path).is_file())

    def test_upsert_normalizes_status_and_updates_search_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            document_path = Path(temp_dir) / "documento.html"
            document_path.write_text("<h1>Documento</h1>", encoding="utf-8")

            upsert_document_metadata(
                document_path,
                status="FINALIZADO",
                interessado="Secretaria",
                tags=["ferias", "servidor"],
            )

            loaded = load_document_metadata(document_path)
            self.assertEqual(loaded.status, "finalizado")
            self.assertIn("secretaria", metadata_search_blob(document_path))
            self.assertIn("ferias", metadata_search_blob(document_path))

    def test_rename_copy_and_delete_metadata_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = Path(temp_dir) / "origem.html"
            renamed_path = Path(temp_dir) / "renomeado.html"
            copied_path = Path(temp_dir) / "copia.html"
            source_path.write_text("<h1>Origem</h1>", encoding="utf-8")
            save_document_metadata(
                source_path,
                DocumentMetadata.for_document(source_path, titulo="Origem"),
            )

            rename_document_metadata(source_path, renamed_path)
            self.assertFalse(metadata_path_for(source_path).exists())
            self.assertTrue(metadata_path_for(renamed_path).exists())

            copy_document_metadata(renamed_path, copied_path)
            self.assertTrue(metadata_path_for(copied_path).exists())
            self.assertEqual(load_document_metadata(copied_path).titulo, copied_path.stem)

            delete_document_metadata(copied_path)
            self.assertFalse(metadata_path_for(copied_path).exists())


if __name__ == "__main__":
    unittest.main()
