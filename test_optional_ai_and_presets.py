from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ai.prompt_assistant import build_review_prompt, write_review_prompt
from core.export_presets import EXPORT_PRESETS, get_export_preset


class OptionalAiAndPresetsTests(unittest.TestCase):
    def test_build_review_prompt_keeps_document_text(self) -> None:
        prompt = build_review_prompt("Texto do documento")

        self.assertIn("Texto do documento", prompt)
        self.assertIn("nao invente fatos", prompt)

    def test_write_review_prompt_creates_sidecar_file(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            document_path = Path(temp_dir) / "documento.html"

            prompt_path = write_review_prompt(document_path, "<p>Teste</p>")

            self.assertEqual(prompt_path.name, "documento.ia_prompt.txt")
            self.assertIn("<p>Teste</p>", prompt_path.read_text(encoding="utf-8"))

    def test_export_presets_have_default_fallback(self) -> None:
        self.assertGreaterEqual(len(EXPORT_PRESETS), 4)
        self.assertEqual(get_export_preset("normal").id, "normal")
        self.assertEqual(get_export_preset("inexistente").id, "normal")


if __name__ == "__main__":
    unittest.main()
