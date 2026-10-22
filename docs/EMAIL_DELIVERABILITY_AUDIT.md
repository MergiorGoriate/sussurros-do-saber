# Auditoria de entregabilidade — Sussurros do Saber

## 1. Diagnóstico inicial e âmbito

Auditoria em 21 de outubro de 2026 (UTC; 22 de outubro em Maputo), sobre `main` no commit `079e3150d91d65fad98490c62cbfd027185df467`, que já integra o PR #256. Inspeccionados `mail_delivery.py`, `newsletter_service.py`, `submissions.py`, `app.py`, a administração, os modelos, os testes e a documentação de implantação. Não houve acesso ao Coolify, ao painel do alojamento, à conta Cloudflare nem a caixas de correio. Nenhuma credencial de produção foi consultada. Não houve alterações DNS, ligações SMTP de teste ou envios reais.

**Confirmado no código:** fila persistente coordenada, aprovação separada da autorização, quotas internas e quotas externas manuais, TLS com validação do certificado/nome, um destinatário por envelope, multipart HTML/texto, cancelamento público assinado com um clique e interrupção de mensagens pendentes. Rejeições síncronas são registadas; aceitação SMTP é distinguida de entrega. Resultados incertos não são repetidos automaticamente.

**Falhas confirmadas:** o emissor não acrescentava `Date`; não havia configuração explícita de endereço de resposta. O DNS público consultado não apresenta DMARC. Não existe processamento automático de devoluções assíncronas ou reclamações no repositório.

**Hipóteses, não conclusões:** uma configuração SMTP diferente da autorizada pelo SPF, falta de assinatura DKIM, problemas de reputação ou uma lista com endereços não controlados podem afectar os envios. Nada disso foi demonstrado em mensagens reais. MX e SPF indicam Spacemail, mas não comprovam qual SMTP o Coolify utiliza.

## 2. DNS observado e origem da evidência

Consultas públicas através de Google Public DNS, por HTTPS. Respostas completas, TTL, código DNS e hora inicial da recolha em [EMAIL_DNS_EVIDENCE.json](EMAIL_DNS_EVIDENCE.json). São observações pontuais de um resolvedor recursivo, não uma inspecção do painel Cloudflare nem uma garantia de propagação global.

| Mecanismo | Resultado observado | Avaliação e limite |
| --- | --- | --- |
| SPF | `v=spf1 include:spf.spacemail.com ~all` | Um único SPF na resposta, sem duplicação; sintaxe dos mecanismos observados compatível com SPF. Autoriza o conjunto publicado pelo Spacemail, mas o IP real de envio continua desconhecido. |
| Cadeia SPF | `spf.spacemail.com` inclui `spf.jellyfish.systems`; este último contém apenas `ip4` e `~all` | Dois termos `include` no percurso completo publicado; sem outros mecanismos que causem consultas. A cadeia observada fica abaixo do limite de dez termos DNS. O resultado PASS para uma mensagem depende do IP e do MAIL FROM reais. |
| DKIM | TXT em `spacemail._domainkey.sussurrosdosaber.com`, `v=DKIM1;k=rsa;p=…` | Selector identificado pela documentação oficial do fornecedor, não por tentativa de nomes. Chave pública RSA de 2048 bits, descodificada e inspeccionada localmente; não prova que esteja activa no SMTP real, que seja a chave actualmente utilizada ou que uma mensagem passe a verificação. |
| DMARC | `_dmarc.sussurrosdosaber.com` devolveu `NXDOMAIN` (Status 3) | Registo ausente na consulta; sem política ou relatórios publicados nesse nome. Alinhamento não verificável sem cabeçalhos reais. |
| MX | Prioridade 0: `mx1.spacemail.com.` e `mx2.spacemail.com.` | Recepção associada ao Spacemail. Não determina o IP de saída. Preservar ambos os registos. |

Não substituir nem adicionar outro SPF. Antes de qualquer alteração, inventariar os emissores legítimos (portal, webmail, clientes de correio e outros sistemas) e comparar as instruções oficiais de cada um. Não copiar os intervalos IP do ficheiro de evidência para um SPF estático: pertencem ao fornecedor e podem mudar.

## 3. SMTP, autenticação e segurança

O código lê `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_SSL` e `SMTP_TLS`. `SMTP_USERNAME` activa `smtp.login`; as credenciais não estão no repositório. A porta por omissão é 465 com SSL directo e 587 no restante caso. STARTTLS é usado se TLS estiver activo sem SSL directo. `ssl.create_default_context()` exige certificado válido e verifica o nome; envio sem TLS/SSL é rejeitado. Falhas de autenticação pausam a fila, preservando motivos sanitizados. Não desactivar a validação TLS.

