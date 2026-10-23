# Sussurros do Saber Premium: implementação e relatório

Data: 23 de Outubro de 2026. Base analisada: `37973d1fcef1d2c8ce9bec08b136a54e67eab8c2`, ramo `main` de `MergiorGoriate/sussurros-do-saber`.

## Resultado e âmbito desta entrega

Foi implementada a primeira fase recomendada: página Premium, planos configuráveis, biblioteca de conteúdos adicionais, controlo de acesso no servidor e gestão administrativa. A contratação e as cobranças reais continuam indisponíveis. Não foram integrados gateways, criados mandatos de débito, cobrados clientes ou alteradas assinaturas em serviços externos. Esta entrega não deve ser apresentada como um sistema de pagamentos concluído.

Os artigos informativos do portal e os artigos científicos da revista, incluindo investigações originais e revisões, mantêm o acesso gratuito existente. Não foi acrescentado qualquer campo de assinatura aos modelos `Article` ou `Journal`, nem alterado o seu mecanismo de autorização, pesquisa, publicação, PDF, RSS ou divulgação. A periodicidade da revista também não foi alterada.

A biblioteca Premium aceita apenas quatro tipos de conteúdos adicionais: cursos especializados, séries educativas, eventos e entrevistas. Os conteúdos desta fase são páginas de texto em Markdown. Não existe ainda um sistema de aulas, inscrições em eventos, videoconferência, certificados, progresso pedagógico ou transmissão privada de vídeo.

## Análise da arquitectura

O projecto usa Flask, SQLAlchemy e Jinja, com estilos próprios e Tailwind compilado. As contas de leitores reutilizam `Researcher`; a função existente `submissions.researcher()` verifica se a conta está activa e se o nonce da sessão corresponde ao da conta. A administração dispõe de sessões associadas às credenciais e autenticação de dois factores.

A implementação acrescenta dois blueprints em `premium.py`, modelos separados em `premium_models.py` e uma migração aditiva. Reutiliza a autenticação, o CSRF, o renderizador sanitizado de Markdown, o limitador de pedidos e os modelos de página existentes. Não cria outro sistema de contas. A navegação pública recebe uma ligação Premium; o menu administrativo apresenta a gestão Premium apenas ao administrador principal.

## Funcionalidades entregues

| Área | Comportamento |
| --- | --- |
| `/premium` | Apresentação, compromisso de acesso aberto, formatos de conteúdo, planos visíveis e estado do acesso da conta |
| `/premium/biblioteca` | Catálogo público de descrições, filtro por tipo e paginação de 12 conteúdos |
| `/premium/conteudos/<id>` | Conteúdo publicado completo apenas para uma conta confirmada com acesso válido; resposta 403 para visitantes sem acesso |
| `/admin/premium` | Planos, assinaturas paginadas, conteúdos paginados e últimas 30 alterações de auditoria |
| Planos | Criar/editar nome, periodicidade mensal ou anual, preço, moeda, descrição e visibilidade |
| Conteúdos | Criar/editar texto, descrição pública, tipo e publicação; retirar da biblioteca sem eliminar o registo |
| Acessos | Procurar uma conta confirmada por e-mail, conceder oferta, definir validade, suspender, cancelar ou renovar a oferta |

Os dois planos iniciais, mensal e anual, são criados ocultos, com preço zero como valor de preparação. Não representam planos gratuitos nem preços comerciais aprovados. O administrador define os preços; a publicação de um plano exige um valor positivo. São aceites MZN, USD, EUR e ZAR, em unidades monetárias mínimas inteiras, com duas casas decimais e sem aritmética de vírgula flutuante na gravação.

A periodicidade do plano identifica a proposta comercial; nesta fase o administrador define explicitamente o início e o fim de cada oferta. Não existe cálculo de facturação nem renovação automática. O formulário e a página pública explicam que os acessos concedidos são ofertas sem cobrança.

A alteração de um preço ou a ocultação de um plano não modifica os acessos já atribuídos. Cada assinatura conserva uma cópia do nome, periodicidade, moeda e preço do plano no momento da concessão. Os registos não são eliminados pelos formulários desta fase.

## Controlo de acesso e integridade

A entrega do corpo de um conteúdo exige, em cada pedido, sessão de leitor válida, conta activa, e-mail confirmado e assinatura da própria conta em estado `active`, cujo início já ocorreu e cujo fim ainda não foi atingido. O fim é exclusivo: no instante indicado o acesso termina. A expiração não depende de uma tarefa agendada. Cancelamento e suspensão retiram o acesso no pedido seguinte, incluindo quando o navegador já tinha uma sessão aberta.

Os estados enviados pelo navegador, parâmetros na URL e indicadores como `premium=true` não concedem acesso. O catálogo consulta apenas os metadados necessários. A página de recusa apresenta título e descrição públicos, sem incluir o corpo reservado. Rascunhos e identificadores inexistentes respondem com 404, mesmo a assinantes. Não é disponibilizada uma API de entrega alternativa.

