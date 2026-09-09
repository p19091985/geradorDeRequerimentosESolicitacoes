from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]


def main() -> int:
    pyinstaller = shutil.which("pyinstaller")
    if pyinstaller is None:
        print("PyInstaller nao encontrado. Instale com: python -m pip install pyinstaller")
        return 1

    command = [
        pyinstaller,
        "--name",
        "gerador-documentos-cma",
        "--windowed",
        "--add-data",
        f"{ROOT_DIR / 'template'}:template",
        str(ROOT_DIR / "ttk_pdf_generator.py"),
    ]
    return subprocess.call(command, cwd=ROOT_DIR)


if __name__ == "__main__":
    raise SystemExit(main())
