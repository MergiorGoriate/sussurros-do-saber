# Auditoria pública de SEO dos artigos

Observação em 22 de Outubro de 2026. Foram percorridas as três páginas do catálogo e abertas as 27 páginas de artigo no navegador. Os valores abaixo vêm do DOM renderizado. Nenhum registo de produção foi alterado. As colunas «proposto» são propostas, não resultados aplicados.

## Resultados observados

26 títulos HTML têm 70 ou mais caracteres; oito títulos principais excedem o limite; 12 meta descrições excedem 160 caracteres. Existe uma meta descrição em cada página observada. Não foram encontradas duplicações exactas dos títulos principais ou descrições entre estes 27 artigos.

O artigo de genómica africana apresenta 73 H1 na página completa (um principal e 72 no corpo) e três saltos ascendentes de nível. O de xenotransplantes apresenta um salto H1 → H3 no início do corpo. As outras 25 páginas não apresentaram H1 adicionais nem saltos ascendentes na leitura do DOM. Isso não prova que todos os níveis escolhidos sejam semanticamente adequados: por exemplo, um parágrafo introdutório não deve ser um título apenas para ganhar destaque.

Foram identificados 101 elementos de imagem no corpo dos artigos, todos com atributo alt não vazio no momento da leitura. A presença do atributo não demonstra que a descrição corresponda à imagem. A inspecção visual permanece pendente; a largura zero durante carregamento diferido não foi tratada como prova de imagem quebrada. Capas, legendas, créditos e licenças não foram modificados.

## Contagens e propostas

As contagens incluem espaços e pontuação. «Título HTML proposto» simula o modelo corrigido, que omite o sufixo se este elevar o total a 70 caracteres. Os títulos principais que já cumprem o critério foram conservados literalmente. As descrições já adequadas foram conservadas, com uma proposta adicional para Python: o texto actual descreve sobretudo a folha de cálculo e resume insuficientemente o artigo sobre automação e reprodutibilidade.

