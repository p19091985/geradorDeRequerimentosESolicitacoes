from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from core.template_catalog import (
    load_default_template_path,
    load_template_catalog,
    load_template_content,
)


class TemplateCatalogTests(unittest.TestCase):
    def test_load_template_catalog_reads_manifest_and_validates_files(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_dir = root / "template"
            template_dir.mkdir()
            (template_dir / "modelo.html").write_text("<h1>Modelo</h1>", encoding="utf-8")
            (template_dir / "catalogo_templates.json").write_text(
                json.dumps(
                    {
                        "templates": [
                            {
                                "id": "modelo",
                                "nome": "Modelo Teste",
                                "categoria": "Teste",
                                "arquivo": "modelo.html",
                                "descricao": "Template usado no teste.",
                                "padrao": True,
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            templates = load_template_catalog(root)

            self.assertEqual(len(templates), 1)
            self.assertEqual(templates[0].id, "modelo")
            self.assertEqual(load_default_template_path(root), template_dir / "modelo.html")
            self.assertEqual(load_template_content(templates[0], root), "<h1>Modelo</h1>")

    def test_load_template_catalog_reports_missing_template_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            template_dir = root / "template"
            template_dir.mkdir()
            (template_dir / "catalogo_templates.json").write_text(
                json.dumps(
                    {
                        "templates": [
                            {
                                "id": "ausente",
                                "nome": "Template Ausente",
                                "categoria": "Teste",
                                "arquivo": "ausente.html",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            with self.assertRaises(FileNotFoundError):
                load_template_catalog(root)


if __name__ == "__main__":
    unittest.main()
