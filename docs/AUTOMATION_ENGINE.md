# Sussurros Automation Engine

## Arquitectura

O portal existente usa Flask/Gunicorn, SQLAlchemy, PostgreSQL, Alembic e Docker. Já dispõe de agendamento editorial, trabalhadores de boletins, traduções, permissões por mandato, auditoria de conteúdo, notificações internas e um procedimento de restauro. A automação reutiliza estes modelos e mecanismos. A fila de automação é persistida na base de dados. O comando periódico do Coolify executa um trabalho num subprocesso separado do servidor web. Não são necessários Redis adicional, Celery, novos serviços pagos ou alterações ao Dockerfile, portas ou redes.

A pasta `automation/` contém catálogo, validação de configurações, modelos, cliente HTTP, cinco operadores, executor e rotas administrativas. A migração aditiva `20261127_23` cria quatro tabelas: `automation_operator`, `automation_run`, `automation_alert`, `automation_discovery`. Os cinco operadores começam desactivados.

## Operadores

| Operador | Verificações reais | Limites |
| --- | --- | --- |
| Qualidade editorial | Artigos, notícias PT/EN e revistas, campos, comprimentos de títulos e resumos, slugs, capas, ALT disponível, headings, ligações, títulos repetidos e sinais da auditoria editorial existente. Lotes por identificador com cursor persistente. | Comprimentos são recomendações; ligações externas e capas são verificadas sintacticamente. Referências internas reconhecidas são verificadas contra os conteúdos publicados. Existência e licenças de imagens externas, similitude semântica, originalidade e exactidão científica exigem revisão humana. |
| SEO e indexação | HTTP, title, meta description, canonical, noindex, robots.txt, sitemaps e ligações internas reconhecidas, em páginas públicas seleccionadas PT/EN. | Redireccionamentos são registados sem seguir destinos; não há crawler geral, nem verificação de indexação real no Search Console. |
| Infraestrutura e backups | Health check público, SELECT 1 na base de dados, ocupação do sistema de ficheiros acessível ao worker, falhas e fila de automação, relatório de restauro quando configurado. | Sem acesso ao host, logs externos ou configuração Coolify. O relatório existente de restauro não prova a data de criação do backup. Uma base indisponível impede gravar alertas nela; nesse caso o CLI devolve erro. |
| Investigação científica | Metadados Crossref, temas e período configuráveis, títulos, DOI, autores, datas quando fornecidas, ligação à fonte e deduplicação. | Amostra de até 10 resultados por tema, catálogo controlado de áreas/palavras-chave, sem IA obrigatória ou publicação automática. |
| Fluxo editorial | Prazos de tarefas e pareceres, submissões sem actualização e artigos a aguardar acção. | Relatórios por identificador; decisões e atribuições continuam no processo editorial existente. |

Só são feitas chamadas HTTPS ao domínio canónico do portal, em caminhos fixos seleccionáveis, e à API pública Crossref. Não há sondagem arbitrária de endereços, seguimento de redireccionamentos, credenciais em pedidos ou registo de respostas brutas. Há seis páginas mais três recursos por execução SEO e até quatro pedidos Crossref, timeout de 2–8 segundos por pedido, 512 KiB por resposta e 110 segundos para o subprocesso. A API está documentada na [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/).

## Painel, segurança e execução

O menu Automação, em `/admin/automacao`, dá acesso aos indicadores, cinco operadores, histórico paginado, configurações, detalhes e alertas. As permissões `automation.read` e `automation.manage` são explícitas e gerais, integradas no sistema de mandatos existente. Os administradores principais têm acesso. As contas históricas sem concessão explícita não recebem estas permissões. Toda a configuração, execução manual e resolução exige autenticação, permissão e proteção CSRF.

Seleccione um operador, configure as opções, intervalo (15–10080 min), retenção (7–365 dias) e notificações opcionais. O botão Executar enfileira a tarefa. Uma execução pendente ou em curso impede outra do mesmo operador (índice único parcial). A programação usa actualização condicional; trabalhos coincidentes não acumulam fila. Estados: queued, running, success, warning, failed, cancelled. A desactivação cancela trabalhos pendentes e deixa terminar a execução iniciada.

Os relatórios guardam até 200 observações com gravidade, referência, recomendação e indicação de truncagem. Alertas recorrentes são agregados e podem ser resolvidos manualmente; reaparecimento reabre o alerta. Quando configurado, os críticos e altos produzem notificações agrupadas no painel dos administradores principais, com intervalo mínimo de seis horas por alerta. Email, ntfy e webhook ficam para integração futura. A retenção remove apenas histórico de automação antigo, alertas resolvidos e identificadores bibliográficos expirados. Não são feitas alterações a artigos ou submissões nem operações sobre serviços, ficheiros de produção ou backups.

## Instalação e rollback

1. Construa a imagem do commit aprovado e ensaie numa base isolada. Faça backup recuperável antes da implantação.
2. Com o ambiente da nova imagem e o DATABASE_URL correcto, execute `python -m alembic upgrade head`. Confirme `20261127_23` com `python -m alembic current`. A migração é aditiva.
3. Configure uma tarefa periódica no Coolify (por exemplo, a cada minuto) no serviço da aplicação ou num worker da mesma imagem, sem privilégios adicionais. O comando termina após processar uma execução.
   ```sh
   BOOTSTRAP_ON_STARTUP=false SUSSURROS_AUTOMATION_WORKER=true python -m flask --app app automation-tick
   ```
4. Confirme `/healthz`, o painel e uma execução manual em ensaio. Active primeiro os operadores editoriais de leitura. Confirme a conectividade HTTPS para os operadores externos.
5. Opcionalmente, disponibilize `AUTOMATION_BACKUP_REPORT_PATH` como caminho de um relatório de `scripts/restore_drill.py --report` numa montagem apenas de leitura. O monitor verifica o estado declarado, data de restauro, formato da identificação da cópia e actualidade. Não lê o arquivo nem executa a recuperação.
6. Para desactivar, desligue os operadores no painel e retire a tarefa periódica. Para rollback, pare a tarefa, aguarde a execução activa ou a expiração do prazo e reinstale a imagem anterior. Conserve as tabelas; o downgrade destrutivo é recusado.

Não há segundo servidor, novo socket Docker ou segredo obrigatório. O cron necessita da base de dados e da mesma configuração da aplicação. Se o job ficar pendente, verifique a tarefa programada; se falhar, abra o histórico. O worker recupera execuções interrompidas ao expirar o prazo. Uma falha de base de dados devolve erro ao Coolify.

## Testes e extensibilidade

Executar `python -m unittest discover -s tests -p 'test_automation_engine.py' -v` e a suite prevista no repositório. As fixtures verificam os cinco operadores, fila, agendamento, timeout, retenção, permissões, destinos limitados, metadados e deduplicação. O Playwright verifica a interface em computador e telemóvel. Os testes de rede usam respostas simuladas; a disponibilidade real das integrações e backups exige ensaio no ambiente de implantação.

Para acrescentar um operador, registe código, versão e defaults em `automation/config.py`, a função de leitura em `automation/operators.py` e em OPERATORS. Inclua a validação de campos, uma migração aditiva e testes. O executor comum aplica prazo, histórico e alertas.

Próximas fases, por prioridade: confirmar a configuração real do Coolify e evidência de restauro, integrar notificações externas mediante autorização, avaliar uma integração Search Console e ampliar a validação editorial de ligações com destinos controlados.
