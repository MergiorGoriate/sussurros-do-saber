# Artigos geridos pelo administrador principal

O administrador principal pode iniciar e gerir o fluxo de um artigo cujo autor não está associado à equipa. Não são criados colaboradores, mandatos ou permissões. O perfil público do autor continua a ser `Article.author_rel`; criar ou editar um artigo não altera a sua autoria pública.

`ArticleWorkflow.owner_id` é opcional. `primary_owned` identifica a responsabilidade editorial assumida pela conta principal quando não existe um membro associado ao autor. Não constitui uma inferência de identidade pelo nome nem prova de que a pessoa que introduziu o texto seja o autor.

O administrador principal pode aprovar e publicar qualquer artigo directamente, incluindo textos da sua autoria ou de um colaborador removido. No fluxo, pode usar **Aprovar e publicar sem revisão** ou **Publicar directamente**. A aprovação mantém o comportamento existente de publicar imediatamente. No editor, pode seleccionar **Publicado**, inclusive ao criar um artigo ou alterar o conteúdo de um artigo aprovado. Estas operações exigem sessão principal válida, autenticação de dois factores, CSRF e conteúdo completo.

A decisão directa regista eventos de aprovação e publicação com o responsável, a data e a indicação de que a revisão foi dispensada. Os pareceres anteriores são preservados; não é criado um parecer fictício. Repetir o botão do fluxo num artigo já publicado não duplica os eventos. A correspondência de e-mails, os mandatos e a revisão independente continuam a ser verificados nas operações dos colaboradores secundários.

Fluxos de colaboradores conservam os vínculos existentes. Publicar um artigo de um colaborador removido não reactiva a sua conta nem os seus mandatos. Mudar a autoria invalida a revisão anterior; o administrador principal pode emitir uma nova decisão directa de publicação. A conta principal recebe as notificações internas do fluxo, incluindo quando usa a autenticação configurada por variáveis de ambiente.

## Aplicação

A migração `20261022_09` preserva os fluxos existentes e torna a associação à equipa opcional. Execute no ambiente da aplicação, com a ligação habitual à base de dados:

```sh
python -m alembic upgrade head
```

O mecanismo existente de compatibilidade no arranque também aplica a actualização quando `AUTO_SCHEMA_UPGRADE=true`. Com esse mecanismo desactivado, a migração deve preceder o arranque do novo código. A actualização é idempotente, utiliza o bloqueio de migrações existente no PostgreSQL e a operação batch do Alembic no SQLite. O downgrade destrutivo é recusado para preservar fluxos sem membro associado.

Depois da actualização, basta ao administrador principal voltar a abrir o fluxo do artigo. Não é necessário associar a sua conta à equipa. Consultar a página não grava um novo fluxo; uma acção editorial válida grava-o.
