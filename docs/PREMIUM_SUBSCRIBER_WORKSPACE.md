# Produtos Pró/Max e área do assinante

Entrega de 24 de Outubro de 2026, sobre `75b383d2364ae7d4acf148fe0047423537acef08`. Complementa a auditoria `PREMIUM_AUDIT_20261024.md`; não declara concluídos todos os 34 pontos do documento de requisitos nem confirma implantação em produção.

## Funcionalidades desta entrega

- Quatro produtos em MZN: Pró Mensal, Pró Anual, Max Mensal e Max Anual. São criados como rascunhos, sem preços ou benefícios presumidos. Planos anteriores conservam identidade, preço e contratos.
- Identidade comercial única por nível, periodicidade e moeda. O administrador configura preços, benefícios, condições e limites de novas inscrições por período. A alteração da identidade de produtos existentes é impedida.
- Nos produtos Pró/Max, o total anual é calculado no servidor por `mensalidade × 12 × 0,80`, com arredondamento à unidade monetária mínima por ROUND_HALF_UP. A página pública apresenta a poupança calculada. Mudar a mensalidade recalcula o anual, invalida propostas antigas por versão e retira o anual da página pública até nova confirmação administrativa. Os contratos e preços de renovações recorrentes já autorizadas são preservados.
- Painel `/premium/painel`, com plano, estado efectivo, validade, benefícios contratados, pagamentos, certificados, aprendizagem, pedidos e acesso às notificações. Datas em hora de Moçambique. Contas sem subscrição não recebem um plano gratuito Prémio; antigos assinantes mantêm consulta dos registos após o vencimento. As ofertas administrativas já existentes continuam identificadas como ofertas.
- Tolerância de três dias para subscrições pagas vencidas, exclusivamente para recursos anteriormente consultados. O primeiro acesso é registado separadamente e não é prolongado pelo uso posterior. Suspensões, impedimentos financeiros, publicação e permissões por plano continuam a prevalecer. A tolerância não permite novas inscrições em cursos ou eventos. Ofertas não recebem tolerância comercial.
- Novos produtos Pró/Max exigem autorização explícita nos planos elegíveis de cada recurso. Uma lista vazia conserva o comportamento dos planos anteriores, mas não concede automaticamente todo o catálogo aos novos produtos.
- Inscrições em cursos com limite verificado no servidor a partir das condições contratadas. A verificação e criação são serializadas por participante. Produtos Pró/Max exigem inscrição expressa antes das aulas. O percurso dos planos anteriores mantém compatibilidade com a abertura directa das aulas.
- Prazo de conclusão opcional por curso, configurável apenas quando aprovado. O prazo é guardado na inscrição e verificado nas rotas de conteúdo, aulas e ficheiros; não prolonga a subscrição. Campos vazios não criam um prazo ou quota presumidos.
- Pedidos de assistência, reembolso, prorrogação e reactivação em `/premium/pedidos`, com histórico próprio e decisões fundamentadas em `/admin/premium/pedidos`. Finanças trata reembolsos; conteúdos trata os restantes pedidos. Versões detectam alterações concorrentes e um índice impede pedidos activos duplicados.
- Aprovar um reembolso regista o montante, sem movimentar fundos ou inventar confirmação financeira. A conclusão exige lançamentos de reembolso confirmados após a apresentação do pedido. Não se aplica automaticamente a proposta de desistência de sete dias. Um reembolso parcial tem designação própria na consulta do pagamento.
- Aprovar prorrogação/reactivação actualiza o prazo da inscrição e preserva as restantes restrições de acesso. A decisão é auditada e comunicada ao titular.
- Verificação de certificados por referência aleatória em `/premium/certificados/verificar/<referência>`, com curso e data de emissão. Nome pessoal e PDF continuam privados. O PDF indica a ligação institucional de verificação e mantém os critérios de conclusão existentes.
- O comando periódico `premium-reconciliar` passa a emitir avisos de renovação próxima, início e fim de tolerância, com deduplicação e processamento limitado. As notificações utilizam a caixa interna existente.
- A eliminação de conteúdos com inscrições, pedidos ou histórico de acesso é impedida; devem ser arquivados.

## Arquitectura e dados

`premium_commercial.py` concentra a identidade e os cálculos comerciais; `premium_members.py` reúne a área pessoal, inscrições, tolerância e pedidos. As rotas reutilizam os blueprints, contas, permissões e notificações existentes. `billing.py` conserva os adaptadores e a reconciliação financeira; não foi alterado o critério de confirmação dos pagamentos.

