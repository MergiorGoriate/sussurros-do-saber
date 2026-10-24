# Relatório técnico — Sussurros do Saber Prémio

Data: 24 de Outubro de 2026. Versão candidata a integração; não corresponde a uma confirmação de implantação ou de pagamentos em produção.

## 1. Funcionalidades reutilizadas

Foi preservada a aplicação Flask, com SQLAlchemy, os dois planos de periodicidade mensal e anual, o catálogo `PremiumContent`, as subscrições `PremiumSubscription`, os registos `PremiumAudit`, a autenticação das contas existentes e as sessões administrativas com segundo factor. Não foi criada outra plataforma ou outro sistema de contas.

Mantêm-se a contratação com preço calculado no servidor, a proposta assinada e limitada no tempo, a preservação do plano durante a autenticação, as integrações ClicPay/NetShop e Stripe, a verificação dos pagamentos no servidor, os lançamentos financeiros imutáveis, os comprovativos, a recuperação das reconciliações e o cancelamento da renovação sem perda antecipada do período já pago. Os meios de teste continuam sem activar acesso pago real.

O Prémio utiliza a caixa de notificações existente através da sua função de emissão. O funcionamento das notificações das outras áreas não foi alterado.

## 2. Funcionalidades implementadas

A navegação própria do Prémio reúne biblioteca, cursos e formações, vídeos e séries, eventos e seminários, colecções, planos e preços, benefícios, membros, relatórios, notificações, configurações e pagamentos.

O editor permite gerir título, subtítulo, descrição pública, autoria, categoria, área científica, idioma, editora, ano, ISBN, DOI, instrutor, objectivos e licença. O administrador confirma os direitos de utilização antes da publicação. Foram acrescentados rascunho, publicação, programação, suspensão, arquivo e restauro. A eliminação definitiva exige confirmação; recursos com histórico de aprendizagem, certificados ou inscrições devem ser arquivados.

Os documentos PDF, EPUB, DOCX e PPTX, as capas e os vídeos MP4/WebM são guardados privadamente na base de dados. A entrega passa sempre por uma rota que verifica o estado de publicação e o acesso efectivo. É possível adicionar vários materiais, substituir um ficheiro escolhido e associar vídeos e documentos às aulas. Os limites são 25 MB por documento e 40 MB por vídeo. Ficheiros de aula em uso precisam de ser desassociados antes da eliminação.

O leitor integra o visualizador PDF do navegador e uma leitura de capítulos EPUB na ordem indicada pelo livro. Permite guardar posição, notas e até vinte marcadores por recurso. O conteúdo EPUB é sanitizado, sem scripts, formulários, CSS ou pedidos remotos. Pesquisa e ampliação de PDFs dependem do visualizador do navegador; nos capítulos EPUB usa-se também a pesquisa do navegador. Recursos com obrigação de acesso aberto continuam legíveis gratuitamente, incluindo sem conta; guardar progresso exige uma conta confirmada.

O catálogo tem pesquisa por título, descrição e autoria, filtros por categoria, tipo e formato, destaques, favoritos e histórico pessoal. Os materiais individuais mantêm as permissões ao serem incluídos numa colecção.

Os cursos e séries têm módulos ou temporadas, aulas ou episódios, ordenação, publicação, vídeos privados, documentos e avaliações de escolha múltipla. A avaliação é corrigida no servidor. É necessário acertar todas as perguntas de cada aula para a concluir; aulas sem avaliação têm confirmação de conclusão pelo participante. A alteração de uma aula invalida a conclusão dessa versão. O certificado, quando activado pelo administrador, exige a conclusão de todas as aulas publicadas. O PDF é pessoal e não representa atribuição de grau académico.

Os eventos têm datas em hora de Moçambique, modalidade, capacidade, palestrantes, local e ligação privada da sessão. Os subscritores podem inscrever-se ou cancelar a inscrição. A ligação da sessão é apresentada apenas a participantes inscritos com acesso válido. O administrador consulta os participantes e regista a presença. Inscrições repetidas não ocupam lugares adicionais e a capacidade é verificada no servidor.

As condições de renovação, cancelamento, reembolso e limitações são configuradas por plano e apresentadas numa página própria e na contratação. As alterações invalidam propostas ainda não confirmadas. As condições são guardadas com os novos pedidos, preservando a informação contratada. O preço anual configurado é o valor efectivamente cobrado; não são inventados descontos ou benefícios sem correspondência na configuração.

