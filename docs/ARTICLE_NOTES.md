# Notas de rodapé e referências

No editor de artigos, coloque o cursor no texto, escolha **Nota de rodapé**, escreva a nota e seleccione **Inserir nota**. Uma selecção existente é preservada; a chamada é colocada depois dela. O identificador é escolhido sem reutilizar identificadores existentes.

Também é possível escrever Markdown directamente:

```markdown
Uma afirmação com uma fonte[^fonte]. Outra chamada à mesma fonte[^fonte].

[^fonte]: Nome da fonte e [ligação](https://example.org).
    Continuação da nota com quatro espaços de indentação.
```

A numeração segue a primeira chamada no texto. Cada nota inclui ligações de retorno às chamadas. Notas em secções diferentes recebem identificadores distintos. As ligações funcionam no artigo publicado sem JavaScript. Os URLs HTTP(S) escritos nas notas tornam-se clicáveis; as fontes devem ser verificadas pelo autor.

A pré-visualização usa o mesmo renderizador sanitizado da publicação. O endpoint privado `POST /admin/artigos/previsualizar` exige sessão autenticada, CSRF e permissão `article.write` ou `article.edit`, limita o texto a 400 000 caracteres e não grava alterações. Falhas de pré-visualização mantêm o texto no editor. A gravação manual e a gravação automática existentes preservam a sintaxe das notas.

Não são necessárias migrações de base de dados.