As respostas Premium usam `no-store`; as páginas completas reservadas também recebem instruções de não indexação e não arquivo. O catálogo não acrescenta conteúdo reservado ao sitemap ou RSS. A aplicação preserva os cabeçalhos de segurança e a sanitização existentes. Nenhum mecanismo de controlo de acesso impede uma pessoa autorizada de copiar o texto que já recebeu.

A gestão exige `superadmin_required`, que revalida credenciais, privilégios e configuração de dois factores. As funções editoriais não recebem permissões Premium por herança. Todas as alterações exigem POST e CSRF. Há limites específicos de pedidos nos formulários. Os preços, tipos, datas, identificadores e estados são validados no servidor; o acesso de oferta exige confirmação explícita e motivo registado.

A base de dados impõe estados/tipos admitidos, preço não negativo, preço positivo para planos visíveis, fim posterior ao início e uma única assinatura por conta. Os registos editáveis usam versões optimistas; um formulário antigo recebe 409. As gravações administrativas e os respectivos eventos de auditoria pertencem à mesma transacção. A auditoria conserva alterações de planos, concessões, alterações de validade/estado e publicação de conteúdos. Os motivos são apresentados apenas na administração; evite colocar neles dados sensíveis desnecessários.

## Implantação e operação

1. Fazer uma cópia de segurança e ensaiar numa base isolada com a mesma estrutura da produção.
2. Com o código desta versão e `DATABASE_URL` configurado, executar `python -m alembic upgrade head` antes de servir tráfego. Confirmar `python -m alembic current`: resultado esperado `20261023_10 (head)`.
3. Publicar a aplicação e confirmar `/healthz`, `/premium`, `/premium/biblioteca`, um artigo do portal e um artigo da revista. Não foram alteradas variáveis de ambiente, serviços SMTP, tarefas agendadas ou dependências.
4. Entrar como administrador principal, definir preços e descrições dos planos e preparar conteúdos adicionais. Publicar apenas conteúdos e preços aprovados pela equipa.
5. Usar uma conta de teste confirmada para conceder uma oferta. Verificar a leitura numa sessão dessa conta e a recusa numa janela anónima. Suspender ou cancelar e repetir o pedido.

A migração cria apenas `premium_plan`, `premium_subscription`, `premium_content` e `premium_audit`, sem modificar tabelas de artigos, revistas ou contas. Pode ser repetida sem duplicar os planos iniciais. O mecanismo de compatibilidade já existente no arranque também reconhece estas tabelas quando `AUTO_SCHEMA_UPGRADE` está activo; não alterar essa configuração como parte desta funcionalidade.

Não há downgrade destrutivo: a migração recusa eliminar histórico. Uma reversão de código pode conservar as tabelas adicionais; qualquer reversão de dados exige recuperação planeada de uma cópia de segurança. A integração no GitHub e os testes locais não comprovam publicação nem migração na produção. Nenhuma operação desta entrega foi feita na base de produção.

## Pagamentos: verificação e fases seguintes

Documentação consultada em 23 de Outubro de 2026. Uma integração tecnicamente documentada não confirma a elegibilidade comercial da entidade, as condições contratuais, a liquidação de fundos ou a disponibilidade de débitos recorrentes na conta concreta.

| Opção | Evidência consultada | Decisão nesta entrega |
| --- | --- | --- |
| M-Pesa Moçambique | A Vodacom documenta C2B síncrono/assíncrono, reversões e consulta de estado | Candidato à cobrança local. A página consultada não comprova mandatos recorrentes para esta entidade. Não confundir C2B com autorização de débitos futuros |
| e-Mola | Agregadores locais, como PAY e ClicPay, apresentam documentação de pagamentos e-Mola | Exige validação comercial/técnica com Movitel ou agregador contratado; recorrência automática não confirmada |
| Cartões via agregador local | A documentação PAY descreve cobranças por cartões, dependentes da configuração da conta | Confirmar aceitação de cartões internacionais, tokenização, liquidação, disputas e recorrência; não presumir que uma cobrança pontual permite uma assinatura automática |
| Stripe Billing | Documentação oficial descreve assinaturas, facturas e webhooks recorrentes | Moçambique não aparece na lista consultada de países de suporte directo a Payments. Não tratar Stripe como disponível automaticamente para uma entidade moçambicana |

Fontes primárias:

