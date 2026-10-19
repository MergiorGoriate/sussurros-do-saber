# Pesquisa científica e ligações DOI

A pesquisa pública existente passa a consultar também palavras-chave, DOI e ORCID do autor nos artigos de divulgação. O catálogo de revistas consulta título científico em português e inglês, resumos, palavras-chave, autores estruturados ou antigos, DOI e edição, além dos campos anteriores. Os registos não publicados continuam excluídos no servidor.

O catálogo mantém o filtro imediato dos cartões no navegador e acrescenta um formulário GET na mesma barra, utilizável sem JavaScript e com URL partilhável. Depois de uma pesquisa no servidor, o filtro imediato actua sobre os resultados recebidos; «Limpar pesquisa» volta ao catálogo completo. Não há nova barra ou mecanismo de indexação, nem paginação nova do catálogo. A paginação e o filtro por categoria dos artigos são preservados.

As pesquisas aceitam identificadores simples, URLs doi.org/orcid.org e prefixos DOI:/ORCID:. A correspondência é parcial e literal: % e _ são caracteres de pesquisa, não operadores SQL. Não existe ordenação nova por relevância ou garantia de desempenho para catálogos grandes; medir antes de adoptar índices ou pesquisa de texto integral.

As ligações DOI dos artigos de divulgação, do cabeçalho científico e da citação usam o mesmo normalizador. Este aceita a forma simples e URLs do resolvedor, evita prefixos duplicados e codifica o sufixo como caminho. Valores sem estrutura DOI continuam visíveis como texto, sem ligação. Nenhum identificador guardado é modificado. Uma ligação ao resolvedor não comprova registo ou resolução; não foram introduzidos depósitos Crossref, validação externa ou custos de serviços.

## Âmbito e reversão

Não há migrações, mudanças de permissões, estados editoriais, autenticação ou configuração de produção. A alteração está limitada à pesquisa pública, apresentação das ligações DOI e respectivos testes. A reversão pode ser feita revertendo o commit da alteração; não exige operações sobre os dados.

## Validação

`python -m unittest discover -s tests -p 'test_scientific_search.py' -v` verifica pesquisa por título, autor, coautor, DOI e ORCID, autores antigos, caracteres especiais, resultados vazios, filtros e paginação existentes, rascunhos privados, ligações normalizadas e valores inválidos. Os ensaios devem usar uma base isolada; importar a aplicação inicializa o esquema conforme a configuração existente.

O teste de navegador correspondente verifica o filtro dos cartões, a submissão GET, a pesquisa sem JavaScript e a ligação DOI em larguras móveis e de computador. A validação no deployment efectivo e a resolução externa de DOI continuam separadas dos testes locais.

Validação local em 19/10/2026: 293 testes Python passaram em SQLite, incluindo sete testes novos. Os três testes de navegador novos passaram: 320 px, 1440 px e JavaScript desactivado. Foi usado Chromium 153 do pacote @sparticuz/chromium, pois o download do navegador padrão do Playwright não produziu um arquivo válido neste ambiente. Os três cenários foram executados em processos separados devido ao encerramento do navegador alternativo entre contextos. Não foi executada localmente toda a suite de navegador nem um ensaio PostgreSQL; estes continuam a cargo da CI e da homologação.
