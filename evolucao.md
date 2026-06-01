# Plano de Evolucao do Sistema

Este documento organiza um caminho pratico para evoluir o gerador de documentos HTML, PNG, JPG e PDF para uma plataforma mais robusta, modular e produtiva.

## Visao

O sistema atual ja entrega uma base funcional: edicao de HTML, preview em tempo real, CRUD local de documentos e exportacao para formatos finais. A evolucao proposta busca transformar essa base em um ambiente profissional de producao documental, mantendo a simplicidade de uso local.

O objetivo de estado da arte para este projeto e:

- permitir criacao de documentos a partir de templates catalogados;
- reduzir a necessidade de editar HTML cru;
- melhorar a confiabilidade da exportacao;
- organizar documentos com metadados, busca e status;
- preparar o codigo para manutencao, testes e futuras funcionalidades com IA.

## Status Atual

Atualizado em 2026-06-01.

Concluido:

- pastas oficiais renomeadas para `documentos_em_elaboracao`, `documentos_finalizados` e `materiais_de_consulta`;
- separacao inicial de responsabilidades em `core/`, `storage/` e `rendering/`;
- catalogo de templates em `template/catalogo_templates.json`;
- validacao de existencia dos arquivos HTML declarados no catalogo;
- seletor de template ao criar novo documento;
- template generico `template/template-abnt-monografia.html`;
- `pyproject.toml` com configuracao inicial do Ruff;
- testes unitarios para catalogo, paths e storage;
- GitHub Actions com validacao rapida de sintaxe e testes leves;
- README atualizado com a estrutura atual.

Ainda pendente:

- extrair a interface PySide6 para um pacote `app/`;
- implementar variaveis preenchiveis em templates;
- melhorar editor, preview e UX;
- adicionar metadados, busca e historico;
- fortalecer automacao, empacotamento e recursos opcionais com IA.

## Principios

- Evoluir sem quebrar o fluxo atual.
- Separar responsabilidades antes de adicionar complexidade.
- Priorizar recursos que reduzam trabalho manual do usuario.
- Manter o sistema local e simples de executar.
- Tratar HTML, PDF e assets como artefatos rastreaveis.
- Automatizar validacoes para evitar regressao visual e funcional.

## Fase 1: Fundamento Tecnico

Separar o codigo em camadas menores, preservando o comportamento atual.

Estrutura sugerida:

```text
app/
  interface PySide6
core/
  regras de documento, templates e configuracoes
rendering/
  Playwright, captura, PNG, JPG e PDF
storage/
  leitura, escrita, paths seguros e metadados
templates/
  modelos HTML e manifestos
tests/
  testes por modulo
```

Entregaveis:

- [x] mover responsabilidades de paths, storage, catalogo e exportacao para modulos menores;
- [ ] extrair janelas e controlador PySide6 para `app/`;
- [x] manter compatibilidade com `iniciar.sh` e `iniciar.bat`;
- [x] preservar os diretorios oficiais `documentos_em_elaboracao` e `documentos_finalizados`;
- [x] garantir que os testes atuais continuem passando.

Prioridade: alta.

## Fase 2: Catalogo de Templates

Substituir a lista fixa de templates por um catalogo com metadados.

Exemplo de manifesto:

```json
{
  "id": "abnt-monografia",
  "nome": "Template ABNT - Monografia",
  "categoria": "Relatorio academico",
  "arquivo": "template-abnt-monografia.html",
  "descricao": "Modelo generico com capa, folha de rosto, sumario e estrutura de monografia ABNT"
}
```

Entregaveis:

- [x] criar um arquivo de catalogo de templates;
- [x] listar templates disponiveis na interface;
- [x] permitir escolher o template ao criar documento;
- [x] manter um template padrao para compatibilidade;
- [x] validar se o arquivo HTML de cada template existe.

Prioridade: muito alta.

## Fase 3: Templates com Variaveis

Adicionar campos reutilizaveis aos templates para diminuir edicao manual de HTML.

Exemplos de variaveis:

```text
{{nome_requerente}}
{{cargo}}
{{setor}}
{{data}}
{{assunto}}
{{fundamentacao}}
```

Entregaveis:

- definir sintaxe simples de variaveis;
- detectar variaveis presentes no template;
- exibir formulario para preenchimento;
- renderizar HTML final preenchido;
- manter opcao de editar o HTML depois da geracao.

Prioridade: alta.

## Fase 4: Editor Mais Inteligente

Melhorar o editor para tornar o trabalho diario mais rapido e seguro.

Entregaveis:

- autosave com indicador de estado;
- busca e substituicao;
- formatacao de HTML;
- validacao basica de HTML e CSS;
- snippets para secoes comuns;
- historico simples de versoes;
- alerta para documento nao salvo antes de fechar.

