# Correcções do painel administrativo — 1 de Novembro de 2026

Revisão do código na base `fcafc9379a59f49f01e6652f46c447c27e1c4826`.

Foram corrigidos os seguintes problemas confirmados:

- O botão Caixa explicativa inseria sequências literais de escape em vez de mudanças de linha. Os títulos também passavam por uma expressão regular incorrecta. A inserção passa a produzir um bloco reconhecido pelo renderer.
- Uma selecção antiga podia substituir texto entretanto alterado. A caixa agora exige que o conteúdo de origem permaneça igual e verifica o limite de tamanho antes da inserção.
- A pré-visualização da caixa não acompanhava a classe de tema escuro do painel (`admin-dark`).
- O formulário de um artigo omitia o seu autor quando o perfil estava inactivo. Esse autor volta a aparecer seleccionado, inclusive após um erro de validação, sem oferecer outros perfis inactivos como substitutos.
- A ordem zero de um autor era convertida em 100. O valor zero passa a ser conservado.
- As políticas editoriais não avisavam antes de abandonar alterações por guardar. Passam a ter essa protecção; respostas de pré-visualização antigas são ignoradas e pedidos têm tempo limite.
- O campo de tempo de leitura passa a declarar o máximo de 120 minutos, de acordo com a validação do servidor.

Validação local: 729 testes Python executados, sem falhas, com um teste dependente de PostgreSQL omitido; 15 testes JavaScript aprovados; sintaxe dos templates administrativos verificada. Acrescentados testes de regressão de autoria, ordem, inserção de caixas, selecções desactualizadas, limites e políticas editoriais. A integração contínua passa também a executar os testes de `tests/js`.

Foi acrescentado um percurso de navegador que insere a caixa, verifica a pré-visualização, o tema escuro e a apresentação móvel, guarda o artigo e volta a abri-lo. A sua execução fica a cargo do CI; não foi executado localmente.

Não foram alterados dados nem configurações de produção. A revisão automatizada não certifica todos os percursos do painel. Correio, pagamentos, armazenamento e outros serviços externos exigem validação no ambiente configurado, e a publicação destas correcções depende da integração da proposta e do processo habitual de implantação.