O domínio real do remetente não pode ser confirmado pelo código: `SMTP_FROM` é uma variável de produção. Usar apenas uma caixa/identidade existente e autorizada. O mesmo valor é usado no cabeçalho From e no envelope solicitado ao SMTP; o fornecedor pode reescrever o envelope, pelo que é necessário verificar Return-Path na recepção. Message-ID não comprova alinhamento. O código não assina DKIM: a assinatura cabe ao fornecedor.

No Coolify, verificar os valores sem os copiar para relatórios ou logs. Guardar a palavra-passe como segredo de execução; não incluí-la no Dockerfile, na imagem, nos argumentos de build ou no Git. Confirmar disponibilidade das variáveis no processo periódico e no servidor web. `smtp_ready()` indica apenas configuração aparente, não ligação, autenticação ou entregabilidade testada.

Se o administrador confirmar que a conta utiliza Spacemail, a documentação oficial consultada indica `mail.spacemail.com`, porta 465, SSL directo: comparar com o painel da caixa e usar `SMTP_SSL=true`, `SMTP_TLS=false` para esse modo. Não alterar automaticamente um serviço que possa ser outro. Confirmar credenciais e acesso SMTP no Spacemail Manager ou nas definições IMAP/SMTP/POP3 do webmail.

## 4. Lista, conteúdo e resultados de entrega

`POST /api/newsletter` activa a inscrição directamente após validação do endereço e aplica limite de pedidos. **Não existe double opt-in nem prova de posse da caixa** nesse fluxo; a mensagem «Inscrição confirmada» descreve o registo, não uma confirmação por e-mail. Essa política foi preservada. O modelo não contém um histórico completo de consentimento. Rever com o responsável pela lista a origem dos endereços, o texto do formulário e o tratamento de inscrições indevidas antes de aumentar o volume; uma eventual confirmação de posse exige um trabalho próprio, sem invalidar silenciosamente subscritores existentes.

A preparação selecciona subscritores activos e artigos públicos da última semana completa. A selecção e o estado do subscritor são novamente verificados no envio. A edição tem assunto identificável, marca, versão simples e HTML, ligações canónicas e cancelamento assinado. Em produção, confirmar `SITE_URL=https://www.sussurrosdosaber.com` (ou a origem HTTPS oficial efectivamente utilizada); o código admite HTTP para desenvolvimento e não certifica as ligações em produção.

`List-Unsubscribe` e `List-Unsubscribe-Post` já existem. GET mostra confirmação sem cancelar; POST com token válido dispensa sessão de leitor e cancela mensagens pendentes. Pedir ao fornecedor que inclua ambos os cabeçalhos na assinatura DKIM para suportar cancelamento com um clique autenticado. Não há CC ou envio colectivo que exponha a lista.

A fila limita novas tentativas, conserva o histórico e não repete automaticamente resultados incertos. Os valores iniciais 100/hora, 500/dia e 2500/edição são limites internos, não quotas certificadas do fornecedor. Configurar quotas oficiais mais restritivas com fonte e data no painel existente. «Aceite pelo SMTP» não significa entregue, lido ou recebido na caixa principal. Sem integração de bounces/complaints, as devoluções posteriores precisam de acompanhamento manual pelo fornecedor e pela caixa de retorno; não marcar mensagens como entregues nem inferir ausência de reclamações.

## 5. Alterações e testes

- `mail_delivery.py`: acrescenta `Date` UTC ao construir cada mensagem e `SMTP_REPLY_TO` opcional. Um Reply-To inválido, com múltiplos endereços ou injecção de cabeçalho é rejeitado antes de reservar tentativas. Sem a variável, as respostas continuam a seguir o From. Não foi inventada uma caixa de resposta.
- `tests/test_mail_delivery.py`: verifica a data, o cabeçalho opcional, a preservação do envelope privado e a rejeição de configuração inválida sem consumir quota. Mantém os testes existentes de TLS, limites, falhas, cancelamento e recuperação.
- Este relatório e `EMAIL_DNS_EVIDENCE.json`: documentação e evidência reproduzível de leitura pública, sem segredos.

Validação local: 36 testes de `test_mail_delivery.py` e 19 de `test_newsletter.py` passaram (55 no total), em bases SQLite isoladas; `compileall` e `git diff --check` passaram. Os testes PostgreSQL e as restantes verificações do CI devem ser consultados no PR correspondente. Os testes SMTP usam simulação; não comprovam configuração de produção. Não há alteração de esquema, dependência, fila, permissões, Docker ou interface. Não foi acrescentado painel de reputação porque não existe integração que disponibilize verificações contínuas: uma fotografia DNS não deve surgir como um estado de produção actual.

