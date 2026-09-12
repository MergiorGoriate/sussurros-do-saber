const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status,
  headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store" },
});

export default {
  async fetch(request, env) {
    if (request.method !== "POST") return json({ ok: false, answer: "Método não permitido." }, 405);
    if (!env.ASSISTANT_SHARED_KEY || request.headers.get("X-Assistant-Key") !== env.ASSISTANT_SHARED_KEY) {
      return json({ ok: false, answer: "Não autorizado." }, 401);
    }
    let payload;
    try { payload = await request.json(); } catch { return json({ ok: false, answer: "Pedido inválido." }, 400); }
    const message = String(payload.message || "").trim();
    if (!message || message.length > 800) return json({ ok: false, answer: "A pergunta deve ter entre 1 e 800 caracteres." }, 400);

    try {
      const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct-fast", {
        messages: [
          { role: "system", content: "És o assistente científico do Sussurros do Saber. Responde em português claro, com rigor, sem inventar fontes. Em saúde, segurança ou temas de alto risco, informa os limites da resposta e recomenda apoio profissional. Sê conciso." },
          { role: "user", content: message },
        ],
        max_tokens: 500,
      });
      const answer = result.response || result.result?.response;
      return json({ ok: true, answer: answer || "Não consegui produzir uma resposta.", links: [] });
    } catch {
      return json({ ok: false, answer: "O modelo está temporariamente indisponível.", links: [] }, 502);
    }
  },
};

