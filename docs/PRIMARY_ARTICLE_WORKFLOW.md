# Artigos geridos pelo administrador principal

O administrador principal pode iniciar e gerir o fluxo de um artigo cujo autor não está associado à equipa. Não são criados colaboradores, mandatos ou permissões. O perfil público do autor continua a ser `Article.author_rel`; criar ou editar um artigo não altera a sua autoria pública.

`ArticleWorkflow.owner_id` passa a ser opcional. `primary_owned` identifica a responsabilidade editorial assumida pela conta principal quando não existe um membro associado ao autor. Não constitui uma inferência de identidade pelo nome nem prova de que a pessoa que introduziu o texto seja o autor. Por precaução, o administrador principal não pode aprovar estes fluxos; a revisão e a aprovação exigem outros responsáveis elegíveis. A correspondência do e-mail do autor com o membro ou a sua conta também impede uma revisão ou aprovação do próprio texto.

Fluxos de colaboradores conservam os vínculos existentes. Colaboradores removidos não são reactivados através desta excepção. Mudar a autoria invalida a revisão e a aprovação anteriores. A conta principal recebe as notificações internas do fluxo, incluindo quando usa a autenticação configurada por variáveis de ambiente.

## Aplicação

A migração `20261022_09` preserva os fluxos existentes e torna a associação à equipa opcional. Execute no ambiente da aplicação, com a ligação habitual à base de dados:

```sh
python -m alembic upgrade head
```

O mecanismo existente de compatibilidade no arranque também aplica a actualização quando `AUTO_SCHEMA_UPGRADE=true`. Com esse mecanismo desactivado, a migração deve preceder o arranque do novo código. A actualização é idempotente, utiliza o bloqueio de migrações existente no PostgreSQL e a operação batch do Alembic no SQLite. O downgrade destrutivo é recusado para preservar fluxos sem membro associado.

Depois da actualização, basta ao administrador principal voltar a abrir o fluxo do artigo. Não é necessário associar a sua conta à equipa. Consultar a página não grava um novo fluxo; uma acção editorial válida grava-o.
