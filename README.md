# Sussurros do Saber

Portal editorial científico criado com Python (Flask), Tailwind CSS e JavaScript. Produção no OVHcloud VPS-2, administrada pelo Coolify, com PostgreSQL 18 e backups para Cloudflare R2. O Coolify acompanha a branch `deploy/coolify-vps` até à integração do PR de migração em `main`.

## Executar no Windows

1. Instale Python 3.11 ou superior.
2. Abra o terminal dentro desta pasta.
3. Crie o ambiente: `python -m venv .venv`
4. Active-o: `.venv\Scripts\activate`
5. Instale: `pip install -r requirements.txt`
6. Execute: `python app.py`
7. Abra `http://127.0.0.1:5000`

## Administração e base de dados

A área editorial está disponível em `/admin`. Antes de publicar, configure:

- `SECRET_KEY`: sequência longa e aleatória para proteger sessões.
- `ADMIN_USERNAME`: nome do administrador.
- `ADMIN_PASSWORD_HASH`: hash seguro da palavra-passe administrativa (recomendado).
- `ADMIN_PASSWORD`: alternativa compatível; mantenha apenas enquanto migra para o hash.
- `DATABASE_URL`: ligação PostgreSQL fornecida pelo serviço de base de dados.
- `SITE_URL`: endereço canónico, por exemplo `https://www.sussurrosdosaber.com`.
- `ASSISTANT_SHARED_KEY`: segredo igual no Coolify e no Cloudflare Worker.
- `ASSISTANT_WORKER_URL`: URL do Worker (opcional se mantiver o endereço actual).
- `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY`: protecção Cloudflare Turnstile no login (recomendado).
- `REQUIRE_TURNSTILE=true`: impede o login quando o Turnstile não está corretamente configurado.
- `RATELIMIT_STORAGE_URI`: URL Redis para limites partilhados entre processos; sem ela usa memória local.

Para gerar o hash da palavra-passe no Prompt de Comando do Windows, execute:

`python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash(input('Palavra-passe: ')))"`

Copie o resultado completo para `ADMIN_PASSWORD_HASH` no Coolify e remova `ADMIN_PASSWORD` depois de confirmar o login.

### Upload de imagens com Cloudinary

Crie uma conta Cloudinary e configure no Coolify:

- `CLOUDINARY_CLOUD_NAME`: nome da cloud mostrado no painel
- `CLOUDINARY_API_KEY`: chave da API
- `CLOUDINARY_API_SECRET`: segredo da API
- `CLOUDINARY_FOLDER`: pasta de destino opcional; por padrão `sussurros-do-saber/artigos`

As imagens são verificadas, reduzidas para até 2000 × 2000 px, convertidas em WebP e enviadas com ligação HTTPS. O máximo aceite é 8 MB.

### Cloudflare Worker

O código pronto e as instruções do assistente estão em `cloudflare-worker/`. Nunca coloque `ASSISTANT_SHARED_KEY` no JavaScript público.

### Ensaio de recuperação

O guia operacional completo está em `/admin/docs`. Para arquivos de backup custom/tar do PostgreSQL, use `scripts/restore_drill.py` com cliente PostgreSQL 18 e as dependências Python do projeto. Configure `RESTORE_ADMIN_URL` num ambiente privado, apontando para a base de manutenção `postgres`, e execute `python scripts/restore_drill.py backup.dump --report restore-report.json`.

A ferramenta cria uma base nova com nome aleatório, verifica oito tabelas e relações entre artigos/autores/categorias/comentários, e grava um relatório privado. Nunca substitui nem elimina bases existentes. A revisão dos conteúdos, a comparação com contagens do momento do backup e a recuperação dos ativos Cloudinary precisam de validação separada. A execução CI usa uma cópia sintética PostgreSQL 18, não o backup de produção.

Sem `DATABASE_URL`, o projeto usa SQLite apenas para desenvolvimento local. Em produção no Coolify, configure a ligação ao PostgreSQL do VPS; confirme a ligação antes de cada mudança de branch ou implantação.

## Operação e recuperação

- A base de produção `sussurros-postgresql` usa backups agendados locais e no R2. Verifique cada execução e teste periodicamente a restauração num ambiente isolado.
- Configure notificações para falhas de backup, deploy e disponibilidade. Documente a retenção e o procedimento de recuperação.
- O antigo serviço e base do Render foram eliminados após a migração. Não implante novamente usando a configuração legada.

- Configure o monitor de disponibilidade para `GET /healthz`.
- Active backups automáticos da base PostgreSQL e faça um teste de restauração antes do lançamento público.
- Use Redis em `RATELIMIT_STORAGE_URI` quando executar mais de um processo ou instância.
- Mantenha Cloudinary, Coolify, GitHub e Cloudflare com autenticação de dois fatores.
- Todas as contas administrativas secundárias são obrigadas a configurar 2FA no primeiro acesso; não podem usar o restante painel antes da ativação.
- Teste localmente com `python -m unittest discover -s tests -v` antes de cada publicação.

## Funcionalidades

- Página inicial editorial responsiva
- Pesquisa e filtro de artigos
- Páginas individuais de leitura
- Área de periódicos científicos
- Formulário de newsletter com API Python
- API JSON em `/api/artigos`
- Menu móvel, acessibilidade básica e página 404
- Modo escuro, favoritos e progresso de leitura
- Calculadora estatística descritiva
- Gerador básico de referências APA
- Glossário científico pesquisável
- Página de favoritos guardados no navegador
- Quiz científico interactivo
- Partilha de artigos e botão de favorito visível
- Sugestões de artigos relacionados
- Feed RSS, sitemap XML e robots.txt para SEO
- Pesquisa também disponível pela API com `?q=palavra`
- Assistente científico flutuante com sugestões e API Python
- Respostas orientadas para Biologia, estatística, APA, Python e navegação
- Páginas Sobre Nós, Autores e Contacto
- Termos e Condições e Política de Privacidade
- Formulário de contacto validado pela API Python
- Centro de aprendizagem pesquisável por formato, tema e nível
- Laboratório virtual interactivo de osmose
- Colecções pessoais de recursos guardadas no navegador
- Partilha de artigos no WhatsApp, Facebook, X, LinkedIn e Telegram
- Partilha por e-mail e botão para copiar a ligação
- Página de Serviços para Autores e Pesquisadores
- Página detalhada de Edição Científica
- Página Revistas com catálogo pesquisável e informações editoriais
- Painel administrativo protegido, rascunhos e publicações programadas
- Gestão de artigos, autores, categorias, contactos e subscritores
- Cadastro de administradores individuais com palavras-passe protegidas por hash
- Upload de imagens optimizadas para Cloudinary
- Editor Markdown com pré-visualização, referências, DOI e palavras-chave
- Limites de utilização no login, assistente, contacto e newsletter
- Turnstile opcional e segredo privado entre Flask e Cloudflare Worker
- Política Editorial, Política de Correções e Declaração de Acessibilidade


## Frontend e resiliência de imagens

O Tailwind é compilado durante o build e servido localmente em `/static/css/tailwind.css`; o navegador não depende de `cdn.tailwindcss.com`. Execute `npm run build:css` depois de alterar classes nos templates ou scripts.

Imagens editoriais devem, de preferência, ser carregadas no Cloudinary pelo painel. Quando uma imagem externa falha ou bloqueia hotlinking, o frontend substitui-a automaticamente pelo ativo local `/static/img/image-fallback.svg`.
