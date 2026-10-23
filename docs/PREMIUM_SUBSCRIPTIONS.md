# Subscrições Premium — implementação e preparação operacional

## Âmbito e auditoria

Base analisada: `23236387669a7385a37ada861c3c2e53e616ccd8`. Flask, SQLAlchemy/Alembic, Jinja, JavaScript e CSS existentes; não foi criado outro sistema de utilizadores, planos ou pagamentos.

Já existiam e foram preservados: planos mensais/anuais configuráveis, biblioteca com autorização no servidor, ofertas administrativas, preços em unidades mínimas, propostas assinadas e temporárias, consentimento, integrações ClicPay/Stripe, reconciliação no servidor, notificações internas, expiração temporal, cancelamento de renovação Stripe, registos financeiros imutáveis, reembolsos/contestações e separação entre teste e produção. Os artigos científicos e informativos continuam gratuitos; o sistema editorial não foi alterado.

Lacunas corrigidas: perda do plano durante a autenticação; apresentação incompleta da confirmação; falta de comprovativo descarregável; ausência de filtros na consulta/exportação financeira; cancelamentos ClicPay apresentados como recusas; indisponibilidade de pagamentos sem percurso claro para consultar condições.

## Comportamento implementado

1. Cada plano activo encaminha para a rota existente `/premium/aderir/<id>`.
2. O plano fica numa intenção assinada de 24 horas, contendo apenas o identificador. A autenticação existente conserva-o através da rotação da sessão. As ligações de criação de conta, confirmação de e-mail e recuperação transportam esta intenção. Nunca se aceita um URL de destino fornecido pelo visitante.
3. «Confirmar subscrição» mostra o preço administrativo, moeda, duração, benefícios efectivamente configurados, total, renovação e cancelamento. Não há preço anual, desconto ou benefício inventado. Os 200 MZN indicados no pedido não foram inscritos automaticamente: a base de dados de produção não foi consultada. A administração deve confirmar ambos os planos antes de activar cobranças.
4. «Subscrever agora» só surge com métodos configurados em modo real; «Testar subscrição» identifica o modo de teste. Sem métodos, «Consultar condições» apresenta a indisponibilidade sem criar uma cobrança. A configuração local não equivale a certificação comercial ou operacional do fornecedor.
5. O formulário adapta número de carteira e consentimento recorrente ao método. O servidor revalida plano, versão, proprietário, CSRF, método e consentimento. Stripe exige autorização expressa para renovação. Carteiras e NetShop mantêm renovação manual.
6. O pedido fica persistido antes da chamada externa. A mesma proposta não origina outra chamada. A referência aberta da conta impede nova cobrança concorrente. Falhas ambíguas exigem reconciliação, não repetição automática.
7. Cartões encaminham para a página alojada validada do fornecedor. O regresso do navegador nunca activa benefícios. Mantêm-se a assinatura do webhook Stripe e a consulta independente do fornecedor.
8. Apenas recebimentos legítimos em modo real concedem acesso durante o período contratado. Os testes não concedem acesso real. Renovações manuais acrescentam um período; uma mudança de plano durante validade activa é recusada antes da chamada externa, sem cálculo improvisado de créditos.
9. «A minha assinatura» reutiliza a página de pagamentos, validade, benefícios e cancelamento existentes. O detalhe apresenta estado, movimentos e ligação ao comprovativo PDF, quando há recebimento no diário. O PDF é privado, exclusivo do titular e identifica claramente testes e reembolsos. É um comprovativo interno, não uma factura fiscal nem confirmação de liquidação bancária.
10. O painel financeiro permite pesquisa por e-mail/referência/pedido, estado, ambiente, plano e datas UTC. A paginação e o CSV preservam os filtros. A integridade e os valores agregados continuam globais e são identificados como tal. São apresentados assinantes com registos pagos, validade, pedidos pendentes, pagamentos confirmados e planos com mais períodos pagos; as ofertas e os testes não entram nos totais globais de assinantes pagos.

## Estados, dados e segurança

Não há migração de base de dados nesta alteração. Reutilizam-se `PremiumPlan`, `PremiumSubscription`, `BillingAccount`, `BillingOrder`, `BillingGrant`, `BillingJournal` e `BillingEvent`.

