# Títulos e subtítulos dos artigos

## Diagnóstico

O editor é uma área de texto Markdown em `templates/admin/article_form.html`, com ferramentas em `static/js/admin-editor.js`. `Article.title`, `Article.body` e `Article.references`, em `models.py`, guardam separadamente o título, o corpo e as referências. A gravação manual em `admin.py`, a gravação automática e o histórico em `article_history.py` preservam o Markdown. Não foi necessária uma migração.

O filtro `markdown`, em `app.py`, já utilizava Python-Markdown com `extra` e `sane_lists`, notas em `article_notes.py`, directivas próprias e saneamento Bleach. Já conservava H1 a H6. Contudo, a pré-visualização local usava expressões regulares, reconhecia apenas H2/H3 e podia interpretar texto dentro de código de modo diferente da publicação. A pré-visualização autenticada existente só era chamada quando havia notas.

A página pública apresentava `Article.title` como H1, mas também permitia H1 no corpo e nas referências. Não havia índice automático na página de divulgação. A revista tinha um índice próprio em `templates/journal.html`, limitado a H2/H3.

## Comportamento corrigido

- O processador Markdown existente continua a reconhecer os seis níveis. Não foi acrescentado outro interpretador. No corpo e nas referências dos artigos, os marcadores ATX exigem espaço ou tabulação depois de um a seis `#`; marcadores sem esse separador e sete ou mais `#` são texto literal. As revistas e outros consumidores do filtro genérico conservam a interpretação anterior.
- O filtro `article_markdown` reutiliza esse processamento e o saneamento. Depois, `article_headings.py` apresenta H1 do corpo e das referências como H2 e acrescenta identificadores às secções. A fonte guardada não é reescrita. H2 a H6 conservam os seus níveis.
- O campo Título permanece o H1 principal da página pública. Títulos, endereços, metadados e dados estruturados mantêm a lógica existente.
- O corpo utiliza identificadores `sec-…`; as referências utilizam `ref-sec-…`. Textos repetidos recebem sufixos numéricos. Os identificadores são reproduzíveis enquanto se mantiverem o texto e a ordem dos cabeçalhos equivalentes; não são identificadores permanentes independentes das edições.
- A pré-visualização inicial é renderizada pelo servidor no formulário. As actualizações reutilizam a rota autenticada `/admin/artigos/previsualizar`, com atraso de 500 ms, cancelamento de pedidos antigos e protecção contra respostas atrasadas. Em caso de falha, apresenta texto literal e uma mensagem, conservando o conteúdo editável.
- A barra existente oferece H2 a H6. O selector substitui o marcador da linha seleccionada em vez de acrescentar marcadores sucessivos. O formulário recomenda H2 a H6 e explica a apresentação dos H1 do corpo como H2.
- `article-headings.css` fornece a hierarquia partilhada, incluindo a mesma família, tamanho, peso e altura de linha na pré-visualização e na página pública a 320, 390, 768 e 1440 píxeis. A pré-visualização carrega os estilos existentes de conteúdo para conservar tabelas, vídeos e gráficos renderizados pelo servidor.
- O índice da revista inclui H2 a H6 e conserva os seus identificadores e ligações existentes. Não foi criado um segundo índice.

O saneamento continua anterior à decoração dos cabeçalhos. A geração de identificadores não autoriza atributos arbitrários fornecidos pelo conteúdo. Notas e directivas continuam a utilizar a implementação existente. O processamento só actua sobre elementos de cabeçalho resultantes da análise, não sobre os símbolos `#` dentro de texto literal ou código.

## Ficheiros e finalidade

