# Centro de Divulgação Científica

Implementação da primeira fase no painel do Sussurros do Saber. A geração decorre em segundo plano; a decisão editorial é humana e a publicação nas redes é manual. Não há envio automático para redes sociais nesta versão.

## Utilização

1. Abra **Centro de Divulgação Científica** no menu administrativo.
2. Pesquise um artigo publicado do portal ou um artigo científico publicado da revista. As páginas de apresentação da revista sem artigo completo não são elegíveis.
3. Escolha Facebook, Instagram, Bluesky, X ou Reddit, e o formato: imagem de curiosidade, infográfico conceptual, carrossel educativo, cartaz de descoberta ou texto.
4. Inicie a geração. O pedido HTTP apenas coloca a tarefa na fila. Actualize a página do material para acompanhar o resultado.
5. Compare cada afirmação com o trecho de suporte e com o artigo completo. Reveja o título, a legenda e todos os slides. A análise automática examina também as imagens compostas.
6. Solicite correcção, rejeite ou aprove. A aprovação exige confirmação expressa da revisão científica, linguística e visual, uma revisão automática completa sem bloqueios e uma ligação pública que responda com HTTP 200.
7. Após aprovação, o responsável com permissão de publicação pode copiar o texto e a ligação, ou descarregar um ZIP com os slides PNG, texto e registo de revisão.
8. Publique manualmente na rede escolhida e registe a ligação da publicação. O estado «Publicado» corresponde a uma declaração do administrador; o sistema não a confirma por API.
9. Consulte os pedidos de redireccionamento efectivamente registados. Os parâmetros UTM permitem atribuição adicional no sistema de análise de tráfego do portal.

A IA produz a primeira versão. A responsabilidade pela aprovação e autorização da divulgação pertence ao administrador.

## Revisão e estados

Os estados são **Em geração**, **A aguardar revisão**, **Em correcção**, **Aprovado**, **Publicado**, **Rejeitado** e **Falha na geração**. O histórico regista estado, versão, acção, nota, responsável e data. As datas apresentadas no painel usam Africa/Maputo; a base de dados guarda UTC.

Uma revisão incompleta, uma afirmação sem trecho literal de suporte, um valor numérico sem suporte no trecho ou uma avaliação científica, linguística ou visual negativa bloqueiam a aprovação. O reconhecimento literal de um trecho não prova que sustente a afirmação: uma segunda chamada ao modelo de revisão verifica a relação semântica. A verificação preliminar por IA pode falhar e não substitui a revisão humana nem a consulta de fontes primárias quando necessária.

Correcções manuais criam uma nova versão e uma nova tarefa de composição e revisão. A recuperação de uma versão anterior também cria uma versão nova, sem recuperar a autorização antiga. Os textos dos slides, título, legenda, afirmações, evidências, natureza da representação, composição e cor de destaque podem ser corrigidos. A regeneração permite indicar o problema encontrado sem escrever instruções técnicas.

Solicitar correcção de um material aprovado invalida a aprovação e a ligação identificada anterior. Um material rejeitado permanece bloqueado; para recomeçar, crie outro material a partir do artigo. Se o artigo de origem mudar ou deixar de estar publicado, a aprovação, a exportação e o redireccionamento ficam bloqueados até gerar e rever novamente.

O sistema não consegue remover ou corrigir uma publicação já efectuada numa rede social. Essa intervenção é manual. A pré-visualização é privada, mas nenhum sistema consegue impedir um revisor autorizado de copiar texto ou fazer uma captura de ecrã; os bloqueios aplicam-se à exportação formal e às operações do módulo.

## Identidade e formatos

O compositor usa o ficheiro oficial `static/img/logo-sussurros-light.png`. A IA não recria o logotipo nem escreve os textos de sobreposição. O Pillow aplica a imagem, o logotipo, a tipografia, a legenda de representação conceptual/hipotética e o endereço do portal.

As saídas usam 1080 × 1350 píxeis para Instagram e 1200 × 1200 para as outras quatro redes. O carrossel contém entre três e cinco slides. Uma ilustração é reutilizada nos slides, com textos próprios. O formato «Texto» não solicita uma imagem. Os infográficos desta fase são composições conceptuais: não há geração de gráficos quantitativos com eixos, escalas ou séries de dados. Não apresentar esquemas conceptuais como resultados medidos.

