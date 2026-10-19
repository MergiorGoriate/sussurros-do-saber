# Boletim científico

O boletim reutiliza Subscriber e EditorialNotification. Não há tabelas, migrações ou permissões novas. A gestão continua em /admin/subscritores e exige subscribers.manage, incluindo POST, confirmação e CSRF. O painel apresenta a selecção antes de a colocar na fila; rejeita uma selecção alterada desde a pré-visualização.

## Conteúdo e envio

Cada edição reúne até cinco artigos de divulgação publicados na última semana completa, de segunda-feira às 00:00 UTC até à segunda-feira seguinte, sem incluir esse limite final. A ordenação é por data e ID decrescentes. Não inclui rascunhos, manuscritos, artigos em revisão ou publicações da revista científica. Uma semana sem artigos não cria e-mails vazios.

O título da edição contém o ano e a semana ISO. A preparação consulta a fila existente e não volta a criar a mesma edição para o mesmo endereço, mesmo se já foi enviada. Um bloqueio transaccional serializa a preparação em PostgreSQL e SQLite. Um novo subscritor pode receber a edição corrente numa preparação posterior. A entrega SMTP existente continua a ser pelo menos uma tentativa com novas tentativas após falha; uma falha entre aceitação SMTP e commit ainda pode duplicar uma entrega, como no mecanismo transaccional anterior.

Cada mensagem contém uma ligação de cancelamento assinada, sem expor o endereço no URL, e cabeçalhos List-Unsubscribe/List-Unsubscribe-Post. GET mostra confirmação sem desactivar a inscrição; POST com token válido desactiva-a, incluindo o pedido One-Click. O comando de entrega verifica novamente se a inscrição está activa. Mensagens canceladas permanecem na fila como canceladas, sem serem marcadas como enviadas. A pessoa pode voltar a subscrever pelo formulário existente.

O erro que mostrava falha após uma inscrição guardada foi corrigido: o JavaScript guarda a referência ao formulário antes de aguardar a resposta. A confirmação não depende de envio imediato; inscrever-se apenas guarda a inscrição. A interface informa quando falta configuração SMTP.

## Activação no servidor

Publicar a branch ou integrar o PR não configura o Coolify nem comprova entrega. No mesmo ambiente da aplicação, verificar as variáveis existentes SMTP_HOST, SMTP_FROM, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD e SMTP_TLS/SMTP_SSL. O remetente é um endereço simples; a porta padrão é 587 com STARTTLS ou 465 com SSL. É necessário pelo menos um transporte seguro.

NEWSLETTER_ENABLED tem padrão true, mas só permite preparação com configuração SMTP segura presente. Definir false pausa os boletins e preserva notificações transaccionais. A detecção de configuração não testa conectividade, autenticação, aceitação pelo destinatário ou tarefas agendadas. SITE_URL deve ser a origem pública correcta; SECRET_KEY deve manter-se estável para conservar as ligações de cancelamento.

Antes do primeiro envio, rever o conteúdo em /admin/subscritores ou inspeccionar a edição sem criar e-mails:

```bash
python -m flask --app app preparar-boletim --dry-run
```

Preparar a edição e entregar a fila são operações distintas:

```bash
python -m flask --app app preparar-boletim --limit 500
python -m flask --app app enviar-notificacoes --limit 50
```

Estes dois comandos, sem dry-run, podem enviar mensagens reais quando executados no servidor. Usar primeiro dados sintéticos e SMTP de teste em homologação. Só activar a entrega real após rever a selecção e confirmar o remetente e os destinatários.

Para automatizar a edição semanal, configurar no servidor uma tarefa diária às 06:00 UTC (08:00 em Maputo) com preparar-boletim e manter a tarefa enviar-notificacoes a cada minuto. A preparação diária usa a mesma edição semanal, permite completar lotes e incluir inscrições novas, sem repetir os destinatários já preparados. O limite aceita 1–5000; a entrega aceita 1–500. As tarefas devem usar a mesma base de dados, SECRET_KEY, SITE_URL e variáveis SMTP do portal. Não configurar uma segunda tarefa de entrega se já existe uma activa.

Os limites e custos dependem do provedor SMTP existente. Não foi criado um contrato, serviço pago ou integração com outro provedor. Este trabalho não executou comandos de envio contra produção nem instalou agendamentos no Coolify. A entrega real e a disponibilidade do SMTP continuam por confirmar.

## Testes e reversão

tests/test_newsletter.py cobre selecção temporal, exclusão de conteúdo privado, destinatários activos, preparação idempotente, cancelamento por token, novas tentativas SMTP, cabeçalhos, pausa sem bloquear e-mails transaccionais e permissões existentes. Os ensaios SMTP usam mocks; não comprovam entrega na caixa de entrada.

Os testes de navegador verificam a mensagem de confirmação e limpeza do formulário a 320 e 1440 px, cancelamento e nova inscrição. Usar apenas bases isoladas para fixtures. Para pausar sem reverter dados, definir NEWSLETTER_ENABLED=false e manter a entrega transaccional; as inscrições e a fila ficam preservadas. Reverter o código só depois de pausar os boletins e tratar a fila preparada, pois um worker antigo não reconhece as regras de cancelamento dos boletins.

Validação local de 19/10/2026: passaram 308 testes Python em SQLite, incluindo dez testes novos, e os três cenários de navegador descritos acima. O navegador foi Chromium 153 alternativo, com cenários em processos separados; não foi executada toda a suite de navegador local. A CI passa a incluir test_newsletter.py no job PostgreSQL existente; esse resultado e a entrega SMTP real não estão confirmados por estes ensaios locais. O comando preparar-boletim --dry-run foi executado com base isolada, sem preparar ou enviar mensagens.
