# Sussurros do Saber

Portal editorial científico criado com Python (Flask), Tailwind CSS e JavaScript.

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
- `ALLOW_LEGACY_ADMIN_PASSWORD=true`: apenas para uma migração temporária; em produção, `ADMIN_PASSWORD` é ignorada por padrão.
- `DATABASE_URL`: ligação PostgreSQL fornecida pelo serviço de base de dados.
- `SITE_URL`: endereço canónico, por exemplo `https://sussurrosdosaber.com`.
- `ASSISTANT_SHARED_KEY`: segredo igual no Render e no Cloudflare Worker.
- `ASSISTANT_WORKER_URL`: URL do Worker (opcional se mantiver o endereço actual).
- `TURNSTILE_SITE_KEY` e `TURNSTILE_SECRET_KEY`: protecção Cloudflare Turnstile no login (recomendado).
- `REQUIRE_TURNSTILE=true`: impede o login quando o Turnstile não está corretamente configurado.
- `RATELIMIT_STORAGE_URI`: URL Redis para limites partilhados entre processos; sem ela usa memória local.
- `ADMIN_TIMEZONE`: fuso usado no agendamento editorial; por padrão `Africa/Maputo`.

Para gerar o hash da palavra-passe no Prompt de Comando do Windows, execute:

`python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash(input('Palavra-passe: ')))"`

Copie o resultado completo para `ADMIN_PASSWORD_HASH` no Render e remova `ADMIN_PASSWORD` depois de confirmar o login.

### Upload de imagens com Cloudinary

Crie uma conta Cloudinary e configure no Render:

- `CLOUDINARY_CLOUD_NAME`: nome da cloud mostrado no painel
- `CLOUDINARY_API_KEY`: chave da API
- `CLOUDINARY_API_SECRET`: segredo da API
- `CLOUDINARY_FOLDER`: pasta de destino opcional; por padrão `sussurros-do-saber/artigos`

As imagens são verificadas, reduzidas para até 2000 × 2000 px, convertidas em WebP e enviadas com ligação HTTPS. O máximo aceite é 8 MB.

### Cloudflare Worker

O código pronto e as instruções do assistente estão em `cloudflare-worker/`. Nunca coloque `ASSISTANT_SHARED_KEY` no JavaScript público.

Sem `DATABASE_URL`, o projeto usa SQLite apenas para desenvolvimento local. No Render, utilize PostgreSQL para manter artigos, contactos e subscritores após reinicializações.

## Operação e recuperação

- Configure o monitor de disponibilidade para `GET /healthz`.
- Active backups automáticos da base PostgreSQL e faça um teste de restauração antes do lançamento público.
- Use Redis em `RATELIMIT_STORAGE_URI` quando executar mais de um processo ou instância.
- Mantenha Cloudinary, Render e Cloudflare com autenticação de dois fatores.
- Teste localmente com `python -m unittest discover -s tests -v` antes de cada publicação.
- Execute `flask db upgrade` no processo de implantação quando forem adicionadas migrações Alembic.
- Não envie `.venv`, `.env`, bases SQLite nem credenciais para o Drive ou repositório.

### Comando de arranque no Render

Use exatamente:

`gunicorn app:app --bind 0.0.0.0:$PORT --workers 2 --timeout 120 --access-logfile - --error-logfile -`

O parâmetro `--bind 0.0.0.0:$PORT` é obrigatório para que o Render detete a porta do serviço. O projecto inclui também `render.yaml` e `Procfile` com esta configuração.

## Segurança administrativa

- A `SECRET_KEY` de produção deve ter no mínimo 32 caracteres; a aplicação recusa iniciar sem ela.
- A conta configurada no Render atua como acesso inicial de superadministrador. Crie uma conta individual e mantenha apenas `ADMIN_PASSWORD_HASH` durante a transição.
- Editores não podem gerir administradores. Somente superadministradores podem criar, desativar, reativar ou redefinir palavras-passe.
- Desativar uma conta ou redefinir a sua palavra-passe invalida sessões abertas.
- Palavras-passe de novas contas exigem 14 caracteres, letra maiúscula, letra minúscula e número.

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
- Gestão completa de revistas: catálogo, criação, edição, ISSN, periodicidade, edição atual, diretrizes, capa por Cloudinary ou URL, publicação/ocultação, eliminação e página pública por slug
- Cadastro de administradores individuais com palavras-passe protegidas por hash
- Upload de imagens optimizadas para Cloudinary
- Editor Markdown com pré-visualização, referências, DOI e palavras-chave
- Limites de utilização no login, assistente, contacto e newsletter
- Turnstile opcional e segredo privado entre Flask e Cloudflare Worker
- Política Editorial, Política de Correções e Declaração de Acessibilidade
