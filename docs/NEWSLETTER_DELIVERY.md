# Limites e entrega do boletim

## Diagnóstico e âmbito

Antes desta revisão, `newsletter_service.queue_digest` preparava texto/HTML na fila
`EditorialNotification`, com bloqueio de preparação e deduplicação por assunto e
endereço. O comando `enviar-notificacoes` verificava cancelamentos e confirmava a
aceitação antes de QUIT. Não havia limite persistente por hora/dia, aprovação de
campanha separada, espera progressiva ou retenção de resultados ambíguos.

Esta revisão mantém Subscriber, a selecção semanal, o HTML, as ligações de
cancelamento, o endpoint `/admin/subscritores`, a permissão `subscribers.manage`,
CSRF, a auditoria GovernanceAudit e o mesmo comando periódico. Não cria serviço
pago, fornecedor SMTP, tarefa dependente de visitas HTTP ou trabalhador adicional
obrigatório. Não altera Dockerfile nem o arranque Gunicorn.

## Preparar aprovar e agendar

1. Rever a selecção da última semana completa, de segunda a segunda em UTC.
2. Confirmar **Preparar envio do boletim**. Isto cria campanha e destinatários,
   sem SMTP e sem autorização de processamento.
3. Em **Limites e entrega**, abrir a edição e rever o conteúdo guardado. A
   confirmação e a impressão digital da campanha protegem a aprovação.
4. **Aprovar campanha** não envia nem agenda mensagens.
5. **Autorizar processamento agora** ou **Agendar envio** em UTC permite que a
   próxima execução periódica processe a campanha. Não há envio no POST.
6. Acompanhar os estados e a utilização; pausar a campanha ou todos os envios
   quando necessário. Consultar campanhas/falhas mais antigas pela paginação.

Uma edição é identificada pela semana ISO, com unicidade na base. A selecção
continua limitada a cinco artigos públicos de divulgação, sem publicações da
revista científica, rascunhos ou manuscritos. Preparações repetidas completam o
lote somente enquanto a campanha está em preparação. Depois de aprovada,
repetir `preparar-boletim` devolve zero e não reabre a edição, muda conteúdo ou
acrescenta destinatários. Mudança de conteúdo durante a preparação exige revisão;
não se substitui silenciosamente a fotografia guardada.

## Política inicial e quotas externas

| Controlo | Valor inicial |
| --- | --- |
| Destinatários máximos por edição | 2500 no conjunto dos lotes |
| Frequência editorial | Uma edição semanal |
| Limite global por hora UTC | 100 tentativas reservadas |
| Limite global por dia UTC | 500 tentativas reservadas |
| Intervalo mínimo global | 36 segundos |
| Tentativas adicionais | 3, até 4 tentativas no total |
| Destinatários por mensagem | 1, sem CC ou BCC de outros leitores |
| Trabalhador lógico | 1 coordenado pela base |

Estes valores são internos e não constituem quotas verificadas do fornecedor.
No painel podem ser ajustados limites, intervalo e tentativas, com validação e
auditoria. A frequência continua semanal; não é um construtor de campanhas com
periodicidade arbitrária.

As quotas externas por hora e por dia são opcionais e manuais, acompanhadas da
origem e data da verificação. Em cada período aplica-se o menor limite interno
ou externo conhecido. Quotas externas conhecidas são também protegidas por janelas
móveis conservadoras de 60 minutos e 24 horas, para não libertar capacidade apenas
porque mudou a hora ou o dia. Quando falta uma quota, o painel indica que a verificação
é incompleta e aplica o respectivo limite interno. Credenciais presentes não
comprovam conectividade, autenticação, quota ou entrega. A integração não consulta
automaticamente o painel do fornecedor.

O orçamento abrange **toda a fila EditorialNotification**, incluindo confirmações,
recuperações e decisões. A pausa global também pára esses e-mails. NEWSLETTER_ENABLED=false
continua a pausar apenas boletins. Correio enviado por outros programas ou pelo
webmail não é observável por este contador: configurar a quota disponível para
esta aplicação, reservando capacidade para esses outros emissores.

Cada reserva consome uma unidade, incluindo falhas de ligação e cancelamento
detectado depois da reserva. A contagem é conservadora. As janelas são fixas em
UTC, reiniciando em HH:00 e 00:00; as quotas externas acrescentam as janelas móveis
acima, independentemente do fuso de reposição do fornecedor. Não se importam
tentativas históricas sem timestamp conhecido. Aceitações antigas com sent_at
podem ser preservadas no histórico. Uma edição de 2500 requer pelo menos cinco
dias com o orçamento diário inicial inteiramente disponível, e mais se houver
outras mensagens, falhas ou limitações externas. A tarefa a cada minuto pode
ter ritmo inferior ao limite interno; o intervalo não provoca espera bloqueante.

