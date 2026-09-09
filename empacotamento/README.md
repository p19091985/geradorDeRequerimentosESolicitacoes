# Empacotamento

Este diretório guarda instruções e scripts auxiliares para empacotar a aplicação.

Fluxo recomendado:

1. Criar a `.venv` com `./iniciar.sh` ou `iniciar.bat`.
2. Validar sintaxe e testes rápidos.
3. Instalar PyInstaller apenas no ambiente de empacotamento.
4. Executar o script `python packaging/build_pyinstaller.py`.

O empacotamento não é obrigatório para desenvolvimento local.