Os recursos podem autorizar planos específicos. Sem restrição explícita, são acessíveis às subscrições válidas existentes. Há permissões delegadas próprias do Prémio para conteúdos, participantes, planos, ofertas, finanças e relatórios. A gestão das delegações e das configurações gerais permanece reservada ao administrador principal. Um responsável de biblioteca não recebe automaticamente permissões financeiras ou de alteração de preços. As permissões são verificadas em cada pedido e podem ser revogadas.

Os meios e moedas podem ser desactivados no painel. A activação administrativa não ultrapassa a falta de credenciais ou aprovações do prestador. As mensagens de pagamento, conteúdo, aprendizagem e eventos podem ser activadas por grupo e personalizadas com texto e os marcadores `{mensagem}` e `{assunto}`. Não é preciso alterar o código para estas operações.

## 3. Componentes modificados

Foram ampliados `premium.py`, `premium_models.py`, `premium_schema.py`, os templates em `templates/premium/` e `templates/admin/premium*`, e as folhas de estilo próprias do Prémio. Os novos serviços são `premium_access.py`, `premium_resources.py`, `premium_settings.py` e `premium_features.py`, com um pequeno ficheiro JavaScript próprio para o editor.

No subsistema financeiro do Prémio, `billing.py` passa a guardar as condições contratadas e permite a delegação financeira explícita; `billing_providers.py` respeita os meios e moedas desactivados no painel; `billing_service.py` utiliza as preferências de notificação do Prémio. Os adaptadores dos prestadores e os critérios de confirmação financeira foram preservados.

Fora do Prémio, a alteração autorizada limita-se à versão esperada em `tests/test_migrations.py` e `tests/test_scientific_metrics_migration.py`. Não foram modificados artigos, revista, submissões, editor, newsletter, métricas científicas, autenticação geral, navegação geral ou páginas institucionais. A permissão de enquadramento do PDF aplica-se exclusivamente à resposta do leitor Prémio.

## 4. Migração da base de dados

A migração aditiva `20261024_15` sucede a `20261024_14`. Cria treze tabelas: `premium_resource`, `premium_file`, `premium_lesson`, `premium_progress`, `premium_event`, `premium_registration`, `premium_collection_item`, `premium_certificate`, `premium_setting`, `premium_staff`, `premium_plan_terms`, `premium_category` e `premium_usage`.

Os conteúdos e registos financeiros anteriores não são convertidos nem eliminados. Conteúdos antigos sem metadados adicionais conservam o comportamento e as permissões anteriores. As relações de aprendizagem reutilizam as contas e os conteúdos existentes.

Aplicar `alembic upgrade head` antes de iniciar a versão nova, especialmente quando `AUTO_SCHEMA_UPGRADE=false`. Os testes verificam a criação repetida das tabelas e a preservação de dados existentes. O retorno a código anterior deve preservar as tabelas e o histórico; não se fornece um procedimento destrutivo de eliminação dos dados.

## 5. Integrações de pagamento

Mantêm-se M-Pesa e e-Mola através de ClicPay, cartão via ClicPay/NetShop e subscrições de cartão via Stripe. A carteira e o ambiente são verificados na integração existente. Cartões e CVV não são guardados no portal. O regresso do navegador não confirma uma transacção: a activação decorre da reconciliação ou dos eventos verificados no servidor.

O painel permite consultar a configuração detectada e controlar novas vendas, sem revelar chaves. Desactivar novas vendas não interrompe a verificação de pedidos existentes ou o cancelamento das renovações. M-Pesa, e-Mola e NetShop mantêm renovação manual; a recorrência Stripe exige consentimento e disponibilidade do prestador.

## 6. Dependências externas e activação

