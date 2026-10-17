# Auditoria administrativa e editorial — 17/10/2026

Base examinada: `main` em `1abfa98256b406c6c4151595f2f1b20005d8269b`, incluindo PR #184 e histórico da [PR #154](https://github.com/MergiorGoriate/sussurros-do-saber/pull/154). Evidências desta auditoria referem-se a dados sintéticos isolados, nunca a conteúdo real.

## A. Diagnóstico

1. **Falha confirmada e corrigida:** o editor associado recebia a notificação de parecer entregue, mas `staff.reviews` exigia `manuscript.assign` para consultar relatórios. Reproduzido: HTTP 403 antes da correcção. A consulta passa a aceitar edição do manuscrito efectivamente atribuído ou decisão científica no âmbito correcto. A atribuição continua a exigir `manuscript.assign` no POST. Não se alteraram funções nem se concederam privilégios globais.
2. **Falha confirmada e corrigida:** `scripts/audit_permissions.py` ignorava `removed_at` ao calcular permissões efectivas. Agora exclui colaboradores arquivados, em concordância com a autorização real. A mensagem de erro passa a identificar a migração actual, `20261008_03`.
3. **Falha confirmada e corrigida:** revisão electrónica e reatribuição editorial aceitavam membros sem conta administrativa ligada. Agora são excluídos da selecção de revisores e recusados no POST; reatribuições sem conta retornam 400 e preservam editor/revisão anteriores. Teste novo cobre as três operações.
4. **Secretariado:** a perda de permissões não foi reproduzida no código actual. Configuração personalizada guardada pelo formulário, logout real, seed, novo login e 2FA preservam as quatro escolhas exercitadas. `seed_roles` só cria funções ausentes. Não é possível atribuir retrospectivamente uma causa ao incidente real sem ler os mandatos/configuração dessa base. Um mandato de revista não concede poderes gerais; falta de aceite, suspensão e vigência também bloqueiam acesso por desenho.

### Arquitectura e classificação por funcionalidade

Flask/SQLAlchemy com blueprints `admin`, `staff`, `submissions`, `reader` e Google; Jinja, CSS administrativo e Tailwind 4 compilado. PostgreSQL em produção, SQLite nos testes locais. Alembic tem baseline, governação e ciclo de vida (`20261008_03`). Login administrativo: palavra-passe + TOTP, sessão vinculada às credenciais e revalidação de conta; investigador: conta própria e GIS opcional, validado no servidor. Integrações: Google, Cloudinary, correio em fila, Redis/limites, PDF. Docker/Gunicorn; nenhuma operação no Coolify.

A = implementada e validada **nos cenários automatizados indicados**; B = cobertura insuficiente; C = parcial; D = falha confirmada; E = ausente; F = indisponível neste ambiente. Esta classificação não certifica todas as combinações possíveis.

