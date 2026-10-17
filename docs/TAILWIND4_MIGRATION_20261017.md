# Compilação CSS e ícones locais

## Migração do PR #182

O aumento isolado de Tailwind 3.4.19 para 4.3.3 retirava a CLI usada pelo
comando `npm run build:css`. A falha `tailwindcss: not found` foi reproduzida
numa instalação separada antes da migração.

O projecto usa agora `tailwindcss` e `@tailwindcss/cli` 4.3.3. A configuração
de cores, fontes e modo escuro está em `static/css/tailwind.input.css`, com
fontes de classes explícitas em `templates` e `static/js`. O comando de build
e o estágio de assets do Docker deixam de depender de `tailwind.config.js`.
Foram adaptadas as classes identificadas pelo migrador oficial, preservados
os valores anteriores de bordas, placeholders, cursores e centragem de diálogos,
e recompilado `static/css/tailwind.css`.

A CLI exige temporariamente o override de `@parcel/watcher` para 2.6.0.
Essa versão remove a cadeia micromatch/braces vulnerável incluída em 2.5.1.
Não há supressões de avisos na auditoria: `npm audit --audit-level=high`,
incluindo as ferramentas de desenvolvimento, passou sem vulnerabilidades.

O [guia oficial](https://tailwindcss.com/docs/upgrade-guide) descreve a mudança
da CLI, directivas e requisitos mínimos: Safari 16.4, Chrome 111 e Firefox 128.
Navegadores anteriores não estão cobertos por esta migração.

## Ícones sem dependência da fonte externa

Os testes reproduziram links ORCID e partilhas sem área clicável quando a fonte
de ícones não carregava. O ORCID usa o indicador local já definido no CSS;
Bluesky e Reddit usam SVGs inline; a seta da conta usa SVG local dentro de um
elemento HTML que continua a respeitar a propriedade `hidden`.

Os testes de autores, partilhas e conta Google bloqueiam explicitamente a
fonte externa para verificar estes controlos. A autenticação Google nesses
testes usa respostas simuladas, não uma conta real.

Os SVGs das marcas foram obtidos de Font Awesome Free. A licença e atribuição
estão em `static/licenses/fontawesome-free-icons.txt`; não foi adicionada uma
dependência de ícones ao pacote de produção.

## Limites da verificação

Os ensaios locais usam Python 3.12, SQLite isolado e Playwright 1.64.0 com
Chromium 153.0.8010.0 obtido do pacote `@sparticuz/chromium` 153.0.0. O download
do Chromium 156 que acompanha esta versão do Playwright devolveu um ZIP inválido.
A configuração de lançamento alternativa é apenas local; a CI continua a
instalar o navegador normal do Playwright.

O build Docker completo e os ensaios PostgreSQL não foram executados localmente.
O GitHub Actions falha antes de executar etapas e atribuir runners; não foram
desactivadas verificações para ocultar esse bloqueio. Consultar também o registo
de resolução dos PRs para os resultados finais das suites.