| Ficheiro | Alteração |
| --- | --- |
| `app.py`, `article_headings.py` | Apresentação dos cabeçalhos dos artigos após o processamento existente. |
| `article_history.py` | Mesma apresentação na rota de pré-visualização, conservando permissões, CSRF e limites. |
| `templates/article.html` | Aplicação ao corpo e às referências; título principal preservado. |
| `templates/admin/article_form.html` | Selector H2–H6, instruções e pré-visualização inicial no servidor. |
| `static/js/admin-editor.js` | Ferramenta de subtítulos e remoção do interpretador local do corpo; ferramentas restantes mantidas. |
| `static/js/article-footnotes.js` | Actualização de toda a pré-visualização pela rota existente. |
| `static/css/article-headings.css` | Hierarquia, ancoragem, cores herdadas e selector responsivo. |
| `templates/journal.html` | Extensão do índice existente aos níveis mais profundos. |
| `static/css/tailwind.css` | Reconstrução com o comando existente do projecto. |
| `tests/test_article_headings.py` | Conversão, segurança, compatibilidade, identificadores, gravação, histórico e correspondência entre rotas. |
| `tests/browser/headings.spec.js`, `tests/browser/headings_fixture.py` | Interacção, persistência, temas, dimensões, falhas de rede, respostas antigas e índice. |
| `tests/test_article_seo_maintenance.py` | Registo do filtro novo no ambiente Jinja mínimo usado pelo teste de metadados. |
| `.github/workflows/ci.yml` | Inclusão dos testes de cabeçalhos na validação PostgreSQL já existente. |

## Validação

Comandos do projecto:

```sh
python -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/consent.test.cjs
npm run build:css
npx playwright test headings.spec.js footnotes.spec.js dropcap.spec.js editors.spec.js autosave.spec.js article-backgrounds.spec.js article-covers.spec.js
git diff --check
```

Os testes utilizam registos sintéticos. A suite Python foi executada em SQLite; a CI mantém a validação PostgreSQL e passa também a executar os testes novos nessa base de dados. Não houve acesso ou alteração aos dados de produção, ao VPS ou ao Coolify. O resultado detalhado da execução acompanha o Pull Request; a inclusão de um teste na CI não significa que esse teste já tenha passado no PostgreSQL.

Resultados locais de 22 de Outubro de 2026:

- Suite completa Python: 411 testes aprovados, em 201,920 segundos. Depois do ajuste final aos identificadores de acessibilidade das notas, 54 testes específicos foram repetidos e aprovados.
- Navegador: 31 dos 33 cenários de regressão passaram na primeira execução alargada. Os dois restantes foram resolvidos com a pré-visualização inicial no servidor e a configuração sintética Cloudinary usada pela CI. A execução final de nove cenários, incluindo esses dois casos, títulos e notas, passou integralmente. Assim, os 33 cenários seleccionados tiveram resultado aprovado; não se apresenta a primeira execução como integralmente aprovada.
- Seis testes JavaScript de consentimento aprovados; reconstrução de CSS, verificações de sintaxe JavaScript, compilação dos módulos novos e `git diff --check` concluídos sem erros.
- Capturas do editor e do artigo inspeccionadas em modo escuro a 320 e 1440 píxeis; os testes também cobrem os temas claro/escuro e a largura do selector. Os testes de editores existentes verificam 320, 390, 768 e 1440 píxeis.

O Chromium disponível para a execução local difere do descarregado pelo Playwright da CI. As verificações locais de navegador devem ser confirmadas pela CI com as versões do projecto. A falha da rede não impede editar ou guardar: apenas a actualização da pré-visualização passa a texto literal.

## Limites e compatibilidade

A aplicação apresenta H1 do corpo como H2, mas não tenta corrigir automaticamente saltos entre H2 e H5 escritos pelo autor. A organização editorial dos níveis continua a exigir revisão do conteúdo. O tratamento específico dos artigos não modifica a extracção do título das revistas. Não foram alterados os modelos de dados, as regras de publicação, as permissões, o autosave, a recuperação de versões, as dependências ou a configuração de produção.


## Verificação complementar da implementação consolidada

Os ajustes complementares foram integrados sobre o commit `7688436` do mesmo Pull Request, preservando a pré-visualização inicial no servidor, as regras de H1 e o índice das revistas. Não foi criada outra implementação em paralelo no repositório remoto.

