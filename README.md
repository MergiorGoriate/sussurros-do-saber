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
- `ADMIN_PASSWORD`: palavra-passe forte.
- `DATABASE_URL`: ligação PostgreSQL fornecida pelo serviço de base de dados.

Sem `DATABASE_URL`, o projeto usa SQLite apenas para desenvolvimento local. No Render, utilize PostgreSQL para manter artigos, contactos e subscritores após reinicializações.

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
- Política Editorial, Política de Correções e Declaração de Acessibilidade
