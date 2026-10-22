# Cabeçalhos Markdown dos artigos

## Diagnóstico

A fonte de verdade foi a branch `main` do repositório, no commit
`d4b80987b8e79564e958da382bebb57f73629c23`.

- O formulário editorial utiliza uma `textarea` Markdown (`bodyEditor`), não um editor HTML visual.
- `Article.title` e `Article.body` são campos distintos; `body` é `db.Text`.
  A gravação manual, o autosave e o histórico conservam o texto de origem.
- O servidor já utiliza Python-Markdown (`extra`, `sane_lists`) e Bleach.
  Os seis níveis de cabeçalho já eram reconhecidos no servidor.
- `admin-editor.js` mantinha uma aproximação independente por expressões regulares,
  limitada a H2/H3 e sem as regras completas de código e texto literal.
- `article-footnotes.js` já utilizava o endpoint autenticado de pré-visualização,
  mas apenas quando havia chamadas de notas.
- O template público já apresenta o campo de título como H1. Os H1 do corpo e
  das referências podiam criar outros H1.
- Não foi encontrado índice automático de secções nos artigos. Não foi criado um segundo índice.

## Alteração

A pré-visualização de todo o corpo passa pelo endpoint existente
`/admin/artigos/previsualizar`, com as mesmas permissões, CSRF, limite de tamanho,
limitação de pedidos e política `no-store`. Mantêm-se o debounce, cancelamento,
controlo de respostas antigas e tratamento de falhas. O estado da pré-visualização
identifica pedidos em curso e falhas sem alterar o conteúdo do editor.

O filtro `article_markdown` é uma configuração do processador existente, não
um segundo processador Markdown. Configura o reconhecimento de cabeçalhos
`#`–`######` seguidos de espaço. Blocos de código e texto literal continuam
sob controlo do analisador Markdown. O filtro genérico `markdown`, usado nas
restantes páginas e na revista científica, mantém o comportamento anterior.

Após a sanitização existente, o corpo apresenta H1 como H2, conservando H2–H6.
O título do formulário continua a ser o único H1 público. O texto de origem
não é reescrito, incluindo H1 existentes, HTML antigo e sintaxe Setext.
Não é efectuada uma reorganização automática dos outros níveis: a escolha
correcta da hierarquia continua a ser uma responsabilidade editorial.

A barra existente passa a oferecer H2–H6. Os botões actuam sobre as linhas
seleccionadas e substituem um prefixo de cabeçalho existente, em vez de o
acumular. A ajuda recomenda o uso de H2–H6 no corpo.

Cabeçalhos recebem identificadores determinísticos, com acentos normalizados
e sufixos para nomes repetidos. Exemplo: `## Introdução` → `sec-introducao`;
uma repetição → `sec-introducao-2`. As referências usam `ref-sec-` para evitar
colisões. Ligações como `[Introdução](#sec-introducao)` funcionam sem JavaScript.
Alterar o texto de um cabeçalho altera o identificador; mudar a ordem de títulos
iguais pode alterar o sufixo. Os identificadores das notas mantêm a sua lógica existente.

A pré-visualização mantém também os estilos responsivos dos vídeos e gráficos
ao receber as classes canónicas do servidor. A escala de cabeçalhos é partilhada pelo corpo e pela pré-visualização, com
cores herdadas da superfície, quebras de palavras longas e adaptação móvel.
Não se alteram título, slug, resumo, metadados ou dados estruturados.

## Ficheiros e responsabilidades

| Ficheiro | Alteração |
| --- | --- |
| `app.py` | Configuração de renderização específica dos artigos e registo do filtro. |
| `article_notes.py` | Configuração do processador de cabeçalhos existente, apenas no modo artigo. |
| `article_headings.py` | Política H1 do corpo e identificadores, após a sanitização. |
| `article_history.py` | Endpoint de pré-visualização chama o mesmo filtro usado na publicação. |
| `static/js/admin-editor.js` | Remove a aproximação de Markdown em JavaScript; acrescenta controlos H2–H6. |
| `static/js/article-footnotes.js` | Generaliza o pedido existente a todo o conteúdo. Mantém a inserção de notas. |
| `static/css/article-headings.css` | Escala partilhada e comportamento responsivo. |
| `templates/admin/article_form.html` | Controlos, instruções acessíveis, classes e versões dos recursos. |
| `templates/article.html` | Aplica a política ao corpo e às referências; mantém o H1 do título. |
| `tests/test_article_headings.py` | Conversão, código literal, segurança, âncoras, edição, autosave e publicação. |
| `tests/test_article_seo_maintenance.py` | Regista o novo filtro no ambiente Jinja mínimo do teste de SEO existente. |
| `tests/browser/article-backgrounds.spec.js` | Aguarda o conteúdo assíncrono antes de medir o contraste, mantendo o mínimo 4,5:1. |
| `tests/browser/headings_fixture.py` | Conteúdo sintético isolado para testes de navegador. |
| `tests/browser/headings.spec.js` | Teclas da barra, persistência, igualdade semântica, temas, larguras e respostas antigas. |
| `docs/ARTICLE_MARKDOWN_HEADINGS.md` | Diagnóstico, decisões e validação. |

## Validação

Os comandos de referência são:

```sh
python -m unittest discover -s tests -p 'test_article_headings.py' -v
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/consent.test.cjs
npm run build:css
npx playwright test tests/browser/headings.spec.js
```

As variáveis de ambiente e a base de dados devem ser exclusivamente de teste.
A suite Playwright utiliza o servidor de teste já configurado na CI do projecto.
A execução local do navegador requer Chromium instalado pelo Playwright.

Não há migração de PostgreSQL, alteração de Coolify, ligação ao VPS, actualização
de artigos da produção ou publicação em produção nesta alteração. Testes locais
com SQLite não substituem uma execução sobre PostgreSQL; a CI existente contém
verificações adicionais de PostgreSQL.
