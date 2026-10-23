# Sussurros Premium — auditoria e aperfeiçoamento incremental

Data: 23 de Outubro de 2026. Referência: `main`, commit `9db697400738a47d911c6804be58203d0e834002`, após integração do PR #269. Esta alteração não activa cobranças nem publica uma nova versão em produção.

## 1. Auditoria e decisão de arquitectura

Foi examinada a árvore completa do repositório (393 ficheiros versionados), as dependências, a inicialização da aplicação, os módulos, modelos, rotas, templates e testes Premium. Não existe `AGENTS.md` nessa referência. Arquitectura existente: Flask 3.1.3, Flask-SQLAlchemy 3.1.1, SQLAlchemy, Alembic 1.20.0, Jinja, CSS com variáveis de tema e Tailwind 4.3.3. SQLite nos testes locais; PostgreSQL previsto em produção e no CI. Testes Python com unittest e HTTP real através do cliente Flask; Playwright 1.64.1 no CI. Não foram acrescentadas dependências.

| Área / fase | Estado encontrado | Decisão e resultado |
| --- | --- | --- |
| Auditoria / problemas | PRs anteriores já integrados; implementação funcional | Reutilizar `premium.py`, `billing.py`, modelos, rotas e painel existentes |
| Página Premium | Hero, identidade azul/dourado, formatos, planos, FAQ e modos claro/escuro já implementados | Preservar composição; acrescentar benefícios, condições por período e melhorar legibilidade |
| Biblioteca | Publicação, tipos, paginação, detalhes e autorização no servidor concluídos | Acrescentar pesquisa pública, categorias, filtros combinados, capas gráficas por formato e estados sem resultados |
| Planos | Mensal/anual, preços em unidades menores, MZN por omissão, edição, versão e auditoria concluídos | Acrescentar benefícios configuráveis e preservar os benefícios contratados em snapshots |
| Assinante | Conta existente, pagamentos, validade e cancelamento concluídos | Enriquecer a mesma página com plano, estado, periodicidade, origem, datas e benefícios contratados |
| Administração | Permissões, 2FA, CSRF, ofertas, conteúdos, planos e finanças existentes | Integrar novos campos nos formulários e visão geral; modernizar cartões/formulários locais |
| Pagamentos | ClicPay e Stripe, simulação, confirmação, idempotência, livro financeiro e reconciliação existentes | Preservar; acrescentar benefícios ao snapshot da adesão e apresentá-los antes do consentimento |
| Validação | Suíte de regressão e cenários de navegador já existentes | Executar referência e alteração; acrescentar nove testes Python e adaptar os testes de teclado à categoria |

Não foram criadas novas rotas, tabelas de utilizadores, páginas alternativas de planos, serviços de pagamento paralelos ou menus globais. O comparador continua em `/premium#planos` (também acessível como `/premium/#planos`). Biblioteca e detalhes mantêm os respectivos identificadores e referências. A área pessoal continua em `/premium/pagamentos`; a gestão permanece em `/admin/premium` e `/admin/premium/financeiro`.

## 2. Funcionalidades preservadas

- Autenticação `Researcher`, confirmação de e-mail, conta activa, nonce de sessão e autorização administrativa existentes. A administração Premium continua reservada ao administrador principal, segundo as regras anteriores.
- Artigos científicos da revista e artigos informativos do portal integralmente gratuitos. Não foi alterado nenhum modelo, consulta ou rota editorial para exigir Premium.
- Conteúdos com `open_access_required` continuam disponíveis gratuitamente; não se carrega o corpo exclusivo antes de verificar autorização. Rascunhos continuam indisponíveis publicamente.
- Sanitização Markdown, cache privado `no-store`, paginação, controlo optimista de concorrência e auditoria administrativa.
- Ofertas separadas de receitas, snapshots anteriores intactos, preços e moedas existentes, configurações e referências dos conteúdos.
- Confirmação autenticada no fornecedor, assinatura do webhook Stripe, idempotência, reconciliação, livro financeiro imutável, retenção de eventos, cancelamento e notificações existentes.
- Cabeçalho, rodapé, navegação global, autenticação, fornecedores, credenciais e configurações de cobrança sem alterações.

## 3. Melhorias implementadas

### Planos e condições

`PremiumPlan.benefits` armazena uma lista JSON configurada pelo administrador: até 20 linhas diferentes, com até 180 caracteres por benefício. Não há benefícios ou preços inventados. Planos anteriores recebem uma lista vazia. A lista aparece nos cartões existentes, no checkout antes da confirmação e no painel administrativo.