Prioridade: media.

## Fase 5: Preview e UX Moderna

Refinar a experiencia de uso, mantendo foco operacional.

Entregaveis:

- tela principal integrada com documentos, editor e preview;
- seletor visual de templates;
- barra lateral de documentos recentes;
- status claro de salvo, nao salvo e exportando;
- preview com zoom;
- botoes com icones e tooltips;
- tema claro e escuro;
- atalhos de teclado para salvar, exportar, duplicar e abrir pasta.

Prioridade: media.

## Fase 6: Exportacao Profissional

Tornar a exportacao mais previsivel, auditavel e flexivel.

Entregaveis:

- presets de qualidade: rascunho, normal, alta resolucao e arquivo leve;
- exportacao em lote;
- fila de exportacao com progresso;
- logs tecnicos por exportacao;
- deteccao de paginas cortadas;
- pre-validacao de tamanho A4;
- compactacao opcional de PDF;
- manifesto de geracao salvo junto aos arquivos finais.

Exemplo de manifesto:

```json
{
  "origem": "documentos_em_elaboracao/exemplo.html",
  "template": "abnt-monografia",
  "gerado_em": "2026-05-11T00:00:00",
  "formatos": ["html", "pdf", "png"]
}
```

Prioridade: alta para validacao e logs; media para lote e compactacao.

## Fase 7: Gestao de Documentos

Adicionar metadados e busca para transformar as pastas em uma pequena gestao documental.

Metadados sugeridos:

- titulo;
- tipo;
- interessado;
- tags;
- data de criacao;
- ultima modificacao;
- status: rascunho, revisado ou finalizado;
- template de origem.

Entregaveis:

- arquivo de metadados por documento;
- busca por nome e conteudo;
- filtros por tipo, status e template;
- lista de documentos recentes;
- opcao de arquivar documentos antigos.

Prioridade: media.

## Fase 8: Qualidade, Testes e Automacao

Profissionalizar a base de desenvolvimento.

Entregaveis:

- [x] criar `pyproject.toml`;
- [x] configurar `ruff` para lint e formatacao;
- [x] organizar testes atuais e adicionar testes unitarios leves;
- [x] adicionar testes unitarios para templates, paths e storage;
- [ ] adicionar testes de renderizacao com HTMLs pequenos;
- [x] configurar GitHub Actions para validacao automatica;
- [ ] revisar estrategia de dependencias com `requirements.in`, lock file ou `uv`.

Prioridade: alta.

## Fase 9: Recursos com IA

Adicionar IA como recurso opcional, com transparencia e controle do usuario.

Possibilidades:

- gerar minuta de requerimento a partir de dados informados;
- revisar linguagem formal;
- adaptar tom para texto juridico, administrativo ou academico;
- extrair dados de PDFs de apoio;
- sugerir fundamentacao com base em arquivos locais;
- resumir documentos finalizados;
- comparar versoes de documentos.

Cuidados:

- indicar claramente quando texto foi gerado ou revisado por IA;
- manter os arquivos locais como fonte principal;
- permitir revisao humana antes de salvar ou exportar;
- evitar substituir automaticamente conteudo juridico sensivel.

Prioridade: futura, depois da base de templates e storage estar madura.

## Fase 10: Empacotamento e Distribuicao

Preparar o sistema para uso mais amplo.

Entregaveis:

- AppImage ou pacote equivalente para Linux;
- instalador Windows;
- icone e identidade visual do app;
- versionamento interno;
- pasta de dados do usuario fora do codigo-fonte;
- backup automatico;
- migracoes de configuracao;
- documentacao de instalacao e recuperacao.

Prioridade: futura.

## Ordem Recomendada de Execucao

1. Modularizar o codigo sem mudar comportamento.
2. Criar catalogo de templates.
3. Adicionar escolha de template ao criar documento.
4. Implementar variaveis nos templates.
5. Melhorar editor e preview.
6. Criar metadados e busca.
7. Fortalecer testes e automacao.
8. Melhorar exportacao.
9. Adicionar IA opcional.
10. Empacotar como aplicativo distribuivel.

## Primeiro Marco Sugerido

O primeiro marco recomendado e implementar o catalogo de templates com selecao na criacao de documento.

Esse marco e pequeno o suficiente para ser feito com seguranca e ja muda a natureza do sistema: ele deixa de ser apenas um editor com modelos fixos e passa a ser um gerador de documentos baseado em templates.

Escopo do marco:

- [x] criar manifesto de templates;
- [x] carregar templates dinamicamente;
- [x] mostrar uma lista de modelos ao criar novo documento;
- [x] gerar o novo HTML a partir do modelo escolhido;
- [x] atualizar testes e README.
