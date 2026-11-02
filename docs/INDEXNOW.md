# Notificações IndexNow

As publicações, actualizações, mudanças de slug e retiradas de artigos do portal
e periódicos públicos geram notificações no mesmo commit da base de dados.
Rascunhos, agendamentos futuros e alterações revertidas não são enviados.
O arranque importa o modelo da fila antes de `db.create_all()`, mas instala os
observadores depois da inicialização dos conteúdos, sem reenviar o arquivo.

O serviço está activo por defeito (`INDEXNOW_ENABLED=true`). Usa a origem
canónica `SITE_URL`, incluindo `www`, e a chave do ficheiro de verificação.
O ficheiro deve continuar acessível nessa mesma origem, sem autenticação.
`INDEXNOW_ENABLED=false` desliga a recolha e o envio, sem apagar a fila.
Com `AUTO_SCHEMA_UPGRADE=false`, executar `alembic upgrade head` antes de
iniciar a nova versão. A migração é idempotente se a tabela já existir.

Os envios HTTP decorrem numa thread separada, depois do commit. Os pedidos
seguintes retomam a fila, no máximo uma vez a cada 30 segundos por processo;
as verificações de saúde e os pedidos da chave não iniciam trabalhadores.
Uma falha de rede conserva os registos e agenda novas tentativas com espera
crescente, até 24 horas. O estado HTTP e a última falha ficam na tabela
`index_now_notification`. Os códigos 200 e 202 indicam recepção; o código 202
significa que a validação da chave ainda está pendente. Nenhum confirma indexação.

Para garantir retentativas mesmo sem tráfego, pode executar no Coolify, a cada
minuto, `flask --app app processar-indexnow`. O comando entrega até 100 registos
vencidos por execução. Em PostgreSQL, os trabalhadores usam bloqueio de linhas
com `SKIP LOCKED`, permitindo execução simultânea sem reservar o mesmo lote.
Uma interrupção após a recepção pode provocar um reenvio, que é inofensivo.

Esta integração cobre as páginas originais de artigos e periódicos. As páginas
inglesas, perfis de autores e páginas institucionais continuam descobertas pelo
sitemap; as suas alterações independentes não geram notificações nesta versão.
Manter o sitemap e a configuração dos motores de pesquisa existentes.

Documentação do protocolo: https://www.indexnow.org/documentation
