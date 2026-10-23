# Premium: pagamentos, operação e relatório da segunda fase

Data: 23 de Outubro de 2026. Base analisada: `1feb4b68b72ce92ecfce1e73b56e9fa7782bbb82`.

## Estado da entrega

A primeira fase e o layout existente foram reutilizados. Os acordos, pedidos e bloqueios financeiros são separados por ambiente: uma contestação de teste não suspende um acesso real. Esta entrega acrescenta adaptadores de pagamento, contratação, consentimento, reconciliação, renovação, cancelamento, histórico e controlo financeiro. Os pagamentos estão desactivados por omissão. Não foram utilizadas credenciais reais, iniciadas cobranças externas ou alterada a produção. A existência dos adaptadores não comprova aprovação comercial nem funcionamento com a conta concreta de um fornecedor.

Os artigos informativos e os artigos científicos da revista semestral continuam gratuitos. Não se acrescentam verificações de pagamento a `Article` ou `Journal`. Nos conteúdos adicionais, a nova opção editorial `open_access_required` impede a restrição quando existe uma obrigação de acesso aberto. A equipa deve verificar as licenças, os acordos de financiamento e as obrigações de cada conteúdo; o código não consegue determinar essas obrigações a partir do texto.

## Fornecedores e modalidades

| Meio | Adaptador | Modalidade implementada | Dependência externa |
| --- | --- | --- | --- |
| M-Pesa | ClicPay v2 | Cobrança C2B em MZN; renovação manual | Contrato, token e carteira autorizada |
| e-Mola | ClicPay v2 | Cobrança C2B em MZN; renovação manual | Contrato, token e carteira autorizada |
| Cartões por fornecedor local | ClicPay/NetShop | Página de pagamento alojada pelo fornecedor; renovação manual | Carteira NetShop, aceitação comercial de cartões internacionais e domínio real do checkout confirmado |
| Cartões com recorrência | Stripe Checkout/Billing | Assinaturas mensais/anuais, cobrança recorrente pelo fornecedor e gestão do cartão no portal da Stripe | Entidade elegível, credenciais, webhook e configuração do portal |

A documentação da ClicPay apresenta meios locais e cartões. A confirmação de aceitação, liquidação e condições comerciais da entidade concreta continua necessária. Não foram inventados endpoints de débito recorrente para M-Pesa ou e-Mola. A Stripe não deve ser tratada como automaticamente disponível para uma entidade registada apenas em Moçambique; a lista de disponibilidade e a elegibilidade comercial devem ser verificadas com o fornecedor antes de activar essa opção.

A implementação Stripe usa REST, com versão fixada em `2025-06-30.basil`, sem acrescentar um SDK às dependências. A implementação ClicPay usa exclusivamente `https://clicpay.co.mz/api/v2`. Antes de iniciar uma cobrança local, consulta a carteira e confirma ambiente (`sandbox`/`production`), moeda, método e autorização C2B. Não considera uma carteira de produção como carteira de testes.

Fontes técnicas consultadas:

