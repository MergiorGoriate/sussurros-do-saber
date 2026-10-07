# Remoções e notificações internas

## Base e causas

Base: `main` após o PR #153 (`7197475e4db69ae0960fae329effa41a0636a71a`). Preserva as 11 funções e 24 permissões reais e as configurações personalizadas. A matriz anterior permanece em [PERMISSIONS_AUDIT.md](PERMISSIONS_AUDIT.md).

- `StaffNotice` já guardava avisos de alguns fluxos, mas `/admin/notificacoes` apenas permitia ler um aviso. Não existiam eliminação por destinatário, leitura global, contador ou barra ligada à mesma consulta.
- `EditorialNotification` é a fila externa editorial preexistente, não a caixa interna. O novo mecanismo usa `StaffNotice`; não acrescenta email nem outros canais externos.
- `StaffDocument` e `Manuscript` não tinham arquivo lógico. `GovernanceAudit` representa eventos, não relatórios individuais. Foi criada a entidade `AuditReport` com uma fotografia imutável dos eventos.
- O colaborador tem `TeamMember`, `AdminUser` e mandatos separados. A remoção tem de revogar todas essas concessões e invalidar sessões, sem apagar autoria ou pareceres.
- Na validação integrada foi identificada uma consulta adicional: `publication_saved` podia procurar `publication_id IS NULL` quando a revista nova ainda não tinha ID. A nova revista é agora persistida na transação antes da consulta, evitando associação a submissões não ligadas.

## Operações exclusivas do fundador

Todas usam o mecanismo existente `superadmin_required`: identidade autenticada, marca de segurança actual, 2FA e `admin_superuser` derivado da conta actual. Não foi criada uma permissão que um gestor de equipa possa conceder a si próprio.

| Item | Acesso e operação | Preservação e limites |
|---|---|---|
| Submissão | Lista e detalhes → confirmação → POST `/admin/remover/manuscript/<id>` | `removed_at`; fora da lista activa, de novas decisões, preparação, avaliações e operações do autor. Versões, anexos, pareceres, decisões, publicação e DOI preservados. Histórico e downloads arquivados apenas pelo fundador. |
| Colaborador | Equipa e convites → confirmação → POST `/admin/remover/member/<id>` | Estado terminado, mandatos inactivos, conta administrativa inactiva e nova versão de segurança. Sessão aberta bloqueada na próxima requisição, mesmo se a conta for reactivada por outro formulário. Convite representado pelo estado do membro encerrado. Conta pública independente, perfil de autor, artigos e histórico preservados. Não permite remover o fundador. |
| Documento | Documentos da equipa → confirmação → POST `/admin/remover/document/<id>` | Fora das listas activas; sem novos aceites. Mesma versão, texto, anexo, `accepted_at` e `accepted_by` preservados, inclusive sem anexo. Histórico do fundador permite consulta e download. |
| Relatório | Gerar/guardar em Relatórios e auditoria → confirmação → POST `/admin/remover/report/<id>` | Arquiva só a fotografia guardada. Eventos de `GovernanceAudit` não são eliminados. Guarda até 1.000 eventos recentes por relatório e mantém lista separada dos 200 eventos exibidos na página. |

Confirmações mostram nome, identificador e consequências. GET e Cancelar não alteram dados. POST exige CSRF e confirmação explícita. Repetir a remoção mantém o estado e não duplica o evento de auditoria. Não foram executadas remoções de dados reais.

Histórico: `/admin/historico-remocoes`, exclusivo do fundador. O catálogo actual não tem uma tabela ou token de convite de equipa independente: o convite é o membro em estado convidado, associado à conta administrativa. A remoção encerra essa associação e impede novos mandatos. Tokens de autenticação das contas públicas independentes não são revogados.

### Responsabilidades

`/admin/equipa/<id>/responsabilidades` mostra tarefas pendentes, submissões ainda activas como editor, pareceres convidados/aceites e responsabilidades de autoria/revisão/aprovação em artigos não publicados. Reatribuição exclusiva do fundador, com CSRF e validação do novo mandato, revista e conflitos. Autoria original não muda: um artigo próprio pendente pode receber outro responsável editorial. Um parecer em curso é cancelado e gera uma nova atribuição; a identidade e conteúdo da atribuição anterior ficam preservados. Não reatribui pareceres já entregues ou artigos publicados. O formulário normal de tarefas também permite reatribuição por `tasks.manage`.