Novas ofertas e novos pedidos de pagamento guardam os benefícios no snapshot das condições. A apresentação do assinante usa esse snapshot, não os benefícios actuais do plano. Assinaturas antigas não recebem benefícios retroactivamente. Todos os planos continuam a dar acesso à mesma biblioteca; benefícios são condições descritivas, não níveis novos de autorização.

O plano anual mantém a periodicidade de 12 meses. O administrador pode definir um preço anual inferior a 12 mensalidades; não se inventa uma percentagem nem se compara automaticamente planos cujos benefícios possam ser diferentes. Não se alteram os preços anteriormente configurados. MZN continua a ser a moeda por omissão, preservando também os planos internacionais existentes.

### Biblioteca

Pesquisa por título/descrição, combinável com tipo e categoria; os caracteres `%` e `_` são tratados como texto literal, não como curingas SQL. O corpo protegido nunca participa na pesquisa. Limites de entrada: pesquisa 120 caracteres, categoria 80. A lista de categorias usa apenas recursos publicados. A paginação mantém os filtros, apresenta contagem e permite limpar critérios.

Capas gráficas leves por formato, sem downloads externos ou imagens fictícias de cursos; cartões com distinção entre acesso aberto e exclusivo, ligações com nomes acessíveis e estados diferentes para biblioteca vazia e pesquisa sem resultados. Os detalhes apresentam categoria e regresso à biblioteca. Não foi criado um sistema de upload de imagens ou de distribuição privada de vídeos.

### Área pessoal e administração

Resumo da assinatura com periodicidade, estado, origem, datas UTC e benefícios contratados. Sem assinatura, a página encaminha para os planos existentes. Contas sujeitas a bloqueio financeiro não recebem uma ligação de acesso activo: a apresentação usa a mesma verificação de autorização do catálogo.

Formulários administrativos com benefícios e categoria, validação no servidor e auditoria na transacção existente. A visão geral distingue recursos abertos/exclusivos e mostra categorias e benefícios. Cartões, formulários e navegação local usam os estilos existentes e os modos de tema; não há uma nova aplicação administrativa.

### UX, acessibilidade e desempenho

Grelhas adaptáveis, campos com nomes associados, foco visível, alvos de acção com pelo menos 44–48 px nas novas interfaces, contagem de resultados com `role=status`, texto adicional para identificar as ligações dos recursos e cores baseadas no tema existente. Melhorada a legibilidade dos textos de planos e cartões.

A biblioteca continua renderizada no servidor, sem pedidos assíncronos nem novas dependências JavaScript; utiliza o carregamento nativo do navegador. Erros de validação administrativos e do checkout mantêm mensagens e códigos HTTP existentes; não foram introduzidos estados de carregamento artificiais. As listagens carregam metadados e mantêm 12 recursos por página. A pesquisa é SQL simples, sem serviço de indexação novo; não foi efectuado benchmark de carga ou auditoria WCAG completa.

## 4. Dados e instalação

Migração aditiva `20261023_12`, posterior a `20261023_11`:

- `premium_plan.benefits JSON NOT NULL DEFAULT '[]'`;
- `premium_content.category VARCHAR(80) NOT NULL DEFAULT ''`.

O helper `upgrade_catalogue_schema` é idempotente. A instalação automática já existente chama-o através de `upgrade_premium_schema`, antes de consultar planos. Para instalações com migrações explícitas: executar o processo habitual de backup e `alembic upgrade head` antes de iniciar o código novo. As tabelas financeiras e os corpos de conteúdos não são reescritos. O downgrade destrutivo é recusado para reter configurações e histórico; eventual reversão do código deve manter as colunas adicionais.

## 5. Testes executados e limites

| Verificação | Resultado local |
| --- | --- |
| Referência sem alterações, reconstruída a partir dos ficheiros da versão auditada | 526 testes Python aprovados |
| Suíte completa com as alterações | 535 testes Python aprovados |
| Verificação dirigida de catálogo, Premium, pagamentos e migração financeira | 82 testes aprovados |
| JavaScript existente de consentimento | 6 testes aprovados |
| Compilação CSS Tailwind | Aprovada |
| Compilação dos módulos Python alterados e sintaxe do teste Playwright | Aprovadas |
| Playwright / comparação visual em navegador | Não executados: download Chromium devolveu ZIP truncado |
| Migração PostgreSQL, Safari/Firefox e dispositivos reais | Não executados localmente; validar no CI/ambiente de homologação |

Os nove testes novos cobrem pesquisa combinada, ausência de pesquisa no corpo exclusivo, curingas literais, limites de entrada, categorias sem rascunhos, paginação, estados vazios, benefícios configurados/escapados/auditados, recusa de benefícios inválidos, apresentação de condições anteriores, conta sem assinatura, edição de categoria com autorização preservada e migração repetida a partir de tabelas com a forma anterior. Alguns testes agrupam cenários relacionados.