- [ClicPay: documentação oficial da API](https://www.clicpay.co.mz/api/documentation).
- [ClicPay: meios de pagamento apresentados pelo fornecedor](https://www.clicpay.co.mz/en).
- [Stripe: disponibilidade global](https://stripe.com/global).
- [Stripe: criação de Checkout Sessions](https://docs.stripe.com/api/checkout/sessions/create).
- [Stripe: webhooks de assinaturas](https://docs.stripe.com/billing/subscriptions/webhooks).
- [Stripe: consulta de pagamentos de uma factura](https://docs.stripe.com/api/invoice-payment/list).
- [Stripe: verificação de webhooks](https://docs.stripe.com/events/manage-webhook-endpoints).
- [Stripe: portal do cliente](https://docs.stripe.com/api/customer_portal/sessions/create).

## Percurso do utilizador

A página Premium mantém os planos existentes. Quando os pagamentos estão configurados e activados, cada plano apresenta a ligação para consultar as condições. Apenas uma conta activa, autenticada e com e-mail confirmado pode contratar.

O formulário apresenta o preço, a moeda e a periodicidade. Exige aceitação das condições e, para Stripe, uma autorização adicional de renovação automática. Uma proposta assinada no servidor, válida por 15 minutos, associa conta, plano, versão, ambiente e identificador único. A gravação conserva as condições aceites; uma alteração posterior ao preço exige nova confirmação e não modifica contratos já criados.

O pedido fica persistido antes de contactar o fornecedor. O identificador é usado como chave de idempotência. Repetir o mesmo formulário devolve o pedido existente. Uma segunda adesão com outro formulário fica bloqueada enquanto existir um pedido pendente/incerto ou um acordo automático ainda activo. Assim, um timeout não desencadeia outra cobrança.

M-Pesa e e-Mola recebem apenas o número necessário à operação e os dados do pedido. O portal não guarda esse número nem pede PIN. ClicPay/NetShop e Stripe recebem os dados dos cartões nas respectivas páginas alojadas; o portal não dispõe de campos ou colunas para PAN, CVV ou números completos de cartão. Os destinos de checkout são validados: Stripe por domínio fixo e NetShop pela lista explícita de domínios confirmados na configuração.

O regresso do fornecedor para uma página do portal não confirma o pagamento. A página mostra o estado guardado e permite uma consulta autenticada ao fornecedor. Os estados são «A iniciar», «Pendente», «Confirmado», «Recusado», «Expirado», «A reconciliar» e «Reembolsado». O histórico é privado e paginado por conta.

Em carteiras móveis e cartões locais, o próximo período exige nova autorização. Na Stripe, a renovação é executada pelo fornecedor segundo o consentimento registado. Os preços são conservados no acordo; alterações, descontos, períodos experimentais, prorrateios e impostos adicionais configurados externamente não são suportados automaticamente por esta versão. Uma divergência de valor exige reconciliação, em vez de conceder acesso com valores presumidos.

## Confirmação e acesso

A ClicPay é reconciliada pelo endpoint autenticado de estado da transacção. A referência utilizada foi devolvida pela iniciação autenticada de um pedido com montante fixado no servidor; não pode ser fornecida por um visitante. Quando a resposta inclui montante ou moeda, estes também são conferidos. A resposta documentada de estado pode omitir esses campos: nesse caso, a associação ao montante depende da referência da iniciação, e a conferência contabilística deve comparar o pedido com o relatório do fornecedor.

Na Stripe, os webhooks exigem assinatura HMAC válida sobre o corpo original e timestamp com tolerância de cinco minutos. O corpo está limitado a 256 KiB. O evento é deduplicado e o estado é novamente obtido pela API. Para lançar um pagamento, são conferidos a factura, o acordo, o cliente, o preço, a moeda, o ambiente e o período. Um `InvoicePayment` pago e o respectivo `PaymentIntent` efectivamente recebido são obrigatórios. Uma factura marcada manualmente como paga não basta.

São tratados eventos de factura paga, falhada ou a exigir acção; sessão concluída/expirada; alterações do acordo; reembolsos e contestações. A leitura do estado actual evita aplicar simplesmente o conteúdo de um evento antigo. Eventos de outros produtos da mesma conta Stripe são reconhecidos sem conceder acesso. Uma falha temporária de consulta responde com erro para permitir nova entrega.

O lançamento do recebimento, a concessão do período de acesso e a notificação interna pertencem à mesma transacção. As restrições únicas e o controlo de concorrência impedem duplicações. Os períodos locais respeitam meses e anos de calendário, incluindo Fevereiro e anos bissextos. Uma renovação manual acrescenta um período depois da validade já paga. Os períodos Stripe provêm da factura verificada; uma factura antiga não cria um período novo a partir do dia de recepção.

Um pagamento de teste nunca cria um acesso real. Um resultado pendente, recusado ou expirado também não o cria. Para carteiras móveis, ultrapassar o prazo local sem resposta conclusiva significa «A reconciliar», sem libertar o pedido para uma nova cobrança. A expiração de um checkout Stripe só é aplicada quando confirmada pelo fornecedor.

Os acessos pagos usam o modelo `PremiumSubscription` existente, com origem `billing`, e concessões por pagamento em `BillingGrant`. Não podem ser reescritos no formulário de ofertas. Suspensões administrativas e contestações impedem a leitura reservada, sem alterar os artigos gratuitos. A suspensão de acesso não cancela débitos no fornecedor; o painel explica essa distinção.

## Cancelamento e notificações

«Assinatura e pagamentos» inclui um botão para cancelar a renovação automática. O pedido é persistido antes do contacto externo. O fornecedor recebe `cancel_at_period_end=true`; o acesso conserva o período já pago. A página distingue cancelamento pedido de cancelamento confirmado. O comando periódico volta a tentar os pedidos ainda sem confirmação. Uma sessão Stripe ainda não paga pode ser expirada pelo fornecedor durante esse percurso.

O portal da Stripe permite gerir o cartão sem fornecer esses dados ao Sussurros do Saber. A identidade do cliente é obtida a partir do acordo verificado, nunca de um parâmetro enviado pelo navegador. A configuração comercial do portal deve permitir actualizar o meio de pagamento e consultar facturas, sem mudar preços ou activar funcionalidades incompatíveis com esta integração.

Os avisos de pagamento pendente, confirmação, recusa, reembolso, cancelamento e reconciliação reutilizam a caixa interna de notificações existente. O comando periódico prepara avisos de proximidade do fim e término do acesso. Os avisos são deduplicados. Esta entrega não acrescenta um serviço de SMS nem um envio automático próprio por e-mail. Os e-mails de recibo, recuperação de pagamento e alertas da Stripe dependem da configuração do fornecedor; a fila SMTP do portal não foi alterada.

## Registo financeiro e limites contabilísticos

| Registo | Responsabilidade |
| --- | --- |
| `BillingAccount` | Pedido em curso, acordo automático, cancelamento e bloqueios |
| `BillingOrder` | Pedido e condições aceites; tentativa local, adesão Stripe ou pagamento de um período |
| `BillingGrant` | Período de acesso concedido por um pagamento real |
| `BillingJournal` | Diário imutável de pares débito/crédito, com valor inteiro e moeda |
| `BillingEvent` | Identidade, tipo e resumo criptográfico de evidência, sem guardar o payload bruto |
| `BillingRisk` | Contestação ou reembolso que exige acompanhamento |

Cada recebimento cria um débito em `gateway_clearing` e um crédito em `premium_deferred`, de igual valor. Cada reembolso confirmado inverte o par pelo montante adicional efectivamente reconciliado. Os registos de diário e de eventos recusam UPDATE e DELETE também na base de dados, em SQLite e PostgreSQL. Correcções financeiras não devem apagar lançamentos: devem ter evidência e contrapartida.

As moedas e os ambientes são apresentados separadamente. O painel não soma MZN, USD, EUR e ZAR como se fossem a mesma unidade. Os valores são inteiros em unidades mínimas; não se utiliza vírgula flutuante para gravar dinheiro. O exportador CSV neutraliza células susceptíveis de serem interpretadas como fórmulas e é exclusivo do administrador principal.

O auditor confere recebimentos, reembolsos, contas, moeda, ambiente e a relação entre concessões de acesso e recebimentos. Um diário equilibrado não prova que o banco liquidou o valor nem substitui a conferência com extractos externos. As chaves de eventos e referências de pagamento têm unicidade. A transacção de origem não pode ser reutilizada para pagar várias contas.

Os totais representam cobranças brutas e reembolsos no fornecedor. **Não são lucro, facturação fiscal, saldo bancário ou receita já reconhecida.** Não são inventadas taxas, impostos, despesas cambiais, regras fiscais ou datas de liquidação. Taxas do gateway, impostos, reconhecimento de receita diferida e reconciliação bancária exigem tratamento contabilístico próprio, com apoio de um profissional e documentos do fornecedor. Contestações abertas são mostradas separadamente; a perda financeira final de uma contestação não é lançada automaticamente nesta versão.

Os reembolsos Stripe são lidos na API e registados por montante acumulado, sem duplicação. Um reembolso total revoga a concessão daquele pagamento. Um reembolso não cancela, por si só, um acordo recorrente. Se um reembolso ou uma contestação chegar antes do evento de pagamento, a leitura da cobrança actual permite recuperar esse estado.

Para ClicPay, um estado de reembolso parcial pode não trazer o valor. Nesse caso, é criado um bloqueio de acompanhamento: não se inventa o montante. O comando específico abaixo exige confirmação do estado na API e identificação de um documento já conferido pelo responsável financeiro. Esse comando regista um reembolso já efectuado; não envia dinheiro. Reembolsos a executar devem ser tratados no fornecedor, segundo a política aprovada da entidade.

## Configuração

| Variável | Utilização |
| --- | --- |
| `PREMIUM_PAYMENTS_ENABLED` | `false` por omissão; activa a apresentação dos meios configurados |
| `PREMIUM_PAYMENTS_MODE` | `test` por omissão; `live` para produção |
| `PREMIUM_LIVE_APPROVED` | Deve ser `true` para oferecer novas cobranças reais após validação operacional/comercial |
| `CLICPAY_TOKEN` | Token Bearer privado; nunca no frontend |
| `CLICPAY_MPESA_WALLET` | Identificador da carteira M-Pesa |
| `CLICPAY_EMOLA_WALLET` | Identificador da carteira e-Mola |
| `CLICPAY_NETSHOP_WALLET` | Identificador da carteira NetShop |
| `CLICPAY_CHECKOUT_HOSTS` | Domínios exactos de checkout NetShop, separados por vírgulas, confirmados pelo fornecedor; sem esquema, porta ou wildcard |
| `STRIPE_SECRET_KEY` | Chave `sk_test_…` ou `sk_live_…`, coerente com o ambiente |
| `STRIPE_WEBHOOK_SECRET` | Segredo do endpoint de eventos do ambiente correspondente |
| `STRIPE_MERCHANT_APPROVED` | Confirmação operacional da elegibilidade comercial da entidade |
| `STRIPE_PORTAL_CONFIGURATION` | Identificador `bpc_…` da configuração restrita do portal do cliente |
| `SITE_URL` | Origem pública HTTPS correcta, reutilizando a configuração existente |

Não foi acrescentada qualquer dependência a `requirements.txt`. Não foram guardadas credenciais no código. Os valores acima são nomes de configuração, não credenciais fornecidas nem serviços activados. A rotação de chaves e a mudança de ambiente devem preservar a possibilidade de reconciliar pedidos antigos; não misturar carteiras e chaves de teste com produção.

No fornecedor Stripe, registar `/premium/webhooks/stripe` como destino dos eventos tratados. Activar apenas depois de confirmar a versão e o contrato dos payloads com a conta de teste. O exemplo de domínio NetShop da documentação não é um endereço real de produção e não é utilizado como valor por omissão.

## Migração e comandos

Fazer cópia de segurança, ensaiar a migração numa base isolada e aplicar antes de servir a nova versão:

```bash
python -m alembic upgrade head
python -m alembic current
```

Head esperado: `20261023_11`. A migração cria as seis tabelas financeiras, os mecanismos de imutabilidade e a coluna `premium_content.open_access_required`, sem alterar dados de artigos ou revistas. Conteúdos anteriores recebem `false`; a equipa deve rever obrigações preexistentes antes de vender acesso. A compatibilidade de arranque com `AUTO_SCHEMA_UPGRADE` reutiliza a configuração existente; não a alterar por causa desta entrega. A reversão destrutiva é recusada para preservar o histórico.

```bash
python -m flask --app app premium-reconciliar --limit 100
python -m flask --app app premium-auditar-financas
```

Agendar a reconciliação, por exemplo a cada minuto, com uma execução de cada vez. Ela consulta pedidos não terminais e o acordo recorrente actual, recupera facturas quando um webhook se perde, volta a tentar cancelamentos e produz avisos internos. O limite deve ser dimensionado ao número de pedidos e acordos; esta versão não inclui uma fila distribuída de cobrança. O código do portal não inicia débitos recorrentes por cron: essa função pertence ao fornecedor autorizado.

Pedidos sem referência após uma falha de iniciação permanecem em acompanhamento. Não criar outro pedido nem repetir cobranças para «desbloquear» o cliente. Na Stripe, é possível recuperar uma sessão existente, conferindo a associação à referência interna:

```bash
python -m flask --app app premium-recuperar-stripe --pedido REFERENCIA_INTERNA --sessao cs_REFERENCIA_EXISTENTE
```

Para ClicPay, a recuperação de uma iniciação sem referência exige investigação com o fornecedor. Não existe um botão que marque arbitrariamente como pago ou que liberte um resultado incerto sem evidência.

Registar um reembolso local já efectuado e documentalmente verificado:

```bash
python -m flask --app app premium-confirmar-reembolso-local \
  --pedido REFERENCIA_INTERNA --total-minor VALOR_ACUMULADO_EM_CENTAVOS \
  --documento IDENTIFICADOR_DO_RELATORIO --motivo 'Descrição da conferência efectuada'
```

O painel financeiro fica em `/admin/premium/financeiro`, com consulta, reconciliação e exportação. Os comandos de operação exigem acesso de manutenção ao servidor; não devem ser expostos como endpoints públicos nem executados sobre dados de produção para fins de teste.

## Validação e critérios para utilizadores reais

A suite específica acrescenta testes de assinatura/CSRF, consentimento, preço alterado, repetição de formulários, iniciação incerta, consulta pendente/recusada, expiração confirmada, ambiente, recibos, períodos mensais/anuais, renovação, cancelamento, reembolsos, contestações, imutabilidade SQL, auditoria, concorrência e isolamento entre contas. Inclui a proibição de carteiras de produção no modo de testes e a leitura anónima de conteúdos sujeitos a acesso aberto.

Resultados locais finais: **526 testes Python passaram**, incluindo **49 testes específicos de pagamentos** e **um teste adicional de migração financeira**. **Os seis testes JavaScript existentes também passaram**. A verificação de sintaxe dos novos cenários Playwright e a compilação dos módulos Python passaram. Os 104 testes do subconjunto Premium/migrações/autenticação fazem parte da suite completa; não são testes adicionais aos 526.

Comandos de validação:

```bash
PYTHONPATH=tests:. python -m unittest discover -s tests -p 'test_*.py' -q
node --test tests/consent.test.cjs
node --check tests/browser/billing.spec.js
python -m compileall -q billing.py billing_models.py billing_providers.py billing_schema.py billing_service.py
```

As chamadas HTTP dos fornecedores são simuladas; testes unitários não demonstram que a conta comercial aceita um pagamento real. Os adaptadores são ensaiados contra os campos documentados, incluindo destino seguro de checkout e gestão do cartão. Não houve SCA/3DS real, débito M-Pesa/e-Mola real, reembolso real ou liquidação bancária.

Há dois cenários Playwright adicionais para histórico, estados financeiros, largura móvel e ausência de campos de cartão. A execução local de navegador continua impedida pela instalação truncada do Chromium. O CI deve confirmar esses cenários e o percurso Premium anterior. A validação local da migração e da imutabilidade é em SQLite; o ensaio PostgreSQL do CI continua necessário.

Antes de abrir o serviço a utilizadores reais, confirmar: conta e contrato de cada fornecedor; carteiras correctas por ambiente; preços e condições comerciais aprovados; política de cancelamento/reembolso publicada; configuração restrita do portal Stripe; webhook e comando periódico activos; reconciliação com relatórios do gateway e extractos bancários; alertas operacionais e atendimento a pedidos incertos. Confirmar também o acesso público a artigos e conteúdos com obrigação de acesso aberto. Não há declaração de conformidade PCI, certificação de segurança ou validação fiscal nesta entrega.

## Recomendação estratégica: piloto e parcerias

Começar com um piloto limitado de conteúdos adicionais e utilizadores convidados, usando primeiro o ambiente de testes e depois um ensaio real controlado quando os fornecedores estiverem aprovados. A passagem a uma venda pública deve depender da demonstração de que uma cobrança, uma renovação, um cancelamento e um reembolso podem ser acompanhados do início ao fim, sem divergências financeiras. Medir também pedidos pendentes, tempo de resolução, retenção e utilização dos conteúdos.

Depois dessa validação, estruturar um programa de parcerias com universidades e instituições científicas. Uma proposta inicial pode reunir formação complementar, produção conjunta de cursos, entrevistas e eventos, com os artigos científicos sempre em acesso aberto. Começar com um acordo-piloto de objectivos concretos, responsabilidades editoriais, licenças, orçamento e avaliação, antes de propor uma rede internacional.

Distinguir colaboração institucional, apoio financeiro e decisão editorial. O acesso pago à formação não deve comprar aceitação de artigos ou interferir com a revisão por pares. Publicar apenas parcerias efectivamente acordadas, com autorização de uso dos nomes e logótipos. Essas parcerias podem contribuir para relações internacionais e confiança pública; não garantem indexação, acreditação ou reconhecimento científico por si sós. Esta é uma proposta estratégica, não um programa já negociado ou implementado.
