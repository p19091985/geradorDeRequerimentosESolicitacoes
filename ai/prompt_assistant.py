from __future__ import annotations

from pathlib import Path


def build_review_prompt(document_text: str, mode: str = "revisao_formal") -> str:
    return (
        "Revise o documento abaixo em portugues do Brasil.\n"
        f"Modo: {mode}.\n"
        "Mantenha sentido juridico/administrativo, destaque pontos de atencao e "
        "nao invente fatos, datas, leis ou fundamentos ausentes no texto.\n\n"
        "DOCUMENTO:\n"
        f"{document_text.strip()}\n"
    )


def write_review_prompt(document_path: Path, document_text: str, mode: str = "revisao_formal") -> Path:
    prompt_path = document_path.with_name(f"{document_path.stem}.ia_prompt.txt")
    prompt_path.write_text(build_review_prompt(document_text, mode), encoding="utf-8")
    return prompt_path
