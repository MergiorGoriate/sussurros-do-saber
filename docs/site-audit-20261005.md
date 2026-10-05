# Auditoria de funcionalidades e desempenho — 05/10/2026

Base auditada: `cc76581a0a49a0559464b2ffa038793583b30909`.

## Problemas corrigidos

| Encontrado | Correcção | Verificação |
| --- | --- | --- |
| A biblioteca renderizada antes de importar favoritos antigos ficava desactualizada | Importação confirmada pelo servidor e recarregamento da biblioteca após limpar a cópia antiga | Teste de navegador com IDs duplicados no armazenamento antigo |
| Ausência de controlos para remover favoritos na biblioteca | Remoção de artigos e artigos de revistas com as APIs existentes, CSRF e isolamento por conta | Testes Python e navegador, incluindo persistência após recarregar |
| Contador do sino desactualizado após alterar acompanhamento | Nova consulta da sessão após a alteração confirmada; desactivação na página de notificações | Teste real de seguir, actualizar artigo e desactivar |
| Falhas de gravação visíveis apenas no atributo title | Mensagem visível com região de estado acessível e botão disponível para tentar novamente | Teste de resposta 503 |
| Histórico do navegador podia restaurar estado anterior da conta | Actualização em pageshow e recarregamento das listas privadas restauradas | Revisão de código e cobertura dos fluxos de conta |
| Foto de perfil recebia indevidamente o fallback genérico dos artigos | Avatares usam o seu próprio tratamento de erro | Teste Google de imagem indisponível |
| Consulta extra da conta em todas as visitas autenticadas | Só actualizar novamente quando houver favoritos importados | Revisão do fluxo e testes de importação |
| Consultas adicionais por item da biblioteca | Carregamento conjunto das relações de artigos e revistas | Testes de biblioteca e isolamento |
| CSS e JavaScript servidos em passthrough não eram comprimidos | Gzip de ficheiros de texto até 1 MB, respeitando negociação, Range, Vary e ETag | Teste de bytes descomprimidos, gzip;q=0 e pedido parcial |
| JavaScript de todos os ícones carregado no catálogo, apesar do CSS global existente | Remoção do script redundante; script do catálogo deferido | Testes de navegação e catálogo |
| CSS duplicado de ícones no artigo e fonte repetida sem JavaScript | Remoção de inclusões repetidas | Renderização e testes públicos |
| Capas da home usavam a imagem original do Cloudinary | Variante responsiva de 480 px | Filtro existente mantém outras origens |
| Link de notificações repetido no menu principal | Retirada do texto; acesso pelo sino e pela área da conta | Pedido visual anterior preservado |

## Verificações

123 testes Python locais passaram, incluindo autenticação Google com assinatura, CSRF, isolamento de contas, publicação, administração/2FA, comentários, pesquisa, SEO, PDF, editor e submissões.

16 rotas verificadas localmente: `/`, `/artigos`, `/autores`, `/revistas`, `/sobre`, `/contacto`, `/recursos`, `/servicos`, `/politicas-editoriais`, `/diretrizes-para-autores`, `/conta/biblioteca`, `/conta/notificacoes`, `/sitemap.xml`, `/robots.txt`, `/ads.txt`, `/healthz`.

Novos testes de navegador usam o servidor Flask e uma base SQLite isolada. Só respostas externas de publicidade são substituídas; autenticação por palavra-passe, gravação de favoritos, importação e notificações usam os endpoints e a persistência reais. A fixture recusa uma base que não seja SQLite. Testes existentes Google continuam a verificar assinatura no servidor e a interface com um serviço Google simulado.

Medição local do tamanho transferido, antes/depois do gzip: `style.css` 112.361 → 21.669 bytes (80,7%); `main.js` 14.024 → 5.112 bytes (63,5%); `reader-accounts.js` cerca de 16 KB → 4,6 KB (71%). Esta medição é de payload; não é uma pontuação Lighthouse nem uma medição de Core Web Vitals em produção.

## Banco de dados e regressão

Sem alterações de esquema ou migrações. Favoritos continuam únicos por conta/artigo; acompanhamento usa a preferência existente. Não são criadas áreas paralelas de favoritos, senhas Google ou novas notificações de e-mail/push. Notificações continuam a mostrar actualizações de artigos de revistas seguidos, conforme a funcionalidade existente; o contador mede essas actualizações e não um estado de leitura.

Os testes verificam repetição de gravação, presença do artigo na biblioteca, remoção em outra sessão da mesma conta, ausência de conteúdo não publicado e restrição de notificações para contas não verificadas. Gzip preserva pedidos parciais e não materializa ficheiros grandes.

## Limites de validação

Não há acesso ao Coolify, à base de produção nem aos segredos nesta auditoria. Google real/One Tap, entrega SMTP, upload real e reprodução no Cloudinary, DNS e desempenho real em redes móveis precisam de validação após deploy. A instalação de Chromium local foi bloqueada por um download inválido; os testes de navegador completos são executados pelo CI. Esta auditoria não garante a ausência de qualquer problema futuro ou de configuração externa.
