# Verificação e correcções do portal — 23 de Outubro de 2026

Base analisada: `6e0892a5c46e82caddafe3aa8da0ef39edcc277a`, após a integração da publicação directa pelo administrador principal.

## Falhas confirmadas e correcções

1. **Identificadores de formulários sem limite.** Valores inteiros demasiado grandes em autores, categorias e artigos chegavam ao controlador da base de dados e podiam provocar erros de servidor. A validação passa a exigir identificadores positivos dentro do intervalo INTEGER antes de qualquer consulta.
2. **URLs de categorias ambíguas.** Nomes diferentes podiam gerar o mesmo endereço, como um nome com acentos e a sua versão sem acentos. São rejeitados novos endereços duplicados ou vazios e nomes que excedam os 80 caracteres do esquema. As URLs existentes não são reescritas.
3. **Campos de autor e imagem incompatíveis com o PostgreSQL.** Nome, endereço do perfil, e-mail, ligações externas e fotografia passam a respeitar os limites das respectivas colunas. A ligação da imagem de um artigo também é limitada aos 600 caracteres do esquema, antes dos carregamentos. A ordenação fica limitada ao intervalo INTEGER. A comparação de e-mails ignora diferenças entre maiúsculas e minúsculas. No formato do ORCID, a letra X só é aceite na última posição; isto valida o formato, não a existência ou titularidade do identificador.
4. **Sufixo de URL de artigo acima do limite.** Um endereço já com 260 caracteres ultrapassava o tamanho permitido ao receber o sufixo de desambiguação. O sufixo passa a ter espaço reservado dentro desse limite.
5. **Desvio de fuso horário na programação.** O formulário do editor guardava a hora local de uma data com fuso como se fosse UTC. As datas com fuso são agora convertidas para UTC antes da gravação; as datas sem fuso conservam a convenção UTC do formulário existente.
6. **Programação no passado.** O editor aceitava datas passadas, ao contrário da rota do fluxo editorial. O formulário passa a exigir uma data futura, antes de iniciar carregamentos de ficheiros.
7. **Revisão antiga aplicada a conteúdo actualizado.** Ao publicar directamente uma alteração do texto, o fluxo podia conservar a indicação de revisão concluída da versão anterior. A alteração do conteúdo passa a invalidar essa indicação e a atribuição corrente; os pareceres anteriores permanecem no histórico. A nova publicação continua permitida pela decisão directa do administrador principal e fica na auditoria.

## Verificações realizadas

Foram consultados em produção a página inicial, artigos, revistas, autores, equipa, recursos, serviços, apresentação institucional, contacto, robots.txt, sitemap, feed, entrada administrativa e healthcheck. As 14 respostas tiveram estado HTTP 200. Os pedidos foram apenas de leitura, sem submissões, mensagens ou alterações aos dados.

Uma verificação adicional de 120 ligações internas no ambiente local não encontrou respostas HTTP de erro. Este resultado diz respeito ao conteúdo sintético usado nesse ambiente.

Foram também percorridas as 46 páginas públicas indicadas no sitemap de produção: todas responderam com HTTP 200, tinham exactamente um título H1 e não continham elementos de imagem sem atributo alt. A presença do atributo não comprova a qualidade editorial da descrição.

A bateria anterior de 439 testes passou antes das alterações. Foram acrescentados oito testes de regressão para os problemas dos formulários, endereços, programação e validade da revisão. Os resultados da bateria completa e do GitHub Actions são registados na descrição do PR.

## Âmbito de acesso

As correcções são feitas no código existente, sem nova migração ou alteração directa de conteúdos publicados. Uma verificação exaustiva do servidor, cópias de segurança, filas de correio, credenciais externas e dados privados do painel exige acesso aos respectivos serviços e registos de produção. Esses acessos não estão disponíveis nesta sessão. Os estados de publicação e as permissões existentes são preservados, incluindo a publicação directa pelo administrador principal.
