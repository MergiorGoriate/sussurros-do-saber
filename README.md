# Sussurros do Saber

Plataforma de divulgação científica e publicação editorial em português, construída com Flask, SQLAlchemy, Jinja, Tailwind CSS e JavaScript. Reúne artigos, publicações científicas na área de revistas, perfis de autores, recursos educativos, contas de leitores e um fluxo privado de submissões.

Este README descreve a implementação revista em **5 de outubro de 2026**, com base no código do repositório. Documentar uma integração não comprova que as suas credenciais, serviços externos ou tarefas agendadas estejam activos no servidor. O README deve ser actualizado junto com alterações às funcionalidades.

## Índice

- [Visão geral e arquitectura](#visão-geral-e-arquitectura)
- [Site público](#site-público)
- [Contas, favoritos e notificações](#contas-favoritos-e-notificações)
- [Revistas e artigos científicos](#revistas-e-artigos-científicos)
- [Painel administrativo](#painel-administrativo)
- [Submissões e produção editorial](#submissões-e-produção-editorial)
- [Conteúdo, imagens e vídeos](#conteúdo-imagens-e-vídeos)
- [Integrações](#integrações)
- [Dados e persistência](#dados-e-persistência)
- [Instalação e desenvolvimento](#instalação-e-desenvolvimento)
- [Configuração](#configuração)
- [Produção, manutenção e recuperação](#produção-manutenção-e-recuperação)
- [Segurança, privacidade e desempenho](#segurança-privacidade-e-desempenho)
- [Testes e validação](#testes-e-validação)
- [Limites da implementação](#limites-da-implementação)
- [Inventário completo de rotas](#inventário-completo-de-rotas)

## Visão geral e arquitectura

A aplicação renderiza páginas no servidor e acrescenta interacções no navegador. A base de dados guarda conteúdo, utilizadores e processos editoriais; Cloudinary guarda imagens e vídeos enviados pelo painel. Os anexos originais de submissões ficam privados na própria base de dados. Redis mantém os limites de utilização em produção. O assistente usa um Worker do Cloudflare através do backend Flask.

| Componente | Responsabilidade |
| --- | --- |
| `app.py` | Configuração Flask, páginas públicas, Markdown, SEO, APIs, PDF, cabeçalhos, inicialização e alterações leves do esquema |
| `admin.py` | Autenticação administrativa, 2FA, gestão editorial, utilizadores, comentários e exportações |
| `models.py` | Artigos, autores, categorias, revistas, políticas, administradores, comentários, contactos e subscritores |
| `reader_accounts.py` | Sessão do leitor, favoritos por conta, biblioteca, acompanhamento e notificações |
| `google_auth.py` | Validação do login Google, associação de identidade e comando de migração |
| `submissions.py` / `submission_models.py` | Contas de investigadores, submissões, versões, decisões, produção e fila de e-mails |
| `submission_uploads.py` | Validação de anexos e conversão limitada de DOCX para Markdown |
| `journal_article.py` / `journal_metadata.py` | Campos científicos, ordem de apresentação e autores estruturados/ORCID |
| `journal_pdf.py` | Composição editorial de PDF, tabelas, imagens e gráficos |
| `storage.py` | Validação e envio de imagens/vídeos para Cloudinary |
| `extensions.py` | Instância e armazenamento do limitador de pedidos |
| `editorial_content.py` | Conteúdo editorial inicial e compatibilidade com texto existente |
| `templates/` | Páginas públicas, painel, diálogos e submissões em Jinja |
| `static/js/` | Editores, contas, pesquisa, consentimento, partilha, ferramentas educativas e interfaces responsivas |
| `static/css/` | Estilos próprios e Tailwind compilado |
| `cloudflare-worker/worker.js` | Endpoint privado do assistente e chamada ao Workers AI |
| `tests/` | Testes Python e testes de navegador Playwright |
| `Dockerfile` | Compilação CSS e imagem de execução Python/Gunicorn |
| `.github/workflows/` | Testes, auditorias de dependências e construção Docker |

A execução de referência usa Python 3.11 e Node 22. As dependências efectivas estão em [requirements.txt](requirements.txt), [package.json](package.json) e `package-lock.json`; esses ficheiros são a fonte dos números de versão.

## Site público

### Início, artigos e autores

- A página inicial apresenta até 10 artigos publicados, ordenados por destaque e data, e até três revistas/publicações públicas recentes.
- O catálogo de artigos aceita `q`, `categoria` e `page`, com 12 resultados por página. A pesquisa consulta título, resumo, corpo e nome do autor; a categoria usa o nome normalizado.
- O artigo apresenta título, resumo, autor, categoria, data, tempo de leitura, capa/imagem ou vídeo, corpo Markdown, referências e metadados editoriais disponíveis.
- Os três artigos sugeridos são publicações recentes diferentes do artigo aberto; não existe motor de recomendação semântica.
- Ligações antigas por ID, incluindo `artigo-N`, redireccionam para o slug quando a publicação existe. Rascunhos e artigos programados ainda não publicados ficam fora das consultas públicas.
- Perfis de autores incluem os campos preenchidos: função, apresentação, formação, instituição, biografia, interesses, projectos, publicações, experiência editorial, fotografia e ligações académicas. A lista respeita activação/ordenação; o perfil reúne artigos publicados do autor.
- Ferramentas de leitura e partilha incluem guardar por conta, partilhar por WhatsApp, Facebook, X, LinkedIn, Telegram ou e-mail e copiar a ligação. Alguns recursos usam APIs do navegador, como a área de transferência, com alternativa manual em caso de falha.

### Comentários, contacto e newsletter

Comentários exigem nome, e-mail e texto válido, token CSRF e campo anti-robô. São guardados para moderação; apenas aprovados aparecem publicamente, até 100 por artigo. O envio tem limite específico de cinco pedidos por hora. O nome admite 2–80 caracteres e o comentário 10–2000.

O formulário de contacto envia para `/api/contacto` e guarda a mensagem na base de dados. A equipa consulta e gere essas mensagens no painel. Guardar uma mensagem não equivale a encaminhá-la automaticamente por e-mail.

A newsletter regista o endereço, evita duplicação e permite reactivar uma inscrição. O painel gere subscritores e exporta CSV. O código não inclui um serviço de campanhas nem envio automático de newsletters.

### Recursos educativos

- `/recursos`: ferramentas de estatística descritiva (N, média, mediana e intervalo mínimo–máximo), pequeno quiz de ciência, exploração de organelos, cálculo de diluição pela relação C₁V₁=C₂V₂, frequências de Hardy–Weinberg e cartões de estudo. Também há glossário pesquisável e gerador simples de referência a partir de autor, ano, título e revista; não é um gestor bibliográfico nem validador completo de normas.
- `/aprender`: catálogo educativo definido em `LEARNING_RESOURCES`, com pesquisa, filtros por tipo/tema e contador de resultados. `tipo` e `tema` também podem vir na URL.
- A colecção de recursos educativos e os cartões marcados como dominados usam `localStorage` do navegador; não são os favoritos editoriais por conta.
- `/laboratorio/osmose`: simulação ilustrativa com concentração externa, volume visual da célula, estados hipotónico/isotónico/hipertónico e botão de reinício. Não é um modelo quantitativo validado de transporte celular.
- `/api/recursos` expõe o catálogo educativo; não existe CRUD administrativo desse catálogo.

### Páginas institucionais e descoberta

O site contém Sobre, Contacto, Serviços, Edição científica, Termos e condições, Privacidade, Acessibilidade, Política de correcções, Políticas editoriais e Diretrizes para autores. As políticas editoriais e diretrizes aceitam conteúdo do painel; as restantes páginas usam os seus templates.

Há canonical, metadados de partilha, dados estruturados nas páginas aplicáveis, sitemap, robots, RSS de artigos e `ads.txt`. O RSS não é um feed completo de submissões/revistas. O sitemap reúne as páginas públicas previstas no código, artigos, autores e revistas publicados. O domínio canónico padrão é `https://www.sussurrosdosaber.com`; o domínio sem `www` recebe redireccionamento permanente 308, preservando caminho e parâmetros.

A existência de `ads.txt`, tags de verificação ou integração GTM não comprova aprovação comercial, indexação ou tráfego medido.

## Contas, favoritos e notificações

As contas públicas reutilizam `Researcher`, também usado nas submissões; são independentes das contas de administrador e dos perfis públicos de `Author`.

| Operação | Comportamento |
| --- | --- |
| Criar conta | Nome, e-mail e palavra-passe de 12–128 caracteres; e-mail de confirmação entra na fila SMTP |
| Entrar | E-mail/palavra-passe no diálogo do leitor ou página de submissões; sessão autenticada no servidor |
| Confirmar/recuperar | Ligações temporárias assinadas; confirmação e recuperação através das páginas de submissões |
| Guardar artigo | Relação `ReaderArticle` por conta e artigo publicado |
| Guardar revista/publicação | Preferência `saved` em `ReaderJournal` |
| Biblioteca | `/conta/biblioteca` mostra favoritos ainda públicos |
| Acompanhar | Preferência `following`; requer e-mail confirmado para activar |
| Notificações | Actualizações de publicações acompanhadas; contador compara `updated_at` com a revisão reconhecida pelo leitor |
| Marcar actualização lida | Reconhece a revisão efectivamente apresentada, sem reconhecer uma edição posterior |
| Importar favoritos antigos | Até 100 IDs/slugs por lote; navegador remove a cópia antiga só após confirmação de todos os lotes |
| Sair | POST de logout das submissões, com protecção CSRF |

A página de notificações lista publicações acompanhadas e distingue actualizações; estas notificações são internas ao site. Não há push nem e-mails de acompanhamento implementados. Os favoritos editoriais actuais não dependem apenas do armazenamento local.

### Login Google opcional

`GOOGLE_CLIENT_ID` activa Google Identity Services, botão de login e tentativa automática de apresentação do One Tap. O browser/FedCM pode suprimir a apresentação automática; o botão manual continua disponível.

O backend verifica assinatura, emissor, audiência, validade e nonce do ID token. A identidade é associada pelo identificador Google (`sub`); a associação por e-mail respeita as regras de autoridade/verificação e evita associar automaticamente contas antigas não verificadas ou e-mails externos sem confirmação adequada. A fotografia válida é usada na sessão, não como ficheiro permanente. Não se guarda o ID token, nem se pede palavra-passe do Google ou client secret.

Configuração e cenários de associação estão em [docs/google-login.md](docs/google-login.md). Registar as origens JavaScript exactas utilizadas no Google Cloud, incluindo a origem canónica. Sem client ID, continua disponível o login por palavra-passe.

## Revistas e artigos científicos

### Catálogo e leitura

`/revistas` mostra apenas registos publicados, com pesquisa/filtros no navegador. Cada `/revistas/<slug>` apresenta a identidade da revista e o conteúdo científico disponível. Um registo `Journal` combina dados da revista com uma página de publicação; não há, neste momento, entidades relacionais independentes de volume, edição e artigo científico.

Os campos incluem nome/abreviatura, área, descrição, ISSN, periodicidade, edição actual, capa e texto alternativo, DOI, data de publicação, título científico, autores e ORCID, correspondente, resumo, palavras-chave, abstract e keywords.

O título científico explícito tem prioridade. Na compatibilidade com registos antigos, pode ser derivado do primeiro H1 do conteúdo ou do título da revista. Resumo e palavras-chave bilingues precedem o corpo; contribuição dos autores, agradecimentos, financiamento, conflitos, ética, consentimento e dados são apresentados quando preenchidos. Referências, notas, direitos, licença e histórico editorial são apresentados nas áreas correspondentes.

Autores estruturados admitem até 30 entradas, com nome/ORCID e descrição individual. O formato antigo `authors_orcid` continua a ser lido. No formulário de revista, o ORCID é normalizado e validado por formato; na submissão, também é verificado o dígito de controlo. Não existe consulta automática de perfis ORCID.

O índice é construído a partir das secções do conteúdo. No computador, o painel fica aberto por padrão; em ecrãs até 899 px, mantém o comportamento recolhível. O comportamento adapta-se ao redimensionamento, e no telemóvel há fecho ao seleccionar uma secção, clicar fora ou usar Escape. O diálogo de detalhes permite alternar informações e autores com teclado e devolve o foco ao fechar.

O botão de citação abre uma referência construída com autores, ano, título, revista, edição e DOI ou URL, com opção de copiar. É uma referência de apoio; conferir a norma bibliográfica exigida antes de a usar. A acção de proposta no cabeçalho encaminha ao contacto com assunto; o portal privado de submissões constitui um fluxo separado.

### PDF

- Download público em `/revistas/<slug>/baixar.pdf`, apenas para publicações visíveis.
- Pré-visualização e PDF privados para administradores, incluindo rascunhos.
- Composição em A4 pelo ReportLab, com identidade editorial, metadados, autores, corpo, referências e numeração de páginas; não é simplesmente uma captura do HTML.
- O corpo começa em nova página na composição editorial prevista. Há suporte a parágrafos, cabeçalhos, listas, tabelas, imagens e gráficos SVG gerados pelo renderer, dentro das limitações de conversão.
- Imagens locais são limitadas à pasta estática; figuras de publicação respeitam visibilidade. Downloads externos limitam tamanho/tempo, validam redireccionamentos, portas e endereços públicos, para impedir acesso a redes privadas.
- Vídeos não se tornam vídeos reproduzíveis dentro do PDF. O resultado deve ser revisto editorialmente, sobretudo com tabelas extensas, fontes externas indisponíveis ou conteúdo muito longo.

## Painel administrativo

Entrada em `/admin/login`. O painel tem autenticação central, CSRF, verificação de sessão, ausência de cache privado e autenticação de dois factores. O resumo apresenta número de artigos, rascunhos, programados, contactos não lidos, subscritores activos e artigos actualizados recentemente.

| Área | Funções |
| --- | --- |
| Artigos | Criar, editar, eliminar, gerir slug, autor/categoria, resumo, corpo, referências, palavras-chave, DOI, capa/vídeo, destaque, tempo de leitura, estado e datas |
| Autores | Criar/editar perfis, ordem, activação, fotografia, biografia, formação, investigação e ligações académicas; eliminação sujeita às relações existentes |
| Categorias | Criar/editar nomes/slugs e eliminar respeitando artigos associados |
| Revistas | Criar/editar conteúdo e metadados, autores, capa, rascunho/publicação, pré-visualização HTML/PDF, ocultar e eliminar quando permitido |
| Políticas editoriais | Título/descrição, texto geral, diretrizes de autores/revisores, ética, uso de IA, dados, taxas e acesso aberto; pré-visualização Markdown |
| Comentários | Listar, aprovar/desaprovar e eliminar |
| Contactos | Consultar, marcar leitura no fluxo de consulta, eliminar e exportar CSV |
| Subscritores | Consultar, activar/desactivar e exportar CSV |
| Submissões | Filtrar processos, consultar versões/anexos, atribuir editor, decisões e notas, configurar revistas abertas e preparar publicação |
| Administradores | Superadministrador cria/edita/desactiva/elimina contas; salvaguardas de acesso e da própria conta |
| Segurança | Configuração TOTP para contas da base de dados e códigos de recuperação |
| Documentação | Instruções internas em `/admin/docs` |

### Estados e edição

Artigos de divulgação têm `draft`, `published` e `scheduled`. Um artigo programado torna-se publicado ao chegar a data e ocorrer um pedido que execute a verificação, excepto pedidos excluídos como estáticos/health/robots/ads. **Não existe um agendador autónomo de publicação**. As datas internas usam UTC sem timezone; não assumir conversão automática do campo `datetime-local` para a hora local.

O editor fornece ferramentas Markdown, imagem/vídeo, gráficos, citações e pré-visualização. O HTML sanitizado no servidor é a referência final; a pré-visualização JavaScript não substitui a validação do servidor. Nas revistas, o botão de rascunho e a opção de publicação controlam visibilidade; não há programação temporal de revistas.

Limites relevantes: corpo de artigo/revista até 400000 caracteres, referências até 100000; campos científicos opcionais normalmente até 20000, palavras-chave científicas até 2000; políticas até 100000 por campo. O formulário de artigo valida título 5–240, resumo 10–2000, tempo de leitura 1–120 e exige autor/categoria e corpo suficiente para publicar/programar.

A eliminação de uma revista ligada a submissões ou configuração editorial é bloqueada; ocultar é a alternativa para retirar acesso público sem destruir o histórico. DOI e ISSN são metadados preenchidos pela equipa, não identificadores emitidos pelo site.

### Administradores e 2FA

O administrador principal pode ser definido por variáveis de ambiente; contas adicionais ficam em `AdminUser`. Em produção, a autenticação por ambiente exige hash da palavra-passe e segredo TOTP. `ADMIN_PASSWORD` em texto simples só é aceite no modo de desenvolvimento.

Contas administrativas na base de dados precisam concluir a configuração de 2FA antes de usar as áreas protegidas. A interface produz oito códigos de recuperação, guardados como hashes. A conta gerida por ambiente usa `ADMIN_TOTP_SECRET`; a configuração não é feita nesse formulário. A inactividade administrativa expira por padrão após 15 minutos, ajustável entre 1 e 120.

## Submissões e produção editorial

### Acesso e configuração

O portal `/submissoes` é privado. O autor entra com a conta pública/investigador e confirma o e-mail para as operações que o exigem. Um utilizador não ganha acesso administrativo por ser autor ou por ter uma associação de revisão na base.

Em `/admin/submissoes/configuracao`, a equipa abre/fecha submissões por revista, define tipos de artigo, formatos principais e e-mail editorial. Só revistas habilitadas aceitam novos processos. As directrizes e políticas usadas no formulário são as páginas editoriais do site.

### As sete etapas

1. Revista e tipo: seleccionar revista aberta, tipo autorizado, área e idioma.
2. Autores: 1–30 autores, nome/e-mail, ORCID, afiliação, departamento, instituição, cidade/país e exactamente um correspondente.
3. Informações: título, resumo/palavras-chave, abstract/keywords, comentários ao editor e detalhes científicos opcionais.
4. Ficheiros: exactamente um manuscrito principal por versão; figuras, tabelas, suplementos, dados e outros documentos em categorias separadas.
5. Declarações: originalidade, exclusividade, acordo de autores, aceitação de políticas e diretrizes; conflitos, financiamento, ética, consentimento e dados com aplicabilidade/justificação.
6. Revisão: conferir informação e anexos antes da finalização.
7. Submissão: validação completa, código do processo, versão finalizada e confirmação na fila de e-mails.

Pode guardar rascunhos, retomar o processo e consultar o histórico. Há no máximo 20 rascunhos por conta. A confirmação usa bloqueio/validação no servidor e preserva um snapshot da versão; repetir o envio não deve criar uma nova submissão independente. Versões finalizadas não são editadas como rascunhos. Quando a equipa pede revisão, o autor envia uma nova versão e resposta ao editor, conservando as anteriores.

### Estados editoriais

| Estado | Próximas operações editoriais previstas |
| --- | --- |
| Rascunho (`draft`) | Autor completa/confirma; não aparece como processo editorial submetido |
| Submetido (`submitted`) | Triagem ou rejeição |
| Triagem (`screening`) | Revisão, pedido de revisões, aceitação ou rejeição |
| Em revisão (`review`) | Pedido de revisões, aceitação ou rejeição |
| Revisões solicitadas (`revision_requested`) | Autor envia versão revista; equipa pode rejeitar |
| Manuscrito revisto (`revised`) | Reavaliação, revisão, aceitação ou rejeição |
| Reavaliação (`reevaluation`) | Revisão, pedido de revisões, aceitação ou rejeição |
| Aceite (`accepted`) | Preparar publicação, criando rascunho separado |
| Produção (`production`) | Conferir/editar rascunho e publicar |
| Publicado (`published`) | Ocultar publicação regressa o processo à produção |
| Rejeitado (`rejected`) | Sem transição normal de reabertura na interface |

Decisões exigem observação e respeitam a tabela de transições no servidor. Existem atribuição de editor e notas internas. Eventos guardam actor, acção, estado anterior/novo, nota, data e visibilidade para o autor. Notas internas não são expostas ao autor. Confirmações e decisões são notificações transaccionais, distintas das notificações de acompanhamento do leitor.

`ReviewAssignment` é uma base para futura atribuição de revisores. Não existe portal completo de revisores nem garantia de anonimização/blind review implementada.

### Anexos privados

| Limite | Valor |
| --- | --- |
| Ficheiro individual | 8 MiB |
| Ficheiros por versão | 25 |
| Total de anexos por conta | 100 MiB |
| Formatos suportados | DOCX, XLSX, PDF, PNG, JPG/JPEG, CSV e TXT; principal sujeito à configuração da revista |
| PDF | Não cifrado, 1–500 páginas, sem conteúdo activo detectado |
| Arquivo Office | Até 1500 entradas e 32 MiB descomprimidos |
| Imagem de submissão | Até 20 milhões de pixels, formato real verificado |

São verificados extensão, MIME, assinatura/estrutura, limites e conteúdo inválido. Office com macros, ActiveX, objectos incorporados executáveis, entidades XML ou relações externas não permitidas é rejeitado; hyperlinks normais HTTP/HTTPS/mailto podem ser aceites. PDF com JavaScript/acções proibidas, cifrado ou corrompido é rejeitado. Texto usa UTF-8 e rejeita caracteres de controlo proibidos. Estas verificações não são um antivírus.

Os payloads ficam em `ManuscriptFile` com nome interno, MIME, tamanho e SHA-256, fora de `/static` e do Cloudinary. Download exige propriedade da submissão ou acesso editorial. O backup da base deve incluir esses binários.

### Da aceitação à publicação

“Preparar publicação” cria um **novo registo Journal em rascunho** e mantém a revista de origem. Copia metadados, autores, declarações e histórico; não torna os anexos originais públicos.

DOCX permite importação limitada de texto, tabelas e imagens bitmap; TXT permite importação de texto. PDF não é convertido automaticamente para artigo: a equipa insere/revê o conteúdo. Conteúdo científico fornecido nos campos próprios pode completar/substituir a importação. Figuras são copiadas e sanitizadas para `PublicationAsset`; só ficam públicas quando a publicação está visível. Ao ocultar, voltam a exigir acesso editorial. Rever sempre o resultado antes de publicar.

## Conteúdo, imagens e vídeos

### Markdown e directivas

O servidor usa Python Markdown com extensões `extra`/`sane_lists`, sanitização Bleach e ligações automáticas de URLs em texto apropriado. Links, imagens, tabelas, listas, referências e formatação devem respeitar o conjunto permitido; scripts e HTML perigoso não são conteúdo editorial aceite.

```markdown
## Secção do artigo

Texto com **ênfase**, [fonte](https://example.org) e uma imagem:

![Descrição acessível](https://example.org/figura.jpg)

[video: Título do vídeo](https://www.youtube.com/watch?v=IDENTIFICADOR)

[chart: bar|Comparação|Grupo A=10;Grupo B=20]

[portrait: Texto alternativo|Legenda|Crédito](https://example.org/retrato.jpg)

[destaque: Texto da citação|Autor]

[capitular] Primeiro parágrafo com capitular.
```

Gráficos admitem `bar`, `line` e `pie`, até 12 pontos numéricos finitos não negativos e dados com valor positivo. São gerados como SVG; não consultam dados externos. Vídeos aceitam YouTube (incorporação com domínio de privacidade), Vimeo e ligações directas HTTP/HTTPS MP4, WebM ou OGG reconhecidas. As directivas têm sintaxe própria; testar a apresentação final no artigo e, se aplicável, no PDF.

### Uploads do painel

Imagens públicas passam por Pillow: até 8 MiB e 40 milhões de pixels, validação do formato, redimensionamento e conversão WebP. Limites de enquadramento: artigos 2000×2000, fotografias 800×800 e capas de revista 1600×2200. O URL seguro devolvido pelo Cloudinary é guardado na base. Há optimização de URLs Cloudinary e fallback visual para imagens indisponíveis.

Vídeos enviados pelo painel admitem até 50 MiB, extensões MP4/WebM/OGG e assinatura inicial correspondente. Cloudinary recebe recurso de vídeo e devolve URL seguro, com pedido de saída MP4. A validação local de assinatura não confirma todo o codec/conteúdo do vídeo; verificar reprodução após upload. O limite global do pedido Flask é 60 MiB, incluindo o formulário multipart.

URLs já alojados podem ser usados nos campos compatíveis sem novo upload. Imagens externas continuam dependentes do servidor de origem. Os nomes de pasta Cloudinary são configuráveis; nunca colocar API secret no JavaScript ou no README.

## Integrações

### Assistente científico

O navegador envia pergunta a `POST /api/assistente`; Flask valida 1–800 caracteres, aplica limites de cinco pedidos/minuto e vinte/hora e chama o Worker com `X-Assistant-Key`. O Worker só aceita POST e o segredo correcto, usa binding `AI` e o modelo configurado no código `@cf/meta/llama-3.1-8b-instruct-fast`, com resposta em português e limite de 500 tokens de saída.

Configurar `ASSISTANT_WORKER_URL` e o mesmo `ASSISTANT_SHARED_KEY` na aplicação e nos Secrets do Worker; disponibilizar binding Workers AI chamado `AI` e publicar `cloudflare-worker/worker.js`. O browser não recebe o segredo. Falhas do modelo/Worker são devolvidas como indisponibilidade; não há pesquisa automática de fontes, memória persistente de conversa ou RAG implementados. O ficheiro [cloudflare-worker/README.md](cloudflare-worker/README.md) ainda contém referências históricas ao Render; usar o ambiente actual da aplicação no Coolify para essas variáveis.

### SMTP e e-mails transaccionais

Registo, recuperação, confirmação de submissão e decisões colocam mensagens em `EditorialNotification`. Para entrega, configurar SMTP e executar periodicamente **um único worker**:

```bash
flask --app app enviar-notificacoes --limit 50
```

Agendar, por exemplo, a cada minuto, no ambiente com a mesma base e segredos. O comando aceita limite 1–500, conserva mensagens pendentes, regista tentativas e usa Message-ID estável. TLS ou SSL é obrigatório fora dos testes. Uma falha entre entrega SMTP e commit pode causar duplicação na tentativa seguinte; o Message-ID não garante entrega exactamente uma vez. Sem a tarefa SMTP, as mensagens ficam na fila.

### Analytics, consentimento e redes sociais

A interface gere escolhas de cookies necessários, analytics e publicidade, persiste consentimento `cookie_consent_v3` durante 180 dias e actualiza consentimento Google. Scripts opcionais seguem as escolhas previstas no código. GTM e verificação Search Console são configuráveis; atribuir os IDs da instalação efectiva. O tema claro/escuro usa `sessionStorage`, enquanto a colecção educativa usa `localStorage`.

As ligações de Facebook, Instagram, YouTube, LinkedIn, X e WhatsApp podem ser definidas por ambiente. Conteúdo/links adicionais nos templates devem ser alterados no código. A configuração de consentimento não substitui a revisão das políticas publicadas e dos scripts configurados no GTM.

## Dados e persistência

| Modelo | Conteúdo principal |
| --- | --- |
| `AdminUser` | Identidade administrativa, hash, actividade, privilégios, segredo TOTP e hashes de recuperação |
| `Author`, `Category` | Perfis públicos, metadados académicos e classificação de artigos |
| `Article` | Conteúdo de divulgação, slug, autor/categoria, estado, datas, media e referências |
| `Journal` | Identidade de revista e conteúdo científico público/rascunho, autores e metadados |
| `EditorialPolicy` | Textos editáveis de políticas e diretrizes |
| `Comment` | Texto, identificação do comentador, artigo e aprovação |
| `ContactMessage`, `Subscriber` | Contactos recebidos/estado de leitura e inscrições/activação |
| `Researcher`, `GoogleIdentity` | Conta pública/investigador, confirmação, nonce e identidade Google |
| `ReaderArticle`, `ReaderJournal` | Favoritos e acompanhamento por conta, revisão reconhecida |
| `SubmissionSetting` | Abertura, tipos, formatos e e-mail editorial por revista |
| `Manuscript`, `ManuscriptAuthor` | Processo editorial, metadados/declaracões e autores ordenados |
| `ManuscriptVersion`, `ManuscriptFile` | Snapshots, versões e anexos privados com payload/hash |
| `EditorialEvent` | Histórico de acções, decisões e notas com visibilidade |
| `ReviewAssignment` | Fundação para funcionalidade futura de revisores |
| `EditorialNotification` | Fila transaccional de e-mail e estado de entrega |
| `PublicationAsset` | Cópias sanitizadas de figuras ligadas à publicação |

SQLite é o padrão local (`sqlite:///sussurros.db`, normalmente na pasta `instance/`). Para produção, configurar PostgreSQL persistente por `DATABASE_URL`; o código normaliza `postgres://` para `postgresql://`. A versão exacta do servidor PostgreSQL é definida pela infraestrutura, não pelo repositório.

Ao importar a aplicação, são executados `db.create_all()`, alterações leves de colunas existentes e seed quando as tabelas de conteúdo estão vazias. `create_all()` não migra sozinho colunas de tabelas antigas. Não há Alembic nem ferramenta geral de downgrade; fazer backup antes de upgrades e testar uma cópia da base. Uma base de conteúdo vazia pode receber exemplos iniciais automaticamente.

Comando específico para as tabelas Google/favoritos:

```bash
flask --app app migrar-login-google
```

O comando deve ser executado no ambiente correcto e não substitui a estratégia de migração das outras tabelas. Ver detalhes em [docs/google-login.md](docs/google-login.md).

## Instalação e desenvolvimento

### Linux/macOS

```bash
git clone https://github.com/MergiorGoriate/sussurros-do-saber.git
cd sussurros-do-saber
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
npm ci
npm run build:css
```

Definir as variáveis no ambiente do processo, usando valores locais próprios. O código não carrega automaticamente um `.env` por `python app.py`; não presumir esse carregamento. Gerar segredo e hash sem os guardar no repositório:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "from getpass import getpass; from werkzeug.security import generate_password_hash; print(generate_password_hash(getpass('Palavra-passe: ')))"
```

Depois configurar `SECRET_KEY`, `ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH` e, para a conta administrativa, `ADMIN_TOTP_SECRET` de um autenticador. Para ambiente local, manter `FLASK_ENV` fora de produção; Redis pode ser omitido, usando contador em memória. Executar:

```bash
python app.py
```

Abrir `http://127.0.0.1:5000` e `/admin/login`. O servidor de desenvolvimento não deve ser usado para servir produção. `FLASK_DEBUG=true` só activa debug fora de produção.

### Windows PowerShell

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
npm ci
npm run build:css
$env:SECRET_KEY = 'SUBSTITUIR_POR_SEGREDO_LOCAL'
$env:ADMIN_USERNAME = 'editor-local'
$env:ADMIN_PASSWORD_HASH = 'SUBSTITUIR_POR_HASH_GERADO'
python app.py
```

Configurar também TOTP para a conta usada. Se a política do PowerShell impedir activação, pode executar directamente `.\.venv\Scripts\python.exe` em vez de mudar a política global.

### CSS e execução Docker

`npm run build:css` compila Tailwind; executar após alterações a classes/templates. Node não é necessário para servir a aplicação Python depois do build.

```bash
docker build -t sussurros-do-saber:local .
docker run --rm -p 8000:8000 --env-file /caminho/seguro/config.local sussurros-do-saber:local
```

O ficheiro de ambiente é fornecido pelo Docker, não carregado pela aplicação. Para persistência, usar PostgreSQL externo; não confiar no SQLite dentro de um contentor efémero. A imagem constrói CSS com Node 22, instala Python 3.11, usa utilizador sem privilégios e inicia Gunicorn com um worker, timeout de 120 segundos e porta `PORT` (padrão 8000).

## Configuração

Segredos pertencem às variáveis protegidas do serviço/Worker. Os valores abaixo descrevem nomes e comportamento; não são credenciais reais.

### Aplicação, administração e infraestrutura

| Variável | Uso e requisito |
| --- | --- |
| `FLASK_ENV` | `production` activa regras de produção; definir explicitamente no servidor |
| `RENDER` | `true` também activa modo produção, por compatibilidade histórica; não é requisito do Coolify |
| `SECRET_KEY` | Assinatura de sessão/tokens; obrigatório e não padrão em produção |
| `DATABASE_URL` | PostgreSQL de produção; SQLite por padrão local |
| `SITE_URL` | Origem pública usada em links e metadados; padrão canónico com `www` |
| `RATELIMIT_STORAGE_URI` | Redis para limites; tem prioridade sobre `REDIS_URL`; obrigatório um dos dois em produção |
| `REDIS_URL` | Alternativa de configuração Redis; memória só no desenvolvimento |
| `ADMIN_USERNAME` | Administrador principal por ambiente; define também a precedência dos privilégios |
| `ADMIN_PASSWORD_HASH` | Hash Werkzeug da palavra-passe administrativa, exigido para conta por ambiente em produção |
| `ADMIN_PASSWORD` | Alternativa em texto apenas no desenvolvimento; não usar em produção |
| `ADMIN_TOTP_SECRET` | Segredo TOTP da conta gerida por ambiente; exigido para esse acesso em produção |
| `ADMIN_IDLE_TIMEOUT_MINUTES` | Inactividade administrativa; padrão 15, intervalo 1–120 |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | Chaves pública/privada do Turnstile para o login administrativo |
| `REQUIRE_TURNSTILE` | Obrigatório por padrão em produção; manter `true` e configurar as duas chaves |
| `SESSION_COOKIE_SECURE` | Pode forçar cookie Secure fora de produção; em produção fica activo |
| `FLASK_DEBUG` | Debug local explícito, ignorado em produção |
| `PORT` | Porta do comando Gunicorn no Docker; padrão 8000 |

### Media, identidade e assistente

| Variável | Uso |
| --- | --- |
| `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET` | As três credenciais exigidas pelos uploads |
| `CLOUDINARY_FOLDER` | Pasta de imagens de artigos; padrão `sussurros-do-saber/artigos` |
| `CLOUDINARY_AUTHOR_FOLDER` | Fotografias; padrão `sussurros-do-saber/autores` |
| `CLOUDINARY_JOURNAL_FOLDER` | Capas; padrão `sussurros-do-saber/revistas` |
| `CLOUDINARY_VIDEO_FOLDER` | Vídeos; padrão `sussurros-do-saber/videos` |
| `CLOUDINARY_URL` | Lida para identificação do cloud em optimização; não substitui as três credenciais exigidas pelo upload |
| `GOOGLE_CLIENT_ID` | Login Google opcional; ID público da aplicação Web |
| `GOOGLE_SITE_VERIFICATION` | Token de verificação do site nos metadados |
| `GTM_CONTAINER_ID` | Container GTM; configurar para a instalação efectiva |
| `ASSISTANT_WORKER_URL` | Endpoint do Worker; há URL padrão no código |
| `ASSISTANT_SHARED_KEY` | Mesmo segredo privado na aplicação e no Worker |
| `SOCIAL_FACEBOOK_URL`, `SOCIAL_INSTAGRAM_URL`, `SOCIAL_YOUTUBE_URL` | Ligações institucionais; existem padrões no código |
| `SOCIAL_LINKEDIN_URL`, `SOCIAL_X_URL`, `SOCIAL_WHATSAPP_URL` | Ligações institucionais restantes |

### SMTP

| Variável | Uso |
| --- | --- |
| `SMTP_HOST` | Servidor obrigatório para entrega |
| `SMTP_FROM` | Endereço remetente válido obrigatório |
| `SMTP_PORT` | Padrão 587 com TLS, 465 com SSL |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | Autenticação quando o provedor a exige |
| `SMTP_TLS` | Padrão `true`, usa STARTTLS se SSL não estiver activo |
| `SMTP_SSL` | Padrão `false`, ligação SSL directa quando `true` |

Estas variáveis configuram envio, não DNS do domínio. MX, SPF, DKIM e DMARC são configurados no DNS conforme o provedor de e-mail contratado; os seus valores não devem ser inventados ou copiados de exemplos de outro serviço.

## Produção, manutenção e recuperação

O projecto é compatível com execução Docker no Coolify e PostgreSQL/Redis externos. A infraestrutura usada pelo projecto foi descrita como VPS OVHcloud com Coolify, domínio na Spaceship, DNS no Cloudflare e backups externos. A versão PostgreSQL, destino R2, agenda de backup, ramo de deployment e estado actual dos serviços devem ser confirmados no painel; o código não comprova essas configurações.

### Deployment no Coolify

1. Seleccionar o repositório e o ramo que contém as alterações aprovadas. A configuração antiga pode apontar para `deploy/coolify-vps`; conferir explicitamente o ramo e o commit, sem assumir que segue `main`.
2. Construir pelo `Dockerfile`, definir porta interna 8000 (ou `PORT`) e domínio HTTPS canónico.
3. Configurar produção, segredo, PostgreSQL persistente, Redis e credenciais administrativas/2FA/Turnstile. Acrescentar integrações realmente utilizadas.
4. Fazer backup antes de mudança de versão que altere esquema; testar alteração numa cópia quando aplicável.
5. Executar deploy/redeploy e confirmar o commit servido, logs e `GET /healthz`.
6. Configurar separadamente a tarefa de entrega SMTP. Confirmar envio real de teste e fila; deploy do Flask não cria a tarefa automaticamente.
7. Verificar página inicial, artigo, revista/índice em computador e telefone, PDF, login, submissões e integrações activas.

`/healthz` executa uma consulta simples à base e devolve estado apropriado. Não verifica entrega SMTP, Redis, Cloudinary, Worker AI, Google, DNS ou qualidade do conteúdo. Usar monitorização externa e alertas separados para esses componentes e para disco/memória/processo.

### DNS e e-mail

O registo do domínio e a autoridade DNS são funções diferentes. Se Cloudflare for a autoridade, os nameservers no registador devem coincidir exactamente com os atribuídos à zona. Os registos DNS do site/e-mail devem ser mantidos no provedor autoritativo. O estado visual de propagação num painel não basta para comprovar resolução mundial ou entrega de e-mail.

Coolify executa a aplicação; não é o local de delegação de nameservers. Não tratar correcção de DNS como alteração ao código nem mudar registos de e-mail para resolver um erro de interface.

### Backups e rollback

- Guardar backups consistentes de PostgreSQL, incluindo payloads de anexos/figuras, utilizadores, favoritos e histórico editorial; proteger acesso porque contêm dados privados.
- Manter media Cloudinary, configuração do serviço, versões do código e configuração do Worker segundo a estratégia operacional. Redis armazena contadores, não substitui backup da base.
- Confirmar retenção, cópia externa e ensaiar restauração. Um job configurado sem restauração validada não comprova recuperação.
- No rollback de código, preservar tabelas e dados novos; não executar `db.drop_all()`, apagar volume ou restaurar uma base antiga sobre produção sem plano explícito.
- Mudanças do esquema são aditivas e leves, mas não têm downgrade automático; testar compatibilidade com o código anterior antes de voltar a uma versão.
- Depois de restaurar, verificar contas, conteúdo, anexos, versões, favoritos, acesso privado, fila SMTP e ficheiros externos.

## Segurança, privacidade e desempenho

- Sessões assinadas com cookies HttpOnly/SameSite=Lax e Secure em produção; duração de sessão pública de duas horas. Administração tem controlo adicional de inactividade e 2FA.
- CSRF para mutações, validação de campos e permissões no servidor, hashes de palavras-passe, tokens temporários de confirmação/recuperação e nonce de conta.
- Flask-Limiter aplica limites gerais (300/dia, 100/hora) e específicos por operação. Usar Redis partilhado evita contadores independentes por worker em produção.
- CSP com nonce/scripts autorizados, `nosniff`, política de referência, restrições de permissões e HSTS quando HTTPS. A política mantém estilos inline permitidos para a interface existente; não declarar uma CSP sem qualquer inline.
- `ProxyFix` confia em um salto de proxy para IP/protocolo/host. A implantação deve corresponder a essa topologia e não expor confiança em cabeçalhos arbitrários directamente à aplicação.
- Respostas administrativas, contas, Google e submissões usam cache privado/no-store; áreas privadas também recebem restrições de indexação quando previstas.
- Gzip para texto elegível, respeitando negociação; cache curto nas páginas públicas elegíveis e cache longo de estáticos versionados. Não aplicar cache público ao HTML com sessão/formulário privado.
- Imagens responsivas/lazy loading, optimização Cloudinary e listas que evitam carregar corpos desnecessários. CSS Tailwind é compilado no build.
- Navegação responsiva, labels, foco de teclado, diálogos e página de acessibilidade existem; isso não é certificação WCAG nem auditoria completa por leitores de ecrã.
- CSV administrativo aplica tratamento de valores para reduzir interpretação como fórmulas. Exportações contêm dados pessoais e são restritas ao painel.

Evitar publicar dumps, tokens, segredos TOTP, anexos privados e credenciais em issues, logs ou ficheiros versionados. As validações existentes não equivalem a auditoria de segurança independente.

## Testes e validação

Testes Python:

```bash
python -m unittest discover -s tests -p 'test_*.py' -v
```

Incluem plataforma, regressões do site, submissões, contas, login Google, conteúdo editorial, metadados e PDF. Usar uma base de teste isolada: importar `app` inicializa o esquema e pode criar dados iniciais.

Testes de navegador:

```bash
npm ci
npm run build:css
npx playwright install chromium
npm run test:e2e
```

O Playwright espera aplicação em `http://127.0.0.1:5000`, com fixtures/configuração próprias. Consultar [playwright.config.js](playwright.config.js), `tests/browser/` e a sequência completa de preparação em [.github/workflows/ci.yml](.github/workflows/ci.yml); executar apenas o comando não inicia nem prepara automaticamente o servidor.

A CI de `main`/pull requests executa testes Python, auditoria pip, build CSS, auditoria npm de dependências de produção, navegador Chromium e upload de diagnóstico. O workflow separado constrói Docker. Dependabot está configurado para dependências do projecto. Ver o resultado do commit específico no GitHub Actions; a presença de testes não significa que passaram num deployment diferente.

[docs/site-audit-20261005.md](docs/site-audit-20261005.md) guarda uma auditoria histórica com escopo/commit e limitações próprias. Não usar as contagens ou observações daquele documento como prova automática do estado actual. Nesta revisão do README, a verificação é documental contra o código, não um novo ensaio completo de produção.

## Limites da implementação

- Publicação científica usa `Journal` como registo combinado; template ou campo legado sem rota activa não comprova um módulo completo de edições.
- DOI/ISSN, licenças e histórico são metadados editoriais. Não há emissão Crossref, depósito DOI, registo ISSN, indexação automática ou verificação externa implementados.
- Há estados de revisão e decisões, mas não um portal funcional de revisores/blind review.
- Newsletter guarda inscrições; contacto guarda mensagens. Não existe motor de campanhas ou encaminhamento automático desses contactos.
- Notificações de acompanhamento são internas; e-mails editoriais dependem de SMTP e do comando agendado.
- PDF é uma composição própria e a conversão DOCX é limitada. Publicar exige revisão humana do conteúdo e das figuras.
- O catálogo educativo é definido no código; as preferências educativas locais não sincronizam entre dispositivos.
- O assistente chama um modelo com uma pergunta, sem pesquisa de fontes ou contexto completo da base editorial.
- Programação de artigos é verificada em pedidos, não por cron autónomo. Revistas não têm agendamento de publicação equivalente.
- Não há migrações versionadas Alembic, downgrade automático, antivírus de anexos ou prova de configuração/backup de infraestrutura apenas pela leitura deste repositório.

## Inventário completo de rotas

Inventário dos decoradores de rotas do código revisto. `GET` inclui o tratamento automático de HEAD quando aplicável; OPTIONS é gerido pelo Flask. Os parâmetros entre `<...>` são variáveis, não texto literal. O prefixo do blueprint já está incluído. Rotas administrativas, de conta e submissão mantêm as permissões descritas acima; uma rota listada não significa acesso público.

### Páginas públicas, APIs e pré-visualizações

| Método | Rota | Handler em `app.py` |
| --- | --- | --- |
| GET | `/diretrizes-para-autores` | `author_guidelines` |
| GET | `/ads.txt` | `ads_txt` |
| GET | `/` | `home` |
| GET | `/artigos` | `articles` |
| GET | `/artigo/<slug>` | `article` |
| POST | `/artigo/<slug>/comentarios` | `submit_comment` |
| GET | `/artigo/<int:article_id>` | `article_legacy` |
| GET | `/sobre` | `about` |
| GET | `/autores` | `authors` |
| GET | `/autor/<slug>` | `author_detail` |
| GET | `/autor/<int:author_id>` | `legacy_author` |
| GET | `/contacto` | `contact` |
| GET | `/termos-e-condicoes` | `terms` |
| GET | `/politica-de-privacidade` | `privacy` |
| GET | `/politica-editorial` | `editorial_policy` |
| GET | `/politicas-editoriais` | `editorial_policy` |
| GET | `/politica-de-correcoes` | `corrections_policy` |
| GET | `/acessibilidade` | `accessibility` |
| GET | `/servicos` | `services` |
| GET | `/servicos/edicao-cientifica` | `scientific_editing` |
| GET | `/revistas` | `journals` |
| GET | `/revistas/<slug>` | `journal_detail` |
| POST | `/admin/revistas/previsualizar-markdown` | `journal_markdown_preview` |
| GET | `/admin/revistas/<int:journal_id>/previsualizar` | `journal_preview` |
| GET | `/revistas/<slug>/baixar.pdf` | `journal_download_pdf` |
| GET | `/admin/revistas/<int:journal_id>/baixar.pdf` | `journal_preview_pdf` |
| GET | `/recursos` | `resources` |
| GET | `/aprender` | `learn` |
| GET | `/laboratorio/osmose` | `osmosis_lab` |
| GET | `/api/recursos` | `api_resources` |
| GET | `/favoritos` | `favorites` |
| GET | `/api/artigos` | `api_articles` |
| GET | `/feed.xml` | `feed` |
| GET | `/sitemap.xml` | `sitemap` |
| GET | `/robots.txt` | `robots` |
| GET | `/healthz` | `healthcheck` |
| POST | `/api/newsletter` | `newsletter` |
| POST | `/api/assistente` | `assistant` |
| POST | `/api/contacto` | `submit_contact` |

### Administração

| Método | Rota | Handler em `admin.py` |
| --- | --- | --- |
| GET, POST | `/admin/login` | `login` |
| GET, POST | `/admin/verificar-2fa` | `verify_two_factor` |
| GET, POST | `/admin/seguranca/2fa` | `two_factor_settings` |
| POST | `/admin/logout` | `logout` |
| GET, POST | `/admin/politicas-editoriais` | `editorial_policies` |
| POST | `/admin/politicas-editoriais/previsualizar` | `preview_author_guidelines` |
| GET | `/admin/docs` | `docs` |
| GET | `/admin` | `dashboard` |
| GET, POST | `/admin/administradores` | `administrators` |
| POST | `/admin/administradores/<int:administrator_id>/editar` | `edit_administrator` |
| POST | `/admin/administradores/<int:administrator_id>/eliminar` | `delete_administrator` |
| GET | `/admin/artigos` | `articles` |
| POST | `/admin/api/videos` | `upload_inline_video` |
| POST | `/admin/api/imagens` | `upload_inline_image` |
| GET, POST | `/admin/artigos/novo` | `article_form` |
| GET, POST | `/admin/artigos/<int:article_id>/editar` | `article_form` |
| POST | `/admin/artigos/<int:article_id>/eliminar` | `delete_article` |
| GET, POST | `/admin/autores` | `authors` |
| POST | `/admin/autores/<int:author_id>/eliminar` | `delete_author` |
| GET, POST | `/admin/categorias` | `categories` |
| POST | `/admin/categorias/<int:category_id>/eliminar` | `delete_category` |
| GET | `/admin/revistas` | `journals` |
| GET, POST | `/admin/revistas/nova` | `journal_form` |
| GET, POST | `/admin/revistas/<int:journal_id>/editar` | `journal_form` |
| POST | `/admin/revistas/<int:journal_id>/publicacao` | `toggle_journal` |
| POST | `/admin/revistas/<int:journal_id>/eliminar` | `delete_journal` |
| GET | `/admin/comentarios` | `comments` |
| POST | `/admin/comentarios/<int:comment_id>/estado` | `update_comment_status` |
| POST | `/admin/comentarios/<int:comment_id>/eliminar` | `delete_comment` |
| GET | `/admin/contactos` | `contacts` |
| GET | `/admin/subscritores` | `subscribers` |
| POST | `/admin/contactos/<int:message_id>/eliminar` | `delete_contact` |
| POST | `/admin/subscritores/<int:subscriber_id>/estado` | `toggle_subscriber` |
| GET | `/admin/contactos/exportar.csv` | `export_contacts` |
| GET | `/admin/subscritores/exportar.csv` | `export_subscribers` |

### Contas e biblioteca

| Método | Rota | Handler em `reader_accounts.py` |
| --- | --- | --- |
| GET | `/conta/sessao` | `state` |
| POST | `/conta/entrar` | `login` |
| POST | `/conta/criar-conta` | `register` |
| POST | `/conta/artigos/<int:ident>` | `article_preference` |
| POST | `/conta/importar-favoritos` | `import_favorites` |
| GET, POST | `/conta/revistas/<slug>` | `preference` |
| GET | `/conta/biblioteca` | `library` |
| GET | `/conta/notificacoes` | `notifications` |

### Login Google

| Método | Rota | Handler em `google_auth.py` |
| --- | --- | --- |
| POST | `/conta/google/preparar` | `prepare` |
| POST | `/conta/google/entrar` | `login` |

### Submissões e gestão editorial

| Método | Rota | Handler em `submissions.py` |
| --- | --- | --- |
| GET, POST | `/submissoes/criar-conta` | `register` |
| GET, POST | `/submissoes/entrar` | `login` |
| POST | `/submissoes/sair` | `logout` |
| GET, POST | `/submissoes/confirmacao` | `verify_notice` |
| GET, POST | `/submissoes/confirmar/<token>` | `verify` |
| GET, POST | `/submissoes/recuperar` | `forgot_password` |
| GET, POST | `/submissoes/recuperar/<token>` | `reset_password` |
| GET | `/submissoes` | `mine` |
| GET | `/submissoes/` | `mine` |
| GET, POST | `/submissoes/nova` | `new` |
| GET, POST | `/submissoes/<int:ident>/etapa/<int:step>` | `edit` |
| POST | `/submissoes/<int:ident>/ficheiros` | `upload` |
| POST | `/submissoes/ficheiros/<int:file_id>/remover` | `remove_file` |
| GET | `/submissoes/ficheiros/<int:file_id>` | `download` |
| POST | `/submissoes/<int:ident>/confirmar` | `submit` |
| GET | `/submissoes/<int:ident>` | `detail` |
| POST | `/submissoes/<int:ident>/nova-versao` | `revised` |
| GET | `/admin/submissoes` | `submissions_list` |
| GET, POST | `/admin/submissoes/configuracao` | `submission_settings` |
| GET, POST | `/admin/submissoes/<int:ident>` | `submission_detail` |
| POST | `/admin/submissoes/<int:ident>/preparar` | `prepare_publication` |
| GET | `/submissoes/figuras/<int:asset_id>` | `publication_figure` |

### Protocolo das APIs principais

| Endpoint | Entrada/resposta principal |
| --- | --- |
| `GET /api/artigos` | `q`, `ids` (até 50 IDs), `limit` (1–50, padrão 24); metadados/cartões de artigos publicados, sem corpos completos |
| `GET /api/recursos` | Catálogo educativo JSON; cache específico de 600 segundos e stale-while-revalidate |
| `POST /api/newsletter` | Inscrição validada; grava/reativa subscritor |
| `POST /api/contacto` | Dados de contacto validados; grava mensagem |
| `POST /api/assistente` | Pergunta `message`; JSON com estado/resposta; erro de integração quando indisponível |
| `GET /conta/sessao` | Autenticação, confirmação, CSRF, nome/fotografia, artigos guardados, contador de notificações e supressão Google |
| `POST /conta/artigos/<ident>` | `enabled=true/false`, CSRF; guarda/remove artigo público |
| `GET/POST /conta/revistas/<slug>` | Preferências; POST com `action=saved/following/read`, `enabled` e revisão quando reconhece leitura |
| `POST /conta/importar-favoritos` | Listas `article_ids`/`journal_slugs`, no máximo 100 itens no total por lote |
| `POST /conta/google/preparar` e `/entrar` | Preparação nonce/CSRF e validação de credencial Google; detalhes em `google_auth.py` |
| `POST /admin/api/imagens` e `/videos` | Multipart autenticado com CSRF; validação, upload e URL de recurso |
| Pré-visualizações Markdown | POST administrativo autenticado/CSRF; conteúdo sanitizado, limites próprios |

Os formulários e JavaScript do repositório definem os nomes exactos dos campos e mensagens. As APIs são internas ao site, sem promessa de contrato externo versionado, CORS público ou autenticação por chave para terceiros. Para manutenção, conferir handlers antes de criar clientes independentes.

## Como manter esta documentação

Ao alterar rotas, permissões, estados, campos, limites, variáveis, templates ou tarefas de operação, actualizar esta documentação e os guias relacionados no mesmo trabalho. Separar claramente o que está implementado, o que é configuração do deployment e o que ainda é futuro. Não marcar uma integração como validada só porque há um botão ou uma variável.
