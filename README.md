# CMA - Gerador de Documentos HTML, PNG, JPG e PDF

Aplicacao desktop em Python para criar, editar, visualizar e exportar documentos HTML em `PNG`, `JPG` e `PDF`.

O projeto foi pensado para uso local: os documentos em elaboracao, os arquivos finalizados e os materiais de consulta ficam em pastas de trabalho ignoradas pelo Git.

## Recursos

- edicao de documentos HTML
- preview em tempo real com Qt WebEngine
- CRUD local para documentos em elaboracao e documentos finalizados
- exportacao em alta resolucao com Playwright
- conversao para imagem e PDF com Pillow
- catalogo de templates com escolha ao criar um novo documento
- templates prontos para solicitacao, documento juridico e monografia ABNT

## Tecnologias

- `PySide6`: interface grafica
- `Qt WebEngine`: preview do HTML
- `Playwright`: captura do HTML renderizado
- `Pillow`: conversao de imagens e geracao de PDF

## Estrutura do projeto

```text
CMA/
├── documentos_em_elaboracao/      # HTMLs em andamento, ignorados pelo Git
├── documentos_finalizados/        # HTMLs finais e exportacoes, ignorados pelo Git
├── materiais_de_consulta/         # PDFs, paginas e apoios locais, ignorados pelo Git
├── core/                          # regras de paths e catalogo de templates
├── rendering/                     # exportacao de HTML para PNG, JPG e PDF
├── storage/                       # leitura e escrita de arquivos HTML
├── template/                      # modelos base versionados
├── capture_html_screenshot.py     # motor de captura e renderizacao
├── ttk_pdf_generator.py           # aplicacao principal
├── test_capture_html_screenshot.py
├── test_core_storage.py
├── test_template_catalog.py
├── iniciar.sh                     # bootstrap e execucao no Linux/macOS
├── iniciar.bat                    # bootstrap e execucao no Windows
├── pyproject.toml
├── requirements.txt
└── README.md
```

As pastas `documentos_em_elaboracao`, `documentos_finalizados` e `materiais_de_consulta` sao locais e estao no `.gitignore`.

## Templates disponiveis

O catalogo fica em `template/catalogo_templates.json`. Cada entrada aponta para um arquivo HTML dentro da pasta `template/`.

- `template/template-solicitacao.html`: modelo base de solicitacao
- `template/template-juridico.html`: modelo para documento juridico
- `template/template-abnt-monografia.html`: modelo generico de monografia em formato ABNT

## Requisitos

- Python 3.10+ recomendado
- acesso a internet na primeira execucao, caso seja necessario instalar dependencias
- ambiente grafico funcional no Linux para abrir a aplicacao desktop

Dependencias Python:

```txt
Pillow
playwright
PySide6
```

## Como iniciar

### Linux ou macOS

```bash
./iniciar.sh
```

### Windows

```bat
iniciar.bat
```

Os scripts de inicio:

1. criam a `.venv`, se ela ainda nao existir
2. verificam as dependencias Python
3. instalam pacotes ausentes
4. verificam o Chromium usado pelo Playwright
5. instalam o navegador do Playwright, se necessario
6. garantem a existencia de `documentos_em_elaboracao` e `documentos_finalizados`
7. iniciam a aplicacao principal

## Fluxo de uso

1. Abra a aplicacao.
2. Em `Documentos em Elaboracao`, crie um novo HTML ou abra um arquivo existente.
3. Ao criar um documento, escolha o template no catalogo.
4. Edite o conteudo no editor.
5. Acompanhe o preview na janela do navegador.
6. Escolha os formatos desejados: `PDF`, `JPG` e/ou `PNG`.
7. Clique em `Gerar Arquivos / Capturar Edicao`.
8. O sistema salva o HTML final e os arquivos exportados em `documentos_finalizados`.

Arquivos `HTML` finalizados podem ser reabertos no editor. Arquivos `PDF`, `PNG`, `JPG` e `JPEG` sao abertos pelo sistema operacional.

## Execucao manual

Se preferir iniciar sem os scripts:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m playwright install chromium
python ttk_pdf_generator.py
```

No Windows, adapte o comando de ativacao da virtualenv conforme o shell em uso.

## Validacao rapida

Durante o desenvolvimento, valide sintaxe com:

```bash
python -m py_compile ttk_pdf_generator.py capture_html_screenshot.py core/*.py rendering/*.py storage/*.py test_capture_html_screenshot.py test_core_storage.py test_template_catalog.py
bash -n iniciar.sh
python -m unittest test_core_storage.py test_template_catalog.py
```

## Observacoes

- A pasta oficial de entrada e `documentos_em_elaboracao`.
- A pasta oficial de saida e `documentos_finalizados`.
- `materiais_de_consulta` serve apenas como apoio local.
- O preview depende do Qt WebEngine.
- A exportacao depende do Playwright e do Chromium gerenciado por ele.
