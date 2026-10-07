# Auditoria e correcção de funções e permissões — 08/10/2026

Base remota inspeccionada: `main`, commit `5f56f08c7e1cde8052df7eeebd89326dc347a95a` (PR #152 integrado). Estas alterações são propostas numa branch; não foram integradas nem aplicadas em produção.

## Evidência e causas

- `governance.has_permission` exige membro activo, aceite, conta activa e mandato vigente. Um mandato de revista não satisfaz um pedido de permissão institucional sem revista. Isso explica como uma permissão guardada pode não ser efectiva, mas **não comprova o estado concreto do colaborador em produção**. Não foi possível consultar essa base de dados nesta sessão.
- `has_any_permission` anteriormente aceitava qualquer âmbito para todas as permissões, enquanto os controlos do servidor usavam o âmbito geral. Agora distingue explicitamente permissões de revista e gerais; o formulário de funções e a área de trabalho explicam o requisito e mostram acessos efectivos e bloqueios.
- `scope_manuscripts`, `manuscript_access` e o menu Submissões não consideravam `manuscript.assign` e `manuscript.decide` como acesso contextual ao registo. Essas permissões isoladas ficavam sem caminho até à acção. Corrigidos lista, detalhe, menu, filtros e transições sem conceder edição, pareceres ou produção.
- A interface de tarefas só tinha o formulário dentro da Área de trabalho. Acrescentado acesso explícito «Distribuir tarefas» e âncora para o formulário, respeitando o mesmo `tasks.manage` do servidor.
- `journal_access` fazia publicação científica depender de produção científica; `journal_scope` e menus também ignoravam o utilizador que só publica. Agora publicar/ocultar, consultar pré-visualização e editar são verificações distintas. Publicação científica usa sempre a revista de origem, não o ID do rascunho gerado.
- O editor de revistas verificava a permissão ao publicar, mas não ao ocultar pelo formulário. Agora verifica qualquer mudança do estado de publicação e a interface preserva o estado quando o editor não tem essa permissão.
- A lista de artigos ignorava o utilizador com apenas `article.delete`; o editor era apresentado a escritores para artigos que não podiam editar e a publicadores. Corrigidos os acessos por recurso e criada publicação/programação directamente no fluxo, com aprovação obrigatória, sem abrir edição.
- Fluxos ainda não persistidos dependiam do valor default de `ArticleWorkflow.stage` no flush, em vez de um estado explícito, e exigiam edição global mesmo para o autor. Estado inicial agora explícito, GET sem INSERT e primeira submissão do autor testada. Esta fragilidade foi corrigida; não é possível atribuir com certeza a mensagem anterior em produção a esta única causa sem reproduzir a acção exacta.
- Filtragem da lista de manuscritos só considerava o e-mail do membro, enquanto o detalhe também considerava o da conta. Agora ambos excluem os mesmos conflitos. Opções de revisores excluem conflitos e indisponibilidade.
- Não foi encontrado armazenamento das permissões na sessão nem cache de permissões. O JSON de funções é substituído e confirmado em transacção, e consultado na próxima requisição. Testes cobrem alterações reais do formulário, revogação na sessão existente e preservação de funções personalizadas/identificadores desconhecidos. Esses identificadores são preservados, mas não autorizam operações inexistentes.

## Contrato de âmbito e combinação

A união dos mandatos é calculada **por permissão**. Uma função com atribuição na revista A e outra com decisão na B não passa a atribuir na B nem decidir na A. Mandatos gerais cobrem todas as revistas para permissões de revista. Substituto indicado não herda permissões.

Permissões institucionais e do portal exigem mandato geral porque os recursos actuais — artigos de divulgação, tarefas, contactos, equipa e auditoria — não têm uma revista associada. Um mandato limitado a uma revista não deve dar acesso global a esses recursos. Esta correcção não transforma automaticamente esses mandatos em gerais. Para o caso observado, a auditoria de configuração abaixo permite confirmar se o fundador precisa de atribuir um mandato geral, conforme a sua decisão.

Conta administrativa inactiva revoga a sessão. Estado do membro, aceite, vigência, role JSON, âmbito, autoria, atribuição, fase e versão são consultados no servidor. Os formulários usam essas mesmas verificações; esconder botões não substitui autorização.

## Matriz das funções padrão reais

Esta tabela vem de `DEFAULT_ROLES`; não substitui as escolhas guardadas. Funções personalizadas da base de produção só podem ser enumeradas pelo diagnóstico de leitura, não pela memória nem por nomes inventados.

| Código | Nome exacto | Permissões padrão |
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

## Matriz de todas as permissões reais

Geral = mandato geral. Revista = âmbito específico ou geral. O catálogo tem 24 identificadores. «Gerir autores e categorias» e «Gerir revistas e publicar revistas» são pares de permissões distintas. Não existe `submissions.manage` nem um rótulo «Gerir submissões» no catálogo: existe **Gerir subscritores** (`subscribers.manage`) e as permissões específicas de submissões abaixo.

| Identificador / rótulo exacto | Âmbito | Interface | Rotas e acções |
|---|---|---|---|
| `team.manage` — Gerir equipa, convites e mandatos | Geral | Equipa e convites; Documentos da equipa | `/admin/equipa`, `/admin/documentos-equipa`. Registar/editar membros e convites; entregar documentos. Ligar contas, criar/terminar mandatos e alterar funções continuam reservados ao fundador. |
| `tasks.manage` — Distribuir tarefas | Geral | Distribuir tarefas; Área de trabalho | `/admin/trabalho`. Formulário de atribuição, todas as tarefas, estado e comentários. Sem este poder, apenas tarefas próprias com mandato válido. |
| `reports.read` — Consultar relatórios e auditoria | Geral | Relatórios e auditoria | `/admin/relatorios-equipa`. Consulta institucional da actividade e últimos 200 registos; não concede acesso aos ficheiros de manuscritos. |
| `article.write` — Escrever artigos próprios | Geral | Artigos → Novo artigo / Editar / Fluxo editorial | `/admin/artigos/novo`, `/admin/artigos/<id>/editar`, `/admin/fluxo-artigos/<id>`. Perfil de autor associado obrigatório. Criar/editar/submeter artigos próprios; conteúdo aprovado/publicado exige reabertura por editor. |
| `article.edit` — Editar todos os artigos | Geral | Artigos → Editar / Fluxo editorial | `/admin/artigos/<id>/editar`, `/admin/fluxo-artigos/<id>`. Editar todos, submeter, atribuir revisor independente ou reabrir. Não implica rever, aprovar ou publicar. |
| `article.review` — Rever artigos atribuídos | Geral | Artigos → Fluxo editorial | `/admin/fluxo-artigos/<id>`. Só artigos atribuídos: parecer concluído ou correcções. Revisor diferente do autor, disponível e com mandato válido. |
| `article.approve` — Aprovar artigos revistos | Geral | Artigos → Fluxo editorial → Aprovar | `/admin/fluxo-artigos/<id>`. Só depois do parecer; responsável diferente do autor e revisor. Não publica. |
| `article.publish` — Publicar artigos aprovados | Geral | Artigos → Fluxo editorial → Publicar / Programar | `/admin/fluxo-artigos/<id>`. Só fluxo aprovado, com aprovação registada. Não abre o editor nem altera o texto. |
| `article.delete` — Eliminar artigos | Geral | Artigos → Eliminar | `/admin/artigos/<id>/eliminar`. Eliminação de artigos; bloqueada quando existem pareceres. Não concede edição. |
| `authors.manage` — Gerir autores | Geral | Autores | `/admin/autores`, `/admin/autores/<id>/eliminar`. Criar/editar/eliminar perfis; perfis usados por artigos ou membros não podem ser eliminados. |
| `categories.manage` — Gerir categorias | Geral | Categorias | `/admin/categorias`, `/admin/categorias/<id>/eliminar`. Criar/editar/eliminar categorias; mantém protecções de categorias usadas. |
| `journal.manage` — Gerir revistas | Revista | Revistas → Editar / Pré-visualizar / PDF / Eliminar | `/admin/revistas`, `/admin/revistas/<id>/editar`, `/admin/revistas/<id>/eliminar`. Revistas no âmbito; criar revista exige âmbito geral. Publicações ligadas a manuscritos exigem produção científica; não publica/oculta sem journal.publish. |
| `journal.publish` — Publicar revistas | Revista | Revistas → Pré-visualizar / PDF / Publicar / Ocultar | `/admin/revistas/<id>/publicacao`. Publicar/ocultar no âmbito. Nas publicações científicas, âmbito é a revista de origem, estado produção/publicado e conteúdo preparado. Não concede edição. |
| `manuscript.read` — Consultar submissões da revista | Revista | Submissões → Detalhes / Ficheiros | `/admin/submissoes`, `/admin/submissoes/<id>`, `/submissoes/ficheiros/<id>`. Consultar submissões não rascunho da revista; sem acções editoriais; bloqueio de conflitos de autoria. |
| `manuscript.edit` — Tratar submissões atribuídas | Revista | Submissões → Detalhes → Notas e transições | `/admin/submissoes/<id>`. Apenas editor atribuído e revista autorizada. Notas internas e transições de acompanhamento; aceite/rejeição exigem decidir. Fundador mantém acesso global. |
| `manuscript.assign` — Atribuir editores e revisores | Revista | Submissões → Detalhes → Atribuir editor / revisores | `/admin/submissoes/<id>`, `/admin/pareceres?manuscript_id=<id>`, POST `/admin/pareceres`. Acesso contextual ao registo da revista para atribuir editores/revisores válidos. Exclui conflitos, indisponíveis e duplicados por versão. Não emite decisão. |
| `manuscript.decide` — Emitir decisões científicas | Revista | Submissões → Detalhes → Decisão | `/admin/submissoes/<id>`. Acesso contextual para aceite/rejeição nas transições permitidas, com fundamentação e notificações em fila. Não concede notas, produção ou publicação. |
| `manuscript.production` — Preparar artigos científicos | Revista | Submissões → Preparar para publicação; Revistas → Editar rascunho | `/admin/submissoes/<id>/preparar`, `/admin/revistas/<publication_id>/editar`. Só aceite/produção/publicado, no âmbito da revista de origem. Preparação importa conteúdo e metadados e mantém o original privado. Não publica sem journal.publish. |
| `manuscript.review` — Emitir pareceres atribuídos | Revista | Meus pareceres → Abrir parecer | `/admin/pareceres/<id>`, `/admin/pareceres/<id>/ficheiros/<file_id>`. Só atribuição própria e mandato da revista; declarar conflito/aceitar/recusar/emitir parecer. Ficheiros apenas após aceite, versão corrente e fase válida; não decide o manuscrito. |
| `submissions.configure` — Configurar submissões | Revista | Submissões → Configurar submissões | `/admin/submissoes/configuracao`. Revistas autorizadas: tipos, formatos, e-mail editorial e activação. Não concede acesso às submissões. |
| `policies.manage` — Gerir políticas editoriais | Geral | Políticas Editoriais | `/admin/politicas-editoriais`, `/admin/politicas-editoriais/previsualizar`. Guardar políticas e API de pré-visualização. Não concede decisão científica. |
| `comments.manage` — Moderar comentários | Geral | Comentários | `/admin/comentarios`, `/admin/comentarios/<id>/estado`, `/admin/comentarios/<id>/eliminar`. Aprovar/rejeitar/eliminar comentários. |
| `contacts.manage` — Gerir contactos | Geral | Contactos | `/admin/contactos`, `/admin/contactos/exportar.csv`, `/admin/contactos/<id>/eliminar`. Consultar, marcar como lidos pelo comportamento existente, exportar e eliminar contactos. |
| `subscribers.manage` — Gerir subscritores | Geral | Subscritores | `/admin/subscritores`, `/admin/subscritores/<id>/estado`, `/admin/subscritores/exportar.csv`. Consultar, activar/desactivar e exportar subscritores. Não é uma permissão de gestão de submissões. |

APIs de upload `/admin/api/imagens` e `/admin/api/videos`, e pré-visualização Markdown `/admin/revistas/previsualizar-markdown`, exigem pelo menos `article.write`, `article.edit`, `manuscript.production` ou `journal.manage`, conforme o âmbito aplicável. Apenas renderizam conteúdo enviado ou validam ficheiros; não concedem leitura nem alteração de recursos de outras revistas. APIs de políticas exigem `policies.manage`. Login, 2FA, CSRF, sessões vinculadas a credenciais e respostas `no-store` mantidos.

A Área de trabalho, notificações próprias e documentos próprios continuam acessíveis sem poderes de gestão. Actualizar tarefa recebida exige membro activo e algum mandato vigente. Documentos próprios e aceite continuam disponíveis a convidados, para permitir o próprio processo de entrada; um convite não recebe outras permissões automaticamente.

## Inconsistências de padrões separadas das correcções

- `team.manage` tem o rótulo «Gerir equipa, convites e mandatos», mas a política existente reserva criação/fim de mandatos e ligação de contas ao fundador. Essa reserva foi preservada e explicada na interface; delegá-la com controlo contra auto-elevação seria uma decisão de política adicional.
- `secretariat` padrão só contém tarefas e leitura de manuscritos. Contactos, relatórios e escrita só estarão disponíveis se o fundador os guardar na função e o mandato for geral. Não foram adicionados por defeito.
- `coordination` padrão não aprova nem publica. `publisher` padrão publica artigos do portal, não revistas científicas. Não foram alterados para fazer aparecer botões.
- `chief_editor` contém edição atribuída e atribuição. O editor principal colaborador pode atribuir-se um manuscrito autorizado antes de fazer acompanhamento; decisão científica continua independente da permissão de edição. O fundador mantém o acesso global existente.

## Testes e resultados

**Resultado local: 177 testes Python aprovados** (`python -m unittest discover -s tests -p 'test_*.py' -v`), incluindo 13 novos testes de matriz com múltiplos subcasos. `node --check tests/browser/permissions.spec.js` e `git diff --check` aprovados. Dados sintéticos isolados; nenhuma operação de validação em conteúdo real, nenhuma entrega SMTP. Importação TXT e publicação científica exercitadas pelo servidor real de testes, sem mocks dessas acções.

`tests/test_permission_matrix.py` percorre as 24 permissões isoladas: interface, operação com resultado persistido, revogação, expiração, início futuro, suspensão, falta de aceite e conta inactiva. Percorre os nove poderes de revista fora do âmbito e os 15 gerais limitados indevidamente a uma revista. Testa união de mandatos sem cruzar privilégios, atribuição real de revisor, aprovação/publicação separadas, configuração personalizada e diagnóstico sem escritas. As suites existentes mantêm testes de autoria, terceiros, conflitos, documentos, tarefas, 2FA e CSRF.

**Resultado inicial do CI:** 37 testes de navegador aprovados, incluindo o teste novo de colaborador, além de testes Python, migração/restauro PostgreSQL 18, auditoria de dependências e Docker build.

Teste novo de navegador: `tests/browser/permissions.spec.js` usa conta colaboradora sintética, verifica menus/formulário em desktop e mobile, cria tarefa e artigo próprios, abre atribuições numa submissão e revoga sem novo login. Fixture apenas nos testes; não adiciona bypass à aplicação.

## Base de dados e diagnóstico da configuração actual

Não há alteração ao esquema, seed de padrões, migração nem necessidade de repetir `alembic upgrade head` para este PR. O head esperado continua `20261007_02`. Não alterar `AUTO_SCHEMA_UPGRADE`.

Para inspeccionar o catálogo **guardado na base de dados** e os pré-requisitos efectivos, executar no terminal da aplicação após disponibilizar esta branch num ambiente de teste:

```bash
python scripts/audit_permissions.py
```

O script não importa a aplicação Flask, não executa seeds ou actualização de esquema e abre uma transacção de leitura (`SET TRANSACTION READ ONLY` em PostgreSQL / `PRAGMA query_only` em SQLite). Mostra todos os códigos, nomes e permissões de funções reais, IDs dos membros e mandatos válidos, permissões gerais e por revista, e identificadores bloqueados. Não exporta palavras-passe, TOTP, e-mails, documentos nem conteúdo de artigos. Pode ser executado contra a configuração actual com a variável `DATABASE_URL` já existente; não é necessário colar credenciais.

Sem esse resultado, permanece pendente confirmar exactamente o estado, aceite, associação de autor, revista e escolhas do Secretariado em produção. Não foi feita qualquer alteração à base de produção.

## Checklist final em staging, com contas sintéticas

- [ ] Responsável principal com 2FA: verificar acesso completo e catálogo personalizado preservado; criar mandatos de teste, sem tocar nos existentes.
- [ ] Secretariado de teste, membro activo/aceite/conta activa, mandato geral: guardar apenas tarefas, escrita, relatórios e contactos; verificar acessos efectivos, menu, atribuição de tarefa e artigo próprio.
- [ ] Secretariado limitado à revista A: confirmar que apenas os poderes de revista são efectivos; diagnóstico deve indicar quais poderes gerais não se aplicam.
- [ ] Editor atribuído à A: abrir só os manuscritos atribuídos; negar outro editor e revista B.
- [ ] Responsável com apenas atribuição na A: abrir detalhe, atribuir editor e revisor válidos; negar decisões, produção e revista B.
- [ ] Responsável com apenas decisão na A: emitir decisão permitida fundamentada; negar notas de edição, atribuição e revista B.
- [ ] Revisor próprio: aceitar sem conflito, obter apenas ficheiros da versão actual e emitir parecer; negar ficheiros antes do aceite, de outro revisor e após mudança de versão.
- [ ] Autor do portal → revisor independente → aprovador distinto → publicador: verificar transições e que cada conta só dispõe das suas acções; alterações de conteúdo exigem nova revisão.
- [ ] Produção na A → publicador de revistas na A: preparar rascunho, editar pela produção, publicar pelo publicador sem lhe dar edição; negar publicador da B.
- [ ] No mesmo login, conceder/revogar no catálogo e terminar/expirar mandato: próxima requisição deve reflectir a mudança. Repetir com conta/membro inactivo.
- [ ] Com múltiplos mandatos, confirmar união por permissão sem transferir âmbito entre revistas.
- [ ] Receber tarefa, actualizar estado/comentário, ler documento próprio e registar aceite; negar recurso de terceiro; repetir sem CSRF.
- [ ] Verificar desktop/mobile e concluir CI do PR. Não usar conteúdo real para publicar/eliminar nos testes.

## Limitações

Não foram executadas verificações novas no site de produção nem acções no Coolify. O histórico de capturas apenas confirma a migração anterior e o aparecimento do fluxo; não comprova as correcções propostas. A instalação local de Chromium falhou por download incompleto; o CI executou efectivamente o novo teste e a suite completa: **37 testes de navegador aprovados**, incluindo o colaborador sintético. O resultado do último commit está nos checks do PR. PostgreSQL local indisponível; a execução inicial do CI passou a migração/restauro em PostgreSQL 18, testes Python, auditoria de dependências e Docker build. A verificação do último commit é acompanhada no PR. Esses resultados são reportados separadamente dos testes locais.
