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


## Gravação automática de rascunhos

Depois do primeiro registo do artigo, o editor guarda automaticamente título, resumo, texto, referências, palavras-chave, DOI e tempo de leitura. Para criar um artigo e permanecer no editor, use **Guardar e continuar**. A primeira alteração de texto é enviada após dois segundos sem edição; as seguintes respeitam um intervalo de pelo menos trinta segundos. Ao ocultar a página, o editor tenta antecipar a gravação pendente. O indicador só confirma a gravação depois de receber a resposta do servidor.

Cada alteração efectiva cria uma versão com responsável e motivo **Gravação automática de rascunho**. A primeira gravação preserva uma versão de base do conteúdo anterior. Pedidos sem alterações não criam versões nem alteram a data. A API privada exige sessão, permissões actuais, CSRF e um token actualizado; a escrita usa uma condição sobre a data de alteração para proteger também SQLite. O endpoint tem limite próprio de doze pedidos por minuto por identidade, em substituição dos limites gerais.

A gravação automática só altera rascunhos; não publica, aprova ou reabre artigos. Alterações de autoria, categoria, endereço, estado, capas, destaque ou ficheiros seleccionados pausam a gravação automática e exigem **Guardar artigo**. Campos inválidos também a pausam. Conteúdo em revisão, aprovado, programado ou publicado exige uma acção manual adequada ao fluxo editorial.

Se outra sessão alterar o artigo, a gravação automática pára e conserva o texto no editor. Copie esse texto e consulte o histórico antes de voltar a guardar. Falhas de ligação mantêm o indicador de alterações por guardar e disponibilizam **Tentar novamente**. Se o servidor tiver guardado mas a resposta se perder, uma nova tentativa pode detectar um conflito; o histórico permite conferir o conteúdo registado. A gravação manual aguarda pedidos automáticos em curso e usa o token mais recente, preservando texto escrito durante o pedido.

Não se guarda conteúdo de artigos em localStorage ou sessionStorage. Fechar o navegador antes de uma confirmação pode perder as alterações ainda pendentes; o aviso de saída permanece activo nessas situações. As alterações confirmadas ficam no servidor e no histórico. Incluir a tabela de versões nos backups. Esta funcionalidade não exige migrações adicionais.
