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
    if (!payload || typeof payload !== "object" || Array.isArray(payload) || typeof payload.message !== "string") {
      return json({ ok: false, answer: "Invalid question." }, 400);
    }
    const english = payload.language === "en";
    const reply = (pt, en) => english ? en : pt;
    const message = payload.message.trim();
    if (!message || message.length > 800) return json({ ok: false, answer: reply("A pergunta deve ter entre 1 e 800 caracteres.", "The question must contain between 1 and 800 characters.") }, 400);

    try {
      const result = await env.AI.run("@cf/meta/llama-3.1-8b-instruct-fast", {
        messages: [
          { role: "system", content: english ? "You are the science assistant for Sussurros do Saber. Respond in clear English with scientific accuracy. Do not invent sources. For health, safety or high-risk topics, explain the limits of your answer and recommend professional support. Be concise." : "És o assistente científico do Sussurros do Saber. Responde em português claro, com rigor, sem inventar fontes. Em saúde, segurança ou temas de alto risco, informa os limites da resposta e recomenda apoio profissional. Sê conciso." },
          { role: "user", content: message },
        ],
        max_tokens: 500,
      });
      const answer = result.response || result.result?.response;
      return json({ ok: true, answer: answer || reply("Não consegui produzir uma resposta.", "I could not produce an answer."), links: [] });
    } catch {
      return json({ ok: false, answer: reply("O modelo está temporariamente indisponível.", "The model is temporarily unavailable."), links: [] }, 502);
    }
  },
};
