# Ícones do Sussurros do Saber

O projecto usa Flask e modelos Jinja, com Tailwind para os estilos; não usa React ou Vite. Antes desta alteração, três modelos referenciavam apenas `static/img/favicon.png`, equivalente ao PNG de 16 × 16 fornecido. Não havia manifesto nem registo de service worker no repositório analisado.

## Ficheiros recebidos e utilizados

| Ficheiro | Formato e dimensões | Destino |
| --- | --- | --- |
| favicon-16x16.png | PNG RGBA, 16 × 16 | static/icons/favicon-16x16.png |
| favicon-32x32.png | PNG RGBA, 32 × 32 | static/icons/favicon-32x32.png |
| apple-touch-icon.png | PNG RGBA, 180 × 180 | static/icons/apple-touch-icon.png |
| android-chrome-192x192.png | PNG RGBA, 192 × 192 | static/icons/android-chrome-192x192.png |
| android-chrome-512x512.png | PNG RGBA, 512 × 512 | static/icons/android-chrome-512x512.png |
| site.webmanifest | JSON válido | static/site.webmanifest, com configuração corrigida |

Os cinco PNG foram copiados sem conversão, redimensionamento ou alteração dos bytes. Todos são quadrados. Não foram fornecidos ICO ou SVG; não existem referências a esses formatos. O antigo `static/img/favicon.png` continua disponível para ligações antigas, mas os modelos passam a usar a configuração partilhada.

## Implementação

`templates/partials/site_icons.html` contém duas referências PNG com dimensões explícitas, uma referência Apple Touch Icon e uma referência ao manifesto. É incluído em `templates/base.html`, `templates/admin/base.html`, `templates/submissions/base.html`, `templates/admin/login.html` e `templates/admin/verify_2fa.html`. Estes são os documentos HTML do site; o modelo de correio electrónico não recebe favicons.

O manifesto fornecido tinha nomes vazios e caminhos na raiz sem ficheiros correspondentes. Foram definidos `name`, `short_name`, `start_url` e `scope`, e corrigidos os caminhos relativos à localização pública `/static/site.webmanifest`. Os ícones Android declaram `purpose: any`: os ficheiros não são apresentados como ícones maskable sem desenho e validação próprios.

Como não existia uma aplicação instalada configurada, `display: browser` conserva a abertura normal no navegador. Não foram introduzidos modo standalone, service worker, funcionamento offline ou pedidos de instalação. O manifesto fornece identidade e ícones; não constitui uma certificação de PWA instalável.

## Cache

As ligações HTML reutilizam `url_for('static', ...)` e o mecanismo existente de versão SHA-256 do conteúdo. As ligações dos ícones dentro do manifesto também incluem a versão correspondente. Os testes confirmam cache de um ano com `immutable` apenas para a versão correcta; URLs sem versão ou com uma versão antiga exigem revalidação. O manifesto sem versão também exige revalidação. Não foi necessário alterar as regras globais do servidor.

Se um PNG Android for substituído futuramente, actualizar o parâmetro `v` da respectiva entrada no manifesto com os primeiros 16 caracteres do SHA-256 do novo ficheiro. Essa alteração modifica também a versão do manifesto referenciada no HTML.

## Validação e limites

Os testes em `tests/test_site_icons.py` verificam páginas públicas, entrada administrativa e entrada de submissões, ausência de referências duplicadas, dimensões reais, tipos MIME, HTTP 200, caminhos relativos do manifesto e políticas de cache. Os cinco ficheiros foram comparados byte a byte com os originais. A sintaxe do teste JavaScript foi validada com `node --check`.

`tests/browser/site-icons.spec.js` acrescenta verificações Playwright para larguras de 1440 e 390 píxeis: descodificação dos PNG pelo navegador e acesso ao manifesto e aos ícones Android. A execução deste teste depende do CI; uma largura móvel não equivale a um teste num dispositivo físico. Consultar os resultados do PR para a execução completa.

Não foram testados directamente Windows, Linux, macOS, Firefox, Edge, Safari, Android ou iOS como plataformas de utilização final. O teste HTTP local não demonstra a apresentação do ícone no separador ou num atalho instalado.

Após integrar e publicar a alteração:

1. Abrir a página em Chrome, Firefox, Edge e Safari disponíveis; verificar o ícone do separador e dos favoritos. No painel de rede, confirmar HTTP 200 e ausência de referências antigas no HTML.
2. Em Android, abrir o site e usar a opção de adicionar ao ecrã principal disponível no navegador. Confirmar o símbolo, o nome e a abertura do atalho.
3. Em iPhone ou iPad, abrir no Safari e usar Partilhar → Adicionar ao ecrã principal; confirmar o Apple Touch Icon. Remover e criar novamente um atalho antigo se continuar a apresentar o ícone anterior.
4. Em Chrome/Edge, inspeccionar o manifesto nas ferramentas de desenvolvimento. Confirmar que os dois ícones são carregados. Não pressupor que surgirá um pedido de instalação PWA.
5. Se um ícone antigo persistir, testar uma nova janela privada ou novo perfil e limpar apenas os dados/cache desse site quando necessário. Favicons e atalhos existentes podem ter cache própria do navegador ou do sistema.

Referências técnicas: [Web App Manifest, W3C](https://www.w3.org/TR/appmanifest/) e [Configuring Web Applications, Apple](https://developer.apple.com/library/archive/documentation/AppleApplications/Reference/SafariWebContent/ConfiguringWebApplications/ConfiguringWebApplications.html).
