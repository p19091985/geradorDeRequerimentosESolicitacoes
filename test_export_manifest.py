from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from storage.export_manifest import manifest_path_for, write_generation_manifest


class ExportManifestTests(unittest.TestCase):
    def test_write_generation_manifest_creates_json_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)

            manifest_path = write_generation_manifest(
                output_dir,
                "documento",
                {
                    "origem": "documentos_em_elaboracao/documento.html",
                    "template": "solicitacao",
                    "formatos_solicitados": ["html", "pdf"],
                },
            )

            self.assertEqual(manifest_path, manifest_path_for(output_dir, "documento"))
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(data["template"], "solicitacao")
            self.assertEqual(data["formatos_solicitados"], ["html", "pdf"])


if __name__ == "__main__":
    unittest.main()