## 6. DNS proposto e passos manuais

**SPF e MX:** nenhuma alteração proposta. O SPF publicado corresponde ao exemplo oficial Spacemail consultado; a autorização do SMTP real continua dependente dos dados de produção.

**DKIM:** o registo documentado pelo fornecedor já está publicado. No Spaceship: Launchpad → Advanced DNS → domínio → Inactive records → Spacemail DNS records; comparar o nome e o valor completos com a zona Cloudflare, confirmar a assinatura activa e identificar `s=` e `d=` numa mensagem real. Não gerar outra chave nem substituir o registo sem confirmar se houve rotação. Se o SMTP real utilizar outro selector, consultar precisamente o selector confirmado nos cabeçalhos/painel.

**DMARC:** após confirmar todos os emissores e a autorização administrativa, uma proposta inicial de monitorização é TXT, nome `_dmarc`, conteúdo `v=DMARC1; p=none`. Trata-se de política proposta, não de configuração já aplicada nem de valor fornecido pelo alojamento. Esse conteúdo sem `rua` não fornece relatórios agregados. Criar ou designar primeiro um destino real capaz de os processar; só depois acrescentar o `rua=mailto:` correspondente, exactamente como aprovado, incluindo autorização externa quando aplicável. Não foi inventado endereço de relatórios. Observar autenticação e alinhamento de todos os emissores antes de avaliar políticas restritivas. Não adoptar automaticamente quarantine/reject.

No Cloudflare, confirmar a zona, exportar os registos existentes, aplicar apenas as alterações aprovadas e voltar a consultar o DNS após o TTL. Não apagar outros TXT, não alterar MX e não activar proxy sobre nomes de serviço de correio. A aplicação deste PR não cria nenhum registo.

## 7. Pedidos objectivos ao alojamento e reputação

Solicitar, sem enviar credenciais: confirmação do SMTP/porta/modo TLS e identidade autorizada; IP(s) públicos reais de saída por mensagem; IP partilhado ou dedicado; EHLO de saída; PTR e resolução directa correspondente; suporte DKIM, selector e domínio de assinatura activos; cobertura DKIM dos cabeçalhos de cancelamento; comportamento do MAIL FROM/Return-Path e acesso às devoluções; quotas por hora/dia/caixa/conta e limites de destinatários; política de newsletters e capacidade para uma edição superior a 2000 subscritores; métricas, rejeições, reclamações e relatórios disponíveis.

Só depois de obter IP e EHLO reais verificar PTR, A/AAAA, consistência e eventuais blocklists nas ferramentas oficiais correspondentes. O IP do site, os MX e o IP de submissão SMTP não devem ser tratados como IP de entrega. Não se concluiu boa ou má reputação, nem se confirmou IP partilhado. Não foram realizadas consultas de blocklist sem um IP de saída identificado.

Google Postmaster Tools: o administrador pode adicionar o domínio autenticador, copiar o TXT/CNAME único de verificação fornecido pela própria conta, publicá-lo com autorização e concluir Verify. Não há conta ligada, token de verificação ou integração/API implementada. Os painéis podem não ter dados com volumes reduzidos; ausência de dados não equivale a boa reputação.

## 8. Teste controlado Gmail e Outlook

**Estado: não executado em ambos.** Não houve autorização/destinatários controlados para envio real. SPF, DKIM e DMARC de mensagens reais, pasta de recepção e reputação permanecem não verificados.

Depois de autorização específica, usar apenas duas contas controladas e endereços elegíveis, nunca uma campanha da lista real. Numa cópia isolada da base, sem subscritores ou tarefas reais, preparar uma edição representativa pelo fluxo existente e aprovar/autorizar apenas os destinatários de teste. Confirmar que o servidor de teste não contém a fila de produção. Utilizar o SMTP real apenas para esse teste autorizado, respeitando a quota global do fornecedor. Testar separadamente o fluxo implantado com acompanhamento do administrador quando necessário.

No Gmail usar Mostrar original; no Outlook usar a opção de detalhes/origem da mensagem disponível no cliente. Guardar a mensagem completa de forma privada e recolher data UTC, versão implantada, Message-ID, destino controlado, resposta SMTP, pasta observada e Authentication-Results acrescentado pelo servidor receptor confiável. Comparar `spf=pass` e `smtp.mailfrom`, `dkim=pass` e `header.d`/selector `s=`, `dmarc=pass` e `header.from`. Confirmar alinhamento SPF ou DKIM com From segundo a política, não apenas três palavras PASS isoladas. Só os resultados do receptor confiável servem como evidência; cabeçalhos arbitrários não são prova.

