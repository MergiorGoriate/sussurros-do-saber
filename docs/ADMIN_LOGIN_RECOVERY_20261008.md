# Recuperação do login administrativo — 08/10/2026

## Evidência e limite do diagnóstico

A captura mostra a resposta genérica HTTP 400 na URL /admin/login?next=/admin. Uma navegação GET independente no site real abriu normalmente o formulário. A captura não permite saber se o pedido que falhou era GET ou POST, nem confirmar a causa na infraestrutura.

No código, validate_csrf() abortava com 400 quando o token não correspondia à sessão. Um formulário anterior à perda do cookie ou à mudança da chave de assinatura reproduz esse resultado. A correção trata esse caso confirmado por testes; não afirma diagnosticar todos os erros 400 do proxy, parser ou Coolify.

## Alteração

Somente nos POSTs do login e da verificação 2FA, uma falha CSRF retorna HTTP 400 com mensagem clara e formulário protegido por um novo token. O pedido rejeitado não verifica credenciais nem códigos. O utilizador deve preencher e submeter novamente. Nunca repetir automaticamente credenciais.

Prazo, identidade e estado do desafio 2FA continuam sujeitos às verificações existentes. O prazo não é prolongado. Códigos de recuperação não são consumidos no pedido recusado. Os restantes formulários administrativos continuam a rejeitar CSRF inválido como antes. Cache-Control no-store continua aplicado.

## Validação

- Suite completa local: 212 testes Python aprovados.
- Segurança administrativa: 16 aprovados, incluindo cinco novas regressões.
- Casos novos: sessão perdida entre GET e POST; tokens ausentes e diferentes; nova tentativa com palavra-passe e 2FA; token desatualizado no desafio sem consumo de códigos ou extensão de prazo; outros erros 400 não mascarados; ação administrativa recusada sem alterar 2FA.
- Site real: apenas abertura GET do formulário de login. Não submetidas credenciais reais neste diagnóstico.
- Sem migração de base de dados. Sem deploy ou integração realizados pelo assistente.

## Checklist após deploy

1. Abrir um formulário novo em https://www.sussurrosdosaber.com/admin/login e entrar com uma conta de teste, concluindo 2FA.
2. Com dados isolados, guardar um formulário anterior à renovação da sessão e submetê-lo. Esperar a mensagem de formulário expirado, sem autenticação.
3. Preencher o formulário renovado e confirmar que ainda exige palavra-passe e 2FA.
4. Se HTTP 400 aparecer também ao abrir o login por GET numa janela privada, obter os logs da aplicação e do proxy no Coolify no mesmo instante. Verificar método, caminho e código de resposta; não partilhar cookies, palavras-passe, tokens ou segredos.
5. Manter SECRET_KEY estável entre réplicas e deploys. Não alterar nem divulgar o valor durante esta validação.

A validação Google, uploads reais Cloudinary e fluxos editoriais com contas reais continua dependente de acesso autenticado e dados de teste isolados.
