# Métricas Científicas — implementação e operação

Relatório técnico de 23/10/2026. Extensão da revista científica sobre o código de `main` em `3573d761b09c65ac191b45839ebb370dcac0278f`. A activação em produção requer revisão, migração e configuração operacional. Não foram alterados conteúdos de produção.

## Auditoria e preservação

A aplicação utiliza Flask, SQLAlchemy, Alembic, Jinja, Tailwind/CSS e JavaScript, com unittest e Playwright. Já existiam autenticação administrativa, 2FA, permissões e âmbito editorial por revista, páginas públicas, geração/cache de PDF, autores/ORCID, DOI, edições em texto e exportação CSV com protecção contra fórmulas.

`Article` representa o portal; não participa nestas métricas. O modelo existente `Journal` reúne apresentação da revista e publicação científica. Consideram-se artigos científicos os registos `Journal` publicados com `content_markdown` não vazio. As apresentações sem corpo científico e os rascunhos ficam excluídos. O título da revista e `current_issue` são usados nos filtros existentes; não foi criado um sistema editorial ou uma entidade de edição paralelos.

Foram preservados os modelos editoriais, conteúdos, autenticação, leitores, rotas, cabeçalho, rodapé, permissões, submissões, leitura, citação e cache de geração de PDF. As alterações partilhadas limitam-se aos pontos de integração e a uma entrada no menu administrativo. Premium e pagamentos não foram modificados. Artigos e métricas públicas continuam gratuitos.

## Funcionalidades entregues

- Contabilização interna separada de visualizações e pedidos de PDF, com deduplicação atómica entre processos, filtros de tráfego e respeito por DNT/GPC.
- Botão «Ver métricas», secção expansível e página pública por artigo. A leitura continua disponível se a consulta ou escrita de métricas falhar.
- Estatísticas no catálogo de revistas, com selecção de edição, e página pública agregada.
- Painel «Métricas Científicas»: cartões, gráficos locais interactivos, distribuição geográfica condicionada à cobertura, rankings, tabela paginada de 50 linhas e CSV.
- Filtros por período (7/30/90/365 dias ou até 366 dias personalizados), ano de publicação, revista, edição, artigo, autor/ORCID e fonte de citações.
- Adaptadores servidor para Crossref, OpenAlex, OpenCitations e Altmetric; actualização por CLI, fora dos pedidos dos leitores.
- Correspondência bibliográfica assistida via Crossref: até três candidatos; um editor confirma o DOI no editor já existente. Não há atribuição automática de DOI ou de citações por semelhança de título.
- Modos claro/escuro, apresentação responsiva, tabelas alternativas aos gráficos, foco de teclado, selecção de pontos com setas/Home/End e mensagens de erro/ausência de dados.

## Rotas e permissões

| Rota GET | Acesso e função |
| --- | --- |
| `/admin/revistas/metricas` | Sessão administrativa válida e `journal.manage`, `journal.publish` ou `manuscript.production`; apenas registos autorizados por `journal_scope` |
| `/admin/revistas/metricas/exportar.csv` | Mesmas verificações e filtros; limite de 10 pedidos/minuto |
| `/revistas/<slug>/metricas` | Gratuito, sem autenticação; apenas artigo científico publicado |
| `/metricas-cientificas` | Agregados públicos de artigos científicos publicados |
| `/revistas` | Estatísticas resumidas dos últimos 30 dias e filtro `edicao` |

Painéis limitados a 60 pedidos/minuto pelo mecanismo Flask-Limiter existente. As rotas de métricas usam `private, no-store`; dados administrativos conservam as protecções de resposta existentes. Filtros são validados no servidor. CSV usa BOM UTF-8, escapa células susceptíveis de fórmulas e respeita o âmbito editorial. Não existe endpoint público para incrementar directamente um número.

## Critérios de recolha e privacidade

Uma unidade por artigo, tipo de evento, endereço de rede e dia UTC. O endereço só é utilizado em memória para HMAC-SHA256 diário; não são persistidos IP, user-agent, cookie, conta ou identificador de leitor. O recibo único e o incremento agregado são confirmados na mesma transacção, usando upsert de SQLite/PostgreSQL. Alterar apenas o user-agent não gera uma nova unidade.

