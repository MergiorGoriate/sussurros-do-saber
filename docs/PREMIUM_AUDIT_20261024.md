# Auditoria de requisitos do Prémio

Base: ramo main consultado em 24 de Outubro de 2026. Diagnóstico anterior às alterações desta entrega.

A aplicação usa Flask, SQLAlchemy, PostgreSQL/SQLite, Alembic, Jinja e as folhas de estilo existentes. Não é necessário outro serviço ou sistema de contas.

Já existem planos configuráveis, ofertas, pagamentos ClicPay e Stripe, propostas assinadas, consentimento para recorrência, reconciliação, histórico imutável, comprovativos e cancelamento da renovação. A Biblioteca Exclusiva verifica permissões no servidor; cursos têm aulas, avaliações, progresso e certificados; eventos têm inscrições e capacidade. A administração tem permissões delegadas, notificações e relatórios. Artigos públicos estão separados destes modelos.

## Lacunas face ao documento fornecido

- Os planos são genéricos mensal/anual; não existe identidade comercial Pró/Max nem desconto anual automático.
- A área pessoal está repartida entre aprendizagem e pagamentos, sem painel agregado.
- A validade termina imediatamente; não existe tolerância de três dias limitada aos materiais anteriormente utilizados.
- A aprendizagem não tem inscrição explícita, prazo de conclusão ou pedidos de prorrogação/reactivação.
- Os reembolsos confirmados são reconciliados, mas não existe formulário de pedido e decisão administrativa.
- Os certificados são pessoais e descarregáveis; não existe verificação pública da referência.
- A mudança durante um período pago é bloqueada. Regras de redução, créditos e execução de alterações recorrentes carecem de política aprovada.
- Não há logística ou preços aprovados para certificados impressos, nem política definitiva de reembolso.

## Direcção da implementação

Acrescentar os quatro produtos sem renomear planos antigos nem alterar contratos existentes; calcular anuais a partir da mensalidade; exigir confirmação da publicação após alterações de preço. Reunir serviços num painel próprio, reutilizar autenticação e reforçar os estados de vencimento. Acrescentar inscrições e pedidos auditados, mantendo as decisões comerciais pendentes desactivadas. Preservar a confirmação financeira pelo fornecedor e não executar cobranças reais.

## Dependências de lançamento

Preços e benefícios aprovados, contratos/credenciais de pagamento, política jurídica de reembolso, prazos e limites dos cursos, regras de mudança de plano, custos e entrega física e validação de produção. A implementação de formulários ou adaptadores não comprova a disponibilidade destes serviços em produção.
