# Página Premium: formatos, planos e entrada na conta

23 de Outubro de 2026. Base: `9ec4a7c98422733e841fb9ab39be1a9355316555`, após integração do PR #271.

As duas imagens fornecidas mostram a secção de formatos e um único plano activo, alinhado à esquerda dentro de um painel muito largo. Esta alteração reorganiza apenas a apresentação da página `/premium/`.

## Alterações

- Cartões de cursos, séries, eventos e entrevistas com hierarquia tipográfica mais legível, símbolos, índices e destaque cromático no primeiro formato. Mantêm as mesmas ligações e descrições.
- Quando existe um único plano publicado, a introdução e o estado dos pagamentos ocupam a coluna esquerda e o cartão ocupa a direita. Desaparece a área vazia que anteriormente preenchia metade do painel. No telemóvel, os blocos passam a uma coluna.
- Com vários planos, mantém-se a grelha de comparação. Sem planos activos, mantém-se a mensagem de preparação. Não são criados preços, benefícios ou planos fictícios para preencher o desenho.
- Cartões com periodicidade, preço, descrição e benefícios separados. As condições continuam disponíveis num elemento nativo expansível «Renovação e cancelamento», utilizável por teclado.
- Contratação indisponível apresentada como estado informativo, com símbolo de cadeado; adesão continua disponível apenas quando a integração existente a permite.
- Entrada na conta transformada num bloco próprio; pergunta sobre acesso gratuito à revista apresentada num cartão coerente com a restante página.
- Estilos responsivos e compatíveis com as variáveis de tema existentes. A identidade azul/dourado, o hero, o cabeçalho e o rodapé são preservados.

Não há alterações ao servidor, base de dados, autenticação, preços, permissões ou pagamentos. Os planos apresentados continuam a ser exclusivamente os activos, consultados pela rota existente. Os artigos científicos e informativos continuam gratuitos; as configurações de cobrança não foram alteradas.

## Validação

- 81 testes Python aprovados: Premium, catálogo e pagamentos.
- 12 testes Playwright aprovados em Chromium 153, com servidor e SQLite isolados e dados sintéticos.
- Larguras de 320, 768 e 1440 px verificadas sem transbordo horizontal nos cenários existentes, nos modos claro e escuro.
- Cenário de cartão único adaptado à nova composição: retém um cartão no DOM, aplica a mesma classe usada pelo servidor para um plano e verifica largura e funcionamento por teclado das condições expansíveis. Não modifica planos na base de dados.
- Capturas adicionais da secção de planos nos dois temas, formatos e entrada na conta, para inspecção visual.
- 6 testes JavaScript de consentimento e compilação CSS aprovados.

O Chromium alternativo usado para validação permanece num directório temporário, fora das dependências do projecto. Não foram executados Firefox, Safari, testes em dispositivos físicos ou auditoria WCAG integral. Nenhuma cobrança ou publicação em produção foi efectuada.

## Ficheiros

Modificados: `templates/premium/index.html`, `static/css/premium.css`, `tests/browser/premium.spec.js`.

Criado: `docs/PREMIUM_HOME_LAYOUT.md`.
