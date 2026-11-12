# Auditoria de idiomas e segurança — 12 de Novembro de 2026

Estado: correcção preparada para revisão, sem publicação em produção.

## Alterações

- Países multilingues da lista inglesa consideram primeiro as preferências PT/EN do navegador; sem correspondência, usam inglês.
- Países lusófonos mantêm português por defeito. País desconhecido usa navegador, com português como alternativa.
- Corrigida a prioridade de variantes regionais: pt-MZ de maior qualidade já não perde para en de menor qualidade.
- Escolha manual continua prioritária e guardada durante um ano.
- Página inicial declara Vary: Accept-Language e, quando aplicável, CF-IPCountry; mantém Cache-Control privado/no-store.
- O portal continua a suportar apenas PT/EN. Não se inventaram traduções de artigos.

## Auditoria observada

Coolify mostrou aplicação Running, PostgreSQL e um Redis Running; outro Redis Exited. Não se alteraram serviços.

Foram confirmados quatro domínios: dois principais HTTPS e dois endereços automáticos sslip.io com HTTP, encaminhados para porta interna 8000. O caminho /api/v3 referido anteriormente não apareceu na lista observada e ainda exige inspecção dos detalhes.

A pesquisa por TRUST_CLOUDFLARE_COUNTRY não devolveu resultados nas variáveis da aplicação. O ambiente efectivo e variáveis herdadas ainda não foram confirmados. O código ignora CF-IPCountry sem a opção exactamente igual a true; esta opção não foi activada.

Cloudflare apresentou o formulário de entrada e o pedido seguro foi recusado. DNS, geolocalização, regras, cache e isolamento da origem não foram confirmados. Uma tentativa pelo endereço automático terminou em erro upstream, o que não prova isolamento.

O assistente obtém o idioma do HTML, envia-o ao backend e ao Worker e utiliza títulos ingleses publicados quando disponíveis. A integração PT/EN e os links foram testados com Worker simulado; não se verificou uma resposta real do modelo.

## Testes

Suite de internacionalização: 41 testes aprovados, incluindo negociação regional, países multilingues, cabeçalhos não confiáveis, escolha manual, cache e integração do assistente. A suite existente cobre artigos, revista, páginas institucionais e formulários.

Suite geral test_platform: 75 testes executados; 4 falhas e 2 erros relacionados com ficheiros estáticos/fontes ausentes na cópia local parcial. Não se afirma aprovação da suite geral. Testes de navegador/mobile e CI remoto ainda pendentes.

## Pendências e segurança

Não se removeram domínios nem se alteraram DNS, firewall, proxy ou variáveis de produção.

Antes de confiar no país, verificar proxy DNS, IPv4/IPv6, portas publicadas, firewall do servidor/provedor, regras do proxy e acesso directo à origem com Host principal e cabeçalhos forjados. Remover apenas sslip.io não basta. Verificar SSH, Coolify, ACME, monitorização, webhooks, tarefas e dependências antes de restringir acessos.

Alterações de segurança que afectem o acesso e publicação em produção exigem confirmação do utilizador. A internacionalização integral em produção e a segurança da origem permanecem por validar.

## Reversão

Antes de eventual publicação, registar o commit actualmente implantado. Reverter este commit e republicar a versão anterior reverte a correcção. Para futuras alterações de DNS/firewall/proxy, guardar configurações anteriores e preparar acesso de recuperação antes de solicitar aprovação.

