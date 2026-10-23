# Layout da gestão financeira Premium

23 de Outubro de 2026. Base: `69c6b4fb7b04eb2cc62c41c54d870478493e91dd`. A alteração responde à captura de `/admin/premium/financeiro` fornecida pelo utilizador.

## Apresentação

A página passa a organizar a informação em quatro áreas: resumo, movimentos financeiros, pedidos de pagamento e contas em acompanhamento.

O resumo mostra o número real de pedidos, contestações/reembolsos pendentes de reconciliação e o resultado da auditoria interna já existente. O botão de exportação CSV mantém a rota e as permissões anteriores. Os valores monetários continuam separados por moeda e ambiente: não se somam moedas diferentes nem dados de teste com dados de produção.

Os cartões de movimentos distinguem recebimentos brutos, reembolsos e compensação líquida. Sem registos, apresentam uma mensagem específica, sem inventar saldos ou uma moeda. Os pedidos distinguem estado, ambiente, montante, meio, identificador e referência. Mantêm o formulário POST de reconciliação, com CSRF. As contas em acompanhamento mantêm motivo, ambiente, suspensão/levantamento de suspensão e o aviso de que suspender acesso não cancela débitos.

Os três estados vazios explicam onde surgirão movimentos, pedidos e contas. As limitações contabilísticas ficam indicadas no resumo e detalhadas num elemento expansível utilizável por teclado. A compensação no fornecedor não é apresentada como saldo bancário, lucro ou facturação fiscal.

Os estilos reutilizam as variáveis do painel Premium nos modos claro e escuro e adaptam-se ao telemóvel. O subtítulo financeiro é específico desta página; as outras páginas conservam o texto anterior.

## Preservação

Não foram modificados cálculos, serviços, APIs, modelos, migrações, fornecedores, preços, dados de utilizadores, permissões ou configurações de cobrança. Não foram iniciadas cobranças nem operações nos fornecedores. A barra lateral e o cabeçalho global permanecem intactos. O acesso aberto aos conteúdos científicos e editoriais mantém-se.

## Validação local

- 81 testes Python aprovados: Premium, catálogo e pagamentos; incluem as verificações financeiras e de permissões anteriores.
- 15 testes Playwright aprovados em Chromium 153: 12 existentes e três novos cenários da página financeira, nas larguras de 320, 768 e 1440 px, com ambos os temas.
- Os novos cenários verificam exportação, formulário POST/CSRF, explicação contabilística por teclado, ausência de transbordo horizontal e ausência de pedidos POST durante a consulta.
- Verificação adicional da página vazia num servidor/SQLite novos: três estados vazios presentes, três larguras e os dois temas, sem transbordo horizontal.
- Capturas da página vazia e com pagamentos de teste inspeccionadas visualmente.
- 6 testes JavaScript de consentimento e compilação CSS aprovados.

As verificações de navegador utilizaram dados sintéticos e cobranças desactivadas. O executável Chromium alternativo permanece num directório temporário; não foram acrescentadas dependências. Firefox, Safari, dispositivos físicos e auditoria WCAG integral não foram executados. A alteração aguarda integração; não foi publicada em produção.

## Ficheiros

Modificados: `templates/admin/premium_finance.html`, `templates/admin/premium_base.html`, `static/css/premium-admin.css`.

Criados: `tests/browser/finance.spec.js`, `docs/PREMIUM_FINANCE_LAYOUT.md`.


## Correcção do orçamento de execução do CI

O job de navegador do run `39961915809` foi cancelado ao atingir 15 minutos. A instalação com dependências consumiu 512 segundos, sobretudo em transferências do espelho Ubuntu; sobraram cerca de seis minutos para 151 cenários. Os cenários financeiros e Premium passaram antes do cancelamento. O registo não mostra uma falha de asserção antes da interrupção.

O job passa a ter 30 minutos, com limites próprios de 15 minutos para instalação e 15 para a suíte. O limite individual de 30 segundos por cenário, a repetição de testes falhados, a execução sequencial e todos os cenários são preservados. A instalação usa `--only-shell`, suficiente para os testes headless actuais, evitando descarregar também o Chromium completo. Os registos do servidor passam a ser apresentados também em caso de cancelamento.

Validação da configuração: YAML interpretado e limites verificados; opção `--only-shell` confirmada pelo CLI instalado e pelo comando `install --only-shell chromium --dry-run`. O resultado da nova execução de CI deve ser consultado no PR; estas verificações locais não substituem a conclusão do job remoto.