## Eventos e destinatários

Os avisos são criados dentro da transação da operação. Falha/rollback não deixa avisos. Uma chave única por evento e destinatário, com INSERT ON CONFLICT, impede a duplicação da mesma chave, inclusive concorrente. Não há reenvio retroactivo dos eventos antigos nem ressurreição de avisos eliminados. Pedidos que não mudam estado de tarefa, função, editor ou mandato não geram novos avisos; confirmações editoriais repetidas inválidas são bloqueadas pelas transições.

| Evento real | Destinatários |
|---|---|
| Convite de colaboração, dados/estado do membro, mandato criado/terminado, remoção | Próprio membro quando associado, fundador e gestores institucionais da equipa |
| Alteração de função | Membros associados a mandatos activos dessa função; não concede a eles novas permissões além da configuração guardada |
| Nova tarefa, estado, comentário, reatribuição | Responsável actual com mandato válido e gestores institucionais de tarefas; criador apenas enquanto conserva `tasks.manage`; responsável anterior recebe aviso de transferência se ainda tem mandato válido |
| Documento disponibilizado | Membro destinatário |
| Aceite e remoção de documento | Membro destinatário, fundador e gestores da equipa |
| Submissão nova/revista, atribuição de editor, nota interna, decisão, preparação, publicação/ocultação, remoção | Fundador e responsáveis com mandato na revista; editor atribuído, gestores de atribuições/decisões; leitores científicos em eventos relevantes; produção em estados aceites/produção/publicação e publicadores científicos quando há produção/publicação |
| Convite para parecer, aceite/recusa/conflito, entrega | Revisor atribuído com mandato válido, editor atribuído e responsáveis científicos da revista; decisões/publicação/remoção chegam também aos revisores aceites/que entregaram parecer na versão actual |
| Eventos visíveis da submissão | Investigador proprietário em caixa interna própria, separada da administrativa; notas internas, atribuições e conteúdo de pareceres não vão para o autor |
| Artigo guardado, submetido, revisor atribuído, revisão, correcções, aprovação, programação/publicação | Autor/responsáveis do fluxo com mandato; após revisão, aprovadores; após aprovação, publicadores |
| Relatório guardado/removido | Fundador e utilizadores com `reports.read` institucional |
| Actualização de artigo público acompanhado | Leitor verificado que acompanha o artigo; chave por acompanhamento/revisão, sem acesso a artigos privados ou de outras contas |
| Lembretes de prazo já existentes | Mantidos, com verificação de conta/mandato/recurso e ligação ao destino |

Destinatários científicos são deduplicados mesmo com múltiplos mandatos. Estado activo, aceite, datas do mandato, revista e conflitos são verificados. Avisos editoriais incluem apenas código/estado e tipo de evento: não copiam notas internas nem pareceres para a caixa de outros intervenientes. Nenhuma permissão geral transforma um mandato de outra revista em acesso ao recurso.

### Caixa, barra e propriedade

- `/admin/notificacoes` e `/admin/api/notificacoes` usam a mesma consulta por conta. Caixa do investigador: `/submissoes/notificacoes` e `/submissoes/api/notificacoes`.
- Barra com cinco avisos recentes; página com paginação de 30, em ordem de data e ID decrescentes. Contador inclui todos os não lidos activos, não só a página.
- Ler individualmente, ler todos e eliminar usam POST com CSRF e filtro de propriedade. Eliminar é lógico, apenas para o destinatário, e mantém o recurso/evento. Repetir a eliminação é idempotente.
- O sino público de `/conta/notificacoes` usa também esta caixa: actualizações de artigos acompanhados são materializadas uma vez por leitor/revisão, depois de a revisão estar guardada. Eliminar um aviso não desactiva o acompanhamento; novas revisões produzem novos avisos. Artigos ocultados e acompanhamentos desactivados ficam fora da lista/contador público. Os cartões de artigos acompanhados permanecem uma secção separada dos avisos.
- Actualização ao abrir a barra e a cada 60 segundos apenas numa aba visível; pedidos não se sobrepõem. Índices por destinatário/eliminação/data/ID. Sem JavaScript as listas e formulários continuam funcionais.
- Estado vazio, carregamento e erro, região de estado acessível, controlo nativo details/summary, foco visível e botões adaptados a ecrãs pequenos.
- Abrir um recurso verifica novamente a autorização; eliminação ou revogação apresenta mensagem e devolve à caixa. O link não transporta direitos. GET não marca avisos como lidos: alterações de leitura são POST.
- Fundador configurado por ambiente mantém a identidade administrativa nula, separada dos investigadores; os avisos desse destinatário só são consultados após autenticação administrativa existente.