| Funcionalidade | Classificação | Evidência / limite |
|---|---|---|
| Catálogo, mandatos, âmbito, revogação | A | `test_permission_matrix`, `test_editorial_audit`; 24 identificadores e 11 padrões |
| Secretariado personalizado após relogin | A / F real | Teste de formulário, logout e 2FA; configuração de produção desconhecida |
| Equipa, responsabilidades, sessões revogadas | A | `test_staff_governance`, `test_lifecycle_notifications`, `test_admin_security` |
| Convites da equipa | C | Estado do membro e aceite documental; não há token independente nem envio externo automático |
| Tarefas: criar, actualizar, reatribuir, concluir | A / F real | Testes de estados, destinatários, histórico; tarefa real «Organizar documentos da revista» indisponível |
| Documentos privados, ficheiros e aceite | A | Testes de upload, terceiros, CSRF, remoção lógica e preservação |
| Versionamento documental formal | C | Documentos são registos separados e preservados; não existe cadeia de versões numerada para documentos da equipa |
| Aceite institucional real anterior | F | Sem acesso ao registo de produção |
| Notificações, contadores, leitura, eliminação | A | `test_lifecycle_notifications`, navegador; apagar aviso mantém acompanhamento |
| Submissão, ficheiros, metadados, versões | A | `test_submissions`, `test_functionality_audit` e navegador |
| Editor e revisor elegíveis, conflito e revogação | A | Matriz, governação e ciclo de vida; convites internos de revisão |
| Parecer até ao editor responsável | D → A | Regressão nova reproduzida; BD, destinatário, consulta e isolamento verificados |
| Decisão, revisão do autor, preparação/publicação | A / C | Transições existentes testadas; aceitação na triagem é permitida, não há regra configurável de número mínimo de pareceres |
| Revisão anónima e anexos do parecer | E | Modelo declara autoria identificável; parecer textual sem upload dedicado |
| GIS | A / F serviço real | Assinaturas/claims/nonce/CSRF em testes; nenhuma conta Google real usada |
| Interface móvel | A nos percursos testados | Administração/editor, artigos, revistas, tarefas, notificações; não prova todos os aparelhos |
| Tema escuro administrativo | E | Não há alternância de tema em `admin/base.html`; preferência de sistema não cria funcionalidade ausente. Tema público possui testes próprios |
| PostgreSQL/restauro/Docker desta alteração | B | Verificação no CI descrita em K; local não tem esses serviços |
| Produção e entregas externas | F | Sem base/contas/deploy nem SMTP real |

## B. Inventário completo no código

As permissões são atribuídas à função em `/admin/funcoes` (fundador), guardadas em `TeamRole.permissions` JSON e ligadas ao colaborador por `TeamAppointment`, com datas, actividade e revista. Não há coluna de concessão individual directamente no utilizador: uma função personalizada/mandato permite escolhas específicas sem duplicar catálogo. Todas as funções podem receber escolhas do catálogo pelo fundador; a tabela mostra os padrões, que não substituem personalizações guardadas.

| Função | Nome | Permissões padrão |
|---|---|---|
| `direction` | Direcção institucional | `team.manage`, `tasks.manage`, `reports.read`, `contacts.manage`, `subscribers.manage` |
| `coordination` | Coordenação do portal | `tasks.manage`, `reports.read`, `article.edit`, `authors.manage`, `categories.manage`, `comments.manage` |
| `chief_editor` | Editor científico principal | `manuscript.read`, `manuscript.edit`, `manuscript.assign`, `manuscript.decide`, `manuscript.production`, `submissions.configure`, `journal.manage`, `journal.publish`, `policies.manage`, `reports.read` |
| `associate_editor` | Editor associado | `manuscript.edit` |
| `reviewer` | Revisor científico | `manuscript.review` |
| `author` | Autor do portal | `article.write` |
| `portal_reviewer` | Revisor do portal | `article.review` |
| `portal_editor` | Editor do portal | `article.edit`, `article.approve` |
| `publisher` | Responsável de publicação | `article.publish` |
| `secretariat` | Secretariado editorial | `tasks.manage`, `manuscript.read` |
| `production` | Produção científica | `manuscript.production` |

O fundador mantém o controlo global explícito; contas históricas não geridas seguem a compatibilidade documentada em `governance.has_permission`. Não são novas funções do catálogo. Utilizadores, funções personalizadas e escolhas reais de produção: **NÃO VERIFICADO**. `python scripts/audit_permissions.py` enumera-os em leitura, sem importar Flask, seed ou migrações e sem exportar credenciais. Nenhum identificador duplicado no catálogo; os 24 são exercitados por operações reais. `team.manage` tem um rótulo abrangente, mas ligar contas/criar e terminar mandatos e editar catálogo continuam reservados ao fundador.

## C. Matriz individual

Cada linha abaixo foi percorrida isoladamente por `test_each_permission_survives_real_logout_login_and_revocation`: atribuição no modelo, commit, logout POST, novo login por palavra-passe e 2FA, operação HTTP com resultado persistente e nova tentativa negada após retirar a concessão. `test_permission_matrix` acrescenta UI, conta inactiva, suspensão, falta de aceite, datas, âmbito e HTTP directo. Relatórios/leitura não têm escrita de negócio: comprova-se HTTP 200; não se inventa persistência de uma mutação. Operações exactas e asserções estão em `PermissionMatrixTests.operation`.

