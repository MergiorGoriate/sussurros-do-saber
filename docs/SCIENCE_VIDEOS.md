# Vídeos de Ciência

O catálogo público está em `/videos` e `/en/videos`. Cada versão editorial tem um endereço próprio. O editor pode ligar versões no campo **Tradução do vídeo (ID)**. Cada versão tem estado e data de publicação independentes.

## Fluxo editorial

1. Em **Artigos**, escolha uma capa de vídeo e assinale **Publicar também em Vídeos de Ciência**. Guarde o artigo. A opção cria um rascunho de vídeo e abre o respectivo editor. O vídeo de capa fica disponível no artigo segundo o formato seleccionado.
2. Em **Vídeos de Ciência**, edite o rascunho, crie um vídeo independente ou importe capas seleccionadas de artigos. A importação conserva os ficheiros existentes e cria rascunhos em português com metadados do artigo. Para um vídeo autónomo, carregue o ficheiro ou indique uma ligação da Cloudinary configurada, do YouTube ou do Vimeo. Pode carregar uma nova miniatura JPG, PNG ou WebP.
3. Reveja o título, a descrição, a miniatura, a categoria, o idioma e a autoria. Preencha os créditos e a licença quando aplicáveis. Confirme que o vídeo tem valor informativo independente, direitos para publicação e acesso público. Use a pré-visualização para verificar a reprodução, as legendas, a transcrição e a miniatura. O reconhecimento do direito de utilização e a disponibilidade dos ficheiros são verificações editoriais.
4. Publique ou agende a publicação no fuso de Maputo. O catálogo aplica a data e o estado do artigo associado em cada pedido. Os endereços atribuídos a vídeos que já tiveram uma publicação ou agendamento ficam fixos.
5. Use **Retirar da publicação** para interromper a apresentação pública. A eliminação exige arquivar e confirmar o registo. É removido o registo e as respectivas estatísticas. A gestão do ficheiro na Cloudinary continua separada, de modo a conservar o conteúdo partilhado com artigos e outros vídeos.

A criação de rascunhos e a importação usam a permissão `article.edit`. A publicação, a programação, a alteração de versões publicadas e a retirada usam `article.publish`. As pré-visualizações exigem uma sessão administrativa com uma destas permissões.

Os ficheiros carregados como capa fornecem duração e dimensões no momento do carregamento. Para um ficheiro existente na Cloudinary, use **Preencher a partir da Cloudinary** no editor. A operação consulta o identificador do ficheiro na conta configurada. Para os restantes suportes, confirme a duração e as dimensões na origem, se disponíveis.

As estatísticas contam visualizações de páginas visíveis com consentimento para análise. O leitor nativo regista reproduções, segundos de reprodução e conclusões. Os leitores incorporados do YouTube e Vimeo contam apenas visualizações da página. Cada vista tem um identificador aleatório de curta validade independente das restantes páginas visitadas.

## Implantação no Coolify

1. Prepare uma imagem Docker do commit aprovado e valide-a num serviço de ensaio com PostgreSQL e Redis isolados. Mantenha os nomes das variáveis do projecto, incluindo `DATABASE_URL`, `SITE_URL` e a configuração Cloudinary.
2. Antes de substituir os processos web, verifique uma cópia recuperável da base e execute `python -m alembic upgrade head` com a imagem nova e o `DATABASE_URL` do ambiente pretendido. Confirme `20261125_22 (head)` com `python -m alembic current`. A revisão só acrescenta as tabelas `science_video` e `video_playback`.
3. Implante a imagem e verifique `/healthz`, os catálogos português e inglês, o painel, o sitemap e uma página de vídeo em cada idioma disponível. Confirme a reprodução pública da Cloudinary e a acessibilidade da miniatura, sem autenticação. Faça o ensaio de publicação e retirada com dados de teste no serviço de ensaio.
4. Caso seja necessário reverter a aplicação, volte à imagem anterior e mantenha as tabelas acrescentadas. Para retirar um vídeo da descoberta, verifique também a expiração das caches externas.

## Google Search Console

Verifique primeiro `/robots.txt` e `/video-sitemap.xml` no domínio canónico. Com pelo menos um vídeo real publicado, abra **Sitemaps** na propriedade verificada e submeta `https://www.sussurrosdosaber.com/video-sitemap.xml`. Depois de o Google ler o ficheiro, inspeccione uma página individual e acompanhe os relatórios de indexação de vídeos. A validação do XML e do `VideoObject` confirma a configuração técnica. A decisão de indexar cabe ao Google.

[Boas práticas de SEO para vídeo](https://developers.google.com/search/docs/appearance/video) · [Sitemaps de vídeo](https://developers.google.com/search/docs/crawling-indexing/sitemaps/video-sitemaps) · [Relatório de sitemaps](https://support.google.com/webmasters/answer/7451001)
