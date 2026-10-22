# Ajustes de SEO dos artigos

Análise do código na revisão `ba2354046f72ce66ad76a22103dcf9f100ce25be`.

## Resultado e limites

Foram preparados ajustes de código e um procedimento executável. **Nenhum artigo de produção foi actualizado.** Não há acesso à base de dados de produção neste ambiente. Foi possível verificar as 27 páginas públicas no navegador: o relatório `docs/ARTICLE_SEO_PUBLIC_20261022.md` contém os valores observados, propostas, contagens e problemas estruturais. O JSON correspondente preserva esses dados públicos, mas não substitui a cópia recuperável dos registos. As propostas continuam pendentes de confronto com os registos e revisão final.

Os limites são critérios editoriais: não garantem apresentação exacta nem posições no Google.

## Localização dos dados

`models.py`, tabela `article`: `title` contém o título visível; `summary`, o resumo; `body`, o corpo em Markdown/HTML; `image`, o endereço da capa. Existem também `slug`, `doi`, autoria, datas, estados e referências. A classe `Article` não dispõe de campos próprios de SEO nem de texto alternativo da capa. `Journal` é um modelo distinto, com outros campos, incluindo `cover_alt`; não é alterado por este procedimento.

`templates/article.html` apresenta `title` num H1 e no `<title>`, anteriormente com um sufixo incondicional. Usa `summary` na meta descrição, nas descrições sociais e nos dados estruturados. `templates/base.html` contém uma meta descrição e um `<title>`; o cabeçalho aí definido não contém H1. Os componentes partilhados e o HTML completo foram incluídos na auditoria das 27 páginas públicas; a verificação tem de ser repetida após as alterações.

`admin.py`, função `article_form`, edita os mesmos campos usados no site público. `article_history.py` usa `article_revision` para as versões. Não se criaram campos paralelos ou alterações à interface, permissões ou fluxo editorial.

## Alterações de código

| Elemento | Antes | Depois |
| --- | --- | --- |
| `<title>` | Acrescentava sempre ` — Sussurros do Saber` | Acrescenta o sufixo apenas quando o total é inferior a 70 caracteres; preserva o título completo |
| Slug omitido/vazio no formulário de artigo existente | Podia ser calculado a partir do novo título | Mantém o slug existente; continua a permitir uma alteração explícita no campo existente |
| Directiva de imagem com alternativa vazia | Recebia `Imagem do artigo` | Mantém alternativa vazia; a classificação decorativa/informativa exige inspecção |
| Níveis H5/H6 | Eram removidos pelo saneamento do Markdown | São conservados, com estilo por CSS |
| Artigos relacionados | Secção sem título semântico, seguida de H3 | H2 na secção, conservando a classe visual e os H3 dos artigos |

Um título principal com 70 ou mais caracteres continua pendente de reformulação editorial. O código não corta palavras nem reescreve automaticamente conteúdos.

As capas ainda usam alternativas genéricas derivadas do título. Não foram substituídas por descrições inventadas. A ferramenta assinala capas e imagens para inspecção. Não foram recomprimidas imagens: não houve medição que justificasse essa operação. Legendas, créditos, licenças e originais permanecem intactos.

## Procedimento na máquina com acesso à base de dados

Instalar as dependências do projecto e executar a partir da raiz, usando `DATABASE_URL` já definida no ambiente seguro do serviço. Não colocar credenciais nos comandos, relatórios ou repositório. Guardar relatórios e cópias fora da pasta pública e do Git, num directório privado com cópia persistente.

```bash
umask 077
python scripts/article_seo.py audit --output /caminho/privado/auditoria-seo.json
```

A auditoria é de leitura e não importa `app.py`, não cria tabelas, não insere demonstrações nem publica agendamentos. Devolve os identificadores, slugs, valores, contagens, impressões digitais dos registos, duplicações, H1 no corpo, saltos de níveis e imagens para revisão. A análise estrutural usa Markdown genérico; as directivas e o resultado final têm de ser confirmados com o renderizador real.

Ler integralmente cada artigo antes de propor uma reformulação. Inspeccionar as respectivas imagens. Preservar valores que cumpram os critérios. O resumo também aparece no texto visível: verificar se a nova formulação funciona nos dois contextos. Um campo de SEO independente exigiria outra alteração de esquema e integração com o painel; não foi introduzido silenciosamente.

Criar um plano JSON, com apenas os artigos a alterar, usando a impressão digital devolvida pela auditoria:

```json
{
  "articles": [
    {
      "id": 123,
      "fingerprint": "SUBSTITUIR_PELA_IMPRESSAO_DA_AUDITORIA",
      "after": {
        "title": "SUBSTITUIR_POR_TITULO_REVISTO",
        "summary": "SUBSTITUIR_POR_DESCRICAO_REVISTA_COM_60_A_160_CARACTERES"
      },
      "reviewed": true,
      "reason": "Explicar por que a reformulação permanece fiel ao conteúdo lido."
    }
  ]
}
```

O exemplo é apenas estrutural: os seus valores não devem ser aplicados.

```bash
python scripts/article_seo.py apply --plan /caminho/privado/plano-seo.json --backup /caminho/privado/antes-seo.json --actor 'Nome do operador'
```

