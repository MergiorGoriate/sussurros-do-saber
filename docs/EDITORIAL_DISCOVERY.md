# Clareza editorial e descoberta de artigos

Registo histórico do PR #218. A activação posterior do boletim e a correcção da mensagem de inscrição estão descritas em [NEWSLETTER.md](NEWSLETTER.md); os parágrafos abaixo descrevem a etapa anterior.

A página inicial usa «Artigos recentes» no bloco que apresenta as publicações mais recentes depois do destaque. O conteúdo e o destaque mantêm a selecção existente; não há contagem de leituras nem ranking de popularidade.

A área de inscrição passa a apresentar «Boletim científico», «Registar interesse» e a indicação de que o envio ainda não está activo. O formulário, os seus identificadores, o endpoint de inscrição, a deduplicação, a gestão de subscritores e a exportação existentes são preservados. Não foi criado um serviço de campanhas, uma subscrição paga ou um canal adicional de notificações.

Na página de divulgação, «Continue a explorar» mantém os mesmos cartões e o limite de três artigos. A consulta existente dá prioridade à categoria do artigo aberto; dentro de cada grupo, ordena por data de publicação e ID decrescentes. Publicações recentes de outras categorias completam a selecção quando faltam artigos do mesmo tema. A consulta filtra o estado publicado e exclui o artigo aberto. Não há personalização, recolha de histórico ou algoritmo semântico.

## Validação e reversão

Os testes em tests/test_editorial_discovery.py verificam prioridade temática, limite de três cartões, preenchimento com outras categorias, ordenação estável, ausência de duplicados e exclusão do artigo aberto e dos estados privados. Verificam também a apresentação dos rótulos e a preservação do formulário.

Os cenários de navegador em tests/browser/editorial-discovery.spec.js verificam os rótulos, a largura da página e uma inscrição no endpoint existente a 320 e 1440 px, com dados sintéticos.

### Falha preexistente identificada

O endpoint guarda a inscrição e responde com sucesso, mas a interface substitui a confirmação por «Não foi possível concluir agora.». O handler em static/js/main.js usa e.currentTarget.reset() depois de await; nessa altura currentTarget já não referencia o formulário. O código actual da main contém esse mesmo handler. A correcção mínima proposta é guardar a referência ao formulário antes do primeiro await e usá-la para reset(). Esta alteração de comportamento fica pendente de autorização separada; os testes desta entrega confirmam a resposta do endpoint, não uma mensagem de sucesso na interface. Não existe envio de newsletter associado à inscrição.

Não há migrações, alterações de permissões, estados editoriais ou configurações de produção. A reversão do commit repõe os rótulos e a ordenação anterior, sem operações sobre os dados. A validação do deployment efectivo continua separada dos ensaios locais. A reformulação das políticas editoriais, novas áreas temáticas, podcasts e envio de newsletters ficam fora desta alteração.

Em 19/10/2026 passaram 298 testes Python em SQLite, incluindo cinco novos. Os cenários de navegador novos foram executados a 320 e 1440 px com Chromium 153 alternativo, em processos separados devido às limitações de contextos desse executável. A suite completa de navegador, PostgreSQL e o deployment não foram executados nesta validação local.

