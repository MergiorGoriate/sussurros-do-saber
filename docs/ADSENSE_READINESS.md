# AdSense: preparação e pendências de publicação

Auditoria de código: 18 de Outubro de 2026. Não é certificação jurídica nem aprovação do Google.

## Corrigido neste conjunto de alterações

- Retirado o carregamento global de AdSense, que ignorava a recusa de cookies e incluía páginas sem conteúdo editorial. O carregador permanece desactivado por omissão; a integração CMP opcional descrita no final mantém os pedidos de anúncios pausados.
- Verificação continua disponível através da meta `google-adsense-account` e do `/ads.txt`, mantendo o ID existente `pub-7920973591685812`. Confirmar a titularidade na conta; o código não a prova.
- Removido o iframe GTM sem consentimento para navegadores sem JavaScript.
- Cookies malformados, futuros, expirados ou com valores não booleanos não concedem consentimento. Escolhas antigas válidas mantêm o prazo máximo de 180 dias.
- Eventos de análise só são enfileirados com autorização actual. Ligações externas não enviam URL, parâmetros ou fragmentos. Retirar análise provoca recarregamento para interromper o código anterior.
- Scripts opcionais desconhecidos e de publicidade ficam bloqueados. O banner local nunca concede consentimento Google para publicidade/personalização.
- Publicadas informações sobre publicidade, parceiros Google, escolhas e comunicação de violações.

## Obrigatório concluir antes de activar anúncios

1. Publicar esta alteração, confirmar acesso público à página inicial, artigos, páginas institucionais e ads.txt. Verificar HTTPS, resposta 200 e que robots/WAF permitem o rastreador AdSense no conteúdo público; manter administração e rascunhos privados.
2. Na conta AdSense, confirmar domínio, ID de editor e propriedade; escolher verificação por meta ou ads.txt e pedir revisão. Confirmar requisitos de idade, identidade, morada e pagamentos. Esta auditoria não acedeu à conta.
3. Configurar e publicar uma CMP certificada em Privacidade e mensagens (ou fornecedor certificado), com consentimento, recusa e gestão/retirada. Avaliar regiões do tráfego, incluindo EEE/Reino Unido/Suíça e mensagens/opt-out de estados dos EUA aplicáveis. O banner local não substitui TCF, GPP nem aconselhamento jurídico.
4. Integrar e testar o código real dessa CMP, os sinais de consentimento e o código AdSense da conta antes de reintroduzir anúncios. Não activar pelo simples valor `ads:true` do cookie local. Publicidade não personalizada também não dispensa automaticamente consentimento. Validar CSP para os domínios efectivos do fornecedor; nunca fabricar sinais TCF.
5. Limitar anúncios a conteúdo editorial publicado e avaliado. Excluir administração, conta, favoritos, formulários, pesquisa sem resultados, erros, páginas legais, previews e publicações restritas. Rever Auto ads, rótulos e distância dos controlos, especialmente no telemóvel; não criar sobreposições ou incentivos a cliques.
6. Rever TODOS os artigos e imagens no banco de produção: originalidade e valor próprio, referências verificáveis, exactidão de alegações científicas e médicas, autoria real, licenças/créditos, conteúdos proibidos/restritos e comentários moderados. Uma revisão do código não comprova qualidade ou direitos do conteúdo publicado. Não existe um número universal de palavras/artigos que garanta aprovação.
7. Confirmar responsáveis e contactos reais, fornecedores, transferências internacionais, conservação e atendimento de pedidos de privacidade; ajustar a política às operações efectivas. Rever a configuração GTM: não incluir anúncios, dados pessoais, remarketing sensível ou tags que ultrapassem a autorização de análise.
8. Avaliar origem de tráfego, bots e actividades inválidas; acompanhar o Centro de políticas, corrigir ocorrências e repetir esta revisão quando mudarem conteúdo, fornecedores ou políticas. Nunca clicar em anúncios reais para testar.

## Validação de aceitação para a futura integração

Usar respostas simuladas de publicidade, sem gerar impressões ou cliques reais. Verificar escolha ausente, inválida, expirada, recusa, consentimento parcial, retirada, erro/ausência de CMP e regiões aplicáveis. Nenhum sinal desconhecido deve autorizar personalização. Confirmar que novos visitantes não carregam tags opcionais, inclusive sem JavaScript; páginas privadas e de erro nunca apresentam inventário. Testar navegação móvel e acessibilidade dos controlos.

## Fontes oficiais consultadas

- Políticas do programa: https://support.google.com/adsense/answer/48182
- Políticas para editores: https://support.google.com/publisherpolicies/answer/10502938
- Verificação por meta/ads.txt e revisão: https://support.google.com/adsense/answer/7584263
- CMP certificada e âmbito regional: https://support.google.com/adsense/answer/13554116
- Política de consentimento UE: https://www.google.com/about/company/user-consent-policy/
- API Privacidade e mensagens: https://developers.google.com/funding-choices/fc-api-docs
- Publicidade não personalizada e pausa: https://support.google.com/adsense/answer/9042142
- Dados de sites parceiros: https://policies.google.com/technologies/partner-sites

A decisão de aprovação e eventuais pedidos de correcção pertencem ao Google.


## Integração CMP preparada (continuação)

A variável `GOOGLE_CMP_ENABLED=true` habilita o carregamento da mensagem do Google nas páginas inicial, privacidade, publicidade e leitura de artigos/revistas publicados. Por omissão permanece `false` até confirmar a publicação da mensagem na conta. Não foi possível confirmar a publicação através da conta; a captura recebida mostrava o editor com o botão Publicar.