- `app.py` e `article_notes.py`: a exigência de separador nos marcadores ATX é uma opção do processador já existente, activada apenas na apresentação dos artigos.
- `static/css/article-headings.css`: a pré-visualização utiliza a tipografia efectiva da página pública, incluindo as regras responsivas carregadas posteriormente pelo sítio.
- `tests/test_article_heading_contract.py`: limites dos marcadores, seis níveis, código literal e conservação do comportamento genérico.
- `tests/browser/heading-parity.spec.js` e `tests/browser/heading_parity_fixture.py`: igualdade de elementos, identificadores, fontes, tamanhos, pesos e alturas de linha; gravação; falhas; respostas fora de ordem; vídeo externo no editor.
- `tests/browser/article-backgrounds.spec.js` e `tests/browser/article-covers.spec.js`: aguardar o redireccionamento após guardar antes de reabrir o formulário. Na comparação das cores dos fundos, as transições são desactivadas exclusivamente no navegador de teste para medir estados finais.
- `.github/workflows/ci.yml`: o teste complementar de marcadores também integra o job PostgreSQL existente. Esta inclusão não constitui, por si só, prova de aprovação nesse ambiente.

Resultados da verificação complementar em 22 de Outubro de 2026:

- Suite completa: 414 testes Python executados, zero falhas, zero erros e zero testes ignorados. O resumo foi também gravado directamente a partir do resultado do runner `unittest`.
- Navegador: 41 cenários seleccionados. Na execução alargada, 33 passaram; quatro exigiram sincronização das asserções/gravações e quatro dos editores exigiram a indicação do executável local porque a configuração do próprio teste substitui as opções de lançamento. Os quatro primeiros passaram numa nova execução; os quatro dos editores passaram com uma cópia temporária que altera apenas o caminho/argumentos de lançamento do navegador. Assim, os 41 cenários foram verificados com resultado aprovado, sem apresentar a execução alargada inicial como integralmente aprovada.
- Seis testes JavaScript de consentimento aprovados. Reconstrução Tailwind, sintaxe Python/JavaScript e `git diff --check` concluídos.
- As novas comparações de tipografia passaram a 320, 390, 768 e 1440 píxeis, em ambos os temas. A pré-visualização externa de vídeo e a recuperação após falha de ligação também passaram.

Esta verificação complementar utilizou Playwright 1.64.1 e Chromium Headless Shell 134.0.6998.35, por disponibilidade local. A CI deve confirmar a branch actualizada com o navegador fixado pelo projecto e com PostgreSQL. Não se executou nem se publicou a aplicação no ambiente de produção.


## Resolução dos conflitos com o PR #259

A integração conserva os identificadores `sec-` e `ref-sec-`, o filtro e os botões H2–H6 já presentes em `main`. O selector deste PR partilha a mesma transformação de linhas com esses botões. Os testes dos dois ramos são conservados em ficheiros distintos e usam fixtures independentes. A falha da pré-visualização apresenta o texto literal com `textContent`, sem interpretar HTML. A sintaxe dos artigos aceita espaço ou tabulação depois dos marcadores. Os estilos de paridade são acrescentados aos estilos existentes de vídeos, gráficos, tabelas e listas.

Validação da resolução, em 22 de Outubro de 2026:

- 434 testes Python aprovados na execução completa final, com SQLite. A primeira execução identificou assets em falta na cópia local e uma asserção que comparava classes do contentor em vez do HTML renderizado; a cópia foi completada com hashes verificados e a asserção passou a comparar o conteúdo interno, preservando as classes públicas existentes.
- Seis testes JavaScript aprovados; Tailwind recompilado, sintaxe JavaScript e `git diff --check` verificados.
- 44 cenários de navegador seleccionados: 42 passaram na execução alargada. Dois revelaram que carregar os estilos de conteúdo no editor introduzia uma largura mínima nos gráficos; foi aplicada uma correcção restrita ao SVG da pré-visualização. Os dois casos e o terceiro teste do mesmo ficheiro passaram na repetição final. Não se apresenta a execução inicial como integralmente aprovada.
- Os testes de ambos os ramos permanecem: `tests/test_article_heading_parity.py` e `tests/browser/heading-persistence.spec.js` conservam os testes que colidiam com nomes já presentes em `main`, com a fixture independente `heading_persistence_fixture.py`. Os identificadores esperados seguem `sec-` e `ref-sec-`, já existentes em `main`.
- Ambiente local: Playwright 1.64.1 com Chromium Headless Shell 134, em configuração temporária externa ao repositório; a configuração de navegador da CI não foi alterada. PostgreSQL será validado pela CI. Sem acesso ou alteração aos dados de produção.