Os testes anteriores foram reforçados para confirmar snapshots de benefícios em ofertas e pagamentos. Foram actualizadas três expectativas da versão de migração para o novo head. Os 49 testes financeiros existentes continuam a cobrir pagamentos confirmados, pendentes, recusados, expirados/incertos, reembolsos, duplicados, permissões, integridade contabilística e isolamento entre testes e produção. As chamadas aos fornecedores são simuladas e a rede real é proibida nesses testes; nenhum pagamento real foi iniciado. A suite emite ResourceWarnings já presentes na referência; termina com sucesso.

Os testes Playwright existentes foram adaptados à posição do novo campo de categoria e aos parâmetros adicionais da URL. Foi acrescentado um cenário de pesquisa/categoria e verificações de largura da biblioteca nos dois temas, a 320, 768 e 1440 px. Estes cenários estão preparados, mas não são apresentados como aprovados sem execução. A aprovação dos testes de HTTP não equivale a uma verificação visual, auditoria de desempenho ou garantia de ausência de regressões em todos os navegadores.

## 6. Problemas corrigidos

- Ausência de benefícios configuráveis e de preservação desses benefícios nas novas adesões.
- Biblioteca sem pesquisa nem categorias; falta de distinção entre ausência de recursos e ausência de resultados.
- Área pessoal sem resumo estruturado das condições contratadas; estado visual agora respeita bloqueios financeiros.
- Texto administrativo desactualizado que afirmava inexistência de pagamentos, apesar da integração anterior.
- Teste de teclado dependente de o botão surgir imediatamente após o filtro de tipo; ajustado ao novo campo.

## 7. Ficheiros criados e modificados

Criados: `premium_catalogue_schema.py`, `migrations/versions/20261023_12_premium_catalogue.py`, `tests/test_premium_catalogue.py`, `docs/PREMIUM_UX_PLANS.md`.

Modificados:

- `premium.py`, `premium_models.py`, `premium_schema.py`, `billing.py`;
- `templates/premium/index.html`, `library.html`, `content.html`, `locked.html`, `checkout.html`, `payments.html`;
- `templates/admin/premium.html`, `premium_plan.html`, `premium_content.html`;
- `static/css/premium.css`, `static/css/premium-admin.css`;
- `tests/test_premium.py`, `tests/test_premium_billing.py`, `tests/test_billing_migration.py`, `tests/test_migrations.py`;
- `tests/browser/premium.spec.js`, `tests/browser/premium_fixture.py`;
- `docs/PREMIUM.md`, para ligar este relatório à documentação existente.

## 8. Pendências e activação de cobranças

Os valores por omissão continuam `PREMIUM_PAYMENTS_ENABLED=false`, `PREMIUM_PAYMENTS_MODE=test`, `PREMIUM_LIVE_APPROVED=false`. Não foram alteradas variáveis do serviço em produção. O desenvolvimento e os testes não autorizam a activação de cobranças reais.

Antes de activar: contratos e elegibilidade comercial; carteiras ClicPay de produção autorizadas para os métodos/moeda; conta Stripe elegível, chaves e webhook de produção e configuração do portal; domínio HTTPS e URLs de retorno aprovadas; credenciais apenas em segredos do ambiente; testes de homologação e conciliação no fornecedor; execução agendada da reconciliação e auditoria; política operacional de cancelamentos, apoio e reembolsos; validação fiscal/contabilística aplicável. Seguir os detalhes de `docs/PREMIUM_PAYMENTS.md`, incluindo limites de fornecedores, devoluções e disputas. M-Pesa/e-Mola continuam com autorização por período; recorrência automática apenas onde efectivamente suportada e expressamente consentida.

Ficam pendentes a aprovação visual nos navegadores, o CI PostgreSQL, a definição editorial dos benefícios/preços reais pelo administrador, recursos multimédia com entrega privada e a configuração operacional dos fornecedores. Capas fotográficas com upload e níveis diferentes de acesso por plano não fazem parte desta alteração. Não se guardam PAN, CVV, PIN de carteira nem payloads financeiros sensíveis.

Recomendação estratégica: depois de validar o piloto Premium, estruturar um programa de parcerias com universidades e instituições científicas, com revisão editorial independente, critérios claros de qualidade e acordos que preservem o acesso aberto. Começar com um piloto mensurável de cursos/eventos conjuntos, avaliar participação e qualidade, e só depois ampliar o programa internacionalmente.
