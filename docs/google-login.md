# Login Google opcional — implementação e publicação

## Auditoria anterior às alterações

A aplicação usa Flask/SQLAlchemy, `Researcher` para as contas e uma sessão assinada
com nonce de revogação; o administrador/2FA é separado. `ReaderJournal` já mantém
favoritos e acompanhamento com restrição única por conta/revista. Os outros artigos
usavam localStorage e `/favoritos`, enquanto a biblioteca da conta listava revistas.
Não existe Alembic: `seed_database()` chama `db.create_all()` e migrações leves.
A CSP usa nonce/strict-dynamic e já permite frames/conexões de domínios Google.

Ficheiros: `google_auth.py`, `reader_accounts.py`, `app.py`, `submissions.py`,
`templates/base.html`, `templates/reader_dialog.html`, `templates/reader_library.html`,
`templates/privacy.html`, `static/js/reader-accounts.js`, `static/js/main.js`,
`static/css/reader-accounts.css`, `static/css/tailwind.css`, `requirements.txt`,
`README.md`, esta documentação e testes Python/Playwright.

## Configuração mínima

1. Crie um cliente OAuth **Aplicação Web** no Google Cloud/Google Auth Platform.
   Configure nome público, suporte, domínio verificado, página inicial,
   privacidade e termos. Use apenas a autenticação básica; nenhum acesso a APIs
   Gmail/Drive nem refresh token é necessário.
2. Adicione à lista **Authorized JavaScript origins** exactamente
   `https://www.sussurrosdosaber.com`. Inclua `https://sussurrosdosaber.com` apenas
   se a aplicação também servir páginas nessa origem. Para testes locais use
   um cliente separado e `http://localhost:5000` / `http://127.0.0.1:5000`.
   Este fluxo GIS usa callback JavaScript + POST same-origin; não usa redirect
   OAuth, código de autorização ou client secret.
3. Configure `GOOGLE_CLIENT_ID=<id>.apps.googleusercontent.com` no Coolify.
   O Client ID é público, mas vem do ambiente; não grave valores reais no git.
   `SECRET_KEY` deve continuar forte, só no ambiente, e `FLASK_ENV=production`
   activa cookies Secure. HttpOnly, SameSite=Lax e validade de duas horas já
   estão configurados. Nunca desactive Secure na produção HTTPS.
4. Sem Client ID válido, a integração Google fica desligada: o site público,
   o botão Entrar e as contas anteriores continuam disponíveis.
5. Faça backup PostgreSQL, instale dependências e execute
   `flask --app app migrar-login-google` antes de abrir a nova versão ao tráfego.
   Publique a branch integrada no Coolify. Não é preciso Redis novo nem outra DB.

## Migração aditiva (duas tabelas)

- `google_identity`: `subject VARCHAR(255)` chave primária, `owner_id INTEGER`
  único/not-null/referência a `researcher.id`, `created_at TIMESTAMP` not-null.
  Não guarda a credencial, access token, refresh token, fotografia ou senha.
- `reader_article`: chave primária composta (`owner_id`, `article_id`), referências
  a `researcher.id` e `article.id`, `created_at TIMESTAMP` not-null.
- Nenhuma alteração de coluna, índice extra ou reescrita dos dados existentes.
  `reader_journal`, manuscritos, autores e administradores permanecem os mesmos.
- O comando é repetível (`create_all(..., tables=[...])`) e também respeita o
  mecanismo de criação de tabelas que já existe no arranque da aplicação.
- Contas criadas por Google usam `password_hash=''` como ausência de credencial
  local, compatível com o NOT NULL antigo. Nenhuma senha/hash fictício é gerado.
  Login/recuperação por senha não se aplica a essas contas. Contas anteriores
  mantêm os seus hashes e podem associar Google sem perder favoritos.
- A migração local de favoritos ocorre após autenticação, em lotes de até 100,
  apenas para conteúdos publicados. Duplicados são eliminados por chaves únicas.
  Só se apaga a cópia do navegador depois da confirmação de todos os lotes.
- `/favoritos` redirecciona para `/conta/biblioteca`; existe uma única área.

Reversão: retire `GOOGLE_CLIENT_ID` para desligar GIS. Mantenha as duas tabelas
para preservar identidades/favoritos; não as elimine durante rollback. Uma
reversão para código anterior perde o acesso aos favoritos dos artigos comuns,
embora os dados permaneçam guardados. Reverta código só depois de avaliar isso.

## Segurança e riscos de regressão

O POST usa o CSRF existente da sessão (o callback GIS é transmitido pelo nosso
fetch; não aceitamos POST directo do Google). `google-auth` valida assinatura,
audience, issuer e tempo; o backend exige ainda nonce da sessão com validade de
10 minutos, subject e e-mail verificado. O nonce é consumido na tentativa e a
sessão/CSRF roda na entrada. Não se descodifica um JWT sem verificar assinatura.
Os certificados são obtidos em HTTPS com timeout e cache segundo Cache-Control.
Nunca se registam tokens em logs.

Uma identidade já associada é localizada por `sub`, mesmo com mudança do e-mail
no Google. Uma conta existente confirmada Gmail/Workspace pode ser localizada
pelo e-mail; para e-mail externo ou conta antiga não confirmada é obrigatório
entrar primeiro na conta existente e associar explicitamente o Google. Contas
inactivas e troca de conta dentro de sessão autenticada são rejeitadas. Novas
contas Google com e-mail externo ficam por confirmar para acompanhamento e
submissões; use a confirmação SMTP existente.

One Tap: sem auto-select, uma tentativa automática por separador e nenhuma
modal própria obrigatória. O navegador/Google pode suprimir One Tap por FedCM,
preferências ou cooldown; o botão manual continua disponível. Ao terminar sessão,
o prompt automático é suprimido nessa sessão. Fechar a janela cancela o prompt.
Leitura não exige rede Google, JS, sessão ou consentimento em login.

A CSP mantém strict-dynamic e o nonce, acrescentando apenas o stylesheet GIS;
frames/conexões Google já eram permitidos. Não foi acrescentado unsafe-eval.
Canonicals, sitemap e conteúdo SSR público mantêm-se. Endpoints pessoais usam
no-store/noindex; a confirmação Google nunca fica na URL.

## Verificação

Python: tokens RSA assinados e assinatura inválida, aud/iss/exp/nonce, CSRF,
indisponibilidade, contas inactivas/ligação, sessão, favoritos isolados/idempotentes,
importação e migração repetível. SQLite é usado na suite local; validar a criação
real das tabelas PostgreSQL na implantação com o comando acima.

Playwright: 360px, botão manual, intenção favorito/acompanhamento, CSRF renovado,
One Tap não bloqueante, uma tentativa por separador, falha do Google e login local.
GIS/credenciais são simulados no navegador; a verificação criptográfica real é
coberta pelos testes Python. Antes de anunciar disponibilidade, confirmar com um
cliente Google real: entrada/saída, fechar One Tap, telemóvel, biblioteca entre
dispositivos e Google Console/origens. Essas verificações dependem da configuração
externa; não podem ser substituídas por mocks.

Referências oficiais:
- https://developers.google.com/identity/gsi/web/guides/verify-google-id-token
- https://developers.google.com/identity/gsi/web/guides/get-google-api-clientid
- https://developers.google.com/identity/gsi/web/reference/js-reference