O script local `static/js/google-cmp.js` define `pauseAdRequests=1` ANTES de inserir a tag AdSense existente. Esta tag é o mecanismo documentado para obter mensagens Google publicadas. Nenhum caminho desta integração despausa publicidade, cria blocos ou converte um cookie local em sinal TCF. A pausa não impede pedidos técnicos do próprio carregador/CMP ao Google; não equivale a ausência de comunicações externas.

O botão “Gerir consentimento de publicidade” só fica disponível após `CONSENT_API_READY` e a presença de `showRevocationMessage`. A chamada passa pela fila oficial. Trata-se de reabertura da mensagem europeia; não é uma implementação de opt-out dos EUA/GPP. Deixar a ligação automática Do Not Sell/Share do Google activa ao publicar mensagens de estados dos EUA, se aplicáveis, e validar essa experiência separadamente.

### Activação e confirmação no alojamento

1. Publicar no AdSense a mensagem europeia para o domínio correcto, em português, com consentir, não consentir e gerir opções; confirmar a URL da política de privacidade. Configurar os parceiros e o âmbito da mensagem de acordo com os serviços efectivamente utilizados.
2. Integrar este PR e definir `GOOGLE_CMP_ENABLED=true` nas variáveis do serviço de alojamento, reiniciando a aplicação. A conta não pode ser configurada por essa variável: a mensagem tem de estar publicada no Google.
3. Confirmar a mensagem na página inicial com `?fc=alwaysshow&fctype=gdpr` e num artigo público. Os parâmetros são de pré-visualização oficial; a mensagem precisa de estar publicada. Confirmar a opção de gerir e retirar consentimento, recusa e apresentação móvel. Limpar estado numa janela de teste para verificar novas visitas.
4. Confirmar no navegador que os domínios efectivos da CMP não são bloqueados pela CSP. Esta alteração admite explicitamente fundingchoicesmessages.google.com nos frames e conexões, além dos domínios Google já autorizados. Não alargar para qualquer domínio em caso de falha; identificar primeiro o pedido legítimo.
5. Se falhar a CMP ou não existir mensagem, o rodapé informa indisponibilidade e os pedidos de anúncios permanecem pausados. Para reverter todo o carregamento externo desta integração, definir `GOOGLE_CMP_ENABLED=false` e reiniciar.
6. Continuar a revisão de conta, políticas e inventário antes de implementar a exibição de anúncios. Esta fase integra a mensagem e a reabertura, não conclui a monetização. A análise opcional continua gerida pelo banner local, sem usar TCF como autorização implícita.

Os testes usam simulações: confirmam ordem da pausa, disponibilidade e reabertura da API, falha e exclusão de páginas privadas/erros. Não certificam o comportamento da mensagem real, a conta ou os fornecedores publicados pelo operador.


## Correcção de inicialização e diagnóstico (18 de Outubro)

Observação no site publicado: a tag AdSense e show_ads_impl foram carregados, sem aparecer uma tag Funding Choices na lista de scripts do documento durante a visita de pré-visualização. Não foram observados erros CSP relativos à CMP na consola consultada. Isto confirma carregamento da tag, mas não confirma a publicação da mensagem nem identifica sozinho a causa de ausência de resposta.

A implementação anterior só anexava a tag com pedidos pausados. Acrescentada a inicialização documentada `push({google_ad_client: ..., enable_page_level_ads: true})` com a pausa definida ANTES do comando e do carregamento. Esta é uma alteração da sequência de inicialização, não uma confirmação de que a conta ou a mensagem estão configuradas. Nenhum caminho define `pauseAdRequests=0`.

Dez segundos sem API deixam agora o estado como não confirmado, com possibilidade de tentar recarregando a página; já não é apresentado como falha comprovada do Google. Erro do pedido tem mensagem própria. Respostas tardias em CONSENT_API_READY/CONSENT_DATA_READY restauram a gestão do consentimento. A indicação de não aplicação da mensagem europeia só é mostrada quando a CMP real confirma `gdprApplies=false` pela API TCF; o tempo decorrido não determina região ou aplicabilidade. Essa indicação não elimina requisitos de outras regiões.

Os testes reproduzem erro de rede, resposta tardia e aplicabilidade confirmada; não substituem a validação da mensagem real depois de publicar a alteração. Foi alterada a versão do script para evitar servir a cópia anterior em cache. Se a mensagem continuar ausente, é necessário verificar o estado Publicada/domínio no AdSense e os pedidos reais do fornecedor; não se deve despausar anúncios ou inventar uma tag de recuperação de adblock como substituto da CMP.



### Correcção após observação da tag real

Depois da instalação da versão v2, a consola do site mostrou `TagError: adsbygoogle.push() error: Only one 'enable_page_level_ads' allowed per page`. O comando acrescentado com base no exemplo oficial antigo é redundante com a tag actual que inicializa Auto ads automaticamente. Foi removido na versão v3; a pausa continua definida antes da tag. Os exemplos oficiais não garantem compatibilidade com todas as versões/configurações actuais. Os testes anteriores simulavam a API mas não esta rejeição: foi acrescentada uma simulação que rejeita o comando legado.

Esta observação invalida a hipótese de que o comando legado em falta resolveria o carregamento. A ausência da CMP ainda exige confirmar a mensagem Publicada e o domínio na conta AdSense. Não há confirmação de que as escolhas de consentimento reais estejam operacionais. Não activar anúncios para tentar contornar esse bloqueio.