Só contam GET com resposta 200: HTML de leitura (destino de navegação compatível) e PDF com MIME correcto. HEAD, respostas parciais 206, 304, erros, pré-visualizações administrativas, pré-carregamentos, robots identificáveis, user-agent vazio, DNT=1 e Sec-GPC=1 ficam excluídos. Os pedidos de métricas não contam como leituras.

O evento PDF significa pedido HTTP completo servido, não conclusão da transferência, leitura efectiva ou leitor único. Redes NAT partilhadas podem ser subcontadas. Bots sofisticados e redes distribuídas podem ultrapassar filtros; não se afirma certificação COUNTER ou resistência absoluta à fraude.

Os recibos com dia anterior a hoje menos dois dias são removidos durante a recolha de um novo evento e pela CLI. Executar a CLI diariamente para manter retenção aproximada de 48–72 horas mesmo sem tráfego. Os agregados diários não contêm identificadores individuais e são conservados para séries históricas. A gestão de logs do servidor/proxy é independente e deve seguir a política de privacidade da plataforma.

### Proxy e geografia

Por omissão usa-se o peer real do transporte, ignorando `X-Forwarded-For` para deduplicação, mesmo com ProxyFix. Em produção atrás de proxy, configurar `SCIENTIFIC_METRICS_TRUSTED_PROXIES` com os CIDR estritamente necessários e confirmar a cadeia de confiança existente. Nunca usar `0.0.0.0/0` como solução de conveniência. Uma configuração incompleta pode agrupar todos os leitores no endereço do proxy.

A geografia só lê `environ['sussurros.country_code']`, preenchido por middleware controlado no servidor com código ISO de duas letras. Cabeçalhos HTTP enviados pelo visitante, incluindo `CF-IPCountry`, não são aceites directamente. Não foi instalado um serviço GeoIP nem transmitidos IP a fornecedores externos. Sem middleware há país `ZZ` e a interface informa indisponibilidade. Só são divulgados grupos por país com pelo menos cinco visualizações no período. Esta supressão básica reduz exposição; não equivale a anonimização diferencial nem impede toda a inferência por comparação de filtros.

## Base de dados

Migração aditiva `20261023_13`, após `20261023_12`:

| Tabela | Conteúdo |
| --- | --- |
| `scientific_metric_day` | Chave artigo/dia/país; visualizações e downloads agregados |
| `scientific_metric_receipt` | Digest único e dia, para deduplicação temporária |
| `scientific_metric_start` | Início da cobertura interna por publicação |
| `scientific_metric_source` | DOI, fornecedor, estado, contagens opcionais, pontuação, consulta/medição e próxima tentativa; único por artigo/fornecedor |
| `scientific_metric_provider` | Lease entre trabalhadores e espera global por fornecedor |

A instalação inicial regista a data de início para os registos existentes; não inventa eventos anteriores. Novos artigos recebem cobertura no primeiro evento elegível. Os três vínculos a `Journal` usam `ON DELETE CASCADE`, para não impedir eliminações já permitidas pelo sistema editorial. A migração não altera artigos, autores, conteúdos ou relações editoriais. É idempotente e suporta os esquemas históricos parciais usados pelos testes. O downgrade destrutivo é recusado para preservar métricas; regressar ao código anterior não exige apagar estas tabelas.

```bash
python -m alembic upgrade head
```

Usar a configuração e cópia de segurança habituais da plataforma antes da migração. O caminho de desenvolvimento com actualização automática de esquema também regista as tabelas; produção deve utilizar Alembic.

## Fontes, significado e actualização

| Fonte | Indicador implementado | Configuração |
| --- | --- | --- |
| Crossref | `is-referenced-by-count`, DOI devolvido verificado | `CROSSREF_MAILTO` recomendado |
| OpenAlex | `cited_by_count`, DOI devolvido verificado | `OPENALEX_API_KEY` quando exigida pela quota/conta |
| OpenCitations Index v2 | `citation-count/doi:…`, campo `count` | `OPENCITATIONS_TOKEN` se aplicável |
| Altmetric Details Page API v1 | `cited_by_posts_count` e `score` não arredondado; não são citações científicas | Chave e aprovações de licença abaixo |

Uma só fonte de citações é seleccionada por relatório. Contagens de diferentes bases nunca são somadas. No agregado, DOI normalizado repetido conta apenas uma vez para citações/menções. Visualizações, downloads, citações, posts e pontuação de atenção são indicadores distintos. A pontuação Altmetric não é apresentada como medida de qualidade científica.

