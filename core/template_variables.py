from __future__ import annotations

import html
import re


VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def extract_template_variables(content: str) -> list[str]:
    seen: set[str] = set()
    variables: list[str] = []
    for match in VARIABLE_PATTERN.finditer(content):
        name = match.group(1)
        if name not in seen:
            variables.append(name)
            seen.add(name)
    return variables


def merge_template_variables(*groups: list[str] | tuple[str, ...]) -> list[str]:
    seen: set[str] = set()
    variables: list[str] = []
    for group in groups:
        for name in group:
            if name not in seen:
                variables.append(name)
                seen.add(name)
    return variables


def humanize_variable_name(name: str) -> str:
    words = name.replace("_", " ").strip().split()
    return " ".join(word.capitalize() for word in words)


def render_template_variables(content: str, values: dict[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        raw_value = values.get(match.group(1), "")
        return html.escape(raw_value, quote=True)

    return VARIABLE_PATTERN.sub(replace, content)
