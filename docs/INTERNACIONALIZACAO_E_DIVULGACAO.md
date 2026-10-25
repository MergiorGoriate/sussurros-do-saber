# Internacionalização e ampliação do Centro de Divulgação Científica

## Auditoria e âmbito

A auditoria incidiu sobre a revisão `c1ff37bfe58fffdc7fa45dc6e41282b081e1fd55`, que já integra o Centro de Divulgação Científica do PR #290. A arquitectura é Flask, templates Jinja, Flask-SQLAlchemy, PostgreSQL em produção configurada, Markdown com saneamento Bleach e Tailwind/CSS. Os testes locais usam SQLite. Existem blueprints separados para administração, governação, submissões, contas, Prémio, pagamentos e métricas.

O modelo `Article` contém título, resumo, corpo Markdown, palavras-chave, referências, imagens, estado e datas. Não existia uma entidade de tradução editorial. O modelo `Journal` já contém `article_title_en`, resumo, abstract e palavras-chave, além do manuscrito Markdown, referências e DOI. Esses campos existentes não são apagados nem substituídos. As novas versões inglesas revistas ficam numa entidade própria e são sobrepostas apenas na apresentação pública inglesa.

A autenticação existente valida sessões, credenciais e 2FA. A governação usa funções e mandatos aceites, activos e com âmbito definido. As novas permissões usam esse sistema e exigem mandato geral; as contas antigas não recebem acesso implícito por compatibilidade.

O portal já publica canonical, Open Graph, JSON-LD, sitemap e feed. O HTML e os cabeçalhos estavam fixados em português. O domínio canónico existente é preservado. Há cache privada de PDF limitada a 64 MB e cinco minutos, com bloqueio entre processos; os artigos com formulários de comentários já evitam cache partilhada. As respostas inglesas e a página inicial que negoceia o idioma usam `no-store`, para não misturar preferências na CDN.

A imagem de produção usa Gunicorn com dois trabalhadores por defeito e timeout de 120 segundos. A geração e a revisão de conteúdos continuam fora dos pedidos públicos. Não foi possível inspeccionar a VPS ou a configuração real da Cloudflare. Os recursos de 8 GB de RAM, quatro núcleos e 75 GB foram fornecidos pelo proprietário e não representam medições desta auditoria.

Esta entrega implementa a estrutura PT/EN, o fluxo editorial das traduções e a composição de vídeos silenciosos. Não constitui activação em produção nem certificação de que todo o acervo já foi traduzido. As traduções reais dependem da configuração do fornecedor e de aprovação humana.

## Idiomas, navegação e SEO

Os endereços portugueses permanecem iguais. As versões inglesas usam o prefixo `/en/`, mantendo as rotas e as funções existentes. Os argumentos de idioma são removidos antes de executar a função original. As rotas de PDF da revista, os webhooks, os callbacks de autenticação e as APIs existentes não são duplicados por este mecanismo.

O selector **PT | EN** aparece na barra superior, incluindo em dispositivos móveis. Guarda uma preferência funcional num cookie `HttpOnly`, `SameSite=Lax`, com duração de um ano e `Secure` quando a ligação é HTTPS. A alteração conserva a página equivalente e os parâmetros de pesquisa. O destino é validado para impedir redireccionamentos externos.

Uma escolha manual, incluindo `?lang=pt` ou `?lang=en`, tem precedência. Sem escolha guardada, os países lusófonos recebem português e os países anglófonos recebem inglês; nos restantes casos considera-se `Accept-Language`. Nesta interpretação, a preferência do navegador é aplicável quando o país não define o idioma inicial. A localização nunca bloqueia a escolha manual.

O cabeçalho `CF-IPCountry` só é utilizado com `TRUST_CLOUDFLARE_COUNTRY=true`. Active esta opção apenas depois de confirmar que o servidor de origem aceita tráfego através de proxies Cloudflare autorizados e que clientes directos não podem falsificar o cabeçalho. Sem essa confirmação, mantenha a opção desactivada: o sistema usa o navegador ou português.

A negociação automática limita-se à entrada na página inicial. URLs explícitos permanecem estáveis e agentes identificados como robôs não são redireccionados por preferência. Não existem ciclos PT/EN.

