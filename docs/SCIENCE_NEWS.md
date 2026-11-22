# Notícias de Ciência

A lista pública está em `/noticias` e `/en/news`. As notícias individuais usam `/noticias/<identificador>` e `/en/news/<identificador>`. Identificadores diferentes em cada idioma são associados pelo número interno da notícia. O menu principal, o selector de idioma e as preferências do portal aplicam-se às duas versões.

A página inicial mostra as três publicações mais recentes do idioma activo, quando existirem. Na lista geral, a escolha editorial aparece na primeira página em destaque. Se estiver vazia, a publicação mais recente ocupa esse lugar. Os filtros mostram a lista cronológica do tema, incluindo o destaque quando pertence ao tema. `tema` e `page` permitem regressar da notícia à mesma lista.

## Redacção

1. Abra **Notícias de Ciência** no painel e guarde um rascunho. Seleccione a autoria e um tema da taxonomia. Use a opção **Investigação feita em África** quando a notícia tratar de investigação efectivamente conduzida no continente.
2. Escreva um resumo que identifique o acontecimento. Registe pelo menos uma fonte primária em HTTPS. Use uma ligação por linha, com o formato opcional `Título | URL`. Verifique a situação da revisão por pares na fonte. Ao assinalar evidência preliminar, pré-publicação ou revisão por confirmar, explique as limitações ou o que está por verificar.
3. A coordenação atribui a revisão. O revisor designado regista o parecer. O editor aprova e um responsável com permissão de publicação publica. A conta principal mantém a opção de publicação directa, sujeita aos mesmos campos obrigatórios. Cada acção regista auditoria.
4. No registo, use **Criar versão em inglês** ou **Criar versão em português** para ligar a outra versão. Publique cada versão quando estiver pronta. Para um tema personalizado, publique primeiro a tradução do nome do tema em **Internacionalização**. A capa pode ser uma ligação HTTPS ou uma imagem enviada pelo mecanismo Cloudinary do portal. Preencha o texto alternativo e o crédito quando aplicável.
5. Numa versão publicada, o responsável pela publicação pode actualizar o texto, alterar o destaque desse idioma ou retirar a versão. Uma edição relevante assinala a data de actualização. O destaque passa a outra versão elegível conforme a regra de recência.

Ao preparar a agenda editorial, reserve em cada semana editorial espaço para investigação realizada em África. Atribua o trabalho a partir de revistas, universidades, institutos e repositórios e confirme os dados na publicação primária. Nenhuma notícia é criada automaticamente. O Radar ainda não tem rotas nem modelos no repositório. Até estar disponível, o campo **Artigo relacionado** permite indicar um artigo do portal. Uma ligação inglesa exige que a respectiva tradução pública exista.

## Implantação para aprovação

1. Use uma cópia da base para o ensaio. Faça uma cópia de segurança e confirme que a revisão anterior é `20261102_20`.
2. Na versão a lançar e com o `DATABASE_URL` correcto, execute `python -m alembic upgrade head` e confirme `20261122_21 (head)` com `python -m alembic current`. A migração acrescenta as tabelas `news_story` e `news_version`, com índices e restrições, sem preencher a base com notícias de demonstração.
3. Compile as folhas de estilo com `npm ci` e `npm run build:css`. A imagem Docker do portal já executa a compilação.
4. Depois da aprovação, coloque o serviço em execução e confirme as listas, o painel e o sitemap. Na camada de distribuição, respeite o `no-store` das páginas de Notícias e da página inicial e a revalidação do sitemap. Verifique com exemplos autorizados, incluindo uma retirada e uma tradução em rascunho.
5. Para reverter a aplicação, volte à imagem anterior e preserve as tabelas. A migração recusa um downgrade que apague conteúdo editorial.

Para reproduzir a validação isolada, execute `python -m unittest discover -s tests -p 'test_science_news.py'`. Os testes Playwright em `tests/browser/science-news.spec.js` usam o servidor de testes e dados sintéticos locais.