A ferramenta admite `title`, `summary` e uma transformação estrutural determinística de `body`, em artigos publicados. Recusa outras reescritas do corpo. Valida os limites nos títulos/descrições submetidos e recusa novas duplicações, rejeita alterações concorrentes e identificadores repetidos, e não recalcula slugs. Bloqueia alterações concorrentes durante a transacção. Antes de escrever cria um ficheiro exclusivo, com permissões 0600, sincronizado em disco, contendo os registos afectados completos e as diferenças com contagens. Regista versões anteriores e novas no histórico existente e uma entrada na auditoria. A operação SQL é atómica; uma repetição sem diferenças não cria versões nem cópias adicionais. Requer as tabelas de versões e auditoria existentes; não improvisa um esquema alternativo.

Se a transacção falhar depois da criação do ficheiro, a cópia pode existir sem que as alterações tenham sido aplicadas. Confirmar com nova auditoria. Não apagar ou sobrescrever uma cópia para contornar um erro.

As alternativas das imagens e as estruturas ambíguas devem ser revistas no editor existente após inspecção, conservando legendas, referências e conteúdo. A ferramenta propõe apenas ajustes em títulos Markdown ATX simples: elimina um H1 inicial que repita exactamente o título do artigo e organiza os níveis seguintes a partir de H2. Preserva os blocos de código cercados e recusa transformar corpos com títulos HTML, Setext ou blocos HTML ambíguos. Casos não abrangidos continuam pendentes de revisão no editor. Não é uma revisão semântica automática das secções.

## Recuperação

```bash
python scripts/article_seo.py restore --plan /caminho/privado/antes-seo.json --backup /caminho/privado/antes-recuperacao.json --actor 'Nome do operador'
```

Recupera os campos alterados (título, resumo e/ou estrutura do corpo) para os valores anteriores e cria novas versões, preservando o histórico. Não repõe a data técnica `updated_at`: actualiza-a para invalidar formulários antigos. Conserva datas de publicação, estado, DOI, autoria e URL. Rejeita a recuperação se o registo tiver mudado entretanto, evitando apagar trabalho posterior. O histórico do painel continua disponível; a recuperação habitual pelo painel converte o artigo em rascunho e exige nova revisão, conforme o fluxo já existente.

## Validação realizada e pendente

Vinte testes passaram em SQLite: manutenção e recuperação, atomicidade, repetição, alterações concorrentes, cópias exclusivas, campos protegidos, estrutura do corpo, plano editorial por slug, execução dos comandos e verificação HTTP simulada. Os testes de integração usam a aplicação real e verificam HTML completo, painel, permissões, endereços, histórico e formulário da revista. As contagens incluem espaços, pontuação e sufixo. Não foram executados testes contra PostgreSQL ou uma sessão editorial de produção.

Após aplicar na produção: voltar a auditar; abrir cada URL anterior; verificar HTTP 200, canónico, um único `<title>`, uma única meta descrição, um H1 na página completa e sequência dos subtítulos. Inspeccionar as imagens; verificar legendas, créditos e licenças. Abrir os mesmos artigos no painel com as funções autorizadas, confirmar valores e edição, histórico e pré-visualização. Não alterar os estados para efectuar esta verificação. Comparar também o aspecto da secção de artigos relacionados.

O relatório final por artigo deve reunir a auditoria anterior, o plano, as diferenças da cópia e a auditoria posterior; incluir título principal, `<title>` e meta descrição com as respectivas contagens, problemas estruturais corrigidos, alternativas inspeccionadas, URL e resultado da validação pública/painel. Até esses passos ocorrerem, as correcções dos registos e a verificação integral permanecem pendentes.

## Preparar planos e verificar o resultado

Para exportar também os textos públicos necessários à revisão, usar `audit --include-content`. O ficheiro continua privado; não contém credenciais, mas não deve ser publicado como substituto de uma cópia de segurança.

```bash
python scripts/article_seo.py audit --include-content --output /caminho/privado/auditoria-com-textos.json
python scripts/article_seo.py plan-editorial --input docs/ARTICLE_SEO_PROPOSALS_20261022.json --output /caminho/privado/plano-editorial.json
python scripts/article_seo.py plan-structure --output /caminho/privado/plano-estrutural.json
```

`plan-editorial` resolve os IDs pelos slugs existentes, compara título e resumo com os valores observados e pára se encontrar diferenças. Não adivinha identificadores nem aplica propostas desactualizadas. Os dois planos são criados com `reviewed: false`: depois de confrontar cada alteração com o texto original, definir `reviewed: true` e uma justificação em `reason`. Rever apenas os artigos que necessitam de alteração. Guardar os planos num local privado.

Se aplicar primeiro o plano editorial, gerar novamente o plano estrutural: a alteração anterior modifica a impressão digital do registo. `apply` rejeita planos antigos. Uma aplicação estrutural não reescreve títulos ou descrições que não façam parte do plano; as pendências continuam a aparecer na auditoria.

A verificação pública pode executar-se sem ligação à base de dados, usando uma auditoria anterior que contenha os IDs e slugs:

```bash
python scripts/article_seo.py verify --input /caminho/privado/auditoria-com-textos.json --output /caminho/privado/verificacao-publica.json
```

Regista o URL final, o estado HTTP, as contagens reais de título HTML, meta descrição e H1, e os saltos ascendentes de nível no HTML completo. Conserva os títulos de acessibilidade de SVG como elementos distintos do `<title>` HTML. Não executa JavaScript, não autentica no painel e não classifica imagens como decorativas. Confirmar também o resultado no navegador e no painel.