A migração aditiva `20261024_16` acrescenta `tier` e `course_limit` a `premium_plan`, cria os índices comerciais e três tabelas: `premium_access_history`, `premium_enrollment` e `premium_service_request`. O histórico inicial de acesso recupera a data do último progresso conhecido; esse valor é evidência de consulta, não data comprovada de inscrição ou conclusão. Os contratos e lançamentos financeiros anteriores são preservados. O comando de migração é repetível. O arranque com actualização automática usa o mesmo serviço após a instalação dos modelos existentes.

Não se alteraram modelos ou permissões dos artigos científicos e informativos. O acesso aberto mantém-se.

## Configuração e implantação

1. Validar a cópia de segurança e aplicar `alembic upgrade head` antes de iniciar a nova versão, sobretudo com `AUTO_SCHEMA_UPGRADE=false`.
2. Na administração Prémio, definir os preços mensais Pró/Max e os benefícios aprovados. Confirmar os totais anuais calculados antes de publicar os produtos. Não converter planos anteriores com contratos em novos produtos.
3. Seleccionar explicitamente os planos Pró/Max autorizados em cada recurso. Configurar apenas as quotas e prazos aprovados.
4. Configurar os fornecedores e as credenciais no gestor de segredos. Mantêm-se as condições de `PREMIUM_PAYMENTS_ENABLED`, `PREMIUM_PAYMENTS_MODE`, `PREMIUM_LIVE_APPROVED` e da aprovação de cada prestador. Não activar produção com base apenas nos testes locais.
5. Manter a tarefa `flask --app app premium-reconciliar --limit 100`. Os avisos dependem da execução periódica; a autorização de acesso e a tolerância são verificadas a cada pedido, sem depender do cron.
6. Validar a interface em navegador e a migração num PostgreSQL de preparação antes do lançamento.

## Verificação executada

Foram aprovados 218 testes Python com as dependências declaradas no repositório. Incluem testes anteriores de pagamentos, biblioteca, aprendizagem, contratação, migrações e portal/revista, e 15 novos testes comerciais, de área pessoal, tolerância, quotas, prazos, pedidos, privacidade, certificados e preservação de dados. Nenhuma cobrança real foi efectuada.

Comando:

```sh
PYTHONPATH=tests python -m unittest test_premium_members test_premium test_premium_learning test_premium_billing test_subscription_journey test_premium_catalogue test_billing_migration test_migrations test_scientific_metrics_migration test_platform -q
```

A compilação Python e `git diff --check` passaram. A suite completa do repositório não foi executada. As migrações foram testadas em SQLite; não foi disponibilizado um PostgreSQL isolado. A tentativa de instalar Chromium para verificação visual não obteve um arquivo válido neste ambiente; não se declara aprovação visual ou de responsividade em navegador. As páginas novas foram renderizadas e verificadas nos testes HTTP. Os avisos de ficheiros estáticos não fechados pertencem aos testes existentes.

## Requisitos ainda pendentes

- Mudança de plano durante o período pago, cálculo proporcional e execução pelo fornecedor: não implementados nesta entrega. Mantém-se a protecção que impede cobranças de outro plano durante a validade actual. A política de cálculo, créditos e redução de plano continua dependente de aprovação.
- Certificados impressos: não implementados. Custos, morada operacional, cálculo de distância, entrega gratuita até cinco quilómetros e logística carecem de confirmação.
- Comercialização independente de cursos e limites especiais de cada produto: só se configuram as regras aprovadas; esta entrega não cria pagamentos avulsos de cursos.
- Inactividade, prazo máximo de resposta, regras após o terceiro mês e relação definitiva entre prazos dos cursos e subscrição: ainda exigem definição. A regra técnica actual exige simultaneamente acesso Prémio válido (ou tolerância aplicável) e prazo do curso válido.
- Documentos anexos nos pedidos: o formulário recebe fundamentos e referências; o carregamento de documentos de suporte não foi implementado.
- As novas comunicações de ciclo de vida são internas. Não foi acrescentada entrega destas mensagens por correio electrónico.
- A política jurídica definitiva, preços, benefícios e condições comerciais não foram presumidos. A entrega não valida conformidade jurídica nem autoriza lançamento.
- Credenciais, testes de aceitação nos ambientes dos prestadores, implantação e confirmação de funcionamento no Coolify não foram executados.

Estes pontos impedem tratar o serviço como integralmente concluído ou pronto para lançamento público. Devem ser acompanhados na revisão e no plano de implementação seguinte.
