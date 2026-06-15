/* ============================================================
   assistant.js — grounded chat. Renders answer, FIR citations,
   "View on map" when a filter is returned, and a mode tag.
   ============================================================ */
Views.Assistant = (() => {
  let el, mounted = false;
  const sessionId = "sess-" + Math.random().toString(36).slice(2, 9);

  const SUGGESTIONS = [
    "Vehicle thefts in Bengaluru last month",
    "Cyber fraud trend",
    "Burglaries after 9pm",
    "Show violent crime in Mysuru",
  ];

  function shell() {
    return `
      <div class="view-head" style="margin-bottom:12px">
        <div>
          <h1 class="view-title"><span class="vt-ico">✦</span> DRISHTI Assistant</h1>
          <div class="view-sub">A grounded analyst. Every answer is drawn only from cited FIRs — it refuses to speculate beyond the data.</div>
        </div>
      </div>

      <div class="chat-shell">
        <div class="chat-log" id="chat-log"></div>
        <div>
          <div class="chat-input-row">
            <input type="text" id="chat-input" placeholder="Ask about crimes, districts, trends, time-of-day…" autocomplete="off"/>
            <button class="btn btn-primary" id="chat-send">Send ➤</button>
          </div>
          <div class="suggest-row" id="chat-suggest">
            ${SUGGESTIONS.map((s) => `<span class="chip" data-q="${UI.esc(s)}">${UI.esc(s)}</span>`).join("")}
          </div>
        </div>
      </div>`;
  }

  // minimal **bold** markdown -> <b>
  function md(t) {
    return UI.esc(t).replace(/\*\*(.+?)\*\*/g, "<b>$1</b>").replace(/\n/g, "<br/>");
  }

  function pushUser(text) {
    const log = document.getElementById("chat-log");
    log.insertAdjacentHTML("beforeend",
      `<div class="msg user"><div class="avatar">🧑</div><div class="bubble">${UI.esc(text)}</div></div>`);
    log.scrollTop = log.scrollHeight;
  }

  function pushTyping() {
    const log = document.getElementById("chat-log");
    const id = "typing-" + Date.now();
    log.insertAdjacentHTML("beforeend",
      `<div class="msg bot" id="${id}"><div class="avatar">✦</div><div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>`);
    log.scrollTop = log.scrollHeight;
    return id;
  }

  function pushBot(resp) {
    const log = document.getElementById("chat-log");
    const citations = resp.citations || [];
    const filter = resp.filter || {};
    const hasFilter = filter && Object.values(filter).some((v) => v != null && v !== "");
    const mode = resp.mode || "extractive-free";
    const modeFree = mode === "extractive-free";

    const citHTML = citations.length
      ? `<div class="bubble-meta">${citations.slice(0, 16).map((f) => `<span class="chip fir" data-fir="${UI.esc(f)}">FIR ${UI.esc(f)}</span>`).join("")}${citations.length > 16 ? `<span class="faint">+${citations.length - 16} more</span>` : ""}</div>`
      : "";

    const filterChips = hasFilter
      ? Object.entries(filter).filter(([, v]) => v != null && v !== "").map(([k, v]) => `<span class="chip term">${UI.esc(k)}: ${UI.esc(v)}</span>`).join("")
      : "";

    const actions = `<div class="bubble-meta">
        <span class="mode-tag ${modeFree ? "free" : "paid"}">${modeFree ? "extractive · free" : UI.esc(mode)}</span>
        ${resp.grounded ? `<span class="mode-tag free">grounded</span>` : ""}
        ${filterChips}
        ${hasFilter ? `<button class="btn btn-teal sm" id="vm-${Date.now()}" data-filter='${UI.esc(JSON.stringify(filter))}'>🗺 View on map</button>` : ""}
      </div>`;

    log.insertAdjacentHTML("beforeend",
      `<div class="msg bot"><div class="avatar">✦</div><div class="bubble">${md(resp.answer || "No answer returned.")}${citHTML}${actions}</div></div>`);
    log.scrollTop = log.scrollHeight;

    // bind view-on-map
    log.querySelectorAll("[data-filter]").forEach((b) => {
      if (b.dataset.bound) return; b.dataset.bound = "1";
      b.addEventListener("click", () => {
        try { App.goWithFilter("hotspots", JSON.parse(b.dataset.filter)); } catch (_) {}
      });
    });
  }

  async function send(text) {
    const input = document.getElementById("chat-input");
    const q = (text ?? input.value).trim();
    if (!q) return;
    input.value = "";
    pushUser(q);
    const typingId = pushTyping();
    try {
      const resp = await API.post("/assistant/chat", { message: q, session_id: sessionId });
      document.getElementById(typingId)?.remove();
      pushBot(resp);
    } catch (_) {
      document.getElementById(typingId)?.remove();
      pushBot({ answer: "I could not reach the intelligence core. Please ensure the backend is running, then retry.", citations: [], filter: {}, grounded: false, mode: "extractive-free" });
    }
  }

  function welcome() {
    pushBot({
      answer: "Hello — I am the **DRISHTI** analyst. Ask me about crime patterns, districts, time-of-day, or trends. I answer **only** from authorised FIRs and cite every record. Try one of the suggestions below.",
      citations: [], filter: {}, grounded: true, mode: "extractive-free",
    });
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("chat-send").addEventListener("click", () => send());
    document.getElementById("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter") send(); });
    document.querySelectorAll("#chat-suggest .chip").forEach((c) =>
      c.addEventListener("click", () => send(c.dataset.q)));
    welcome();
    mounted = true;
  }

  return { mount };
})();