Ausência, erro, DOI inválido, divergência de DOI, limite de API ou campo malformado produzem estados explícitos e «Dados indisponíveis», não um zero artificial. Zero só é exibido quando conhecido. As datas são da consulta e da última medição válida efectuada pela plataforma, não uma garantia da actualidade da base externa.

Resultados válidos têm idade máxima de sete dias para integração nos totais. Em falha posterior mantém-se o último resultado para proveniência, excluído dos totais actuais. As citações/menções são snapshots mais recentes, não as citações ocorridas dentro do intervalo de acessos seleccionado. O histórico apresentado em gráfico é de visualizações e downloads; não existe ainda série temporal histórica de citações ou menções.

O DOI é normalizado e validado. A validação conservadora rejeita identificadores com caracteres de query/fragmento; casos raros requerem revisão futura. Pedidos externos usam hosts fixos, sem redireccionamentos, timeout de ligação/leitura, limite de resposta de 1 MiB e limite de processamento. Chaves e respostas brutas não são devolvidas ao cliente nem persistidas nos registos de métricas.

```bash
python -m flask --app app metricas-cientificas-actualizar --limit 50
python -m flask --app app metricas-cientificas-actualizar --source crossref --source openalex --limit 50
python -m flask --app app metricas-cientificas-corresponder --artigo 123
```

Configurar no agendador do alojamento, por exemplo uma execução horária com o ambiente e directório da aplicação. O agendador não foi instalado nesta entrega. A CLI actualiza no máximo uma vez por 24 horas por artigo/fornecedor e aguarda um segundo entre pedidos. O limite é por fornecedor/execução; ejecuções subsequentes avançam para registos pendentes. Leases persistentes impedem execuções sobrepostas por fornecedor. Em 429 interrompe-se esse fornecedor e aplica-se espera persistente, respeitando `Retry-After` numérico; se ausente ou em formato não numérico, espera-se 24 horas. Não há chamadas externas durante leitura, download ou consulta de métricas.

### Altmetric: bloqueado sem autorização

É necessário definir `ALTMETRIC_API_KEY` e `ALTMETRIC_LICENSE_APPROVED=true` para recolher. A fonte não é incluída na execução por omissão; seleccioná-la explicitamente com `--source altmetric`. A apresentação pública exige também `ALTMETRIC_PUBLIC_DISPLAY_APPROVED=true`; a exportação exige `ALTMETRIC_EXPORT_APPROVED=true`. Estas opções registam a decisão operacional, não substituem contrato, licença ou obrigações de atribuição. Confirmar termos e apresentação exigida antes de activar. Não basta possuir uma chave para presumir autorização de publicação/exportação.

### Documentação primária consultada