Legenda das colunas: G=atribuição; P=persistência; L=novo login; X=execução; R=revogação; U=acesso indevido. OK refere-se ao ensaio isolado; não à produção. Evidência P1=`test_each_permission_survives_real_logout_login_and_revocation`; P2=`test_every_permission_ui_action_denial_expiry_inactivity_and_revocation`.

| Funções padrão com concessão | Permissão / operação | Módulo | G | P | L | X | R | U | Evidência | Correcção nesta concessão | Estado |
|---|---|---|---|---|---|---|---|---|---|---|---|
| direction | `team.manage` — Gerir equipa, convites e mandatos | team | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| direction, coordination, secretariat | `tasks.manage` — Distribuir tarefas | tasks | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| direction, coordination, chief_editor | `reports.read` — Consultar relatórios e auditoria | reports | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| author | `article.write` — Escrever artigos próprios | article | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| coordination, portal_editor | `article.edit` — Editar todos os artigos | article | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| portal_reviewer | `article.review` — Rever artigos atribuídos | article | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| portal_editor | `article.approve` — Aprovar artigos revistos | article | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| publisher | `article.publish` — Publicar artigos aprovados | article | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| Apenas personalizada | `article.delete` — Eliminar artigos | article | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| coordination | `authors.manage` — Gerir autores | authors | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| coordination | `categories.manage` — Gerir categorias | categories | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor | `journal.manage` — Gerir revistas | journal | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor | `journal.publish` — Publicar revistas | journal | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor, secretariat | `manuscript.read` — Consultar submissões da revista | manuscript | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor, associate_editor | `manuscript.edit` — Tratar submissões atribuídas | manuscript | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor | `manuscript.assign` — Atribuir editores e revisores | manuscript | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor | `manuscript.decide` — Emitir decisões científicas | manuscript | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor, production | `manuscript.production` — Preparar artigos científicos | manuscript | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| reviewer | `manuscript.review` — Emitir pareceres atribuídos | manuscript | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor | `submissions.configure` — Configurar submissões | submissions | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| chief_editor | `policies.manage` — Gerir políticas editoriais | policies | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| coordination | `comments.manage` — Moderar comentários | comments | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| direction | `contacts.manage` — Gerir contactos | contacts | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |
| direction | `subscribers.manage` — Gerir subscritores | subscribers | OK | OK | OK | OK | OK | OK | P1/P2 | Nenhuma necessária | FUNCIONA |

### Funções testadas separadamente

`test_every_default_role_permissions_operations_and_role_change_after_login` faz login/logout/login para cada função, confere **264 decisões de autorização (11 × 24)**, executa cada operação incluída no seu padrão e verifica o resultado persistido. Depois substitui o mandato por função vazia e confirma HTTP 403/404 para cada poder anterior, preservando a função original no fim. As 264 decisões são verificações do autorizador; não são 264 percursos distintos no navegador. As negações HTTP de cada identificador também são cobertas isoladamente por P1/P2.

| Função | Padrão persistido / relogin | Operações incluídas | Troca de função / negação | Evidência | Estado |
|---|---|---|---|---|---|
| `direction` | OK | 5 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `coordination` | OK | 6 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `chief_editor` | OK | 10 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `associate_editor` | OK | 1 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `reviewer` | OK | 1 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `author` | OK | 1 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `portal_reviewer` | OK | 1 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `portal_editor` | OK | 2 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `publisher` | OK | 1 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `secretariat` | OK | 2 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |
| `production` | OK | 1 exercitadas | OK | `test_every_default_role_permissions_operations_and_role_change_after_login` | FUNCIONA |

Matriz de recursos e rotas/UI: [PERMISSIONS_AUDIT.md](PERMISSIONS_AUDIT.md). O documento antigo contém contagens históricas; as contagens desta execução estão em K. Consulta de pareceres pelo editor: **FALHA CORRIGIDA**; inventário de membros arquivados: **FALHA CORRIGIDA**. Funções personalizadas de produção e seus titulares: **NÃO VERIFICADO**.

