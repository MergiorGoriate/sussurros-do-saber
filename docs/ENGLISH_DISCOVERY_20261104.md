# Descoberta das versões inglesas após o PR 332

## Evidência e causa

A verificação pública após o deploy do PR 332 encontrou HTTP 200 e canonical correcto em `/artigos?page=2` e `/en/artigos?page=2`. Contudo, a versão inglesa devolvia `X-Robots-Tag: noindex, follow`, sem hreflang, e o sitemap não incluía endereços ingleses.

As primeiras quatro páginas públicas mostravam cinco categorias sem tradução no catálogo de código: Ciência e Universo, Evolução, Ciência em África, Ambiente e Biodiversidade e Evolução e Origens. A apresentação inglesa dessas etiquetas accionava a protecção de página incompleta. Foram acrescentadas traduções inglesas para estes cinco nomes, preservando os nomes portugueses na base de dados.

Existe também uma condição global no código anterior: qualquer registo de interface não publicado bloqueava os endereços ingleses de todo o sitemap. Além disso, o conjunto usado nessa condição era alargado pelo painel com textos dinâmicos de perfis, cursos e políticas. A presença exacta destes registos na base de produção não foi consultada; o bloqueio foi reproduzido localmente com um registo pendente sem relação com a publicação.

## Comportamento revisto

A verificação partilhada usa agora as etiquetas dos templates e do cliente, separadas dos textos dinâmicos recolhidos pelo painel. Traduções publicadas no painel mantêm prioridade; um rascunho não bloqueia uma etiqueta que já tem tradução no catálogo fornecido pela aplicação. A apresentação de um texto realmente sem tradução continua a produzir `noindex` na página afectada.

Para artigos e publicações científicas, a descoberta exige conteúdo público, uma versão inglesa efectivamente publicada e tradução das respectivas etiquetas de categoria ou área/periodicidade. O sitemap e as referências hreflang não anunciam uma publicação inglesa cuja categoria ainda esteja por traduzir. O sitemap considera apenas registos de tradução inglesa; uma referência a versão inexistente não basta para publicar um endereço.

A recolha de textos no painel passa a incluir nomes de categorias. Categorias novas sem tradução ficam pendentes de revisão, sem publicação automática. Os catálogos e indicadores da interface são reinicializados em cada pedido, permitindo que uma tradução entretanto publicada seja reconhecida no pedido seguinte.

## Validação e publicação

Os testes de regressão cobrem traduções pendentes sem relação com a página, rascunhos sobre etiquetas já traduzidas, categorias novas antes/depois da publicação da tradução, ausência real de uma etiqueta comum, as cinco categorias observadas em produção e a recolha administrativa de categorias. Passaram 83 testes locais em conjunto: 11 de capas, nove de SEO bilingue, seis de descoberta inglesa, 37 de internacionalização e 20 de manutenção/integração de SEO. Uma verificação adicional confirmou o contrato do catálogo estático e as seis novas regressões. O resultado da suite completa de CI deve ser confirmado na proposta do GitHub.

Não há migrações nem novas variáveis. Depois do merge e do deploy, verificar novamente os cabeçalhos de `/en/` e `/en/artigos?page=2`, o sitemap e um par de artigos português/inglês com tradução publicada. Se uma página conservar `noindex`, verificar as etiquetas e os textos dinâmicos dessa página no painel; não remover a protecção por omissão. Esta alteração não comprova indexação pelo Google nem substitui a verificação em produção.