O compositor recusa texto que não cabe na área legível em vez de o cortar silenciosamente. A opção de composição compacta reduz a área da imagem e disponibiliza mais espaço para texto. A fonte é `DISSEMINATION_FONT`, DejaVu Sans do sistema, ou DejaVu Serif já incluída no repositório, por esta ordem.

Os textos seguem português de Moçambique, com ortografia anterior ao Acordo de 1990, por instrução de geração e revisão. A validação linguística continua a exigir leitura humana. Os limites conservadores de texto para X e Bluesky incluem o título, a legenda e a ligação completa exportada. O tamanho aceito pela aplicação não substitui a validação das regras vigentes da rede.

No Instagram, coloque a ligação num local clicável permitido pela rede; não presuma que a legenda torna uma ligação clicável. No Reddit, reveja as regras da comunidade e os requisitos relativos a divulgação própria.

## Permissões

O administrador principal tem acesso. Os restantes utilizadores precisam de mandatos gerais, activos e aceites nas funções existentes:

| Permissão | Operações |
| --- | --- |
| `dissemination.manage` | Gerar, solicitar correcção, editar, regenerar e recuperar versões |
| `dissemination.approve` | Rever, solicitar correcção, aprovar ou rejeitar |
| `dissemination.publish` | Copiar a saída autorizada, descarregar e registar publicação manual |

Qualquer destas permissões permite consultar a área e o histórico privado. Um mandato limitado a uma revista não concede acesso global ao Centro. As contas antigas não recebem estas permissões pelo mecanismo de compatibilidade de acesso editorial. Apenas a conta principal pode atribuir as funções através dos mecanismos de gestão já existentes.

O módulo reutiliza autenticação, validade das sessões, 2FA, CSRF, limites de pedidos e cabeçalhos privados existentes. Os ficheiros permanecem fora de `static` e são servidos por rotas autenticadas. Cada ficheiro tem identificador aleatório e resumo SHA-256; alterações detectadas bloqueiam a utilização da saída.

## Configuração no Coolify

Faça backup da base de dados antes da implantação. A migração aditiva `20261025_17` cria apenas tabelas `dissemination_*` e não altera artigos, submissões, revista ou Prémio:

```bash
python -m alembic upgrade head
```

No modo existente `AUTO_SCHEMA_UPGRADE=true`, a inicialização também cria as tabelas novas através de `db.create_all()`. Em produção com migrações controladas, mantenha o procedimento habitual de Alembic.

Configure as variáveis abaixo no serviço web e no trabalhador. Guarde a chave como segredo do Coolify; não a escreva no repositório, no navegador ou em instruções públicas.

| Variável | Configuração |
| --- | --- |
| `OPENAI_API_KEY` | Chave de uma conta com acesso aos modelos seleccionados |
| `DISSEMINATION_TEXT_MODEL` | Modelo compatível com Chat Completions, JSON mode e `max_completion_tokens` |
| `DISSEMINATION_REVIEW_MODEL` | Modelo compatível com o mesmo contrato e com entrada de imagens |
| `DISSEMINATION_IMAGE_MODEL` | Modelo GPT Image compatível com Images API, `quality=low`, `1024x1024` e saída PNG em base64 |
| `DISSEMINATION_JOB_UNITS` | Reserva positiva de unidades administrativas por tarefa, incluindo repetição da revisão |
| `DISSEMINATION_DAILY_UNITS` | Limite diário positivo de unidades administrativas |
| `DISSEMINATION_DAILY_JOBS` | Máximo de tarefas por dia UTC; predefinição: 20 |
| `DISSEMINATION_STORAGE_DIR` | Caminho absoluto num volume privado persistente, partilhado entre web e trabalhador |
| `DISSEMINATION_FONT` | Opcional: caminho de uma fonte TrueType legível |
| `SITE_URL` | Origem HTTPS pública do portal, sem caminho, parâmetros ou credenciais |

Os identificadores de modelos ficam explícitos na configuração: não são escolhidos silenciosamente nem se pressupõe que a conta tenha acesso. Os modelos de texto/revisão precisam de suportar JSON mode; o de revisão também precisa de visão. A utilização do mesmo modelo nas duas etapas não transforma a revisão numa validação externa independente.

