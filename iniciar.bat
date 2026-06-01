@echo off
setlocal

cd /d "%~dp0"

set "PYTHON_CMD="
where py >nul 2>&1
if not errorlevel 1 set "PYTHON_CMD=py -3"
if not defined PYTHON_CMD (
  where python >nul 2>&1
  if not errorlevel 1 set "PYTHON_CMD=python"
)

if not defined PYTHON_CMD (
  echo Python nao encontrado. Instale Python 3 para continuar.
  exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual...
  %PYTHON_CMD% -m venv .venv
  if errorlevel 1 exit /b 1
)

set "VENV_PY=.venv\Scripts\python.exe"

if not exist "documentos_em_elaboracao" mkdir "documentos_em_elaboracao"
if not exist "documentos_finalizados" mkdir "documentos_finalizados"

"%VENV_PY%" -c "import importlib.util, sys; modules=[('PIL','Pillow'),('playwright','playwright'),('PySide6','PySide6'),('PySide6.QtWebEngineWidgets','PySide6')]; missing=[package for module, package in modules if importlib.util.find_spec(module) is None]; sys.exit(0 if not missing else 1)"
if errorlevel 1 (
  echo Instalando dependencias Python...
  "%VENV_PY%" -m pip install -r requirements.txt
  if errorlevel 1 exit /b 1
)

"%VENV_PY%" -c "from playwright.sync_api import sync_playwright; p = sync_playwright().start(); b = p.chromium.launch(headless=True); b.close(); p.stop()" >nul 2>&1
if errorlevel 1 (
  echo Instalando navegador do Playwright...
  "%VENV_PY%" -m playwright install chromium
  if errorlevel 1 exit /b 1
)

"%VENV_PY%" ttk_pdf_generator.py
