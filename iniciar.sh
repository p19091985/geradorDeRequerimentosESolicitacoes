#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

if command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
  PYTHON_BIN="python"
else
  echo "Python nao encontrado. Instale Python 3 para continuar."
  exit 1
fi

VENV_DIR="$ROOT_DIR/.venv"
VENV_PY="$VENV_DIR/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "Criando ambiente virtual..."
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

# shellcheck disable=SC1091
source "$VENV_DIR/bin/activate"

mkdir -p "$ROOT_DIR/documentos_em_elaboracao" "$ROOT_DIR/documentos_finalizados"

if ! "$VENV_PY" - <<'PY'
import importlib.util
import sys

modules = (
    ("PIL", "Pillow"),
    ("playwright", "playwright"),
    ("PySide6", "PySide6"),
    ("PySide6.QtWebEngineWidgets", "PySide6"),
)
missing = [package for module, package in modules if importlib.util.find_spec(module) is None]
sys.exit(0 if not missing else 1)
PY
then
  echo "Instalando dependencias Python..."
  "$VENV_PY" -m pip install -r requirements.txt
fi

if ! "$VENV_PY" - <<'PY'
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    browser.close()
PY
then
  echo "Instalando navegador do Playwright..."
  "$VENV_PY" -m playwright install chromium
fi

exec "$VENV_PY" ttk_pdf_generator.py
