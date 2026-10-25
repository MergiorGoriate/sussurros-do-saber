(() => {
  const style = document.createElement("style");
  style.textContent = `.assistant-launcher{position:fixed;right:22px;bottom:22px;z-index:80;width:58px;height:58px;border:0;border-radius:20px 20px 20px 6px;background:linear-gradient(145deg,#3269a9,#12345e);color:#fff;font-size:25px;box-shadow:0 15px 38px rgba(30,78,140,.38)}.assistant-window{position:fixed;right:22px;bottom:94px;z-index:80;width:min(390px,calc(100vw - 24px));height:min(590px,calc(100vh - 125px));display:none;flex-direction:column;border:1px solid var(--line);border-radius:24px;background:#fff;color:#101820;box-shadow:0 25px 70px rgba(0,0,0,.22);overflow:hidden}.dark .assistant-window{background:#101c1f;color:#eef7f6}.assistant-window.open{display:flex}.assistant-head{padding:16px 18px;background:linear-gradient(135deg,#1e4e8c,#153967);color:#fff;display:flex;align-items:center;gap:12px}.assistant-avatar{width:40px;height:40px;flex:0 0 40px;padding:4px;display:grid;place-items:center;border-radius:13px;background:#fff}.assistant-avatar img{display:block;width:100%;height:100%;object-fit:contain}.assistant-head strong{display:block}.assistant-head small{opacity:.72}.assistant-close{margin-left:auto;font-size:22px}.assistant-messages{flex:1;padding:16px;overflow:auto;background:linear-gradient(180deg,rgba(30,78,140,.035),transparent)}.assistant-message{max-width:85%;padding:11px 13px;border-radius:15px;margin-bottom:10px;font-size:14px;line-height:1.5}.assistant-message.bot{background:#eef6f5;border-bottom-left-radius:4px}.dark .assistant-message.bot{background:#183033}.assistant-message.user{margin-left:auto;background:#1e4e8c;color:#fff;border-bottom-right-radius:4px}.assistant-links{display:flex;flex-wrap:wrap;gap:6px;margin:0 0 12px}.assistant-links a,.assistant-chip{font-size:12px;padding:7px 10px;border:1px solid rgba(30,78,140,.35);border-radius:999px;color:#1e4e8c;background:transparent}.dark .assistant-links a,.dark .assistant-chip{color:#a8ccf7}.assistant-suggestions{display:flex;gap:6px;padding:0 12px 10px;overflow-x:auto}.assistant-form{display:flex;border-top:1px solid var(--line);padding:10px;gap:7px}.assistant-form input{flex:1;min-width:0;border:1px solid var(--line);border-radius:12px;padding:11px;background:transparent;outline:none}.assistant-form button{width:44px;border-radius:12px;background:#1e4e8c;color:#fff}.assistant-typing{opacity:.6;font-size:13px;padding:4px 13px}@media(max-width:500px){.assistant-window{right:12px;bottom:82px}.assistant-launcher{right:14px;bottom:14px}}`;
  document.head.appendChild(style);

  const root = document.createElement("div");
  root.innerHTML = `<button class="assistant-launcher" aria-label="Abrir assistente" aria-expanded="false" aria-controls="assistantWindow">✦</button><section id="assistantWindow" class="assistant-window" role="dialog" aria-modal="true" aria-label="Assistente Sussurros"><header class="assistant-head"><span class="assistant-avatar" aria-hidden="true"><img src="/static/img/logo-sussurros-icon.png" alt="" width="32" height="32" decoding="async"></span><span><strong>Assistente Sussurros</strong><small>Ciência e aprendizagem</small></span><button class="assistant-close" aria-label="Fechar assistente">×</button></header><div class="assistant-messages" aria-live="polite"><div class="assistant-message bot">Olá! Posso ajudar com Biologia, estatística, referências APA, Python ou encontrar conteúdos no portal.</div></div><div class="assistant-suggestions"><button class="assistant-chip">O que são endófitos?</button><button class="assistant-chip">Como calcular a média?</button><button class="assistant-chip">Ajuda com APA</button></div><form class="assistant-form"><input maxlength="400" autocomplete="off" placeholder="Escreva a sua pergunta..." aria-label="Mensagem"><button aria-label="Enviar pergunta">➜</button></form></section>`;
  document.body.appendChild(root);
  const win = root.querySelector(".assistant-window"),
    messages = root.querySelector(".assistant-messages"),
    input = root.querySelector("input");
  const launcher = root.querySelector(".assistant-launcher");
  const toggle = (force) => {
    const open = typeof force === "boolean" ? force : !win.classList.contains("open");
    win.classList.toggle("open", open);
    document.body.classList.toggle("assistant-open", open);
    launcher.setAttribute("aria-expanded", String(open));
    if (open) input.focus(); else launcher.focus();
  };
  launcher.onclick = () => toggle();
  root.querySelector(".assistant-close").onclick = () => toggle(false);
  win.addEventListener("keydown", (event) => {
    if (event.key === "Escape") return toggle(false);
    if (event.key !== "Tab") return;
    const controls = [...win.querySelectorAll('button,input,a[href]')].filter((el) => !el.disabled);
    const first = controls[0], last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  });
  const add = (text, type) => {
    const el = document.createElement("div");
    el.className = `assistant-message ${type}`;
    el.style.whiteSpace = "pre-wrap";
    el.textContent = String(text || "").replace(/\*\*/g, "");
    messages.appendChild(el);
    messages.scrollTop = messages.scrollHeight;
  };
  async function ask(message) {
    if (!message.trim()) return;
    add(message, "user");
    input.value = "";
    const typing = document.createElement("div");
    typing.className = "assistant-typing";
    typing.textContent = "A preparar resposta…";
    messages.appendChild(typing);
    try {
      const r = await fetch("/api/assistente", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message }),
        }),
        data = await r.json();
      if (!r.ok) throw new Error(data.answer || "Erro do assistente");
      typing.remove();
      add(data.answer, "bot");
      if (data.links?.length) {
        const links = document.createElement("div");
        links.className = "assistant-links";
        data.links.forEach((item) => {
          try {
            const url = new URL(item.url, location.origin);
            if (!['http:', 'https:'].includes(url.protocol)) return;
            const link = document.createElement('a');
            link.href = url.href;
            link.textContent = `${String(item.label || 'Consultar')} →`;
            if (url.origin !== location.origin) { link.target = '_blank'; link.rel = 'noopener noreferrer'; }
            links.appendChild(link);
          } catch {}
        });
        messages.appendChild(links);
      }
    } catch {
      typing.remove();
      add("Não foi possível responder agora. Tente novamente.", "bot");
    }
  }
  root.querySelector("form").onsubmit = (e) => {
    e.preventDefault();
    ask(input.value);
  };
  root
    .querySelectorAll(".assistant-chip")
    .forEach((b) => (b.onclick = () => ask(b.textContent)));
})();