O directório predefinido é `instance/dissemination`. Recomenda-se configurar, por exemplo, `/data/divulgacao`, montar um volume persistente no mesmo caminho nos dois serviços e dar acesso ao utilizador do contentor. Não publique esse volume através do servidor web. Faça backup do volume juntamente com a base de dados: os registos de versões referenciam os ficheiros, não os contêm.

Execute num trabalhador ou agendamento próprio, fora dos processos que servem páginas públicas:

```bash
python -m flask --app app processar-divulgacao --limit 2
```

Uma execução periódica a cada minuto é suficiente para iniciar tarefas pendentes. Configure os recursos e o tempo máximo de execução para permitir chamadas de imagem até 300 segundos e chamadas de texto/revisão até 120 segundos cada. Prefira um único trabalhador. A reserva condicional da tarefa evita que dois trabalhadores processem normalmente a mesma entrada; a conclusão também verifica se a reserva continua válida.

Tarefas interrompidas há mais de 30 minutos passam a «Falha na geração» na execução seguinte. Não há repetição automática após falha ou interrupção, pois o fornecedor pode já ter cobrado a tentativa. O administrador pode solicitar nova geração, consumindo outra reserva.

### Custos e desempenho

Cada tarefa reserva unidades e uma vaga antes de contactar a IA, através de uma actualização condicional na base de dados. As reservas de tentativas falhadas permanecem contabilizadas. O limite de tarefas, uma imagem de base por material, os três a cinco slides e o limite de saída de 6000 tokens por chamada restringem a utilização.

As unidades são um mecanismo administrativo configurável; não são dólares, meticais, preços actuais dos modelos nem valores facturados. Não existe reconciliação com a facturação nesta fase. Defina reservas conservadoras, acompanhe a conta do fornecedor e configure os limites financeiros disponíveis nessa conta. A aplicação não garante um tecto monetário exacto com base nestas unidades.

O trabalhador limita respostas e dimensões de imagens e não segue redireccionamentos ao contactar o fornecedor. Os erros mostrados ao administrador não incluem a chave nem o corpo de erros do fornecedor. Os registos operacionais indicam a tarefa e a classe da falha. Conteúdos publicados são enviados ao fornecedor para geração e revisão; não submeta informação confidencial através de um artigo público.

## Ligações e resultados

O pacote aprovado inclui uma ligação privada de campanha, do tipo `/divulgacao/<identificador>`. Quando alguém a abre, o sistema confirma que a versão continua autorizada e que o artigo permanece igual ao analisado, regista o pedido elegível e redirecciona com `utm_source`, `utm_medium=social`, `utm_campaign` e `utm_content`.

O painel conta pedidos de redireccionamento desde a criação do material. Não deduplica pessoas nem dispositivos e não guarda IPs para esse efeito. Exclui HEAD, pré-carregamentos identificados e agentes que se anunciem como robôs; os restantes pedidos podem incluir repetições ou automação não identificada. Não denominar este contador «visitantes únicos», «leituras», «alcance» ou «sessões GA4».

As sessões e o tráfego no artigo dependem do sistema de análise do portal e da respectiva configuração e consentimento. Esta implementação não consulta a API do Google Analytics nem inventa resultados quando não existe medição. Copiar uma ligação directa ao artigo, fora da ligação identificada, pode preservar UTM manualmente, mas não incrementa o contador deste módulo.

## Validação e limitações de entrega

Os testes unitários usam respostas sintéticas, sem chamadas pagas ao fornecedor. Cobrem fila HTTP, textos para as cinco redes, imagens compostas com logotipo oficial, evidência inexistente ou numérica sem suporte, falhas semânticas/linguísticas/visuais, revisão incompleta, decisões, bloqueios de exportação, versões, recuperação, revogação de ligações, alterações ao artigo, CSRF, integridade de ficheiros, quotas, interrupções do trabalhador e permissões.

Resultados locais: a suite completa executou 673 testes com sucesso, com um teste ignorado por falta da configuração específica de PostgreSQL. Após acrescentar verificações de carrossel, limite total de texto, documentação privada e tratamento do fornecedor, os 29 testes específicos do Centro também passaram. Não se deve somar estas contagens, pois a suite completa já inclui os testes do módulo existentes nesse momento. Não foi validada concorrência real sobre PostgreSQL neste ambiente.

