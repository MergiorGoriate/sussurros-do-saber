# Correcções de integridade do site

A gravação manual de artigos e revistas e a gravação automática de rascunhos preservam a indentação e os espaços finais dos campos Markdown. Metadados como título e DOI continuam a ser normalizados. A validação do conteúdo mínimo para publicação considera o texto sem espaços exteriores, para impedir que espaços preencham o mínimo exigido.

As páginas de artigos, perfis de autores, submissões e notificações tratam números de página inválidos ou superiores a 2 147 483 647 como a primeira página. Os parâmetros numéricos das rotas são limitados ao intervalo positivo dos identificadores INTEGER usados pelo esquema; valores impossíveis devolvem 404 antes de consultar a base de dados. Acções de notificações também verificam o identificador recebido pelo formulário. A paginação da caixa de notificações administrativas mantém a sua validação e redireccionamento já existentes.

Os testes verificam preservação de Markdown no histórico, gravação manual e automática, formulários de revistas, paginação pública e autenticada, limites de identificadores e navegação no navegador. A CI executa os testes de integridade em SQLite e PostgreSQL.

Não há migrações. As correcções preservam novos conteúdos guardados; não recuperam automaticamente espaços removidos por gravações anteriores. A validação em produção exige verificar a gravação no painel após publicar a versão.