## Migração

Nova revisão Alembic: `20261008_03`, sobre `20261007_02`. Acrescenta datas de remoção, metadados/destinatário investigador em `StaffNotice`, índices e `AuditReport`. Mantém avisos antigos, chaves de origem, documentos e aceites. Não altera funções ou listas de permissões.

No momento de integrar/deploy, com backup verificado e no terminal do serviço configurado para a base correcta:

```sh
python -m alembic current
python -m alembic upgrade head
python -m alembic current
```

Resultado esperado: `20261008_03 (head)`. Aplicar a migração antes de iniciar os processos com o código novo: `db.create_all` não actualiza tabelas existentes. Nenhuma migração de produção foi executada neste trabalho. Downgrade destrutivo recusado; rollback de dados exige restaurar backup validado.

## Validação

- Suite Python local final: 199 testes, incluindo 21 novos testes de ciclo de vida/notificações e o caso de rascunho sem código; resultados de CI registados no PR.
- Novos testes: quatro eliminações autorizadas/negadas em várias funções, confirmação/CSRF/cancelamento, repetição, versão documental com e sem anexo, preservação de eventos, sessões já abertas, reatribuição e âmbito, destinatários, múltiplos mandatos, conta inactiva/mandato expirado, leitura/eliminação/contadores/persistência, isolamento entre contas administrativas e investigadores, rollback e deduplicação, revogação e recurso eliminado, revisão/aprovação/publicação.
- Mantidos os testes de matriz das 24 permissões, tarefas, aceite documental, 2FA e segurança do PR #153.
- Migração testada em SQLite vazia, existente e repetida, e com estrutura anterior real das colunas modificadas e dados sintéticos para verificar preservação.
- Playwright acrescenta computador/telemóvel, leitura/eliminação pela barra/página, recuperação de erro, cancelamento, execução das quatro remoções, reatribuição e bloqueio de sessão aberta. Execução em CI e PostgreSQL 18 registadas no PR.

### Checklist com contas de teste

1. Fundador de teste: abrir as quatro confirmações, cancelar; verificar que nada mudou. Depois confirmar e consultar os históricos e auditoria.
2. Secretariado/direcção/coordenação: confirmar ausência das quatro eliminações e 403 em pedidos directos; verificar trabalho permitido e documentos activos.
3. Editor e revisor da revista A e contas da revista B: atribuir, aceitar, entregar parecer e decidir; verificar caixas correctas e nenhum acesso cruzado.
4. Autor, revisor, aprovador e publicador distintos: executar o fluxo do artigo; verificar avisos e impedir publicação antes de aprovação ou por quem só revê/aprova.
5. Remover colaborador numa segunda sessão: verificar bloqueio na primeira sessão e reatribuir as responsabilidades com mandato/âmbito correctos.
6. Por conta: ler um/todos, eliminar um, actualizar e voltar a entrar; conferir contador e aviso fora da lista. Tentar alterar o aviso de outra conta: 404.
7. Eliminar recurso ou revogar mandato após receber aviso: abrir link e verificar mensagem de indisponibilidade e ausência de execução.
8. Conferir ficheiros, pareceres, decisões, aceites, autoria, conta pública, DOI e publicação existentes nos dados de teste após remoções.

### Limites

Não houve acesso à base ou contas reais de produção, nem verificação manual no site publicado. Os testes automatizados de navegador usam servidor e identidades sintéticas de CI. Não houve merge ou deploy. Relatórios guardam uma fotografia dos 1.000 eventos mais recentes; não são uma exportação integral. Avisos antigos sem metadados continuam legíveis, sem inventar ligação ao recurso. Não foram criados eventos para funcionalidades inexistentes nem reconfigurado o catálogo.
