# Auditoria funcional do portal — 8 de Outubro de 2026

## Base e limites

Base remota: `959197757b21d800639081cfa51d88ef7f27b62a` (PRs 154–156 integrados).
A auditoria examinou autorização, mandatos, transições editoriais, notificações, favoritos e relações de eliminação. Executou a suite automatizada existente e acrescentou regressões para falhas concretas. Não significa que todos os problemas possíveis do portal estejam eliminados.

Não foram usados dados de produção, contas reais, credenciais do Coolify ou uploads reais no Cloudinary. Não foi feito deploy nem integração do PR. Não há migração adicional: a versão exigida continua `20261008_03`.

## Falhas identificadas e correções

| Falha | Evidência no código anterior | Comportamento corrigido |
| --- | --- | --- |
| Reatribuir revisor conservava aprovação e agendamento | `governance.responsibilities` apenas alterava `reviewer_id` | Reatribuição põe artigo em revisão, cancela agendamento e limpa revisão/aprovação/editor; conserva o parecer histórico. Nova revisão independente é obrigatória. |
| Publicação automática sem aviso nem auditoria | `Article.publish_due_scheduled` actualizava apenas Article/ArticleWorkflow | Publicação cria evento de auditoria e avisos na mesma transação, com chave única; repetir a execução não repete o evento. |
| Agendamento de fluxo gerido sem aprovação podia publicar | Scheduler não verificava aprovação nem estágio do fluxo | Artigo gerido só publica se fluxo estiver programado e aprovado. Artigos legados sem fluxo conservam o comportamento existente. |
| Repetir conclusão de revisão criava vários pareceres/avisos | Ramo `reviewed` permanecia disponível depois de `reviewed_at` | Mesmo parecer repetido é idempotente; alterar um parecer concluído exige reabrir o fluxo. |
| Conta gerida sem membro via resumo global | `dashboard` verificava apenas `current_member()` | Conta com `governance_managed=True` vai à Área de trabalho mesmo sem vínculo; não recupera poderes legados. |
| Eliminar artigo com favoritos deixava FK de ReaderArticle | `delete_article` não limpava preferências | Elimina apenas preferências do artigo eliminado; preserva outros favoritos e conteúdos; artigos com pareceres continuam protegidos. |
| Eliminar revista com favoritos/mandatos podia quebrar FK | `delete_journal` não verificava TeamAppointment/PublicationAsset nem ReaderJournal | Bloqueia eliminação quando existe histórico de mandatos ou ficheiros editoriais; limpa apenas preferências de revista elegível para eliminação; regista auditoria. |
| Contador não anunciado pelo leitor de ecrã | `aria-label` fixo prevalecia sobre texto descendente do sino | Rótulo acessível contém número de avisos por ler, actualizado com o resumo. |

A publicação programada e os pedidos de edição/transição/reatribuição bloqueiam primeiro o artigo e depois o fluxo para serializar alterações concorrentes. `skip_locked` no scheduler permite que outros workers ignorem artigos já em processamento. Não foi realizado teste de carga ou prova de todas as combinações concorrentes.

## Validação

- Base existente: 199 testes Python passaram localmente.
- Oito novos testes executados contra cópia isolada do código anterior: 10 falhas de asserção (incluindo subcasos de reatribuição).
- Os mesmos oito testes passam após as correções.
- Suite completa e navegador: resultados finais constam do PR/CI.
- CI PostgreSQL 18 inclui nova base isolada `functionality_fixture`, migração e execução dos oito testes com chaves estrangeiras reais.
- `git diff --check` e sintaxe JavaScript verificados.

## Cobertura e validações ainda pendentes

| Área | Verificação automatizada | Verificação no site |
| --- | --- | --- |
| Permissões, âmbitos, mandatos, revogação e sessões | Suites permission_matrix, staff_governance e admin_security | Contas de teste em ambiente de homologação pendentes |
| Tarefas, documentos e aceites | staff_governance e lifecycle_notifications | Pendentes no Coolify |
| Revisão, aprovação, publicação e reatribuição | Suites editoriais + functionality_audit | Fluxo completo de contas separadas pendente |
| Notificações, leitura, eliminação, persistência e contador | Suites lifecycle/reader + navegador | Eventos reais de homologação pendentes |
| Google, favoritos e bibliotecas | Suites google_auth/reader + navegador com fixtures | One Tap real e provedor Google pendentes |
| Revistas, metadados, DOI e PDF | Suites journal_metadata/journal_pdf/platform + navegador | DOI externo, PDFs reais longos e ficheiros de produção pendentes |
| Vídeos e armazenamento | Validação de payloads e mocks existentes | MP4/WebM/OGG reais, Cloudinary e reprodução em aparelhos físicos pendentes |
| Segurança e base de dados | CSRF, 2FA, sessões, migrações e restore drill | Configuração real do VPS, backups e monitorização pendentes |
| SEO, acessibilidade e desempenho | Regressões de páginas e navegador; rótulo do sino | Search Console, medição de desempenho e auditoria integral de acessibilidade pendentes |

## Checklist de homologação

1. Aplicar o código em homologação com cópia sanitizada da base de dados e schema `20261008_03`.
2. Usar contas separadas de autor, revisor, editor, publicação e fundador.
3. Rever e aprovar um artigo de teste; programar; reatribuir revisor; confirmar cancelamento da programação e nova revisão obrigatória.
4. Programar outro artigo de teste e confirmar uma única publicação, auditoria e aviso por destinatário; repetir acesso à página.
5. Repetir o POST de conclusão do mesmo parecer e confirmar ausência de duplicação.
6. Retirar o vínculo de uma conta gerida de teste e confirmar ausência de resumo global e menus indevidos.
7. Eliminar apenas artigo/revista de teste com favoritos; confirmar preservação dos favoritos de outros recursos.
8. Confirmar bloqueio de eliminação de revista de teste com mandato, incluindo mandato terminado.
9. Verificar sino, contagem anunciada, leitura/eliminação e foco no computador e telemóvel.
10. Validar os serviços externos acima antes de declarar o portal integralmente validado em produção.
