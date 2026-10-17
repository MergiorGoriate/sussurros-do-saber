# Validação da fila de revisão do portal

Revisão de 17 de outubro de 2026 sobre o PR #183, a partir do commit
`53d4121bd6ea07591de65e7f749997add0a20e7c`.

A Área de trabalho mostra os artigos atribuídos ao revisor com mandato activo
e permissão `article.review`, respeitando `article_scope`. Foi corrigido um caso
em que o artigo permanecia na fila «Artigos do portal para rever» depois da
entrega do parecer: o fluxo continua em `review` até à aprovação editorial,
mas `reviewed_at` já está preenchido. A fila passa a incluir apenas pareceres
por entregar. O acesso ao fluxo e ao histórico continua disponível após a entrega.

## Verificação local

Ambiente Python 3.12, dependências de `requirements.txt`, bases SQLite temporárias
isoladas, contas sintéticas e ficheiros do commit indicado obtidos pelo conector
GitHub. Nenhum teste usou dados ou serviços de produção.

- A regressão nova falhou antes da correcção: artigo ainda presente após entrega.
- Depois da correcção, passaram 214 testes Python na suite completa.
- Após acrescentar a verificação explícita de revogação da permissão, passaram
  novamente os 22 testes de governação.
- Cobertura adicional: reatribuição retira o artigo da fila e do acesso do revisor
  anterior; outro revisor não vê artigos não atribuídos; entrega remove o artigo
  da fila sem impedir a consulta do fluxo; revogação de permissão, desactivação e
  expiração do mandato retiram o acesso na sessão existente.
- `npm ci`, `npm run build:css`, `npm audit --omit=dev --audit-level=high`,
  `pip check` e `git diff --check` passaram. A auditoria npm não abrange dependências
  de desenvolvimento e `pip check` verifica compatibilidade, não vulnerabilidades.

## Validações ainda bloqueadas

A CI 38390016239 do commit anterior terminou com falha. Os quatro trabalhos têm
`steps: []`, `runner_id: 0` e nenhum runner identificado: não há evidência de
execução dos testes nessa tentativa. Os logs não puderam ser recuperados.
A causa exacta do bloqueio do GitHub Actions não foi confirmada; não atribuir
estas falhas aos testes da aplicação nem presumir um problema de facturação.

A instalação local do Chromium do Playwright falhou porque o download não era
um ZIP válido. Os testes de navegador não foram executados nesta revisão.
Docker, ensaios PostgreSQL e auditoria Python de vulnerabilidades também precisam
de validação no ambiente correspondente. Não foi feito merge nem deploy.

Os PRs de actualização de dependências #177 a #182 permanecem fora desta
correcção funcional. Em particular, a actualização principal do Tailwind deve
validar o comando de compilação e os estilos antes de ser integrada.
