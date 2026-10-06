# Alterações

## Limpeza de ficheiros sem utilização — 30/09/2026

- Removidos de `main` os ficheiros `static/css/animations.css`, `static/css/interactives.css` e `static/css/journals.css`: não eram importados por templates, scripts ou outros estilos dessa branch. As animações ativas continuam em `style.css` e `animations.js`. A branch antiga `deploy/coolify-vps` continua a carregar `animations.css` e não é alterada por esta limpeza.
- Removido `templates/admin/journal_issue_form.html`: não existia rota, chamada de renderização ou modelo de edição de revista em `main` ou `deploy/coolify-vps`.
- Os ficheiros ativos de logotipos, Tailwind compilado, imagens responsivas e configuração Docker foram preservados. `Procfile` e `render.yaml` já estavam ausentes das duas branches.

## Gestão de revistas

- Modelo persistente de revistas com título, slug, abreviatura, área, descrição, ISSN, periodicidade, edição atual, diretrizes e capa.
- Catálogo administrativo e formulários independentes de criação e edição.
- Publicação, ocultação e eliminação protegidas por autenticação e CSRF.
- Upload de capas otimizadas para WebP no Cloudinary ou uso de URL externa.
- Página pública individual por slug e catálogo público alimentado pela base de dados.
- Auditoria das alterações administrativas.
- Testes do ciclo de criação, publicação, ocultação, visualização e eliminação.