| Artigo | H1 actual → proposto | HTML actual → proposto | Descrição actual → proposta | H1 na página | Saltos |
| --- | ---: | ---: | ---: | ---: | ---: |
| [1. Do Big Bang ao futuro cósmico: o que sabemos?](https://www.sussurrosdosaber.com/artigo/do-big-bang-ao-futuro-cosmico-o-que-sabemos) | 45 → 45 | 66 → 66 | 154 → 154 | 1 | 0 |
| [2. Como o cérebro produz memórias, emoções e consciência](https://www.sussurrosdosaber.com/artigo/como-o-cerebro-produz-memorias-emocoes-e-consciencia) | 53 → 53 | 74 → 53 | 148 → 148 | 1 | 0 |
| [3. Redes neuronais: como aprendem com grandes volumes de dados](https://www.sussurrosdosaber.com/artigo/edes-neuronais-como-aprendem-com-grandes-volumes-de-dados) | 59 → 59 | 80 → 59 | 145 → 145 | 1 | 0 |
| [4. Câncer como processo evolutivo: seleção natural acontecendo dentro do organismo](https://www.sussurrosdosaber.com/artigo/cancer-como-processo-evolutivo-selecao-natural-acontecendo-dentro-do-organismo) | 79 → 56 | 100 → 56 | 151 → 151 | 1 | 0 |
| [5. IA e descoberta científica: máquinas formulam hipóteses?](https://www.sussurrosdosaber.com/artigo/ia-e-descoberta-cientifica-maquinas-formulam-hipoteses) | 56 → 56 | 77 → 56 | 160 → 160 | 1 | 0 |
| [6. Realidade quântica: por que desafia a nossa intuição?](https://www.sussurrosdosaber.com/artigo/realidade-quantica-por-que-desafia-a-nossa-intuicao) | 53 → 53 | 74 → 53 | 124 → 124 | 1 | 0 |
| [7. O cérebro preditivo: como construímos a percepção](https://www.sussurrosdosaber.com/artigo/o-cerebro-preditivo-como-construimos-a-percepcao) | 49 → 49 | 70 → 49 | 162 → 140 | 1 | 0 |
| [8. Buracos negros e o paradoxo da informação: o que Hawking revelou](https://www.sussurrosdosaber.com/artigo/buracos-negros-e-o-paradoxo-da-informacao-o-que-hawking-revelou) | 64 → 64 | 85 → 64 | 150 → 150 | 1 | 0 |
| [9. Paradoxo de Fermi: onde está a vida extraterrestre?](https://www.sussurrosdosaber.com/artigo/paradoxo-de-fermi-onde-esta-a-vida-extraterrestre) | 51 → 51 | 72 → 51 | 138 → 138 | 1 | 0 |
| [10. Genómica africana: por que a diversidade genética de África pode transformar a medicina](https://www.sussurrosdosaber.com/artigo/genomica-africana-por-que-a-diversidade-genetica-de-africa-pode-transformar-a-medicina) | 87 → 62 | 108 → 62 | 190 → 132 | 73 | 3 |
| [11. AlphaFold resolveu o dobramento de proteínas? O que ainda permanece aberto](https://www.sussurrosdosaber.com/artigo/alphafold-resolveu-o-dobramento-de-proteinas-o-que-ainda-permanece-aberto) | 74 → 56 | 95 → 56 | 175 → 148 | 1 | 0 |
| [12. Xenotransplantes: avanços, riscos e futuro dos transplantes](https://www.sussurrosdosaber.com/artigo/xenotransplantes-orgaos-animais-geneticamente-modificados) | 59 → 59 | 80 → 59 | 179 → 146 | 1 | 1 |
| [13. Evolução humana continua? Evidências no genoma moderno](https://www.sussurrosdosaber.com/artigo/evolucao-humana-continua-acontecendo-evidencias-no-genoma-das-populacoes-modernas) | 54 → 54 | 75 → 54 | 144 → 144 | 1 | 0 |
| [14. DNA não codificante: o que realmente existe nos 98% do genoma que não codificam proteínas?](https://www.sussurrosdosaber.com/artigo/dna-nao-codificante-o-que-realmente-existe-nos-98-do-genoma-que-nao-codificam-proteinas) | 90 → 57 | 111 → 57 | 196 → 140 | 1 | 0 |
| [15. Epigenética: como o ambiente influencia os nossos genes](https://www.sussurrosdosaber.com/artigo/epigenetica-ambiente-reprogramar-nossos-genes) | 55 → 55 | 76 → 55 | 145 → 145 | 1 | 0 |
| [16. Consciência: como matéria cerebral produz experiência subjetiva?](https://www.sussurrosdosaber.com/artigo/consciencia-como-materia-cerebral-produz-experiencia-subjetiva) | 64 → 64 | 85 → 64 | 292 → 148 | 1 | 0 |
| [17. A origem da vida: da química prebiótica às primeiras células](https://www.sussurrosdosaber.com/artigo/a-origem-da-vida-da-quimica-prebiotica-as-primeiras-celulas) | 60 → 60 | 81 → 60 | 168 → 138 | 1 | 0 |
| [18. Modelos de Linguagem de Grande Escala: como os LLM aprendem, raciocinam, erram e transformam a produção do conhecimento](https://www.sussurrosdosaber.com/artigo/modelos-de-linguagem-de-grande-escala-como-os-llm-aprendem-raciocinam-erram-e-transformam-a-producao-do-conhecimento) | 119 → 56 | 140 → 56 | 207 → 140 | 1 | 0 |
| [19. Teoria do caos e efeito borboleta quando leis determinísticas produzem futuros imprevisíveis](https://www.sussurrosdosaber.com/artigo/teoria-do-caos-e-efeito-borboleta-quando-leis-deterministicas-produzem-futuros-imprevisiveis) | 92 → 47 | 113 → 68 | 168 → 145 | 1 | 0 |
| [20. Nanopartículas biogénicas: como combatem micróbios](https://www.sussurrosdosaber.com/artigo/nanoparticulas-biogenicas-como-combatem-microbios) | 50 → 50 | 71 → 50 | 147 → 147 | 1 | 0 |
| [21. Buracos negros: como se formam e quais são as suas propriedades](https://www.sussurrosdosaber.com/artigo/a-fronteira-onde-o-espaco-deixa-de-devolver-respostas) | 63 → 63 | 84 → 63 | 148 → 148 | 1 | 0 |
| [22. Big Data e investigação científica: como os dados transformam a descoberta](https://www.sussurrosdosaber.com/artigo/quando-os-dados-se-tornam-telescopios-a-nova-escala-da-descoberta-cientifica) | 74 → 61 | 95 → 61 | 172 → 134 | 1 | 0 |
| [23. Neuroplasticidade e aprendizagem: como o cérebro muda ao aprender](https://www.sussurrosdosaber.com/artigo/a-neuroplasticidade-explica-por-que-aprender-transforma-o-cerebro-mas-tambem-por-que-nao-existem-atalhos-magicos-para-o-conhecimento) | 65 → 65 | 86 → 65 | 168 → 146 | 1 | 0 |
| [24. Python na investigação: da folha de cálculo à análise reprodutível](https://www.sussurrosdosaber.com/artigo/python-na-investigacao-da-folha-de-calculo-a-analise-reprodutivel) | 66 → 66 | 87 → 66 | 157 → 140 | 1 | 0 |
| [25. Como os radiotelescópios africanos observam o universo](https://www.sussurrosdosaber.com/artigo/como-os-radiotelescopios-africanos-observam-o-universo) | 54 → 54 | 75 → 54 | 140 → 140 | 1 | 0 |
| [26. Plantas medicinais de Nampula e o futuro da investigação local](https://www.sussurrosdosaber.com/artigo/plantas-medicinais-de-nampula-e-o-futuro-da-investigacao-local) | 62 → 62 | 83 → 62 | 163 → 135 | 1 | 0 |
| [27. Bactérias endofíticas: os microrganismos invisíveis que protegem as plantas](https://www.sussurrosdosaber.com/artigo/bacterias-endofiticas-os-microrganismos-invisiveis-que-protegem-as-plantas) | 75 → 53 | 96 → 53 | 96 → 96 | 1 | 0 |

## Valores por artigo

### 1. Do Big Bang ao futuro cósmico: o que sabemos?

URL preservada: https://www.sussurrosdosaber.com/artigo/do-big-bang-ao-futuro-cosmico-o-que-sabemos

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Do Big Bang ao futuro cósmico: o que sabemos? (45) | Do Big Bang ao futuro cósmico: o que sabemos? (45) |
| Título HTML | Do Big Bang ao futuro cósmico: o que sabemos? — Sussurros do Saber (66) | Do Big Bang ao futuro cósmico: o que sabemos? — Sussurros do Saber (66) |
| Meta descrição | Uma revisão científica da origem, evolução e destino do Universo, distinguindo evidências observacionais, modelos cosmológicos e questões ainda em aberto. (154) | Uma revisão científica da origem, evolução e destino do Universo, distinguindo evidências observacionais, modelos cosmológicos e questões ainda em aberto. (154) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 2. Como o cérebro produz memórias, emoções e consciência

URL preservada: https://www.sussurrosdosaber.com/artigo/como-o-cerebro-produz-memorias-emocoes-e-consciencia

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Como o cérebro produz memórias, emoções e consciência (53) | Como o cérebro produz memórias, emoções e consciência (53) |
| Título HTML | Como o cérebro produz memórias, emoções e consciência — Sussurros do Saber (74) | Como o cérebro produz memórias, emoções e consciência (53) |
| Meta descrição | Explore como redes neuronais, memória, emoção e percepção se combinam para produzir experiências conscientes, à luz da investigação neurocientífica. (148) | Explore como redes neuronais, memória, emoção e percepção se combinam para produzir experiências conscientes, à luz da investigação neurocientífica. (148) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 3. Redes neuronais: como aprendem com grandes volumes de dados

URL preservada: https://www.sussurrosdosaber.com/artigo/edes-neuronais-como-aprendem-com-grandes-volumes-de-dados

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Redes neuronais: como aprendem com grandes volumes de dados (59) | Redes neuronais: como aprendem com grandes volumes de dados (59) |
| Título HTML | Redes neuronais: como aprendem com grandes volumes de dados — Sussurros do Saber (80) | Redes neuronais: como aprendem com grandes volumes de dados (59) |
| Meta descrição | Descubra como as redes neuronais aprendem padrões em grandes volumes de dados, desde os neurónios artificiais ao treino, aplicações e limitações. (145) | Descubra como as redes neuronais aprendem padrões em grandes volumes de dados, desde os neurónios artificiais ao treino, aplicações e limitações. (145) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 4. Câncer como processo evolutivo: seleção natural acontecendo dentro do organismo

URL preservada: https://www.sussurrosdosaber.com/artigo/cancer-como-processo-evolutivo-selecao-natural-acontecendo-dentro-do-organismo

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Câncer como processo evolutivo: seleção natural acontecendo dentro do organismo (79) | Cancro: selecção natural e evolução das células tumorais (56) |
| Título HTML | Câncer como processo evolutivo: seleção natural acontecendo dentro do organismo — Sussurros do Saber (100) | Cancro: selecção natural e evolução das células tumorais (56) |
| Meta descrição | Tumores evoluem. Entenda como mutações, seleção clonal, microambiente, metástase e tratamentos moldam a evolução do câncer e a resistência terapêutica. (151) | Tumores evoluem. Entenda como mutações, seleção clonal, microambiente, metástase e tratamentos moldam a evolução do câncer e a resistência terapêutica. (151) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 5. IA e descoberta científica: máquinas formulam hipóteses?

URL preservada: https://www.sussurrosdosaber.com/artigo/ia-e-descoberta-cientifica-maquinas-formulam-hipoteses

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | IA e descoberta científica: máquinas formulam hipóteses? (56) | IA e descoberta científica: máquinas formulam hipóteses? (56) |
| Título HTML | IA e descoberta científica: máquinas formulam hipóteses? — Sussurros do Saber (77) | IA e descoberta científica: máquinas formulam hipóteses? (56) |
| Meta descrição | Analisa como a inteligência artificial gera hipóteses científicas, como avaliá-las e quais são os limites de novidade, evidência, validação e reprodutibilidade. (160) | Analisa como a inteligência artificial gera hipóteses científicas, como avaliá-las e quais são os limites de novidade, evidência, validação e reprodutibilidade. (160) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 6. Realidade quântica: por que desafia a nossa intuição?

URL preservada: https://www.sussurrosdosaber.com/artigo/realidade-quantica-por-que-desafia-a-nossa-intuicao

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Realidade quântica: por que desafia a nossa intuição? (53) | Realidade quântica: por que desafia a nossa intuição? (53) |
| Título HTML | Realidade quântica: por que desafia a nossa intuição? — Sussurros do Saber (74) | Realidade quântica: por que desafia a nossa intuição? (53) |
| Meta descrição | Explore a realidade quântica, a superposição, a medição, o emaranhamento e as experiências que desafiam a intuição clássica. (124) | Explore a realidade quântica, a superposição, a medição, o emaranhamento e as experiências que desafiam a intuição clássica. (124) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 7. O cérebro preditivo: como construímos a percepção

URL preservada: https://www.sussurrosdosaber.com/artigo/o-cerebro-preditivo-como-construimos-a-percepcao

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | O cérebro preditivo: como construímos a percepção (49) | O cérebro preditivo: como construímos a percepção (49) |
| Título HTML | O cérebro preditivo: como construímos a percepção — Sussurros do Saber (70) | O cérebro preditivo: como construímos a percepção (49) |
| Meta descrição | Explore como o cérebro combina sinais sensoriais, expectativas e aprendizagem para construir percepções, e conheça as evidências e os limites da teoria preditiva. (162) | Como o cérebro combina sinais sensoriais, expectativas e aprendizagem para construir percepções, e quais são os limites da teoria preditiva. (140) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 8. Buracos negros e o paradoxo da informação: o que Hawking revelou

URL preservada: https://www.sussurrosdosaber.com/artigo/buracos-negros-e-o-paradoxo-da-informacao-o-que-hawking-revelou

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Buracos negros e o paradoxo da informação: o que Hawking revelou (64) | Buracos negros e o paradoxo da informação: o que Hawking revelou (64) |
| Título HTML | Buracos negros e o paradoxo da informação: o que Hawking revelou — Sussurros do Saber (85) | Buracos negros e o paradoxo da informação: o que Hawking revelou (64) |
| Meta descrição | A radiação de Hawking destrói informação? Explore entropia, curva de Page, holografia, firewalls e ilhas quânticas, com fontes e gráficos científicos. (150) | A radiação de Hawking destrói informação? Explore entropia, curva de Page, holografia, firewalls e ilhas quânticas, com fontes e gráficos científicos. (150) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 9. Paradoxo de Fermi: onde está a vida extraterrestre?

URL preservada: https://www.sussurrosdosaber.com/artigo/paradoxo-de-fermi-onde-esta-a-vida-extraterrestre

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Paradoxo de Fermi: onde está a vida extraterrestre? (51) | Paradoxo de Fermi: onde está a vida extraterrestre? (51) |
| Título HTML | Paradoxo de Fermi: onde está a vida extraterrestre? — Sussurros do Saber (72) | Paradoxo de Fermi: onde está a vida extraterrestre? (51) |
| Meta descrição | Planetas abundantes, vida incerta e buscas limitadas: uma análise científica do paradoxo de Fermi, da equação de Drake e do Grande Filtro. (138) | Planetas abundantes, vida incerta e buscas limitadas: uma análise científica do paradoxo de Fermi, da equação de Drake e do Grande Filtro. (138) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 10. Genómica africana: por que a diversidade genética de África pode transformar a medicina

URL preservada: https://www.sussurrosdosaber.com/artigo/genomica-africana-por-que-a-diversidade-genetica-de-africa-pode-transformar-a-medicina

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Genómica africana: por que a diversidade genética de África pode transformar a medicina (87) | Genómica africana: diversidade genética e medicina de precisão (62) |
| Título HTML | Genómica africana: por que a diversidade genética de África pode transformar a medicina — Sussurros do Saber (108) | Genómica africana: diversidade genética e medicina de precisão (62) |
| Meta descrição | África contém a maior diversidade genética humana. Entenda como genómica africana pode melhorar diagnóstico, farmacogenómica, risco poligénico, descoberta de fármacos e medicina de precisão. (190) | Como a diversidade genética das populações africanas pode contribuir para o diagnóstico, a farmacogenómica e a medicina de precisão. (132) |

Estado: proposta sem aplicação. Corrigir os 72 H1 do corpo e os três saltos, preservando o texto.

### 11. AlphaFold resolveu o dobramento de proteínas? O que ainda permanece aberto

URL preservada: https://www.sussurrosdosaber.com/artigo/alphafold-resolveu-o-dobramento-de-proteinas-o-que-ainda-permanece-aberto

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | AlphaFold resolveu o dobramento de proteínas? O que ainda permanece aberto (74) | AlphaFold e o dobramento de proteínas: avanços e limites (56) |
| Título HTML | AlphaFold resolveu o dobramento de proteínas? O que ainda permanece aberto — Sussurros do Saber (95) | AlphaFold e o dobramento de proteínas: avanços e limites (56) |
| Meta descrição | AlphaFold revolucionou a previsão de estruturas proteicas, mas folding, dinâmica, estabilidade, desordem e ensembles continuam desafios. Entenda o que foi realmente resolvido. (175) | O que o AlphaFold permite prever sobre estruturas proteicas e quais os limites no estudo do dobramento, da dinâmica e da estabilidade das proteínas. (148) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 12. Xenotransplantes: avanços, riscos e futuro dos transplantes

URL preservada: https://www.sussurrosdosaber.com/artigo/xenotransplantes-orgaos-animais-geneticamente-modificados

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Xenotransplantes: avanços, riscos e futuro dos transplantes (59) | Xenotransplantes: avanços, riscos e futuro dos transplantes (59) |
| Título HTML | Xenotransplantes: avanços, riscos e futuro dos transplantes — Sussurros do Saber (80) | Xenotransplantes: avanços, riscos e futuro dos transplantes (59) |
| Meta descrição | Rins e corações de porcos geneticamente modificados já foram transplantados em humanos. Entenda CRISPR, rejeição, PERV, riscos, ensaios clínicos e os limites dos xenotransplantes. (179) | Avanços e limites dos xenotransplantes com órgãos de porcos modificados geneticamente: rejeição, segurança infecciosa, ética e estudos em humanos. (146) |

Estado: proposta sem aplicação. Rever a frase introdutória marcada como H3; poderá ser um parágrafo, dependendo da estrutura original.

### 13. Evolução humana continua? Evidências no genoma moderno

URL preservada: https://www.sussurrosdosaber.com/artigo/evolucao-humana-continua-acontecendo-evidencias-no-genoma-das-populacoes-modernas

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Evolução humana continua? Evidências no genoma moderno (54) | Evolução humana continua? Evidências no genoma moderno (54) |
| Título HTML | Evolução humana continua? Evidências no genoma moderno — Sussurros do Saber (75) | Evolução humana continua? Evidências no genoma moderno (54) |
| Meta descrição | A evolução humana continua. Descubra evidências no genoma ligadas ao leite, à malária, à altitude e ao DNA herdado de neandertais e denisovanos. (144) | A evolução humana continua. Descubra evidências no genoma ligadas ao leite, à malária, à altitude e ao DNA herdado de neandertais e denisovanos. (144) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 14. DNA não codificante: o que realmente existe nos 98% do genoma que não codificam proteínas?

URL preservada: https://www.sussurrosdosaber.com/artigo/dna-nao-codificante-o-que-realmente-existe-nos-98-do-genoma-que-nao-codificam-proteinas

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | DNA não codificante: o que realmente existe nos 98% do genoma que não codificam proteínas? (90) | DNA não codificante: o que ocupa a maior parte do genoma? (57) |
| Título HTML | DNA não codificante: o que realmente existe nos 98% do genoma que não codificam proteínas? — Sussurros do Saber (111) | DNA não codificante: o que ocupa a maior parte do genoma? (57) |
| Meta descrição | Apenas cerca de 1,5% do genoma humano codifica proteínas. Descubra o que existe no restante DNA: intrões, enhancers, RNAs, transposões, pseudogenes, telómeros e regiões ainda sem função conhecida. (196) | O que existe no DNA humano não codificante: intrões, regiões reguladoras, RNAs, transposões e sequências cuja função permanece desconhecida. (140) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 15. Epigenética: como o ambiente influencia os nossos genes

URL preservada: https://www.sussurrosdosaber.com/artigo/epigenetica-ambiente-reprogramar-nossos-genes

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Epigenética: como o ambiente influencia os nossos genes (55) | Epigenética: como o ambiente influencia os nossos genes (55) |
| Título HTML | Epigenética: como o ambiente influencia os nossos genes — Sussurros do Saber (76) | Epigenética: como o ambiente influencia os nossos genes (55) |
| Meta descrição | Descubra como alimentação, tabaco e stress influenciam a epigenética e a regulação dos genes, e conheça os limites da herança epigenética humana. (145) | Descubra como alimentação, tabaco e stress influenciam a epigenética e a regulação dos genes, e conheça os limites da herança epigenética humana. (145) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 16. Consciência: como matéria cerebral produz experiência subjetiva?

URL preservada: https://www.sussurrosdosaber.com/artigo/consciencia-como-materia-cerebral-produz-experiencia-subjetiva

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Consciência: como matéria cerebral produz experiência subjetiva? (64) | Consciência: como matéria cerebral produz experiência subjetiva? (64) |
| Título HTML | Consciência: como matéria cerebral produz experiência subjetiva? — Sussurros do Saber (85) | Consciência: como matéria cerebral produz experiência subjetiva? (64) |
| Meta descrição | Neste instante, milhares de milhões de neurónios estão electricamente activos no seu cérebro. Mas há algo extraordinário que não aparece directamente num eléctrodo: existe uma experiência de estar a ler estas palavras. Como processos físicos podem produzir um mundo vivido em primeira pessoa? (292) | Uma análise das relações entre actividade cerebral e experiência subjectiva, das teorias da consciência e dos limites da explicação neurocientífica. (148) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 17. A origem da vida: da química prebiótica às primeiras células

URL preservada: https://www.sussurrosdosaber.com/artigo/a-origem-da-vida-da-quimica-prebiotica-as-primeiras-celulas

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | A origem da vida: da química prebiótica às primeiras células (60) | A origem da vida: da química prebiótica às primeiras células (60) |
| Título HTML | A origem da vida: da química prebiótica às primeiras células — Sussurros do Saber (81) | A origem da vida: da química prebiótica às primeiras células (60) |
| Meta descrição | A origem da vida não é apenas o problema de sintetizar moléculas orgânicas: é compreender como a química adquiriu organização, hereditariedade e capacidade de evolução. (168) | Uma análise das hipóteses sobre a origem da vida: como a química pode ter adquirido organização, hereditariedade e capacidade de evolução. (138) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 18. Modelos de Linguagem de Grande Escala: como os LLM aprendem, raciocinam, erram e transformam a produção do conhecimento

URL preservada: https://www.sussurrosdosaber.com/artigo/modelos-de-linguagem-de-grande-escala-como-os-llm-aprendem-raciocinam-erram-e-transformam-a-producao-do-conhecimento

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Modelos de Linguagem de Grande Escala: como os LLM aprendem, raciocinam, erram e transformam a produção do conhecimento (119) | Modelos de linguagem: aprendizagem, raciocínio e limites (56) |
| Título HTML | Modelos de Linguagem de Grande Escala: como os LLM aprendem, raciocinam, erram e transformam a produção do conhecimento — Sussurros do Saber (140) | Modelos de linguagem: aprendizagem, raciocínio e limites (56) |
| Meta descrição | Os modelos de linguagem de grande escala (Large Language Models, LLM) constituem uma classe de redes neuronais treinadas em grandes colecções de texto para estimar a probabilidade de sequências linguísticas. (207) | Como os modelos de linguagem aprendem com grandes colecções de texto, quais as suas capacidades e onde surgem erros e limites de raciocínio. (140) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 19. Teoria do caos e efeito borboleta quando leis determinísticas produzem futuros imprevisíveis

URL preservada: https://www.sussurrosdosaber.com/artigo/teoria-do-caos-e-efeito-borboleta-quando-leis-deterministicas-produzem-futuros-imprevisiveis

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Teoria do caos e efeito borboleta quando leis determinísticas produzem futuros imprevisíveis (92) | Teoria do caos: determinismo e efeito borboleta (47) |
| Título HTML | Teoria do caos e efeito borboleta quando leis determinísticas produzem futuros imprevisíveis — Sussurros do Saber (113) | Teoria do caos: determinismo e efeito borboleta — Sussurros do Saber (68) |
| Meta descrição | A teoria do caos investiga sistemas dinâmicos determinísticos cujo comportamento a longo prazo pode tornar-se imprevisível devido à sensibilidade às condições iniciais. (168) | Como sistemas determinísticos podem tornar-se imprevisíveis a longo prazo devido à sensibilidade às condições iniciais, segundo a teoria do caos. (145) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 20. Nanopartículas biogénicas: como combatem micróbios

URL preservada: https://www.sussurrosdosaber.com/artigo/nanoparticulas-biogenicas-como-combatem-microbios

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Nanopartículas biogénicas: como combatem micróbios (50) | Nanopartículas biogénicas: como combatem micróbios (50) |
| Título HTML | Nanopartículas biogénicas: como combatem micróbios — Sussurros do Saber (71) | Nanopartículas biogénicas: como combatem micróbios (50) |
| Meta descrição | Plantas e microrganismos podem produzir nanopartículas antimicrobianas. Entenda os mecanismos, os testes, os riscos e os desafios da síntese verde. (147) | Plantas e microrganismos podem produzir nanopartículas antimicrobianas. Entenda os mecanismos, os testes, os riscos e os desafios da síntese verde. (147) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 21. Buracos negros: como se formam e quais são as suas propriedades

URL preservada: https://www.sussurrosdosaber.com/artigo/a-fronteira-onde-o-espaco-deixa-de-devolver-respostas

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Buracos negros: como se formam e quais são as suas propriedades (63) | Buracos negros: como se formam e quais são as suas propriedades (63) |
| Título HTML | Buracos negros: como se formam e quais são as suas propriedades — Sussurros do Saber (84) | Buracos negros: como se formam e quais são as suas propriedades (63) |
| Meta descrição | Descubra como se formam os buracos negros, o que são horizonte de eventos, singularidade, disco de acreção e ergosfera, e como a ciência os observa. (148) | Descubra como se formam os buracos negros, o que são horizonte de eventos, singularidade, disco de acreção e ergosfera, e como a ciência os observa. (148) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 22. Big Data e investigação científica: como os dados transformam a descoberta

URL preservada: https://www.sussurrosdosaber.com/artigo/quando-os-dados-se-tornam-telescopios-a-nova-escala-da-descoberta-cientifica

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Big Data e investigação científica: como os dados transformam a descoberta (74) | Big Data: como os dados transformam a investigação científica (61) |
| Título HTML | Big Data e investigação científica: como os dados transformam a descoberta — Sussurros do Saber (95) | Big Data: como os dados transformam a investigação científica (61) |
| Meta descrição | Entenda como o Big Data está a transformar a investigação científica, da genómica à astronomia, e conheça os desafios de qualidade, ética, desigualdade e reprodutibilidade. (172) | Como o Big Data apoia a investigação, da genómica à astronomia, e quais os desafios de qualidade, ética e reprodutibilidade dos dados. (134) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 23. Neuroplasticidade e aprendizagem: como o cérebro muda ao aprender

URL preservada: https://www.sussurrosdosaber.com/artigo/a-neuroplasticidade-explica-por-que-aprender-transforma-o-cerebro-mas-tambem-por-que-nao-existem-atalhos-magicos-para-o-conhecimento

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Neuroplasticidade e aprendizagem: como o cérebro muda ao aprender (65) | Neuroplasticidade e aprendizagem: como o cérebro muda ao aprender (65) |
| Título HTML | Neuroplasticidade e aprendizagem: como o cérebro muda ao aprender — Sussurros do Saber (86) | Neuroplasticidade e aprendizagem: como o cérebro muda ao aprender (65) |
| Meta descrição | Descubra como a neuroplasticidade modifica sinapses e circuitos durante a aprendizagem, o papel do sono e do exercício e as estratégias de estudo apoiadas pela ciência. (168) | Como a aprendizagem modifica sinapses e circuitos cerebrais, qual o papel do sono e do exercício e que estratégias de estudo têm apoio científico. (146) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 24. Python na investigação: da folha de cálculo à análise reprodutível

URL preservada: https://www.sussurrosdosaber.com/artigo/python-na-investigacao-da-folha-de-calculo-a-analise-reprodutivel

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Python na investigação: da folha de cálculo à análise reprodutível (66) | Python na investigação: da folha de cálculo à análise reprodutível (66) |
| Título HTML | Python na investigação: da folha de cálculo à análise reprodutível — Sussurros do Saber (87) | Python na investigação: da folha de cálculo à análise reprodutível (66) |
| Meta descrição | A folha de cálculo continuará a ser útil na investigação, sobretudo para observar tabelas, verificar pequenos conjuntos de dados e realizar cálculos rápidos. (157) | Como o Python apoia a investigação: tratamento de dados, automação de análises, documentação de decisões e reprodutibilidade dos resultados. (140) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 25. Como os radiotelescópios africanos observam o universo

URL preservada: https://www.sussurrosdosaber.com/artigo/como-os-radiotelescopios-africanos-observam-o-universo

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Como os radiotelescópios africanos observam o universo (54) | Como os radiotelescópios africanos observam o universo (54) |
| Título HTML | Como os radiotelescópios africanos observam o universo — Sussurros do Saber (75) | Como os radiotelescópios africanos observam o universo (54) |
| Meta descrição | Como antenas e processamento digital permitem aos radiotelescópios africanos estudar o céu, e o que distingue o MeerKAT do projecto SKA-Mid. (140) | Como antenas e processamento digital permitem aos radiotelescópios africanos estudar o céu, e o que distingue o MeerKAT do projecto SKA-Mid. (140) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 26. Plantas medicinais de Nampula e o futuro da investigação local

URL preservada: https://www.sussurrosdosaber.com/artigo/plantas-medicinais-de-nampula-e-o-futuro-da-investigacao-local

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Plantas medicinais de Nampula e o futuro da investigação local (62) | Plantas medicinais de Nampula e o futuro da investigação local (62) |
| Título HTML | Plantas medicinais de Nampula e o futuro da investigação local — Sussurros do Saber (83) | Plantas medicinais de Nampula e o futuro da investigação local (62) |
| Meta descrição | O que sabemos sobre plantas medicinais de Nampula? Estudos etnobotânicos, fitoquímica, segurança, conservação e oportunidades para a investigação científica local. (163) | Plantas medicinais de Nampula: evidências etnobotânicas, fitoquímica, segurança, conservação e oportunidades para a investigação local. (135) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

### 27. Bactérias endofíticas: os microrganismos invisíveis que protegem as plantas

URL preservada: https://www.sussurrosdosaber.com/artigo/bacterias-endofiticas-os-microrganismos-invisiveis-que-protegem-as-plantas

| Campo | Valor observado | Valor proposto |
| --- | --- | --- |
| Título principal | Bactérias endofíticas: os microrganismos invisíveis que protegem as plantas (75) | Bactérias endofíticas: como podem proteger as plantas (53) |
| Título HTML | Bactérias endofíticas: os microrganismos invisíveis que protegem as plantas — Sussurros do Saber (96) | Bactérias endofíticas: como podem proteger as plantas (53) |
| Meta descrição | Dentro das plantas vivem comunidades capazes de produzir compostos com potencial antibacteriano. (96) | Dentro das plantas vivem comunidades capazes de produzir compostos com potencial antibacteriano. (96) |

Estado: proposta sem aplicação. Não foram observados H1 adicionais ou saltos ascendentes de nível.

## Execução e recuperação

A base de dados de produção não está acessível nesta sessão. O relatório público não substitui a cópia dos registos. Usar `scripts/article_seo.py audit --include-content` no servidor, confrontar as propostas com os dados actuais e gerar o plano por slug com `plan-editorial`. Os planos não ficam automaticamente marcados como revistos. Confirmar a fidelidade ao artigo antes de `apply`. A cópia criada por `apply` contém os valores anteriores, diferenças e contagens, e permite `restore`; ambos registam versões no histórico existente.

Os problemas estruturais confirmados devem ser confrontados com o Markdown original. `plan-structure` apenas propõe ajustes ATX simples e preserva casos ambíguos para revisão manual; não reescreve prosa. O histórico e os mecanismos existentes do painel continuam a ser a fonte de edição.

As páginas públicas foram verificadas no navegador antes das alterações. A edição e a correspondência entre formulário, página pública e histórico foram testadas numa base temporária; não foi verificada uma sessão editorial de produção. PostgreSQL e a inspecção visual de todas as imagens permanecem pendentes. Após a aplicação, repetir a auditoria, `verify` e a verificação no navegador/painel.

Os critérios de comprimento não garantem a apresentação dos resultados ou a posição no Google.