`lang`, `Content-Language`, o idioma de Open Graph e JSON-LD acompanham a versão apresentada. Canonical continua a apontar para a própria versão. Hreflang e entradas inglesas no sitemap são publicados de forma conservadora, quando o catálogo da interface está concluído e a tradução correspondente existe. Não se anunciam artigos ingleses que ainda não tenham tradução publicada.

Quando não existe tradução de um artigo, o selector encaminha para a listagem inglesa e apresenta a ligação ao original português. Um acesso directo a uma URL inglesa ainda não publicada devolve uma página 404 explicativa com ligação ao original. Uma página inglesa com textos da interface ainda por traduzir recebe `noindex, follow`.

## Catálogo da interface

A extensão Jinja identifica texto estático, títulos, placeholders, atributos ALT e rótulos de acessibilidade. Não reescreve respostas HTML completas, não traduz código JavaScript/JSON-LD indiscriminadamente e não percorre o manuscrito científico renderizado.

Existe um catálogo inicial pequeno, revisto no código, com termos comuns. **O catálogo inicial não contém a tradução integral de todas as páginas institucionais e interfaces.** Os restantes textos devem ser identificados, traduzidos e aprovados pelo administrador antes de considerar a versão inglesa completa. O número depende dos templates e dos conteúdos públicos existentes.

Em **Internacionalização → Interface e páginas institucionais**:

1. Use **Identificar novos textos dos templates**. A recolha inclui mensagens públicas de validação identificáveis, textos de JavaScript preparados e descrições públicas dos planos e recursos.
2. Use **Gerar tradução dos próximos 20 textos com IA**, ou traduza manualmente cada texto.
3. Reveja o lote no mesmo fluxo dos artigos: rever, aprovar e publicar.
4. Repita a recolha quando o código ou os textos públicos mudarem.

Os identificadores, preços, moeda, benefícios de acesso, planos contratados e regras de pagamento não são traduzidos nem gravados novamente. As descrições públicas revistas são sobrepostas na apresentação. Os corpos de cursos, ficheiros da Biblioteca Exclusiva, dados pessoais, conversas e manuscritos científicos não são traduzidos por este catálogo.

Os textos continuam escapados pelo Jinja; uma tradução de interface não pode executar HTML, JavaScript ou comandos Jinja. Mensagens dinâmicas sem equivalência conservam o original e devem ser incluídas na revisão de cobertura. A verificação final em navegador deve abranger todos os fluxos públicos e as mensagens condicionais utilizadas na instalação real.

## Artigos e metadados da revista

Em **Internacionalização → Tradução de artigos**, o administrador pode pesquisar artigos, seleccionar até 20 por lote e definir prioridade de 1 a 100. É possível preparar traduções de rascunhos durante o processo editorial; a versão inglesa só pode ser publicada depois de o original estar publicado.

Esta fase implementa o percurso português → inglês, de acordo com a norma actual do portal. O idioma original apresentado é português; o revisor deve confirmar essa classificação, pois o modelo anterior não guardava o idioma por artigo. Não se implementa detecção automática infalível nem tradução geral de quaisquer línguas.

Os estados são Não traduzido, Tradução pendente, Em processamento, A aguardar revisão, Aprovado, Publicado, Desactualizado e Erro de processamento. A ausência de um registo corresponde a Não traduzido. A fila distingue ainda tarefas pendentes, suspensas, canceladas, concluídas e falhadas.

O trabalhador protege fórmulas, blocos de código, ligações e citações identificáveis com marcadores temporários. Depois da tradução, confirma a restituição exacta, a hierarquia Markdown, a estrutura de tabelas, as ligações de imagens e as referências. As referências dos artigos informativos são copiadas literalmente. Os textos ALT são traduzidos com o conteúdo. Uma chamada de revisão preliminar compara a tradução com o original; resultados incompletos ou problemas bloqueiam a aprovação.

Estes controlos não garantem exactidão científica nem substituem a revisão editorial, incluindo fórmulas fora das sintaxes reconhecidas, tabelas complexas, HTML e citações de formatos atípicos. Não são inventadas referências para preencher omissões do original. Artigos com mais de 60 000 caracteres são recusados sem truncagem silenciosa nesta fase.

Uma correcção cria outra versão e outra revisão assíncrona. Aprovação e publicação são acções separadas. A recuperação de uma versão antiga também exige revisão. O responsável, a data, o estado e as decisões ficam no histórico.