## Persistência e concorrência

`EditorialNotification` permanece a fila. Recebe campaign_id, subscriber_id,
status, next_attempt_at, last_attempt_at, smtp_code e claim_token. O endereço
guardado pertence à campanha; mudar o e-mail do subscritor invalida essa tarefa.
Unicidades por campanha/endereço e campanha/subscritor impedem preparações
duplicadas, mesmo perante concorrência.

`NewsletterCampaign` guarda semana, impressão digital, assunto, estado,
aprovação e agendamento. `MailDeliveryPolicy` guarda configuração, pausa,
adiamento, intervalo e observação do trabalhador. `MailDeliveryAttempt` guarda
cada reserva e resultado, com número único por mensagem. A auditoria utiliza
GovernanceAudit, sem um segundo sistema de auditoria.

Em PostgreSQL, um advisory lock de sessão numa ligação dedicada coordena o
comando inteiro, incluindo os commits por mensagem. Não depende de memória ou
de um único contentor. O bloqueio é libertado no final; uma ligação perdida
liberta-o no servidor. Uma transacção com bloqueio da linha de política serializa
a reserva, a leitura dos contadores e as alterações administrativas.

Há também uma reserva temporal de 300 segundos e heartbeat para observação e
para testes SQLite. Em PostgreSQL, o bloqueio de sessão é a autoridade mesmo que
o heartbeat expire durante uma operação longa. SQLite é ambiente local de testes,
não substitui a validação dos bloqueios/FKs na implantação PostgreSQL.

O processamento escolhe a mensagem elegível mais antiga por ID entre as
campanhas autorizadas e o correio transaccional. Ao atingir limites mantém as
mensagens na fila e regista o próximo período UTC. Respostas de quota ou
indisponibilidade do fornecedor adiam globalmente durante quinze minutos, além
da espera individual. Uma alteração de limite reavalia suspensões de orçamento,
sem ignorar o adiamento do fornecedor.

## Resultados SMTP e reconciliação

| Estado | Comportamento |
| --- | --- |
| pending | Aguarda autorização, data, intervalo e capacidade. |
| processing | Reserva e tentativa confirmadas na base antes do contacto SMTP. |
| accepted | SMTP aceitou; sent_at conserva essa confirmação, não entrega na caixa. |
| temporary | Recusa temporária conhecida ou falha antes de iniciar o envio. |
| permanent | Recusa definitiva conhecida ou tentativas temporárias esgotadas. |
| cancelled | Campanha cancelada ou destinatário inactivo/incompatível. |
| suspended | Requer intervenção, por exemplo autenticação SMTP recusada. |
| uncertain | Resultado da transmissão desconhecido; sem reenvio automático. |

Recusas explícitas 4xx admitem novas tentativas, com 300, 600 e 1200 segundos
mais variação aleatória de 0 a 60 segundos para as três primeiras repetições.
Tentativas adicionais configuradas mantêm progressão até ao máximo permitido.
Recusas definitivas 5xx não são repetidas, excepto respostas identificadas como
quota/limitação, que são adiadas. Uma rejeição genérica não desactiva
automaticamente o subscritor, pois pode significar política do fornecedor e não
inexistência do endereço. Não são guardadas respostas SMTP brutas ou segredos.

Desconexão, timeout ou erro genérico durante send_message são tratados como
incertos, mesmo que em alguns casos a mensagem não tenha chegado ao servidor.
É uma escolha conservadora para impedir reenvio cego. Tentativas processing
abandonadas por crash são convertidas para uncertain na próxima aquisição do
trabalhador. A recuperação preserva mensagens e reservas.

Aceitação e commit não são uma transacção distribuída. Se o SMTP aceitar e o
processo terminar antes de guardar a confirmação, não há prova automática do
resultado. O operador consulta o fornecedor pelo Message-ID estável
`<editorial-ID@sussurrosdosaber.com>`. O painel permite registar uma referência
de evidência e confirmar aceitação ou não aceitação. Confirmar aceitação encerra
a mensagem; confirmar não aceitação só permite repetição dentro do orçamento
de tentativas. Sem evidência verificável, manter a suspensão. Este processo não
oferece garantia matemática de entrega exactamente uma vez nem uma API de
reconciliação que o fornecedor não disponibilizou.

O commit de aceitação ocorre antes de QUIT. Falha em QUIT não põe uma mensagem
aceite novamente em fila. Pausar impede **novas reservas**; uma tentativa já
reservada pode terminar. O cancelamento é revalidado depois da ligação e antes
da transmissão, mas um SMTP já em curso não pode ser atomicamente recolhido.
Cancelamentos retiram imediatamente tarefas ainda pendentes/temporárias e uma
nova inscrição não reanima esses envios antigos. Listas de endereços num único
destino são rejeitadas; o envelope SMTP usa explicitamente um remetente validado
e uma lista com exactamente um destinatário.

