# Publicação programada no editor de artigos

## Utilização

No editor existente, o administrador principal pode escolher **Programado** no campo Estado, indicar a data e hora e guardar o artigo. O fuso horário apresentado por defeito é **Moçambique (UTC+02:00)**; também pode seleccionar UTC. Ao mudar de fuso no navegador, a hora é convertida para preservar o mesmo instante.

O artigo permanece privado até à hora marcada. Para alterar a programação, edite a data e volte a guardar. Para cancelar, seleccione **Rascunho** e guarde; a data e a aprovação pendente são limpas. Para publicar imediatamente, continua disponível o estado **Publicado**.

Só o administrador principal pode tomar esta decisão directa pelo editor, à semelhança da publicação imediata já existente. As outras contas mantêm a revisão, aprovação e programação através do fluxo editorial autorizado. Enviar manualmente um estado não permitido não contorna essas verificações.

As datas passadas, ausentes ou inválidas são rejeitadas antes de guardar ou carregar ficheiros. Texto incompleto continua sujeito à validação editorial existente. O formulário conserva os valores submetidos quando há erros. Funciona sem JavaScript; as verificações finais são sempre feitas no servidor.

## Arquitectura preservada

Reutilizados `Article.scheduled_at`, estado `scheduled`, `ArticleWorkflow`, auditoria, notificações, histórico e `Article.publish_due_scheduled()`. Não há migração de dados nem alteração às rotas. As datas são guardadas como UTC sem fuso, conforme o contrato anterior; pedidos antigos sem `schedule_timezone` continuam a ser interpretados em UTC. Ao reabrir o editor, a data aparece convertida para Moçambique.

A decisão do administrador principal cria/actualiza o fluxo como programado e regista `article.schedule`; não cria uma revisão independente fictícia nem um evento de publicação antecipado. A execução vencida mantém o processador existente, bloqueios de linhas, auditoria e notificações. A repetição do processamento não publica nem notifica novamente o mesmo artigo. Os artigos futuros não entram nas consultas públicas.

O processamento automático já existente antes dos pedidos HTTP continua activo. Foi acrescentado o comando:

```sh
python -m flask --app app admin publicar-programados
```

Este comando executa o processador existente, que também trata aprovações pendentes válidas. Pode ser chamado por cron, temporizador ou tarefa do alojamento, por exemplo a cada minuto, usando o mesmo ambiente e a mesma base de dados da aplicação. Deve existir uma única configuração operacional da tarefa; os bloqueios existentes protegem os trabalhadores concorrentes no PostgreSQL.

**Configuração externa pendente:** esta entrega não instala nem activa uma tarefa no alojamento. Sem tarefa periódica, o primeiro pedido elegível após a hora marcada processa a publicação; não se promete execução ao segundo num site sem tráfego. Com uma tarefa por minuto, a publicação fica sujeita a essa frequência e à disponibilidade do serviço. Monitorizar falhas e confirmar o relógio UTC do servidor. Não são necessárias credenciais de um serviço de agendamento externo para executar o comando.

## Ficheiros

Alterados: `admin.py`, `governance.py`, `templates/admin/article_form.html`.

Criados: `article_scheduling.py`, `static/js/article-scheduling.js`, `static/css/article-scheduling.css`, `tests/test_article_scheduling.py`, `tests/browser/article-scheduling.spec.js` e este documento.

## Validação

- Primeira execução de regressões: 45 testes aprovados, incluindo programação, publicação directa do principal, auditoria editorial, conversão de fuso e matriz de permissões.
- Oito novos casos Python cobrem programação de rascunho, criação de artigo sem autor associado à equipa, execução CLI sem pedido HTTP, publicação única, alteração/cancelamento, datas inválidas, autorizações, apresentação da hora local e compatibilidade UTC.
- Quatro testes Chromium aprovados a 320, 768 e 1440 píxeis e sem JavaScript. Verificados programação, conservação da data após gravação, conversão entre fusos, cancelamento e ausência de transbordo horizontal nos modos claro/escuro. Capturas da secção inspeccionadas visualmente.
- Compilação Python e `node --check static/js/article-scheduling.js` aprovados.

Os testes usam SQLite isolada, contas e artigos sintéticos. Não foram programados artigos de produção nem alteradas credenciais ou configurações de alojamento. Os ensaios locais não certificam concorrência PostgreSQL ou compatibilidade Safari/Firefox.
- Suite completa: `PYTHONPATH=tests python -m unittest discover -s tests -p 'test_*.py'` — 579 casos, 578 aprovados e um ignorado por exigir PostgreSQL isolado; sem falhas. Execução em 109 segundos. A repetição final dos quatro testes de navegador também passou.

## Correcção após a validação contínua

A execução completa dos testes de navegador na PR #280 detectou seis falhas na gravação automática. O controlo de programação desactivava os campos de data/fuso dos rascunhos depois de a gravação automática ter calculado a referência do formulário. Essa diferença era correctamente tratada como alteração de opções protegidas, pausando a gravação.

A ordem dos scripts foi corrigida: `article-scheduling.js` inicializa os controlos antes de `article-autosave.js` registar a referência. Não se alteraram as verificações de segurança da gravação automática, a protecção contra alterações concorrentes ou as regras de publicação. A falha original foi reproduzida localmente antes da correcção.

Após a correcção: 13 testes Python de programação e gravação automática aprovados. Repetidos também os testes reais de navegador da gravação automática juntamente com os da programação, sem remover verificações ou aumentar os limites de tempo.
