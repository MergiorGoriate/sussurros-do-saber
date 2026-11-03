# SEO bilingue e consultas de tradução

A revisão do código partiu da main `efaed66c435ea2f6544e1a3afba42d8b064799db`.

## Problemas corrigidos

As listas paginadas apontavam para `/artigos` ou `/en/artigos` como canonical, mesmo na segunda página. A regra de robots no HTML bloqueava qualquer parâmetro; a regra HTTP abrangia apenas o caminho português. Agora, `page=2` tem canonical próprio, referências entre idiomas com a mesma página e indicação do número no título. `page=1`, parâmetros vazios e parâmetros de acompanhamento não criam novos endereços canónicos. Pesquisa e categorias mantêm `noindex,follow`, tanto no HTML como no cabeçalho HTTP, em ambos os idiomas. O URL de Open Graph acompanha o canonical da listagem.

O catálogo enviado a todas as páginas inglesas não incluía oito etiquetas. A preparação desse catálogo accionava a protecção `noindex` mesmo quando a página apresentada estava traduzida. Foram acrescentadas as oito traduções. Outra falha ocorria quando uma categoria traduzida voltava a passar por `ui()`: a tradução inglesa era interpretada como texto sem tradução. A função reconhece agora os valores ingleses dos catálogos publicados; textos realmente desconhecidos continuam a activar a protecção.

Com `I18N_ENABLED=false`, o HTML e o sitemap deixam de anunciar versões inglesas desactivadas.

## Desempenho

As consultas de uma mesma tradução publicada são reutilizadas durante o pedido, incluindo resultados sem tradução. O cache reinicia em cada pedido. Os cartões de listas, destaques e sugestões deixam de recarregar e calcular o hash integral da origem apenas para um aviso de desactualização que não apresentam. As páginas individuais conservam a verificação e o aviso. O conteúdo original e o processo de aprovação/publicação não foram alterados; não há cache partilhado de páginas com sessão ou tokens CSRF.

## Validação

Passaram 52 testes locais: nove regressões em `test_bilingual_seo.py`, 37 testes de internacionalização e seis testes existentes da plataforma relativos a descoberta, robots, sitemap, dados estruturados, cache e paginação. `git diff --check` não encontrou problemas. Foram usados dados sintéticos em SQLite. As dependências instaladas localmente incluem ReportLab 4.4.9 e pypdf 6.10.0, diferentes das versões declaradas no projecto; não foram alteradas dependências nem funcionalidades PDF.

Não foi executada a totalidade da suite, nem uma medição Lighthouse, PageSpeed ou Core Web Vitals em produção. A revisão não comprova indexação, posição nos resultados, melhoria de tempos reais nem a versão actualmente implantada. Estes resultados exigem verificações após deploy e, para dados de pesquisa, acesso à Search Console.

## Publicação e conferência

Não há migração de base de dados nem novas variáveis de ambiente. Após integrar a proposta e publicar a imagem no Coolify, conferir `/healthz`, `/artigos?page=2`, `/en/artigos?page=2`, uma pesquisa em cada idioma, um artigo inglês publicado e `/sitemap.xml`. Confirmar canonical e hreflang com a página correcta, ausência de `noindex` nas páginas inglesas completas e manutenção de `noindex` nas pesquisas. Confirmar também que um artigo sem tradução aprovada continua sem versão inglesa pública.
