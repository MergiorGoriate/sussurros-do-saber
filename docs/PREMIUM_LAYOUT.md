# Actualização visual do Premium

23 de Outubro de 2026. Base: `925dfbd32ce57c640caf3c66ba7c261d0bb4d171`, após integração do PR #270. Foram analisadas as três capturas fornecidas: administração Premium, biblioteca e cartões de planos.

## Alterações

- Biblioteca com título de dimensão moderada, introdução e compromisso de acesso aberto em duas colunas no computador; disposição vertical no telemóvel.
- Barra de pesquisa mais compacta, campos e botão alinhados, contagem de resultados separada e grelha de recursos em três, duas ou uma coluna consoante a largura.
- Estado vazio com símbolo, mensagem e acção já existentes, sem conteúdos fictícios.
- Planos em duas colunas, um único plano limitado a 540 px no computador e largura disponível no telemóvel; tipografia, espaços e condições reorganizados. Mantêm-se preços, benefícios e estado de contratação existentes.
- Administração com título sem serifa, navegação local em botões e indicação da página actual, aviso discreto, três indicadores obtidos dos dados reais e secções com hierarquia consistente.
- Cartões administrativos com periodicidade, estado, preço e acção diferenciados. Planos sem preço positivo mostram «Preço por definir», sem alterar o valor guardado.
- Formulários e gestão financeira herdam os estilos locais, incluindo tema escuro, campos e foco. A área pessoal beneficia dos ajustes de apresentação dos detalhes da assinatura.

Não foram modificados serviços, modelos, rotas, migrações, permissões, preços, credenciais, integrações financeiras ou configurações de cobrança. Cabeçalho, rodapé e barra lateral global permanecem intactos. Os artigos e conteúdos sujeitos a acesso aberto continuam gratuitos.

## Validação executada

- 81 testes Python aprovados: `test_premium`, `test_premium_catalogue`, `test_premium_billing`.
- 12 testes Playwright aprovados em Chromium 153: Premium, biblioteca, teclado, filtros, controlo de acesso, concessão/cancelamento de oferta, pagamentos simulados, administração nos três tamanhos e cartão único.
- Sem transbordo horizontal nas larguras de 320, 768 e 1440 px verificadas; capturas nos modos claro e escuro da página Premium, biblioteca e administração.
- Capturas da biblioteca, administração e cartão único inspeccionadas visualmente.
- 6 testes JavaScript de consentimento aprovados; compilação CSS e sintaxe do teste de navegador aprovadas.

O download habitual do Chromium pelo Playwright estava truncado. Foi usado um executável Chromium 153 obtido de `@sparticuz/chromium`, instalado exclusivamente num directório temporário para validação. Não foi acrescentado ao projecto nem alterado o ficheiro de dependências. Os testes usaram servidor local e SQLite isolados, contas e planos sintéticos e cobranças desactivadas. As capturas com preços e recursos de teste não representam dados de produção.

Os quatro novos cenários de navegador verificam a administração em três larguras e o comportamento de um único cartão de plano. A alteração não foi validada em Firefox, Safari, dispositivos físicos ou com uma auditoria WCAG completa. O CI deve confirmar a execução com o Chromium previsto nas dependências do projecto. Não houve publicação em produção.

## Ficheiros

Modificados: `static/css/premium.css`, `static/css/premium-admin.css`, `templates/premium/library.html`, `templates/admin/premium_base.html`, `templates/admin/premium.html`, `tests/browser/premium.spec.js`.

Criado: `docs/PREMIUM_LAYOUT.md`.
