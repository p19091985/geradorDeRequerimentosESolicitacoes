from __future__ import annotations

import unittest

from core.template_variables import (
    extract_template_variables,
    humanize_variable_name,
    merge_template_variables,
    render_template_variables,
)


class TemplateVariablesTests(unittest.TestCase):
    def test_extract_template_variables_preserves_first_seen_order(self) -> None:
        content = "{{nome}} {{cargo}} {{ nome }} {{setor_1}}"

        self.assertEqual(
            extract_template_variables(content),
            ["nome", "cargo", "setor_1"],
        )

    def test_merge_template_variables_deduplicates_across_sources(self) -> None:
        self.assertEqual(
            merge_template_variables(("nome", "cargo"), ["cargo", "setor"]),
            ["nome", "cargo", "setor"],
        )

    def test_render_template_variables_escapes_html_values(self) -> None:
        rendered = render_template_variables(
            "<p>{{nome}}</p>",
            {"nome": "<Patrik>"},
        )

        self.assertEqual(rendered, "<p>&lt;Patrik&gt;</p>")

    def test_humanize_variable_name_formats_label(self) -> None:
        self.assertEqual(humanize_variable_name("cidade_uf"), "Cidade Uf")


if __name__ == "__main__":
    unittest.main()
