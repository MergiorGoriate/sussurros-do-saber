# Editor e histórico dos artigos do portal

O editor indica a contagem aproximada de palavras e estima a leitura a 200 palavras por minuto. O botão «Usar tempo estimado» preenche o campo editorial; o valor pode ser ajustado pelo editor. Alterações por guardar são assinaladas e o navegador pede confirmação antes de abandonar a página. Nenhum rascunho é enviado ao armazenamento local do navegador.

O histórico é privado e respeita a autorização de edição do artigo. Cada gravação que altera texto, referências ou apresentação cria uma versão com número, data UTC e responsável. O primeiro registo de um artigo existente conserva também o conteúdo anterior, sem atribuir a alteração antiga a uma pessoa desconhecida. Visitar o histórico não cria versões. Não é possível recuperar versões anteriores à implantação que nunca tenham sido registadas.

A comparação mostra campos diferentes com texto escapado. O trabalho de comparação é limitado a 20 000 caracteres e 400 linhas por campo; o texto integral da versão seleccionada continua disponível. As listas têm 20 versões por página.

Recuperar exige POST, CSRF, confirmação e um identificador actualizado do artigo. A versão actual permanece no histórico e o conteúdo recuperado fica em rascunho. As aprovações e a programação são anuladas; os pareceres e a auditoria anteriores permanecem. Autoria, categoria e endereço não são recuperados, para não mudar identidades, ligações nem o âmbito de acesso. O artigo precisa de nova revisão e aprovação. Editores com um formulário antigo recebem 409, conservando o texto submetido na página para o copiarem; devem abrir uma versão actualizada antes de guardar novamente.

## Implantação

Fazer backup e executar no ambiente da aplicação:

```sh
python -m alembic upgrade head
```

A migração `20261018_04` cria apenas `article_revision` e o respectivo índice, com verificação de existência. Não reescreve artigos existentes. A criação idempotente de tabelas no arranque também reconhece o novo modelo; a migração mantém o controlo da versão do schema. Incluir a tabela nos backups. Cada versão contém uma cópia do conteúdo guardado; o espaço necessário cresce com a quantidade e tamanho das alterações. A eliminação definitiva de um artigo, quando permitida pelas regras existentes, elimina também as suas versões; a remoção ou recuperação para rascunho preserva-as.

## Uso do REA

Foi tentada a análise estática de `static/js` com `rea-agents analyze-javascript-application`. O REA interrompeu a operação porque a inspecção de propriedade de processos através de `ps` não está disponível neste ambiente Linux. O resultado parcial não foi considerado uma análise concluída. A implementação e a validação usam directamente o código-fonte do projecto e os seus testes. O setup MCP não foi executado nem foram alteradas configurações do agente.