Quando os campos de origem relevantes mudam, o estado passa a Desactualizado na mesma transacção da edição. O apontador da versão inglesa publicada é preservado. O visitante vê um aviso e pode abrir o original actualizado. Uma nova tradução não substitui automaticamente a versão publicada; é necessária nova aprovação e publicação.

Na revista, só são enviados para tradução título do artigo, resumo, palavras-chave, descrição institucional, instruções e âmbito. **Não são enviados nem alterados `content_markdown`, PDF, resultados, métodos, conclusões, DOI ou referências do manuscrito.** A página inglesa identifica que o manuscrito e o PDF permanecem na língua original. Não é criado outro DOI nem outra edição científica.

## Permissões

| Permissão | Âmbito |
| --- | --- |
| `translations.manage` | Criar e corrigir traduções, gerir lotes e a fila, recolher textos da interface |
| `translations.approve` | Aprovar versões após revisão editorial |
| `translations.publish` | Publicar versões previamente aprovadas |

O administrador principal conserva acesso. Os restantes utilizadores precisam de mandatos gerais activos e aceites. Os mecanismos de autenticação, CSRF, 2FA e permissões do editor, das submissões, do Prémio e dos pagamentos permanecem em vigor.

## Centro de Divulgação e vídeos

O Centro já existente é reutilizado. O selector inclui artigos portugueses e versões inglesas publicadas. Uma tradução inglesa desactualizada não pode servir de origem a novos materiais. O texto e as legendas visuais dos materiais ingleses seguem inglês, mantendo o logotipo oficial.

Depois de aprovar os slides, é possível colocar uma composição de vídeo na fila. O trabalhador FFmpeg cria um MP4 H.264 de 720 × 720 píxeis, com seis segundos por slide, no máximo cinco slides, sem áudio e sem acrescentar informação científica. A proporção dos slides é preservada com margens.

O vídeo fica **A aguardar revisão audiovisual**. Um responsável com permissão de aprovação deve vê-lo integralmente e aprová-lo antes do descarregamento formal. O descarregamento exige também permissão de publicação. Alterações ou invalidação da aprovação de origem bloqueiam o acesso ao ficheiro. Um resumo SHA-256 detecta alterações do vídeo no armazenamento.

Não estão incluídos narração, vozes sintéticas, música, avatares, geração de cenas em movimento ou publicação automática nas redes. Os requisitos dessa parte não chegaram na mensagem original, que terminou em «Não alterar a». A composição silenciosa é uma extensão limitada e verificável do fluxo aprovado; não equivale a um sistema completo de produção com áudio.

## Configuração e operação

Faça backup da base de dados e do volume privado antes da implantação. A migração aditiva `20261025_18` cria tabelas novas de traduções, catálogo, fila e vídeo. Não altera as colunas dos manuscritos, DOIs ou PDFs.

```bash
python -m alembic upgrade head
```

Configure no Coolify:

| Variável | Finalidade |
| --- | --- |
| `I18N_ENABLED` | `true` activa as rotas inglesas; `false` desactiva a apresentação inglesa e oculta o selector |
| `TRUST_CLOUDFLARE_COUNTRY` | `false` por defeito; exige validação da protecção da origem antes de activar |
| `OPENAI_API_KEY` | Chave privada do fornecedor, guardada como segredo |
| `TRANSLATION_TEXT_MODEL` | Modelo compatível com Chat Completions, JSON mode e `max_completion_tokens` |
| `TRANSLATION_REVIEW_MODEL` | Modelo para a revisão preliminar das traduções |
| `TRANSLATION_DAILY_UNITS` | Reserva diária em unidades administrativas; predefinição: 100 |
| `DISSEMINATION_STORAGE_DIR` | Volume privado persistente, partilhado entre serviço web e trabalhadores |
| `DISSEMINATION_FFMPEG` | Opcional: executável FFmpeg; predefinição: `ffmpeg` |

Os modelos não são escolhidos silenciosamente. A compatibilidade, o acesso da conta e o preço vigente devem ser confirmados antes da activação. Não foram usadas chaves reais do proprietário nem efectuadas chamadas pagas neste desenvolvimento.

Execute os comandos num trabalhador próprio, com o mesmo código, base de dados e volume privado do serviço web:

```bash
python -m flask --app app processar-traducoes --limit 1
python -m flask --app app processar-divulgacao --limit 1
python -m flask --app app processar-videos-divulgacao
```