Cancelado é distinguido na apresentação e nos filtros pela evidência imutável `poll:<pedido>:CANCELLED`. O estado interno continua `failed`, respeitando a restrição já existente e preservando dados antigos. Recusas sem essa evidência continuam «Recusado». Uma ausência de resposta não é convertida artificialmente em expiração. Expirações devem corresponder a confirmação suportada pelo fornecedor; pedidos ambíguos ficam para reconciliação.

Os PDFs exigem sessão válida, propriedade do pedido e um recebimento no diário. Respostas privadas usam `no-store`; o endpoint tem limite de utilização. Campos de PDF são escapados, sem recursos remotos. O CSV mantém a protecção contra fórmulas e exporta o diário original, sem reescrever movimentos. Não se guardam PAN, CVV, PIN ou credenciais bancárias. As credenciais dos fornecedores permanecem no servidor.

## Fornecedores e dependências externas

- **ClicPay:** reutilizados os adaptadores M-Pesa, e-Mola e NetShop. É necessário contratar e validar a conta, as carteiras e o ambiente. A documentação publica consulta de estado como fonte de confirmação; a reconciliação periódica é indispensável. Os termos referem operação em piloto/sandbox regulatório: confirmar elegibilidade e condições comerciais antes de produção. Não foi inventada uma assinatura de webhook ClicPay.
- **Stripe:** reutilizados Checkout alojado, subscrições, webhooks e portal do cliente. Moçambique não consta da lista de países para abertura directa de conta Stripe; a integração só pode ser activada por uma entidade elegível, expressamente aprovada. A existência de um adaptador não significa disponibilidade comercial local.

Fontes oficiais consultadas em 23-10-2026:

- https://www.clicpay.co.mz/api/documentation
- https://www.clicpay.co.mz/pt/policies/terms
- https://stripe.com/global
- https://docs.stripe.com/checkout/fulfillment

## Configuração e activação

Manter `PREMIUM_PAYMENTS_ENABLED=false` até concluir a validação. `PREMIUM_PAYMENTS_MODE=test` deve usar exclusivamente credenciais de teste. O modo real também exige `PREMIUM_LIVE_APPROVED=true`; estas opções não foram activadas nesta entrega.

ClicPay: `CLICPAY_TOKEN`, carteiras numéricas `CLICPAY_MPESA_WALLET`, `CLICPAY_EMOLA_WALLET`, `CLICPAY_NETSHOP_WALLET` e, para NetShop, `CLICPAY_CHECKOUT_HOSTS` com os hosts autorizados pelo fornecedor. O adaptador verifica moeda, método, ambiente e capacidade da carteira.

Stripe: `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PORTAL_CONFIGURATION` e `STRIPE_MERCHANT_APPROVED=true`, apenas após comprovação de elegibilidade. Configurar no fornecedor o endpoint existente `/premium/webhooks/stripe` e os eventos necessários, conforme `PREMIUM_PAYMENTS.md`.

Configurar `SITE_URL` HTTPS, cookies seguros, SECRET_KEY estável, base PostgreSQL de produção e limites partilhados entre processos. Agendar os comandos existentes de reconciliação (`flask premium-reconciliar --help`) e expedição de notificações segundo `PREMIUM_PAYMENTS.md`; monitorizar atrasos, pedidos a reconciliar, falhas e contestações. As notificações internas são transaccionais; a entrega de e-mail depende do serviço configurado e do respectivo processamento.

Antes de abrir: confirmar preços, moeda, benefícios, termos e apoio; validar sandbox de cada método, autenticação, callback, reconsulta, duplicação, reembolso e cancelamento; conferir recebimentos com extractos do fornecedor e liquidação bancária; estabelecer política fiscal/contabilística, retenção de dados, backups e resposta a incidentes. Nenhuma cobrança real foi efectuada durante esta implementação.

## Rotas

Preservadas: `/premium`, `/premium/aderir/<id>`, `/premium/pagamentos`, `/premium/pagamentos/<id>`, verificação, cancelamento, portal Stripe, webhook, painel e CSV financeiros. Nova: `GET /premium/pagamentos/<id>/comprovativo.pdf`. Os filtros são parâmetros das rotas financeiras existentes, sem duplicar páginas.