## Migração e implantação no Coolify

Não são necessárias novas variáveis de ambiente. Mantêm-se SMTP_HOST,
SMTP_FROM, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, SMTP_TLS/SMTP_SSL,
NEWSLETTER_ENABLED, DATABASE_URL, SECRET_KEY e SITE_URL. A política é guardada
na base, por edição autorizada do painel. Não expor segredos em logs ou no HTML.

1. Parar primeiro a tarefa antiga de enviar-notificacoes e esperar o seu fim.
   Um trabalhador antigo não conhece os novos estados e pode reenviar mensagens
   suspensas; não executar versões antigas e novas em simultâneo.
2. Fazer backup PostgreSQL com anexos e ensaiar restauração/migração em base
   isolada. Preparar a nova revisão, mantendo o serviço antigo de entrega parado.
3. Com o código novo e DATABASE_URL do serviço correcto, executar:

```bash
python -m alembic current
python -m alembic upgrade head
python -m alembic current
```

O head desta alteração é `20261021_08`. A actualização é aditiva e idempotente;
mantém mensagens enviadas, snapshots HTML, inscrições e histórico. Campanhas
antigas são importadas **sem autorização de envio**. Pendentes antigos com
tentativas sem confirmação ficam incertos; duplicados pendentes ficam
cancelados. Registos e sent_at históricos não são apagados. A compatibilidade
de arranque também reconhece o esquema, mas não substitui a migração explícita.

4. Publicar a nova aplicação e verificar /healthz, login e /admin/subscritores.
   Rever as campanhas legadas e os limites antes de autorizar processamento.
5. Reutilizar a tarefa Coolify existente, a cada minuto, com o novo código:

```bash
python -m flask --app app enviar-notificacoes --limit 50
```

O limite CLI é um máximo por invocação, não ignora as quotas. Instâncias
concorrentes coordenam-se, mas configurar uma única tarefa evita trabalho
redundante. O comando executa um lote e termina; Coolify retoma-o na próxima
execução. Paragem/crash não perdem a fila. Não há novo daemon obrigatório.

6. A tarefa de preparação existente pode continuar semanal/diária:

```bash
python -m flask --app app preparar-boletim --dry-run
python -m flask --app app preparar-boletim --limit 2500
```

Preparar não envia. A aprovação e o agendamento explícitos no painel permitem
processamento automático posterior sem alguém ligado ao site. A preparação
periódica não aprova automaticamente cada nova edição.

7. Em homologação, usar SMTP simulado. Em produção, só com destinatário
controlado e autorização de envio, confirmar autenticação, aceitação e recepção,
incluindo spam, cancelamento, quota do fornecedor e histórico. Não executar
uma campanha real como teste. /healthz não valida SMTP nem cron.

Pausar globalmente pelo painel para manutenção. Downgrade destrutivo é recusado
para preservar o histórico; para reversão operacional, parar trabalhadores,
restaurar backup verificado com o código correspondente e reavaliar aceitações
posteriores ao backup com os registos do fornecedor. Não voltar a ligar o
trabalhador antigo sobre a fila nova.

## Verificação

Os testes em tests/test_mail_delivery.py usam SMTP simulado e bases isoladas.
Incluem 2501 subscritores, limite total de 2500 e orçamento diário de 500,
concorrência entre contextos, reinício, pausa, cancelamento, backoff, falhas
permanentes, resultados incertos, unicidade, aprovação e agendamento sem HTTP.
tests/test_mail_migration.py ensaia dados legados duplicados e incertos.
tests/test_newsletter.py conserva cobertura de HTML, selecção, cancelamento,
TLS, permissões e CSRF. tests/browser/mail-delivery.spec.js cobre controlos,
320/390/768/1440 px e ambos os temas.

```bash
PYTHONPATH=tests:. python -m unittest test_mail_delivery test_mail_migration test_newsletter test_migrations -v
MAIL_TEST_DATABASE_URL=postgresql://UTILIZADOR:SEGREDO@HOST/BASE_DE_TESTE python -m unittest discover -s tests -p test_mail_delivery.py -v
npx playwright test mail-delivery.spec.js newsletter.spec.js
```

O comando PostgreSQL usa esquemas temporários; nunca apontar para produção.
O job PostgreSQL já existente na CI inclui agora essa suite. A presença do job
não comprova que passou: consultar o resultado do commit específico. A suite
local e a documentação não confirmam a configuração real do Coolify, as quotas
do fornecedor ou a entrega de correio real.
