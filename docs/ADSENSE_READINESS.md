# AdSense: preparação e pendências de publicação

Auditoria de código: 18 de Outubro de 2026. Não é certificação jurídica nem aprovação do Google.

## Corrigido neste conjunto de alterações

- Retirado o carregamento global de AdSense, que ignorava a recusa de cookies e incluía páginas sem conteúdo editorial. Não existe carregador de anúncios activo nesta versão.
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