Verificar Date, Reply-To se configurado, HTML/texto, ligações HTTPS, cancelamento visível e POST de um clique sem sessão, incluindo interrupção de pendências. Confirmar que os cabeçalhos List-Unsubscribe estão assinados. Se houver rejeição, guardar código e razão sanitizada, sem palavras-passe ou tokens. Um 250 seguido de bounce deve ser registado como tal; não repetir automaticamente uma entrega incerta. PASS não garante caixa principal. Registar cada conta como não executado/aceite/rejeitado/recebido e pasta efectivamente observada, sem extrapolar para todos os destinatários.

## 9. Comandos de diagnóstico

Linux/macOS (consultas de leitura):

```bash
dig TXT sussurrosdosaber.com
dig TXT spf.spacemail.com
dig TXT spf.jellyfish.systems
dig TXT _dmarc.sussurrosdosaber.com
dig MX sussurrosdosaber.com
dig TXT spacemail._domainkey.sussurrosdosaber.com
```

O último nome provém da documentação oficial Spacemail. Se o selector real for diferente, substituir pelo confirmado no painel ou no `s=` da assinatura. Recolher resposta completa, servidor consultado, hora UTC e eventuais erros. Para um IP de saída confirmado: `dig -x IP_CONFIRMADO` e depois A/AAAA do nome PTR; o marcador exige substituição e não deve ser consultado literalmente.

Windows PowerShell:

```powershell
Resolve-DnsName sussurrosdosaber.com -Type TXT
Resolve-DnsName spf.spacemail.com -Type TXT
Resolve-DnsName spf.jellyfish.systems -Type TXT
Resolve-DnsName _dmarc.sussurrosdosaber.com -Type TXT
Resolve-DnsName sussurrosdosaber.com -Type MX
Resolve-DnsName spacemail._domainkey.sussurrosdosaber.com -Type TXT
```

Alternativa: `nslookup -type=TXT sussurrosdosaber.com` e `nslookup -type=MX sussurrosdosaber.com`. Alterar o nome consultado para DMARC/DKIM. Nenhum destes comandos valida a assinatura de uma mensagem.

## 10. Implantação, validação e limites

Rever e integrar o PR; o deploy não foi executado. Manter o procedimento Coolify existente e as migrações já exigidas pela versão base (`20261021_08`). Este trabalho não acrescenta migração. Não mudar credenciais, porta ou remetente sem comparar com o painel real. `SMTP_REPLY_TO` é opcional e deve ser uma caixa existente e acompanhada; omitir a variável mantém a configuração anterior.

Antes de publicar, confirmar backup e versão anterior, testar numa cópia isolada, pausar reservas da fila durante a troca da imagem e aguardar qualquer tentativa em curso. Publicar pelo processo actual; verificar arranque, acesso administrativo, manutenção da fila e logs sanitizados. Retomar apenas o worker actual coordenado, com as quotas oficiais confirmadas. O deploy e as consultas DNS não autorizam uma campanha. Para rollback deste PR, voltar à imagem anterior compatível com o mesmo esquema e remover a variável opcional se introduzida; não apagar campanhas ou tentativas.

Pendências: SMTP/configuração real, posse/consentimento dos endereços, DKIM em mensagens, alinhamento, DMARC aprovado, destino de relatórios, IP/PTR/EHLO, quotas, política comercial, devoluções/reclamações, Gmail/Outlook e Postmaster. A auditoria documenta esses limites; não declara a entregabilidade resolvida.

## Fontes primárias consultadas

- [Spacemail: DKIM](https://www.spaceship.com/knowledgebase/setup-dkim-record-spacemail/) — obtenção da chave e nome do selector.
- [Spacemail: configuração SMTP](https://www.spaceship.com/knowledgebase/connect-spacemail-to-email-client/) — configuração publicada, a confirmar na conta real.
- [Spaceship: SPF, DKIM e DMARC](https://www.spaceship.com/blog/spf-dkim-dmarc-explained/) — exemplo SPF do fornecedor.
- [RFC 7208](https://www.rfc-editor.org/rfc/rfc7208) — SPF, duplicação e orçamento de termos DNS.
- [RFC 5322](https://www.rfc-editor.org/rfc/rfc5322) — Date e formato das mensagens.
- [Google: requisitos de remetentes](https://support.google.com/mail/answer/81126?hl=en) — autenticação, alinhamento e cancelamento.
- [Google: configurar Postmaster Tools](https://support.google.com/mail/answer/9981691?hl=en) — verificação de domínio com dados únicos da conta.