## D. Correcções e ficheiros

- `governance.py`: separa consulta contextual de pareceres de atribuição; mantém POST protegido.
- `submissions.py` e `templates/admin/submission_detail.html`: disponibilizam ligação de consulta ao editor responsável e ao decisor.
- `templates/admin/staff_reviews.html`: formulário apenas para quem pode atribuir; consulta preserva relatórios anteriores.
- `scripts/audit_permissions.py`: exclui arquivados das permissões efectivas, sem escrita.
- `tests/test_editorial_audit.py`: login real de todo o catálogo e funções, Secretariado personalizado, entrega/consulta de parecer e diagnóstico de arquivados.
- `tests/browser/editorial_audit_fixture.py` e `editorial-audit.spec.js`: fixture isolada e consulta em 320/390/1440 px; não há bypass em rotas da aplicação.
- `.github/workflows/ci.yml`: executa os novos testes também no PostgreSQL do job já existente.

## E. Base de dados

Nenhum modelo, relação ou migração alterados. Head esperado: `20261008_03`. `AUTO_SCHEMA_UPGRADE` permanece exactamente inalterado. Preservados FKs, unicidade de revisor/manuscrito/versão, versões, eventos, DOI e registos arquivados. Nenhum comando contra produção. Testes de migração, integridade e restauro descritos em K.

## F. Equipa e tarefas

Testes existentes executam criação, associação limitada ao fundador, suspensão/revogação de sessão aberta, conflito de âmbito, responsabilidade reatribuída, estado da tarefa e comentário. `test_task_assignment_comment_status_reassignment_deliver_and_noop_deduplicates` comprova entrega e ausência de duplicação em repetição. O ensaio de permissões cria tarefas e confirma a BD. A tarefa histórica nomeada pelo utilizador não foi consultada nem alterada: **NÃO VERIFICADO**.

## G. Documentos

`test_private_docs_allow_invited_member_to_accept_but_deny_other_member`, upload validado e testes de ciclo de vida verificam propriedade, download privado, aceite idempotente e preservação após remoção lógica. Convidados podem aceitar o próprio documento sem obter poderes administrativos. Não há substituição silenciosa nem eliminação física adicionada. O aceite real anterior e versionamento formal de documentos institucionais continuam separados dos cenários testados.

## H. Notificações

A PR #154 introduziu remoção lógica e caixa por destinatário; o código actual mantém essa arquitectura. `test_existing_reader_bell_combines_internal_events_and_delete_keeps_following` é executado sem alteração. Testes cobrem leitura, contador, eliminação, destinatário, rollback, repetição, recurso removido e revalidação ao abrir. O novo teste verifica aviso ao editor e relatório na BD; o navegador confirma a consulta. Correio externo é fila/CLI existente, sem entrega real neste trabalho.

## I. Fluxo editorial

Recepção/identificador/metadados/ficheiros e dono: `test_submissions`. Atribuição e persistência, revisores sem conta/inactivos/conflitos/âmbito, convite/aceite/recusa e substituição com histórico: matriz e governação/ciclo de vida. Novo percurso completo: convite existente → aceite sem conflito → parecer submetido → status/data/BD/manuscrito/revisor → aviso ao editor → leitura pelo editor atribuído, sem poder atribuir. Outros editores/revisores e mandato revogado são recusados.

`test_editorial_decisions_internal_notes_revision_and_publication` cobre pedido ao autor, resposta, versão 2, preservação do hash original, reavaliação, aceite, rascunho e publicação separada. `test_article_requires_independent_review_and_approval` verifica o fluxo do portal, distinto do manuscrito científico. Não se inventou mínimo obrigatório de pareceres para manuscritos: a política existente admite aceite na triagem. Alterar isso ou dar atribuição de revisores ao editor associado requer definição editorial; esta correcção concede apenas consulta.

## J. Segurança