Para esta VPS, recomenda-se uma sequência de execução única no agendamento, evitando arrancar vários processos pesados em paralelo. A fila de tradução possui uma reserva global na base de dados para limitar o processamento a uma tarefa. A composição de vídeo usa um bloqueio no volume partilhado e uma thread de codificação. A imagem Docker inclui FFmpeg. O limite de uma execução não substitui os limites de CPU e memória que devem ser configurados no Coolify após medir a instalação real.

As chamadas de tradução/revisão têm limites de resposta e tempo de espera, e a reserva diária considera o tamanho do texto. As unidades não são meticais, dólares, facturação nem um tecto monetário exacto. Configure também os controlos financeiros disponíveis na conta do fornecedor. Tentativas interrompidas podem ter sido cobradas e não são repetidas automaticamente.

O administrador principal pode alterar as unidades diárias em **Administração → Internacionalização → Limite diário de tradução**. O painel mostra o limite, as reservas do dia em UTC e as unidades disponíveis. O valor guardado tem prioridade sobre `TRANSLATION_DAILY_UNITS` e aplica-se aos novos pedidos sem reiniciar a aplicação. Até à primeira alteração, mantém-se o valor do servidor. A migração `20261026_19` cria a configuração persistente e o histórico das alterações, sem modificar as reservas existentes.

Cada unidade corresponde a até 4 000 caracteres dos campos originais enviados pelo fluxo editorial. Tentativas falhadas e tarefas canceladas mantêm a sua reserva. Baixar o limite abaixo das reservas não cancela tarefas aceites: apenas impede novas reservas enquanto não houver quota disponível. O formulário exige a sessão do administrador principal, protecção CSRF e a versão actual da configuração para evitar alterações sobrepostas.

Os vídeos são limitados a 40 MB; a composição verifica uma margem mínima de espaço livre. Versões, imagens e vídeos devem entrar no backup e na política de retenção operacional. Não há eliminação automática de histórico ou limpeza generalizada de ficheiros antigos. Com 75 GB, acompanhe o espaço livre e a utilização efectiva, em vez de presumir capacidade ilimitada.

Na Cloudflare, não force cache de HTML na entrada `/`, em `/en/*`, `/idioma/*`, áreas privadas ou respostas que contenham preferências de utilizador. Preserve os cabeçalhos `no-store`. Os ficheiros estáticos versionados continuam a usar o comportamento existente.

## Validação e reversão

Os testes incluem negociação e escolha manual de idioma, destinos seguros, equivalência de páginas, pesquisa inglesa, traduções não publicadas, revisões, manutenção de versões antigas, alterações ao original, fórmulas, referências, ALT, exclusão de manuscritos/DOIs, concorrência da fila, permissões e preservação dos valores dos planos. Foi codificado e inspeccionado com FFprobe um vídeo MP4 real, sem chamadas a serviços de IA, incluindo os bloqueios de aprovação audiovisual.

Foram acrescentados testes de navegador para PT/EN a 320, 768 e 1440 píxeis, temas claro/escuro e administração de traduções. A execução local do navegador permanece pendente por indisponibilidade do Chromium neste ambiente; os testes devem correr no CI. O build Docker e a migração PostgreSQL devem também passar no CI antes da integração.

Os testes com fornecedor usam respostas sintéticas. É obrigatória uma validação real, com conta configurada, de um artigo informativo, um lote da interface, metadados de revista, um material visual inglês e um vídeo aprovado. É igualmente necessário rever a cobertura de todas as páginas e mensagens da instalação, concluir o catálogo inglês e confirmar a configuração efectiva da Cloudflare.

Resultados locais: a suite geral executou 703 testes com sucesso e um teste ignorado por configuração específica de PostgreSQL. Após os ajustes finais ao registo dos revisores, passaram também 35 testes focados em internacionalização, vídeo e migrações. As contagens sobrepõem-se e não devem ser somadas. O navegador, o build Docker e o fornecedor real permanecem por validar nesta entrega.

Para reverter a apresentação, use `I18N_ENABLED=false`. Para interromper processamento, suspenda os agendamentos e as tarefas pendentes; uma operação já em execução pode terminar. Uma reversão do código deve preservar as tabelas e os ficheiros privados. A migração não elimina o histórico através de downgrade destrutivo.

Esta entrega deve permanecer em revisão até concluir essas verificações. A disponibilidade das rotas e dos trabalhadores não significa que os artigos antigos ou a interface completa já tenham traduções aprovadas.