## Ficheiros

Novos: `premium_return.py`, `billing_receipts.py`, `static/js/billing-checkout.js`, `tests/test_subscription_journey.py`, este relatório.

Modificados: `billing.py`, `billing_service.py`, `submissions.py`, `reader_accounts.py`, `google_auth.py`, `static/js/reader-accounts.js`, `static/css/billing.css`, `static/css/premium-admin.css`, `templates/submissions/auth.html`, `templates/premium/{index,base,checkout,payment,payments}.html`, `templates/admin/premium_finance.html`, `tests/test_premium_billing.py`, `tests/browser/{billing.spec.js,billing_fixture.py}`.

## Validação e limitações

Os resultados finais encontram-se na secção de validação abaixo. Os testes de integração de pagamentos usam respostas controladas e proíbem chamadas financeiras reais. Não foram executadas transacções nos ambientes dos fornecedores: faltam credenciais e contratos. A validação local do navegador usa Chromium e SQLite isolada; não equivale a teste Safari/Firefox, auditoria completa de acessibilidade ou ensaio de carga/concorrência PostgreSQL.

Não foi publicado nem activado o serviço em produção. Não se garante que uma conta comercial ou método esteja operacional sem validação externa. Comprovativos fiscais, taxas, liquidação bancária e reconciliação contabilística continuam a exigir processo próprio. Alterações imediatas de plano e rateios não são disponibilizados.

Recomendação estratégica: estabilizar primeiro pagamentos, reconciliação e apoio; só depois lançar parcerias institucionais com universidades, com contratos e benefícios próprios, mantendo o acesso aberto independente das subscrições.

### Resultados executados

- `PYTHONPATH=tests python -m unittest test_premium_billing`: 49 testes aprovados; respostas dos fornecedores substituídas por contratos de teste, rede financeira bloqueada. Cobrem confirmação, pendência, recusa, expiração suportada, duplicação, concessão, renovação, cancelamento, reembolso, assinatura de webhook e integridade financeira.
- `PYTHONPATH=tests python -m unittest test_site_regressions test_subscription_journey test_premium_billing`: 64 testes aprovados após a correcção do tratamento de pedidos demasiado grandes. Os 7 testes novos cobrem planos mensal/anual após autenticação, intenção inválida, cobrança desactivada, comprovativo privado, cancelamento identificado, filtros/CSV e bloqueio de mudança de plano durante validade activa. A verificação de propriedade do PDF foi ainda repetida com outro leitor autenticado: 7/7 aprovados.
- Playwright/Chromium: 16/16 na primeira execução de `billing.spec.js premium.spec.js finance.spec.js`; 19/19 na execução de `billing.spec.js finance.spec.js reader.spec.js google.spec.js`; repetição final do checkout: 4/4. Existem cenários sobrepostos entre estas execuções; não devem ser somados como testes distintos. Verificados 320, 768 e 1440 píxeis, navegação por teclado nos cenários Premium existentes, administração clara/escura, biblioteca, autenticação de ambos os planos, favoritos e Google. Capturas da confirmação e administração inspeccionadas visualmente.
- `node --check` nos dois ficheiros JavaScript afectados e compilação Python dos módulos alterados: aprovados.
- A primeira execução completa encontrou uma regressão no erro HTTP 413: o contexto global tentava voltar a ler um formulário já rejeitado. A recuperação da intenção passou a ler formulários apenas nos endpoints de autenticação e a tolerar erros de leitura, preservando a resposta original. O teste de regressão existente confirmou a correcção.
- Suite completa final: `PYTHONPATH=tests python -m unittest discover -s tests -p 'test_*.py'` — 571 casos, 570 aprovados e 1 ignorado, sem falhas, em 165 segundos. O caso ignorado exige `SCIENTIFIC_METRICS_TEST_DATABASE_URL` com PostgreSQL isolado. Os avisos de indisponibilidade de métricas e de base de dados fazem parte de cenários de falha controlada; subsistem avisos preexistentes de ficheiros estáticos não fechados nos testes.