Protecções verificadas: autenticação/2FA/CSRF, expiração e vínculo de sessão, revogação ao próximo pedido, âmbito por permissão, dono, atribuição, conflito, versão e fase; documentos/manuscritos/pareceres privados. Contas históricas mantêm compatibilidade preexistente, sem ampliar privilégios. Relatórios científicos não ficam públicos nem disponíveis ao Secretariado apenas por `manuscript.read`. Não é uma certificação formal ou pentest de todos os endpoints.

## K. Testes automatizados e resultados

- `DATABASE_URL=sqlite:////tmp/sussurros-audit-final2.db SECRET_KEY=<isolada> ADMIN_TOTP_SECRET=<sintético> /tmp/sussurros-venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`: **219 testes aprovados**, 42,640 s (antes da correcção final de contas não ligadas); os **6 testes da auditoria** passaram depois dessa correcção em 5,283 s, Python 3.12. A suite final terá 220 testes, incluindo seis novos; a execução completa final será confirmada no CI. Os subcasos percorrem todo o catálogo e funções.
- Navegador local com Playwright 1.64 e executável Chromium 153 alternativo: execução completa inicial deu **61 aprovados e 1 falha de selector no teste novo**. Corrigido o selector; `npx playwright test tests/browser/editorial-audit.spec.js --config playwright.local.cjs`: **1 aprovado**, 3,9 s. São 61 regressões aprovadas + o novo percurso aprovado separadamente. Não se apresenta isto como execução completa final única.
- Servidor Gunicorn isolado, mesma base SQLite sintética, sem SMTP. Preferência de sistema clara/escura e larguras 320/390/1440 no teste novo; sem overflow global e sem erros JS. Captura de 390 px inspeccionada; tabela possui scroll horizontal próprio.
- `npm run build:css`, `node --check tests/browser/editorial-audit.spec.js`, `git diff --check`: aprovados. `app.py`, configuração e modelos sem alterações.
- PostgreSQL 18, migrações/restauro, dependências e Docker desta alteração: execução remota do PR ainda pendente ao escrever este ficheiro. O corpo do PR regista o resultado posterior com links. Nenhum resultado antigo foi reutilizado como teste desta revisão.

## L. Regressões

A suite existente cobre artigos/revistas/PDF, Google, favoritos, sino, administração, ficheiros, recuperação de login, migrações, permissões e publicação programada. Nenhum teste existente foi enfraquecido ou removido. A primeira execução do novo teste de navegador falhou por selector ambíguo entre sino e parecer; corrigido para `td details summary`, sem alterar comportamento da aplicação.

## M. Integração

Alterações preparadas numa branch de auditoria sobre o conteúdo de `main` identificado no início. O corpo do PR associado documentará URL, commit, verificações e integração efectivamente realizadas; este registo local não declara merge antecipadamente.

## N. Produção

Nenhuma funcionalidade validada em produção nesta auditoria. Sem deploy no Coolify, migração real, leitura da base real, conta Google real ou entrega SMTP. Não confundir êxito de CI com aplicação da alteração no site.

## O. Pendências

- Inventário real de funções personalizadas, titulares e mandatos; causa histórica específica do Secretariado.
- Estado/responsável da tarefa «Organizar documentos da revista» e aceite institucional real.
- Validação operacional após deploy autorizado, com contas de ensaio e dados apropriados.
- Definições editoriais para mínimo de pareceres, revisão anónima, anexos ao parecer, delegação de atribuições e versionamento documental formal, se desejadas. Não implementadas como regras inventadas.
- Modos escuros administrativos não existentes; os testes de preferência do sistema não demonstram um tema escuro administrativo.

## P. Próximos passos

Após CI aprovado, disponibilizar a alteração pelo processo existente. No ambiente correcto, executar o diagnóstico de leitura com `DATABASE_URL` já configurado, conferir mandatos do Secretariado e validar os dois registos históricos sem os recriar. Fazer ensaio operacional com contas autorizadas para submissão/revisão/decisão e confirmar a entrega de correio configurada. **A auditoria de produção não está integralmente validada enquanto estas verificações estiverem pendentes.**