Não foi efectuada uma transacção real, não foram inseridas credenciais e não foi activada a produção. Permanecem pendentes a configuração no servidor e a validação comercial/técnica dos prestadores. O código usa, entre outras, `PREMIUM_PAYMENTS_ENABLED`, `PREMIUM_PAYMENTS_MODE`, `PREMIUM_LIVE_APPROVED`, `CLICPAY_TOKEN`, as referências das carteiras ClicPay, os anfitriões autorizados NetShop, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_MERCHANT_APPROVED` e `STRIPE_PORTAL_CONFIGURATION`.

As credenciais devem ser colocadas no gestor de segredos do servidor, não no formulário administrativo nem em ficheiros públicos. As páginas só apresentam os meios efectivamente detectados e permitidos para a moeda e o valor.

O comando periódico existente passa também a publicar recursos programados e a processar notificações de novos conteúdos em lotes:

```sh
flask --app app premium-reconciliar --limit 100
```

Pode usar-se separadamente o comando exclusivo para publicação e notificações:

```sh
flask --app app premium_admin processar --limit 100
```

A tarefa deve ser configurada no servidor, por exemplo a cada minuto. O painel não instala processos ou tarefas no Coolify. O horário de publicação é o primeiro processamento elegível após a data configurada. Os serviços de videoconferência e os eventos presenciais são organizados pelo administrador; a plataforma protege a ligação e gere inscrições e materiais, sem prometer alojar uma transmissão em directo.

## 7. Testes executados

Foram executados os testes existentes de planos, contratação, pagamentos, catálogo e subscrições, bem como novos testes de recursos privados, ficheiros inválidos, permissões por plano, arquivo e eliminação, publicação programada, estrutura e sanitização EPUB, leitura PDF, progresso, avaliações, certificados, capacidade de eventos, colecções, categorias, favoritos, métricas, permissões delegadas, notificações e CSRF.

Também foram preparados testes Playwright para os novos filtros, o leitor PDF privado e o formulário de recursos a 320, 768 e 1440 píxeis. Foram mantidas as verificações anteriores de acesso e de modos claro e escuro. A execução local do navegador não está disponível neste ambiente; os resultados destes testes devem ser confirmados no CI.

## 8. Resultados e evidência

A bateria completa local executou 633 testes Python, com sucesso e um teste ignorado por depender de PostgreSQL dedicado. Não foram utilizadas contas de clientes nem enviados pedidos reais aos prestadores. Os testes financeiros simulam as respostas externas, mantendo reais as operações da aplicação e da base de dados.

Os templates Jinja, a sintaxe JavaScript e as declarações CSS próprias foram analisados. A aprovação dos testes locais não é equivalente à validação de pagamentos em produção ou à aprovação visual num navegador.

## 9. Problemas identificados e tratados

Foi acrescentada uma excepção de segurança de enquadramento limitada ao leitor privado, porque a política geral do portal bloqueia enquadramentos locais. Os restantes ecrãs mantêm a política existente.

As versões do catálogo e das aulas detectam alterações concorrentes. A programação usa o bloqueio do conteúdo antes dos metadados, e as inscrições têm controlo transaccional de capacidade. As notificações têm chaves de deduplicação; o processamento de novidades tem cursor persistente por recurso. Os resultados das avaliações e a elegibilidade do certificado são calculados no servidor, sem aceitar pontuações ou permissões declaradas pelo navegador.

## 10. Limitações técnicas e estado de conclusão

Os pagamentos reais continuam pendentes da configuração e da validação externas. A implantação, a migração no servidor e o funcionamento efectivo da tarefa periódica também precisam de confirmação no ambiente de produção. Por isso, o serviço não deve ainda ser anunciado como integralmente operacional em produção.

O leitor EPUB apresenta texto e estrutura sanitizados; não reproduz todos os estilos ou elementos multimédia do formato. A posição do PDF é guardada pelo utilizador, porque a plataforma não controla a navegação interna de todos os visualizadores nativos. Os marcadores e o progresso documental são guardados por recurso.

O controlo de descarregamento gere as opções oferecidas pelo portal e o acesso no servidor; não é DRM. A entrega para leitura ou reprodução permite tecnicamente que o dispositivo conserve dados. A emissão de certificado verifica a conclusão registada na plataforma; não constitui fiscalização da presença física nem acreditação académica.

As métricas de utilização contam eventos efectivamente registados e são limitadas a uma ocorrência por conta, recurso, acção e dia. Uma abertura de ficheiro não comprova leitura integral ou visualização completa. As receitas continuam a resultar dos registos financeiros existentes, separadas de ofertas e testes.

Os ficheiros ficam na base de dados, com os limites indicados. A infra-estrutura deve ser dimensionada para estes volumes e incluir os ficheiros privados nas cópias de segurança. Os certificados e o histórico de participação são preservados através do arquivo dos recursos usados.

## 11. Manutenção

Validar a migração numa cópia de segurança antes da implantação e verificar os registos do comando periódico. Confirmar as credenciais e os eventos dos prestadores no ambiente de teste antes de aprovar produção. Acompanhar os pedidos que exigem reconciliação, os cancelamentos pendentes, as quotas de armazenamento e as falhas de entrega.

Rever periodicamente os acessos delegados, as condições dos planos e as licenças dos materiais. Ao actualizar uma aula, verificar os efeitos sobre as conclusões da versão anterior. Para retirar um recurso com histórico, preferir o arquivo, mantendo certificados, inscrições e auditoria.
