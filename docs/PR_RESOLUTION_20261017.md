# Resolução dos Pull Requests em 17/10/2026

Foram revistos os oito PRs abertos nesta data. O trabalho usa contas e bases
sintéticas isoladas; não foram usados dados ou credenciais de produção.

## Alterações tratadas

| PR | Resolução |
| --- | --- |
| [#125](https://github.com/MergiorGoriate/sussurros-do-saber/pull/125) | Encerrado como substituído: login/registo, favoritos e acompanhamento já estão implementados e ampliados na main. A branch antiga tinha conflitos. |
| [#177](https://github.com/MergiorGoriate/sussurros-do-saber/pull/177) | Integrado: Cloudinary 1.46.3 e svglib 2.3.0. |
| [#178](https://github.com/MergiorGoriate/sussurros-do-saber/pull/178) | Integrado: CacheControl com limite mínimo 0.14.4. |
| [#179](https://github.com/MergiorGoriate/sussurros-do-saber/pull/179) | Conflito resolvido e integrado: google-auth com limite mínimo 2.61.0. |
| [#180](https://github.com/MergiorGoriate/sussurros-do-saber/pull/180) | Conflito resolvido e integrado: pypdf com limite mínimo 6.20.0. |
| [#181](https://github.com/MergiorGoriate/sussurros-do-saber/pull/181) | Integrado: Playwright 1.64.0. |
| [#182](https://github.com/MergiorGoriate/sussurros-do-saber/pull/182) | Integrado com migração completa do Tailwind 4, CLI, CSS, build Docker, override de segurança e ícones locais. |
| [#183](https://github.com/MergiorGoriate/sussurros-do-saber/pull/183) | Fila de artigos atribuídos com acesso directo e remoção após entrega do parecer; testes de reatribuição, permissões e mandatos. Esta revisão também corrige a expectativa de leitura das notificações. |

O PR #182 foi inicialmente encerrado ao reproduzir a falha da CLI, mas a auditoria
completa revelou vulnerabilidades na cadeia de desenvolvimento do Tailwind 3.
A branch foi restaurada, o PR reaberto, completado e integrado após validação.
Não foi integrada a actualização isolada que quebrava o build.

## Resultados do conjunto final

- 214 testes Python passaram, em Python 3.12 e SQLite isolado.
- 61 testes de navegador passaram em uma execução completa de dois minutos,
  após instalação limpa com `npm ci` e compilação CSS.
- `npm audit --audit-level=high`, incluindo dependências de desenvolvimento:
  zero vulnerabilidades reportadas.
- `pip-audit -r requirements.txt`: nenhuma vulnerabilidade conhecida reportada.
- `pip check` e `git diff --check` passaram.

Versões Python efectivamente testadas: Cloudinary 1.46.3, svglib 2.3.0,
CacheControl 0.14.4, google-auth 2.62.0 e pypdf 6.21.1. Os limites mínimos de
google-auth e pypdf não constituem uma execução adicional dessas versões mínimas.

Os testes de navegador usam Playwright 1.64.0 com Chromium 153.0.8010.0 local,
obtido de `@sparticuz/chromium` 153.0.0. O download habitual do Chromium 156
devolveu um arquivo inválido. A configuração alternativa não foi incluída na CI.
Google é simulado nos testes; não foi validada autenticação numa conta real.

## Regressões reproduzidas e corrigidas

A fila de revisão mantinha artigos com parecer já entregue porque o fluxo ainda
estava no estado `review`. O filtro agora exige `reviewed_at` vazio, preservando
o acesso posterior ao histórico.

Os testes de notificações esperavam o contador oculto apesar de a fixture criar
uma actualização por ler. Agora verificam o contador, a acção explícita de marcar
como vista e a sua persistência após recarregar, mantendo o acompanhamento.

Sem a fonte externa, ORCID, partilhas científicas e seta da conta podiam ficar
sem representação visível. Foram usadas representações locais e os testes
bloqueiam explicitamente a fonte para verificar os controlos.

## Verificações de infraestrutura pendentes

O GitHub Actions continua a terminar antes de atribuir runners ou executar
etapas. Por exemplo, a execução 39039969577 tem os quatro trabalhos com
`steps: []` e `runner_id: 0`; os logs devolvem 404. As execuções anteriores e
novas não devem ser apresentadas como suites aprovadas. A causa exacta não foi
confirmada e nenhuma verificação foi desactivada para ocultar o bloqueio.

O build Docker completo e os ensaios PostgreSQL não foram executados localmente.
As integrações foram validadas pelos ensaios locais descritos acima; resta
restabelecer o GitHub Actions e confirmar Docker, PostgreSQL e o ambiente de
produção. Não foi executado deploy pelo assistente.

Detalhes da migração e requisitos de navegador:
[TAILWIND4_MIGRATION_20261017.md](TAILWIND4_MIGRATION_20261017.md).