Foram também estendidos os testes globais de permissões para exercitar as três novas permissões, incluindo expiração, revogação, conta inactiva, âmbito de revista e login/2FA. Os testes de migração foram actualizados para a nova revisão.

Comandos de verificação:

```bash
PYTHONPATH=tests:. python -m unittest test_dissemination -v
python -m unittest discover -s tests -p 'test_*.py' -v
npx playwright test dissemination.spec.js
```

Os testes de navegador acrescentados verificam a interface a 320, 768 e 1440 píxeis, temas claro/escuro, imagem privada, bloqueio da exportação e solicitação de correcção. A execução local do navegador ficou bloqueada porque a transferência do Chromium não é permitida pela rede deste ambiente; devem correr no CI existente. A composição PNG foi renderizada e inspeccionada separadamente com uma imagem sintética, sem avaliar a qualidade de uma imagem científica real.

Antes da activação em produção, é necessário configurar a conta e os modelos, o trabalhador e o volume, executar o CI e validar uma geração real completa com revisão humana. Não foram usados segredos do utilizador nem efectuadas chamadas pagas neste desenvolvimento. A geração real, a facturação, a ligação pública de produção e a qualidade científica das imagens reais ainda precisam dessa validação.

Outras limitações: artigos com mais de 60 000 caracteres de conteúdo e referências são recusados sem truncagem silenciosa; não há análise de vídeos ou imagens do artigo original, apenas do texto e das imagens produzidas; não existe editor gráfico livre, OCR determinístico, confirmação da publicação por API, agendamento social ou remoção remota de publicações; não há limpeza automática de ficheiros órfãos, retenção configurável ou cópia de segurança automática neste módulo. As imagens e versões devem ser geridas no backup operacional existente.

A segunda fase, com APIs oficiais, deve preservar a autorização por versão e exigir nova revisão sempre que o conteúdo mudar. Nenhuma funcionalidade dessa fase está activada nesta entrega.


## Diagnóstico operacional

Execute no serviço que processa as tarefas:

```bash
python -m flask --app app diagnosticar-divulgacao
```

O comando verifica os nomes das variáveis obrigatórias, limites inteiros e coerência da reserva por tarefa, apresenta contagens da fila e testa escrita no armazenamento local, disponibilidade da fonte e existência do logotipo. Não mostra chaves nem efectua chamadas ao fornecedor. O resultado local não confirma saldo, acesso aos modelos, agendamento, nem partilha efectiva do volume e da base de dados entre serviços. O código de saída é diferente de zero quando há pendências de configuração ou recursos locais.

O painel distingue variáveis preenchidas de uma ligação efectivamente testada e avisa quando existem tarefas na fila. Não apresenta a presença de variáveis como prova de funcionamento. Se os pedidos ficarem na fila, verifique o agendamento de `processar-divulgacao` e se o trabalhador usa a mesma base de dados do serviço web. Se falharem, consulte a mensagem no material e os registos do trabalhador. Recusas HTTP 400, 401, 403, 404 e 429 têm mensagens próprias; erros do fornecedor nunca são reproduzidos integralmente no painel.

Para gerar apenas texto são necessários os modelos de texto e revisão, a chave e os limites. `DISSEMINATION_IMAGE_MODEL` é obrigatório nos formatos com imagem, mas a sua ausência não bloqueia o formato Texto. Um trabalhador com variáveis diferentes das do serviço web apresenta a configuração em falta na falha do material. Não há repetição automática de chamadas falhadas.

A geração dispõe de uma única tentativa adicional de correcção textual, partilhada entre erros no número de slides e trechos de suporte inexistentes. Persistindo o problema, a validação continua a bloquear o material; não se substitui evidência literal por semelhança nem se dispensam a revisão semântica e a revisão humana.

Se os ficheiros de uma versão estiverem ausentes ou alterados, o painel apresenta um aviso e desactiva a aprovação. Este aviso não recupera ficheiros perdidos. Restaure os ficheiros originais do backup no volume correcto ou solicite uma nova geração, sujeita a custos e revisão. Versões antigas não são reescritas automaticamente.
