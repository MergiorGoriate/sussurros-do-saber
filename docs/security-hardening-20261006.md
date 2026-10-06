# Reforço de segurança — 6 de Outubro de 2026

## Alterações no código

- `AdminUser.security_version` é acrescentado de forma compatível com bases existentes. Alterações ORM à palavra-passe, utilizador, estado activo, privilégio ou segundo fator incrementam essa versão.
- Sessões e desafios são associados às credenciais actuais através de HMAC. Sessões anteriores à actualização precisam de novo login. A conta por ambiente também é invalidada quando as credenciais/configuração mudam; `ADMIN_SECURITY_VERSION` permite revogação explícita após reiniciar todos os processos.
- Privilégios são consultados na base em cada verificação, antes de permitir operações de superadministrador.
- Pré-visualizações HTML, Markdown e PDF exigem a mesma inscrição obrigatória em 2FA que o painel. Configuração de 2FA e logout continuam acessíveis durante inscrição.
- Desafios expiram após cinco minutos e são eliminados após sucesso ou rejeição por expiração/alteração de credenciais. O prazo é do passo de login pendente, não do código TOTP, que mantém o seu período próprio.
- Downloads PDF: 10/minuto e 60/hora por IP, além dos limites gerais. Cache privado em `instance/pdf-cache`, máximo de 64 MiB, prazo de cinco minutos, chave dependente de todos os campos do artigo. Alterações a imagens remotas podem demorar até cinco minutos a reflectir-se. PDFs individuais acima de 16 MiB são recusados.
- Uma trava de ficheiro limita a uma geração por vez entre workers do mesmo contentor. Pedidos concorrentes sem PDF em cache recebem 503 e `Retry-After: 5`. Várias réplicas têm travas independentes; exigem uma fila distribuída se forem adoptadas.
- O orçamento de carregamento de imagens é partilhado entre corpo, referências e notas. Limites existentes contra redes privadas, tamanhos e resolução são preservados. DNS e processamento CPU não têm prazo rígido próprio; o timeout do worker continua a ser a protecção final.
- Docker inicia dois workers por omissão (`WEB_CONCURRENCY` pode ajustar). Preload prepara esquema uma vez, e o hook de fork substitui o pool de ligações herdado.
- `PROXY_FIX_X_FOR` e `PROXY_FIX_X_PROTO` mantêm um salto por omissão. `PROXY_FIX_X_HOST` passa a zero: não confiar em host encaminhado sem necessidade confirmada. Variáveis aceitam 0–5; não aumentar por tentativa.

## Verificações externas ainda necessárias

O repositório não comprova a configuração real de Cloudflare, Coolify, OVHcloud ou backups. Estas verificações não foram executadas e não devem ser marcadas como resolvidas apenas pelo merge.

1. No Coolify, confirmar serviço, ramo de produção, Redis partilhado, `FLASK_ENV=production`, credenciais e configuração de proxies. Identificar quais proxies acrescentam ou substituem cada cabeçalho. Ajustar contagens só com essa evidência.
2. Confirmar que a porta interna da aplicação não está publicada no VPS. Fazer o backend aceitar tráfego apenas do proxy local/rede Docker. Se o site deve passar exclusivamente pelo Cloudflare, restringir as portas públicas de origem aos endereços oficiais Cloudflare ou usar um Tunnel, preservando SSH e gestão do Coolify. Primeiro inventariar serviços e testar uma regra reversível; uma lista incorrecta pode bloquear o site ou a administração.
3. Confirmar HTTPS da origem, modo Full (strict) e certificados; verificar externamente que acesso directo ao backend não contorna a protecção. Testar IP real dos visitantes e limites de pedidos sem provocar carga no site.
4. Confirmar destino dos backups, ausência de acesso público, permissões mínimas e separação das credenciais. Proteger cópias que contêm contas, manuscritos e anexos. Confirmar cifragem, retenção e uma restauração em base isolada. Excluir `instance/pdf-cache` dos backups e nunca publicar esse directório.
5. Antes do deployment, obter backup consistente da base; após deployment, testar login normal, 2FA, mudança de palavra-passe, pré-visualizações e download público num computador e telemóvel. A alteração de esquema acrescenta uma coluna e não elimina conteúdo.

## Limites da validação

Testes locais usam SQLite e sessões reais de Flask, com dados de teste. Não demonstram segurança integral da implantação nem substituem teste HTTP em produção. Nenhum segredo do servidor ou backup foi recolhido ou divulgado.
