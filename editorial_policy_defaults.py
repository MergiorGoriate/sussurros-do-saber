"""Conteúdo editorial padrão administrável do Sussurros do Saber.

Estes textos servem apenas para inicializar campos vazios. Depois de gravados,
a base de dados é a fonte de verdade e o administrador pode editá-los livremente.
"""

EDITORIAL_POLICY_DEFAULTS = {
    "author_guidelines": """# Diretrizes para Autores

O **Sussurros do Saber** recebe trabalhos científicos e académicos originais, preparados com rigor, transparência e respeito pela ética da investigação.

## Idiomas
São aceites manuscritos em **português ou inglês**. Independentemente do idioma principal, título, resumo e palavras-chave devem ser apresentados em português e inglês.

## Tipos de manuscritos
- **Artigo de Investigação Original:** até 7.000 palavras; resumo até 250 palavras; recomenda-se até 8 tabelas e/ou figuras; estrutura IMRaD quando adequada.
- **Artigo de Revisão:** até 9.000 palavras; resumo até 250 palavras; deve explicitar a metodologia de busca e seleção da literatura. Revisões sistemáticas e meta-análises devem seguir diretrizes de relato reconhecidas.
- **Comunicação Breve:** até 3.000 palavras; resumo até 200 palavras; recomenda-se até 4 tabelas e/ou figuras.
- **Estudo de Caso:** até 4.500 palavras; resumo até 250 palavras; recomenda-se até 5 tabelas e/ou figuras.
- **Editorial/Perspectiva:** até 2.500 palavras.

Monografias, dissertações e teses não constituem categorias de manuscrito. Trabalhos delas derivados podem ser submetidos após adaptação a uma categoria aceite e declaração da sua origem.

## Palavras-chave
Devem ser apresentadas **3 a 6 palavras-chave**.

## Autoria
Devem ser informados nome completo, afiliação institucional, cidade e país, ORCID quando disponível e e-mail do autor correspondente. A autoria deve refletir contribuição intelectual substancial.

## Avaliação por pares
Os manuscritos científicos são submetidos a **revisão por pares duplo-cega**. O ficheiro destinado à revisão deve ser anonimizado. A decisão final de publicação pertence à equipa editorial.

## Tabelas, figuras e imagens
Devem ser numeradas, identificadas, citadas no texto, apresentar fonte quando aplicável e ter qualidade adequada. Os autores são responsáveis pelas permissões necessárias. Manipulação enganosa de imagens não é permitida.

## Referências
Adota-se **APA, 7.ª edição**. Todas as citações devem corresponder à lista de referências e vice-versa. DOI deve ser incluído quando disponível e pertinente.

## Declarações
Quando aplicável, o manuscrito deve apresentar aprovação ética e consentimento informado, conflitos de interesses, financiamento, contribuições dos autores e disponibilidade dos dados.

## Inteligência Artificial
IA pode ser utilizada como ferramenta auxiliar, mas não pode ser autora ou coautora. Uso substancial de IA generativa deve ser declarado. Os autores humanos permanecem responsáveis pela exatidão, originalidade, referências, dados, direitos de autor e conclusões.

## Integridade científica
Não são tolerados plágio, fabricação ou falsificação de dados, manipulação enganosa de imagens, autoria inadequada, publicação duplicada não declarada ou manipulação da revisão por pares. Suspeitas fundamentadas podem levar a investigação editorial, rejeição, correção ou retratação.

## Fluxo editorial
**Submissão → Triagem editorial → Verificação formal, ética e de integridade → Revisão por pares → Revisões → Reavaliação → Decisão editorial → Produção → Prova → Publicação.**

As decisões podem incluir aceitação, revisões menores, revisões maiores ou rejeição. A submissão não garante publicação.
""",
    "reviewer_guidelines": """# Diretrizes para Revisores

Os revisores devem tratar todo manuscrito como **confidencial**, declarar conflitos de interesses e aceitar apenas avaliações que possam realizar com competência e dentro do prazo.

A avaliação deve ser objetiva, fundamentada, construtiva e respeitosa. Deve considerar, quando aplicável, originalidade e relevância, clareza dos objetivos, adequação metodológica, coerência entre métodos, resultados e conclusões, qualidade da análise, referências, tabelas e figuras, limitações, ética e integridade científica.

Suspeitas de plágio, fabricação ou falsificação de dados, publicação redundante, manipulação de imagens ou outras irregularidades devem ser comunicadas confidencialmente ao editor; o revisor não deve investigar diretamente os autores.

Manuscritos ou partes confidenciais não devem ser introduzidos em serviços externos de IA sem garantia adequada de confidencialidade ou autorização editorial. Qualquer uso autorizado de IA que influencie materialmente a avaliação deve ser comunicado. A responsabilidade intelectual pela revisão permanece humana.
""",
    "ethics_policy": """# Ética e Integridade Científica

O **Sussurros do Saber** orienta a atividade editorial por honestidade, transparência, responsabilidade, independência editorial e respeito pelos participantes da investigação.

Não são tolerados plágio, fabricação ou falsificação de dados, manipulação enganosa de resultados ou imagens, apropriação indevida de ideias, autoria inadequada, publicação duplicada não declarada, manipulação da revisão por pares ou declarações deliberadamente falsas.

Uma alegação não será tratada, por si só, como prova de má conduta. Suspeitas serão analisadas com documentação, confidencialidade e oportunidade razoável de esclarecimento. Conforme as evidências e a gravidade, poderão ser adotadas medidas como pedido de esclarecimentos, rejeição, correção, expressão editorial de preocupação ou retratação.

Investigações envolvendo seres humanos, animais, dados pessoais, material biológico ou outras situações reguladas devem cumprir as exigências éticas e legais aplicáveis e identificar aprovação ética e consentimento informado quando exigidos.

Autores, revisores e editores devem declarar conflitos de interesses relevantes. Erros relevantes identificados após publicação serão analisados e o registo científico poderá ser corrigido ou retratado de forma transparente.
""",
    "ai_policy": """# Política de Inteligência Artificial

Ferramentas de IA podem apoiar atividades de investigação, escrita e edição, mas **não podem ser autoras ou coautoras** e não substituem responsabilidade científica humana.

Uso substancial de IA generativa deve ser declarado de forma transparente, indicando, quando pertinente, ferramenta, finalidade e etapa em que foi utilizada. Quando a IA integrar a metodologia científica, o procedimento deve ser descrito com detalhe suficiente para compreensão e, quando possível, reprodução.

Os autores devem verificar exatidão factual, referências, originalidade, vieses, direitos de autor e integridade de textos, imagens, dados e análises produzidos ou modificados com IA.

Manuscritos submetidos são confidenciais. Revisores e editores não devem carregar conteúdo confidencial em serviços externos de IA quando a confidencialidade não estiver adequadamente assegurada ou quando isso contrariar as regras editoriais. As decisões editoriais permanecem sob responsabilidade humana.
""",
    "data_policy": """# Política de Dados de Investigação

O Sussurros do Saber apoia transparência, verificabilidade e reprodutibilidade, respeitando ética, legislação, privacidade e proteção de dados.

Quando um trabalho produzir ou analisar dados, os autores devem apresentar uma **declaração de disponibilidade de dados**, indicando, conforme aplicável, repositório público, disponibilidade mediante solicitação justificada, restrições éticas/jurídicas/de privacidade, inexistência de novos dados ou outra condição pertinente.

Quando possível, recomenda-se depósito em repositórios institucionais, disciplinares ou generalistas reconhecidos, preferencialmente com identificador persistente.

Dados pessoais, clínicos, confidenciais ou relativos a populações vulneráveis não devem ser divulgados quando isso violar consentimento, privacidade, legislação ou obrigações éticas. Dados não podem ser fabricados, falsificados ou manipulados de forma enganosa.
""",
    "fees_policy": """# Taxas / APC

O Sussurros do Saber compromete-se com **transparência integral** sobre quaisquer taxas editoriais ou de publicação.

Nenhuma taxa será cobrada sem que valor, finalidade, condições e momento da cobrança sejam previamente comunicados de forma clara. A existência ou inexistência de taxas não influencia a decisão científica e qualquer pagamento nunca garante aceitação ou publicação.

**Atualmente, enquanto uma taxa específica não estiver oficialmente estabelecida e publicada, não deve ser presumida qualquer obrigação de pagamento pelos autores.**

Se futuramente forem introduzidas APC ou outras taxas, a política pública informará valor e moeda, momento da cobrança, serviços abrangidos, critérios de isenção ou redução quando existentes e condições aplicáveis.
""",
    "open_access_policy": """# Acesso Aberto e Licenciamento

O Sussurros do Saber adota uma política de **acesso aberto**. Salvo indicação editorial específica apresentada antes da publicação, os artigos abrangidos por esta política são disponibilizados sob a licença **Creative Commons Attribution 4.0 International (CC BY 4.0)**.

A licença permite partilha e adaptação, inclusive para fins comerciais, desde que seja fornecida atribuição apropriada, indicada a licença e assinaladas modificações quando aplicável.

Os autores mantêm os direitos sobre os seus trabalhos nos termos da política editorial e concedem as permissões necessárias para publicação e disponibilização sob a licença indicada.

Materiais de terceiros não abrangidos pela licença geral devem ser identificados adequadamente. Acesso aberto não elimina obrigações de autoria, atribuição, integridade científica, privacidade, proteção de dados ou direitos de terceiros.
""",
}
