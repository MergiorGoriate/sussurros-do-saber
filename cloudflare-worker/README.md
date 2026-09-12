# Worker do assistente

1. No Cloudflare, abra o Worker `assistente-sussurros` e substitua o código por `worker.js`.
2. Em **Bindings**, mantenha Workers AI com o nome `AI`.
3. Em **Settings → Variables and Secrets**, crie o segredo `ASSISTANT_SHARED_KEY`.
4. No Render, crie `ASSISTANT_SHARED_KEY` com exactamente o mesmo valor.
5. Faça o deploy do Worker e depois um novo deploy do serviço no Render.

O navegador não acede directamente ao Worker: ele chama `/api/assistente` no Flask. O Flask aplica limites de utilização e autentica-se no Worker pelo segredo partilhado.