- [Vodacom Moçambique: API Aberta do M-Pesa](https://www.vm.co.mz/m-pesa/artigo/api-aberta-do-m-pesa).
- [Portal de desenvolvimento M-Pesa Moçambique](https://developer.mpesa.vm.co.mz/).
- [PAY: documentação API](https://pay.co.mz/docs) e [pagamentos e-Mola](https://pay.co.mz/e-mola). As afirmações do agregador precisam de confirmação contratual antes de selecção.
- [ClicPay: documentação API](https://www.clicpay.co.mz/api/documentation).
- [Stripe: disponibilidade global](https://stripe.com/global).
- [Stripe Billing: ciclo de vida das assinaturas](https://docs.stripe.com/billing/subscriptions/overview).

A próxima fase deve começar pela escolha de um fornecedor que aceite a entidade e permita os meios de pagamento pretendidos. Para cada meio, obter confirmação escrita sobre cobrança pontual, renovação com nova autorização e mandato recorrente automático. Se uma carteira exigir autorização a cada cobrança, apresentar a operação como renovação manual; não anunciar débito automático.

Depois dessa confirmação, implementar uma camada de pagamentos própria, separada das ofertas: preços versionados, referências externas únicas, tentativas e eventos persistentes, valores/moeda conferidos no servidor, assinatura dos webhooks, protecção contra repetição, idempotência e reconciliação com o fornecedor. Nunca activar acesso com base no redireccionamento do navegador ou num estado enviado pelo cliente. Uma transacção pendente, falhada ou incerta não deve ser registada como liquidada.

Testar eventos duplicados e fora de ordem, atrasos, cancelamentos, falhas de renovação, reembolsos, disputas e reconciliação antes de activar cobranças. Recolher consentimento e condições de cancelamento; usar a página de pagamento/tokenização do fornecedor para cartões, sem guardar números de cartão ou CVV no portal. Só activar produção após validação das credenciais, do contrato e dos ensaios. Não foram criadas credenciais ou páginas de pagamento fictícias nesta fase.

A entrega privada de vídeo, áudio e anexos constitui outra fase: armazenamento privado e URLs temporários emitidos após autorização. Um link público colocado no corpo de um conteúdo não fica protegido pelo Premium. O formulário editorial explica essa limitação.

## Testes e resultados

Executados com dados sintéticos em SQLite, sem pagamentos ou contas externas:

```bash
PYTHONPATH=tests:. python -m unittest test_premium test_migrations test_admin_security test_reader_accounts -v
node --test tests/consent.test.cjs
node --check tests/browser/premium.spec.js
python -m compileall -q premium.py premium_models.py premium_schema.py tests/test_premium.py tests/browser/premium_fixture.py
npm run build:css
```

Resultado: **54 testes Python passaram**, incluindo **23 testes específicos do Premium**; **6 testes JavaScript passaram**. A verificação de sintaxe e a compilação CSS também passaram. Foram instaladas as dependências de `requirements.txt` para a validação final.

A bateria adicional que inclui `test_platform` executou 129 testes: 127 passaram; dois testes de PDF ficaram impedidos pela ausência local de `static/img/pdf-logo-sussurros.png`, um recurso binário existente no repositório que o conector não conseguiu transferir. A fonte DejaVu foi recuperada de uma instalação local com SHA de blob idêntico ao repositório. A imagem de reserva foi recuperada do código e o respectivo teste passou. Não foram substituídos logótipos nem alterados recursos binários no ramo proposto. Estes resultados não equivalem a uma suite completa sem falhas.

Os testes Premium cobrem visitantes anónimos, leitores gratuitos, assinantes válidos, outras contas, estado falsificado no cliente, expiração exacta, início futuro, suspensão, cancelamento, revogação de conta/nonce, confirmação de e-mail, rascunhos, filtragem, paginação, CSRF, administração restrita, valores monetários, criação de ofertas, duplicação, alterações concorrentes, preservação dos preços atribuídos e manutenção das rotas públicas. A migração é ensaiada a partir do head anterior, repetida e verificada quanto à preservação de dados existentes.

`tests/browser/premium.spec.js` acrescenta cinco cenários Playwright: apresentação a 320/768/1440 px e nos temas claro/escuro, navegação por teclado, recusa/entrega de conteúdos e concessão/cancelamento administrativo com duas sessões. Usa dados isolados de `premium_fixture.py` e será incluído na descoberta existente do CI. **Não foi executado localmente**: o descarregamento do Chromium devolveu ficheiros truncados. Não há capturas visuais verificadas nem certificação de acessibilidade ou de funcionamento em dispositivos físicos.

O CI existente descobre `test_premium.py` e `premium.spec.js` sem alteração do workflow. Confirmar os resultados desse CI e fazer a revisão visual antes da publicação. PostgreSQL, fornecedores reais, migração em produção e cobranças recorrentes não foram ensaiados nesta sessão.

## Correcção após a primeira execução do CI

A primeira execução do CI aprovou a suite Python, a auditoria de dependências, o ensaio PostgreSQL e a construção Docker. Nos testes de navegador, 133 cenários passaram e quatro falharam: três verificavam a URL imediatamente após submeter o filtro e um não encontrava o selector pelo nome acessível exacto «Plano».

O teste do filtro passa a confirmar a selecção e a aguardar a navegação com uma asserção Playwright que volta a verificar a URL até ao limite previsto. Os selectores de plano e estado passam a referenciar explicitamente etiquetas de texto próprias, mantendo os controlos nativos e a utilização por teclado. As verificações de acesso e a lógica de assinaturas não são alteradas. A aprovação desta correcção depende da nova execução do CI.
