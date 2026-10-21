# Relatório da implementação de limites SMTP

## Funcionamento anterior

O boletim já seleccionava artigos da semana completa, guardava texto e HTML na
fila EditorialNotification, deduplicava a preparação e verificava inscrições
activas. O comando enviar-notificacoes fazia a entrega SMTP. Faltavam contadores
partilhados, aprovação/autorização separadas, estados de tentativa e tratamento
conservador da janela entre aceitação SMTP e commit.

## Ficheiros da alteração

| Grupo | Ficheiros |
| --- | --- |
| Modelos e evolução | submission_models.py; mail_schema.py; migrations/versions/20261021_08_mail_limits.py; app.py |
| Preparação e entrega | newsletter_service.py; mail_delivery.py; submissions.py |
| Administração | admin.py; templates/admin/subscribers.html; templates/admin/mail_delivery.html; static/css/admin-subscribers.css |
| Testes Python | tests/test_mail_delivery.py; tests/test_mail_migration.py; tests/test_newsletter.py; tests/test_submissions.py; tests/test_migrations.py |
| Navegador e CI | tests/browser/mail-delivery.spec.js; tests/browser/mail_delivery_fixture.py; .github/workflows/ci.yml |
| Documentação | README.md; docs/NEWSLETTER.md; docs/NEWSLETTER_DELIVERY.md; este relatório |

O CSS Tailwind foi compilado para verificação, mas o ficheiro compilado anterior
foi preservado para evitar remover classes de outras áreas nesta alteração. Os
estilos novos são próprios da página e não exigem novas classes utilitárias.

## Modelos migração e limites

A revisão 20261021_08 acrescenta campanhas, política e histórico de tentativas à
fila existente. A configuração inicial é 2500 destinatários por edição, 100
tentativas/hora UTC, 500/dia UTC, intervalo de 36 segundos e três tentativas
adicionais. O limite da edição é total e não reinicia em cada lote. Os limites
abrangem também correio transaccional da mesma fila. A pausa global tem esse
mesmo alcance; a opção NEWSLETTER_ENABLED conserva o alcance apenas dos boletins.

Quotas externas são manuais, com origem e data, e prevalece o limite mais
restritivo. A interface não afirma ter validado o fornecedor. Alterar os limites
é auditado. Reduzir a capacidade de uma edição suspende campanhas autorizadas
que excedam o novo valor.

Os bloqueios PostgreSQL coordenam a reserva e o trabalhador entre instâncias.
Cada tentativa é persistida antes do contacto SMTP. Recusas temporárias têm
espera progressiva; recusas definitivas não são repetidas. Resultados incertos e
claims abandonados exigem reconciliação com evidência, sem reenvio automático.
Aceitação SMTP não equivale a entrega na caixa do destinatário.

## Interface e permissões

A secção Limites e entrega apresenta contadores, quotas, utilização, reserva e
última actividade do trabalhador, pausa, campanhas, agendamento, falhas e últimas
tentativas. O estado do trabalhador não afirma verificar o cron do Coolify.
Campanhas e falhas têm paginação. O conteúdo guardado pode ser revisto antes da
aprovação; autorizar ou agendar é um passo separado. Nenhum POST editorial envia
SMTP directamente.

As acções reutilizam subscribers.manage, sessão/2FA e CSRF. Há testes para cada
acção recusada a contas sem permissão e para ausência de CSRF. A auditoria
reutiliza GovernanceAudit. Não são exibidas credenciais nem respostas SMTP brutas.

## Verificações executadas localmente

- Antes da alteração: 25 testes de newsletter e migrações aprovados.
- Na revisão funcional: 57 testes direccionados de entrega, migração, boletim e
  permissões aprovados em SQLite, com SMTP simulado.
- O ensaio de volume criou 2501 subscritores, preparou 2500 mensagens e aceitou
  apenas 500 no orçamento diário, mantendo 2000 pendentes.
- Dois testes de navegador aprovados, em execuções separadas: controlos,
  aprovação/agendamento, cancelamento e nova inscrição. O controlo de layout
  percorreu 320, 390, 768 e 1440 px nos dois temas.
- Inspecção visual de capturas sintéticas a 320 e 1440 px nos dois temas.
- Seis testes JavaScript de consentimento aprovados; compilação Tailwind
  concluída; git diff --check sem erros.

O navegador local foi Chromium 153 alternativo porque o pacote de navegador
padrão não pôde ser descarregado correctamente neste ambiente. Não foi executada
toda a suite de navegador local. A CI mantém Chromium próprio.

Um problema de repetibilidade na criação dos índices foi encontrado pelos
testes e corrigido: a migração já não acrescenta objectos Index repetidos aos
metadados globais. Os testes de migração preservam conteúdo, timestamps de
aceitação e duplicados legados sem os reenviar.

## Limitações e validações pendentes

O ambiente local não permitiu iniciar PostgreSQL com um utilizador sem
privilégios. A suite de entrega foi acrescentada ao job PostgreSQL existente,
com esquemas isolados para verificar bloqueios e relações reais. O resultado do
GitHub Actions deve ser consultado para o commit específico; o resultado SQLite
não é apresentado como validação PostgreSQL.

Não foram acedidos Coolify, credenciais reais, quotas do fornecedor, DNS de
correio ou dados de produção. Não foram enviadas newsletters reais. A aceitação,
entrega na caixa, reputação do domínio e capacidade contratada dependem do
fornecedor e de validação controlada após implantação. A reconciliação é manual
porque não foi identificada uma API do fornecedor para comprovar os resultados.

Não há promessa de entrega exactamente uma vez: SMTP e PostgreSQL não partilham
uma transacção atómica. O sistema evita repetição automática quando o resultado
é desconhecido. Uma tentativa já reservada pode terminar depois de uma pausa;
mensagens já em transmissão não podem ser recolhidas atomicamente.

## Configuração e implantação

Não há novas variáveis de ambiente, fornecedor pago, daemon obrigatório ou
alteração ao Dockerfile. Reutilizar a tarefa periódica enviar-notificacoes no
Coolify e o mesmo ambiente/base. Preparações automáticas guardam edições mas não
substituem a aprovação e o agendamento de cada campanha.

Parar os trabalhadores antigos; verificar backup e ensaio numa cópia; aplicar
alembic upgrade head com o código novo; confirmar 20261021_08; publicar a nova
aplicação; rever campanhas legadas e limites; retomar somente o comando novo.
Não executar o worker antigo sobre o esquema novo. Validar /healthz, interface,
agendamento e recepção de uma mensagem controlada antes de autorizar campanha.

O procedimento completo, incluindo reversão e falhas SMTP, consta de
[NEWSLETTER_DELIVERY.md](NEWSLETTER_DELIVERY.md). Este trabalho não implantou
alterações em produção nem configurou tarefas no Coolify.
