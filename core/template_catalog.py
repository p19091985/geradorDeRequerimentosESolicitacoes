from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from storage.html_files import read_html_file


CATALOG_PATH = Path("template/catalogo_templates.json")

DEFAULT_TEMPLATE_HTML = (
    "<!DOCTYPE html>\n"
    "<html lang=\"pt-BR\">\n"
    "<head>\n"
    "  <meta charset=\"utf-8\">\n"
    "  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">\n"
    "  <title>Novo Documento</title>\n"
    "</head>\n"
    "<body>\n"
    "  <main>\n"
    "    <h1>Novo Documento</h1>\n"
    "    <p>Edite este HTML para montar o seu documento.</p>\n"
    "  </main>\n"
    "</body>\n"
    "</html>\n"
)


@dataclass(frozen=True, slots=True)
class TemplateDefinition:
    id: str
    nome: str
    categoria: str
    arquivo: str
    descricao: str = ""
    padrao: bool = False
    variaveis: tuple[str, ...] = ()

    def resolve_path(self, root_dir: Path | None = None) -> Path:
        root = (root_dir or Path.cwd()).resolve()
        raw_path = Path(self.arquivo)
        if raw_path.is_absolute():
            return raw_path
        if len(raw_path.parts) > 1:
            return (root / raw_path).resolve()
        return (root / "template" / raw_path).resolve()

    @property
    def display_label(self) -> str:
        return f"{self.nome} [{self.categoria}]"


def _record_to_template(record: dict[str, Any]) -> TemplateDefinition:
    required_fields = ("id", "nome", "categoria", "arquivo")
    missing = [field for field in required_fields if not str(record.get(field, "")).strip()]
    if missing:
        raise ValueError(f"Template sem campo obrigatorio: {', '.join(missing)}")

    return TemplateDefinition(
        id=str(record["id"]).strip(),
        nome=str(record["nome"]).strip(),
        categoria=str(record["categoria"]).strip(),
        arquivo=str(record["arquivo"]).strip(),
        descricao=str(record.get("descricao", "")).strip(),
        padrao=bool(record.get("padrao", False)),
        variaveis=tuple(str(name).strip() for name in record.get("variaveis", []) if str(name).strip()),
    )


def load_template_catalog(root_dir: Path | None = None) -> list[TemplateDefinition]:
    root = (root_dir or Path.cwd()).resolve()
    catalog_path = (root / CATALOG_PATH).resolve()
    if not catalog_path.is_file():
        return _fallback_templates(root)

    raw_data = json.loads(catalog_path.read_text(encoding="utf-8"))
    records = raw_data.get("templates", raw_data) if isinstance(raw_data, dict) else raw_data
    if not isinstance(records, list):
        raise ValueError("Catalogo de templates precisa conter uma lista em 'templates'.")

    templates = [_record_to_template(record) for record in records]
    _validate_template_files(templates, root)
    return templates or _fallback_templates(root)


def load_default_template(root_dir: Path | None = None) -> TemplateDefinition | None:
    templates = load_template_catalog(root_dir)
    if not templates:
        return None
    return next((template for template in templates if template.padrao), templates[0])


def load_default_template_path(root_dir: Path | None = None) -> Path:
    root = (root_dir or Path.cwd()).resolve()
    template = load_default_template(root)
    if template is not None:
        return template.resolve_path(root)
    return (root / "template" / "template-solicitacao.html").resolve()


def load_template_content(
    template: TemplateDefinition | None = None,
    root_dir: Path | None = None,
) -> str:
    root = (root_dir or Path.cwd()).resolve()
    chosen_template = template or load_default_template(root)
    if chosen_template is None:
        return DEFAULT_TEMPLATE_HTML
    template_path = chosen_template.resolve_path(root)
    if template_path.is_file():
        return read_html_file(template_path)
    return DEFAULT_TEMPLATE_HTML


def _fallback_templates(root_dir: Path) -> list[TemplateDefinition]:
    candidates = [
        TemplateDefinition(
            id="solicitacao",
            nome="Solicitacao Administrativa",
            categoria="Administrativo",
            arquivo="template-solicitacao.html",
            descricao="Modelo base de solicitacao administrativa.",
            padrao=True,
        ),
        TemplateDefinition(
            id="juridico",
            nome="Documento Juridico",
            categoria="Juridico",
            arquivo="template-juridico.html",
            descricao="Modelo para fundamentacao juridica administrativa.",
        ),
        TemplateDefinition(
            id="abnt-monografia",
            nome="Template ABNT - Monografia",
            categoria="Academico",
            arquivo="template-abnt-monografia.html",
            descricao="Modelo generico de monografia em formato ABNT.",
            variaveis=(
                "instituicao",
                "curso",
                "departamento",
                "autor",
                "titulo",
                "cidade_uf",
                "ano",
                "orientador",
            ),
        ),
    ]
    return [
        template
        for template in candidates
        if template.resolve_path(root_dir).is_file()
    ]


def _validate_template_files(
    templates: list[TemplateDefinition],
    root_dir: Path,
) -> None:
    missing = [
        str(template.resolve_path(root_dir))
        for template in templates
        if not template.resolve_path(root_dir).is_file()
    ]
    if missing:
        raise FileNotFoundError(
            "Template(s) do catalogo nao encontrado(s):\n" + "\n".join(missing)
        )
