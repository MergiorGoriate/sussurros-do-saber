# Equipa, funções e fluxos editoriais

## Activação

1. Faça uma cópia de segurança e execute `alembic upgrade head` em staging e depois em produção. A revisão `20261007_02` acrescenta tabelas privadas e colunas em falta sem apagar registos. Não tem downgrade destrutivo.
2. O administrador principal encontra **Equipa e convites**, **Funções e permissões**, **Área de trabalho**, **Documentos da equipa**, **Notificações** e **Relatórios e auditoria** no menu.
3. Em **Administradores**, crie a conta individual. Uma conta nova começa associada a um membro convidado, sem permissões automáticas. A configuração de 2FA continua obrigatória.
4. Complete o perfil e associe o perfil de autor quando necessário. Registe a abordagem, o próximo contacto e o aceite documentado. Um termo privado pode ser aceite pela própria conta ainda convidada; o responsável activa o membro posteriormente.
5. Apenas o administrador principal associa contas e atribui ou termina mandatos. Defina função, âmbito, datas, carga semanal, responsabilidades e substituto. O substituto não recebe permissões automaticamente.
6. Para mostrar alguém em `/equipa`, são necessários estado activo, aceite, consentimento público, visibilidade e um mandato vigente. E-mails, notas de contacto, contratos e pareceres não aparecem nessa página.

## Funções e acesso

São criadas onze funções iniciais: direcção institucional, coordenação, editor científico principal, editor associado, revisor científico, autor, revisor do portal, editor do portal, responsável de publicação, secretariado e produção científica. O principal pode editar objectivos, deveres, limites e permissões, ou criar funções adicionais.

Permissões são verificadas no servidor a cada pedido. Um membro suspenso, sem aceite ou sem mandato vigente perde o acesso funcional. Uma conta anteriormente integrada não recupera privilégios antigos quando é desassociada. Os âmbitos por revista aplicam-se às submissões, à configuração e à produção científica.

**Compatibilidade:** contas secundárias anteriores à integração mantêm os acessos históricos de conteúdo até serem associadas à equipa. Não recebem automaticamente a atribuição de editores/revisores ou decisões finais científicas. Migre essas contas para mandatos explícitos antes de entregar acesso a novos colaboradores. A conta principal mantém autoridade administrativa integral.

A direcção institucional não recebe autoridade científica pela função de direcção. O editor associado só trata as submissões atribuídas; decisões finais de aceitar/rejeitar exigem a permissão científica correspondente. Conflitos de autoria pelo e-mail do membro ou da sua conta impedem acesso editorial. Outros conflitos são declarados pelo revisor e devem ser avaliados pelo editor: não há detecção automática de relações pessoais ou institucionais.

## Artigos do portal

Associe o autor do artigo a um membro. O botão **Fluxo editorial** acompanha rascunho, submissão, revisão, correcções e aprovação. O revisor atribuído deve ser diferente do autor. A aprovação requer um responsável diferente do autor e do revisor. Os pareceres integrais são preservados.

O formulário existente publica ou programa apenas artigos já aprovados no fluxo. Alterar o conteúdo aprovado exige reabrir o rascunho e nova revisão. Um responsável apenas de publicação não pode usar esse formulário para escrever ou reabrir conteúdo. O agendamento mantém a publicação automática em UTC e actualiza o estado do fluxo.

Artigos históricos ainda sem fluxo associado mantêm o comportamento anterior para as contas antigas; associe o autor e abra o fluxo para passar ao processo gerido. Artigos com pareceres não são eliminados: reabra-os como rascunho para os retirar do site e preservar o histórico.

## Submissões e pareceres científicos

No detalhe da submissão, **Atribuir revisores e consultar pareceres** permite seleccionar um revisor disponível com mandato no âmbito da revista e fixar um prazo. Cada convite refere-se a uma versão oficial; não é reaproveitado para a versão seguinte.

O revisor consulta os dados do convite, declara ausência de conflito e aceita antes de descarregar os ficheiros. Pode recusar ou declarar conflito, incluindo depois do aceite. Tem acesso apenas ao manuscrito principal, figuras e tabelas da versão atribuída; documentos suplementares e submissões alheias ficam privados. Uma nova versão ou a saída da fase de avaliação fecha o acesso aos ficheiros e à entrega de parecer.

O parecer fundamentado recomenda aceitar, correcções menores, revisão substancial ou rejeitar; não modifica automaticamente a decisão do manuscrito. O editor principal regista a decisão fundamentada no fluxo existente. A produção abre um rascunho apenas após aceitação; publicação exige permissão e conferência do conteúdo.

**Modelo de revisão:** os originais podem revelar autoria; esta implementação é revisão com autoria identificável. Não anuncia anonimato nem revisão duplamente cega. Para adoptar esse modelo será necessário acrescentar preparação e verificação de cópias anonimizadas.

## Tarefas, documentos e auditoria

A coordenação distribui tarefas com responsável, descrição e prazo. O colaborador actualiza apenas as suas tarefas, com estado e comentários. O relatório apresenta tarefas concluídas/atrasadas e pareceres entregues por membro. Mostra os últimos 200 registos de auditoria; o histórico completo permanece na base de dados.

Documentos privados aceitam texto e PDF/DOCX/TXT validados, até 8 MB. Apenas o gestor autorizado e a conta do membro têm acesso. O aceite regista conta e data; não substitui um serviço de assinatura digital certificada.

Contactos e mudanças de abordagem mantêm histórico com data e responsável. A interface não envia convites nem mensagens externas. Notificações de trabalho ficam no painel. As comunicações científicas ao autor continuam no serviço SMTP existente.

Para lembretes de tarefas, pareceres e fim de mandato, agende diariamente num único worker:

```sh
flask --app app notificar-prazos-equipa
```

A execução é idempotente por registo e data de prazo e não envia e-mails. Sem agendamento, notificações de atribuição continuam disponíveis, mas lembretes de prazo não são gerados automaticamente.

## Validação e publicação

Execute `python -m unittest discover -s tests -p 'test_*.py'`. Os novos testes cobrem isolamento de contas e revistas, suspensão/expiração, documentos privados, CSRF, conflitos, versões de parecer, revisão independente e tentativa de publicar sem aprovação. As migrações são testadas em base vazia e existente com preservação de conteúdo. A CI existente faz também o ensaio de migração PostgreSQL.

Depois da integração do PR, execute a migração antes de iniciar o novo código quando `AUTO_SCHEMA_UPGRADE=false`. Com a configuração histórica de actualização automática, a aplicação cria as tabelas e acrescenta a marca de contas geridas; usar Alembic continua a ser o procedimento de publicação recomendado.
