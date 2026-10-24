# Selecção editorial e programação do boletim

Em Administração → Subscritores, a configuração permite escolher até 20 artigos publicados, pesquisar títulos e guardar a selecção. A alternativa automática selecciona entre 1 e 20 artigos da última semana completa, de segunda-feira a segunda-feira em UTC. Artigos em rascunho ou com publicação futura são rejeitados. As escolhas guardadas aparecem primeiro; é necessário guardar antes de pesquisar ou mudar de página.

Após guardar, o painel apresenta os artigos que serão usados na preparação. O administrador pode só preparar para revisão posterior, aprovar e colocar na fila imediatamente ou aprovar e programar uma data. A confirmação verifica a impressão digital do conteúdo: se o título, o resumo, a imagem ou a selecção mudarem, é necessária nova revisão. O conteúdo de campanhas preparadas permanece guardado; mudar a configuração não altera mensagens existentes.

O envio automático semanal fica desactivado por defeito. Para o activar, o administrador escolhe o dia e a hora e confirma expressamente a preparação, aprovação e envio recorrentes. A selecção automática é recalculada em cada execução. Com escolha editorial, a mesma lista é usada nas semanas seguintes até ser alterada. Desactivar a recorrência impede novas preparações; campanhas já autorizadas devem ser pausadas ou canceladas no histórico.

## Horários e fila

Os novos controlos utilizam Africa/Maputo (UTC+2) e convertem as datas para UTC na base de dados. Por exemplo, terça-feira às 09:30 corresponde a 07:30 UTC. Os controlos antigos do histórico continuam explicitamente em UTC.

O comando existente passa a processar os planos vencidos antes da fila SMTP:

```sh
flask --app app enviar-notificacoes --limit 50
```

Este comando deve continuar a ser executado periodicamente no servidor, por exemplo a cada minuto. A interface não instala tarefas no Coolify nem cria processos permanentes. A entrega acontece na primeira execução elegível após a data e pode demorar por causa das quotas e do intervalo entre tentativas. Aceitação SMTP não comprova entrega na caixa de entrada.

O comando `flask --app app preparar-boletim` também respeita a selecção guardada, mas apenas prepara mensagens, sem autorizar o envio. A opção `--dry-run` permite inspeccionar a edição sem criar mensagens.

São mantidos o limite por edição, a pausa global, os limites horários/diários, as tentativas com espera progressiva, o cancelamento de inscrição e a reconciliação dos resultados incertos. Cada edição semanal continua a ser única: campanhas canceladas ou concluídas não são reabertas pela automatização e uma edição preparada com conteúdo diferente exige intervenção no histórico. O sistema não cria um novo envio da mesma edição para contornar estes estados.

Preparação e autorização são guardadas na mesma transacção. O plano e a fila usam o bloqueio partilhado existente, e a próxima execução fica persistida. Execuções repetidas não criam destinatários duplicados. Se o trabalhador ficar parado durante várias semanas, utiliza apenas o horário semanal mais recente vencido, sem preparar uma sequência de edições atrasadas. Uma selecção editorial que deixe de ser pública, ou um conflito com conteúdo já preparado, suspende a automatização e apresenta a razão no painel. Edições vazias são ignoradas.

## Instalação e validação

Aplicar a migração Alembic `20261024_14` antes de iniciar a nova versão, sobretudo com `AUTO_SCHEMA_UPGRADE=false`. Cria apenas a tabela `newsletter_plan`; não modifica artigos, inscrições ou campanhas existentes. A instalação que já usa `db.create_all()` também cria a tabela nova. Não é necessário alterar credenciais SMTP para esta funcionalidade.

Os testes cobrem selecção manual e automática, artigos privados e futuros, consentimento, impressão digital, programação local, preparação sem SMTP, execução recorrente, pausa, deduplicação, permissões, CSRF e criação repetida da tabela sem alteração de dados alheios. SMTP é simulado nos testes; não são enviados boletins reais.