- [Crossref Cited-by](https://www.crossref.org/documentation/cited-by/)
- [OpenAlex API](https://help.openalex.org/api/)
- [OpenCitations Index v2](https://api.opencitations.net/index/v2)
- [Altmetric: início e autenticação](https://docs.altmetric.com/details-page-api/getting-started/)
- [Altmetric: campos e respostas](https://docs.altmetric.com/details-page-api/endpoints/counts/)
- [Altmetric: licenciamento](https://docs.altmetric.com/details-page-api/licensing/)

## Inventário de ficheiros

Criados:

- `scientific_metrics.py`: relatórios, rotas, autorização e comandos CLI.
- `scientific_metrics_models.py`, `scientific_metrics_schema.py` e `migrations/versions/20261023_13_scientific_metrics.py`: persistência e migração.
- `scientific_metrics_collection.py`: recolha e deduplicação.
- `scientific_metrics_sources.py`: adaptadores e candidatos bibliográficos.
- `templates/metrics/panel.html`, `filters.html`, `unavailable.html`: componentes e erro recuperável.
- `templates/scientific_metrics.html`, `templates/admin/scientific_metrics.html`: páginas pública e administrativa.
- `static/css/scientific-metrics.css`, `static/js/scientific-metrics.js`: apresentação e gráficos sem dependências externas.
- `tests/test_scientific_metrics.py`, `tests/test_scientific_metrics_migration.py`, `tests/test_scientific_metrics_postgres.py`: testes funcionais/migração.
- `tests/browser/scientific_metrics_fixture.py`, `tests/browser/scientific-metrics.spec.js`: dados sintéticos isolados e testes em navegador.
- `docs/SCIENTIFIC_METRICS.md`: este relatório.

Modificados: `app.py`, `.github/workflows/ci.yml`, `migrations/env.py`, `templates/journal.html`, `templates/journals.html`, `templates/admin/base.html`, `tests/test_migrations.py`, `tests/test_premium.py`, `tests/test_billing_migration.py` e `README.md`. Os três testes antigos só actualizam a revisão Alembic esperada. Não foram acrescentadas dependências de produção.

## Validação e problemas resolvidos

Resultados locais executados:

| Execução | Resultado |
| --- | --- |
| `python -m unittest discover -s tests -p 'test_*.py'` | 564 testes descobertos: 563 aprovados e 1 omitido por exigir PostgreSQL isolado; 126,253 s |
| `PYTHONPATH=tests python -m unittest test_scientific_metrics test_scientific_metrics_migration` | 28 aprovados; inclui migração e conflitos de chaves estrangeiras em SQLite |
| Testes específicos de métricas em Chromium | 6 aprovados, incluindo PDF real, filtros, 320/768/1440 px e uso sem JavaScript |
| `node --test tests/consent.test.cjs` | 6 aprovados |
| CMP em Chromium, serviços Google simulados e opção activada | 4 aprovados |
| Compilação dos cinco módulos Python e `node --check` do JavaScript | Sem erros |

A regressão alargada em navegador e o teste PostgreSQL do CI são registados após conclusão. A execução local de Chromium utilizou o binário headless `@sparticuz/chromium` num ambiente temporário, sem acrescentar dependências ao projecto. Foram inspeccionadas capturas dos painéis público e administrativo; dados das capturas são sintéticos. As integrações externas são testadas com respostas simuladas identificadas, sem publicar dados de teste ou pedir credenciais reais. As fixtures em navegador exigem SQLite isolado e recusam ambiente de produção.

Cobertura específica: deduplicação e viragem do dia; distinção HTML/PDF; status HTTP; robots, prefetch, DNT/GPC; falsificação de proxy/país; confiança explícita no proxy; artigos do portal, apresentações e rascunhos excluídos; indisponibilidade da base; períodos, edição/autor/ano/artigo; agregações; DOI duplicado; valores desconhecidos/zero; antiguidade; fontes separadas; licenças; autenticação, âmbito e revogação; CSV; 429/erros/limites de fornecedor; correspondência assistida; migração preservando conteúdos; eliminação editorial com chaves estrangeiras.

Problemas encontrados e corrigidos durante a validação: restrição de chave estrangeira que impediria eliminações permitidas; compatibilidade da migração com esquemas históricos parciais; texto sem dados a quebrar de forma pouco legível nos cartões; selectores dos testes em navegador ajustados aos papéis acessíveis efectivos.

## Activação e limitações conhecidas

Antes de activar: rever/aplicar a migração, confirmar permissões e âmbito editorial, definir segredo HMAC estável (`SCIENTIFIC_METRICS_HMAC_KEY`, ou o `SECRET_KEY` existente), validar proxies, instalar o agendamento e monitorizar estados/quotas. Confirmar a elegibilidade científica dos registos existentes e os DOI. A recolha geográfica exige middleware de confiança adicional. Segredos ficam no ambiente do servidor, nunca no código do cliente.

As APIs reais não foram certificadas em produção; são necessários configuração, contas/quotas aplicáveis e validação com DOI reais. Altmetric depende de licença, chave e autorizações de utilização. Não foram executados testes de carga, auditoria independente de acessibilidade ou testes em Firefox/Safari/dispositivos físicos. Os ensaios responsivos em Chromium não equivalem a certificação entre navegadores.

Para grande volume, mover agregações do relatório para SQL/materializações e exportação para streaming/tarefa assíncrona: actualmente a tabela visível é paginada, mas o relatório agrega os registos seleccionados em memória. Recolha faz transacção curta e não consulta APIs externas. Avaliar retenção e capacidade a partir de tráfego real; não foram inventados benchmarks.

Recomendação: activar primeiro as métricas internas e confirmar qualidade da classificação e da recolha. Depois validar cobertura DOI por fornecedor e activar a actualização agendada. Só disponibilizar indicadores altmétricos após licença e comunicação clara dos limites. Um futuro programa de parcerias universitárias pode apoiar a normalização de DOI/ORCID e a revisão da qualidade dos indicadores, sem condicionar o acesso aberto.
