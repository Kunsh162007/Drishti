/* ============================================================
   cdr.js — Call Detail Record analysis: top contacts, common
   towers, co-location leads, ego call-network (sigma), and a
   tower-dump tool. Lawful-interception use only.
   ============================================================ */
Views.CDR = (() => {
  let el, graph, renderer, mounted = false;

  const TYPE_COLOR = { phone: "#2ba6bd", target: "#C9A227" };

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">☎</span> CDR Analysis</h1>
          <div class="view-sub">Call-pattern intelligence — top contacts, shared cell towers, co-location leads, and ego call-networks from authorised records.</div>
        </div>
      </div>

      <div class="banner warn">
        <span class="b-ico">🔒</span>
        <div><b>Lawful interception — authorised use only.</b> Call Detail Records are accessed strictly under a competent authority's order. Co-location is an <b>investigative lead</b>, not proof of association.</div>
      </div>

      <div class="panel panel-pad" style="margin-bottom:18px">
        <div class="row wrap" style="justify-content:space-between">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Subscriber lookup</h3>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Phone (MSISDN)</span>
              <input type="search" id="cdr-msisdn" placeholder="e.g. 9876543210" style="min-width:190px"/>
            </div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary sm" id="cdr-go">Analyse</button></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-teal sm" id="cdr-net">⚇ Show call network</button></div>
          </div>
        </div>
      </div>

      <div id="cdr-summary"></div>

      <div class="grid" style="grid-template-columns:1fr 1fr;gap:18px">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Top contacts</h3>
          <div class="tbl-wrap scroll" style="max-height:360px" id="cdr-contacts">${UI.empty("Enter a number", "Look up a subscriber to list their frequent contacts.", "☎")}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Common towers</h3>
          <div class="tbl-wrap scroll" style="max-height:360px" id="cdr-towers">${UI.empty("Enter a number", "Cell towers this subscriber frequently connects through.", "⌖")}</div>
        </div>
      </div>

      <div class="panel panel-pad" style="margin-top:18px">
        <h3 class="panel-title"><span class="dotaccent"></span> Co-location matches <span class="faint" style="margin-left:8px;font-weight:600;text-transform:none;letter-spacing:0">— numbers seen at the same towers in the same windows (investigative leads)</span></h3>
        <div class="tbl-wrap scroll" style="max-height:300px" id="cdr-coloc">${UI.empty("Enter a number", "Co-location leads will appear here.", "⌖")}</div>
      </div>

      <div class="panel panel-pad" id="cdr-net-panel" style="margin-top:18px;display:none">
        <h3 class="panel-title"><span class="dotaccent"></span> Call network — ego graph</h3>
        <div class="map-shell" style="height:440px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)">
          <div id="cdr-sigma" style="position:absolute;inset:0"></div>
          <div class="map-overlay map-side" style="top:14px;right:14px;width:230px;bottom:14px">
            <div class="panel panel-pad" style="background:rgba(11,31,58,.82);backdrop-filter:blur(14px)">
              <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> Legend</h3>
              <div class="legend">
                <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.target}"></span>Target number</div>
                <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.phone}"></span>Contact</div>
              </div>
              <div class="faint mt12" id="cdr-net-stats" style="font-size:11px"></div>
            </div>
          </div>
        </div>
      </div>

      <div class="panel panel-pad" style="margin-top:18px">
        <div class="row wrap" style="justify-content:space-between">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Tower-dump tool</h3>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Tower id</span>
              <input type="search" id="cdr-tower" placeholder="e.g. TWR-0421" style="min-width:170px"/>
            </div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary sm" id="cdr-dump">Dump tower</button></div>
          </div>
        </div>
        <div class="dim mb12" style="font-size:11.5px;margin-top:8px">Lists every number active on a given tower — used to scope suspects near a scene at a given time.</div>
        <div class="tbl-wrap scroll" style="max-height:340px" id="cdr-dump-out">${UI.empty("Enter a tower id", "Active numbers on the selected tower will appear here.", "⌖")}</div>
      </div>`;
  }

  function renderSummary(d) {
    const host = document.getElementById("cdr-summary");
    if (!d) { host.innerHTML = ""; return; }
    host.innerHTML = `
      <div class="grid kpi-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:18px">
        <div class="kpi accent-gold"><div class="kpi-label">Subscriber</div><div class="kpi-value" style="font-size:22px">${UI.esc(UI.val(d.msisdn))}</div><div class="kpi-foot">MSISDN under analysis</div></div>
        <div class="kpi accent-teal"><div class="kpi-label">Total calls</div><div class="kpi-value">${UI.num(d.total_calls)}</div><div class="kpi-foot">In the available window</div></div>
        <div class="kpi"><div class="kpi-label">Co-location leads</div><div class="kpi-value">${UI.num((d.co_location || []).length)}</div><div class="kpi-foot">Numbers sharing towers</div></div>
      </div>`;
  }

  function renderContacts(rows) {
    const host = document.getElementById("cdr-contacts");
    if (!rows || !rows.length) { host.innerHTML = UI.empty("No contacts", "No frequent contacts found.", "☎"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>Number</th><th>Calls</th><th>Duration</th></tr></thead><tbody>${
      rows.map((c) => `<tr>
        <td class="mono">${UI.esc(UI.val(c.number))}</td>
        <td>${UI.num(c.count)}</td>
        <td class="dim">${fmtSecs(c.total_seconds)}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  function renderTowers(rows) {
    const host = document.getElementById("cdr-towers");
    if (!rows || !rows.length) { host.innerHTML = UI.empty("No towers", "No common towers found.", "⌖"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>Tower</th><th>Hits</th></tr></thead><tbody>${
      rows.map((t) => `<tr>
        <td class="mono">${UI.esc(UI.val(t.tower))}</td>
        <td>${UI.num(t.count)}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  function renderColoc(rows) {
    const host = document.getElementById("cdr-coloc");
    if (!rows || !rows.length) { host.innerHTML = UI.empty("No co-location leads", "No other number shared towers in matching windows.", "✓"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>Number</th><th>Shared towers</th><th>Shared windows</th><th></th></tr></thead><tbody>${
      rows.map((c) => `<tr style="background:rgba(230,147,47,.06)">
        <td class="mono"><b>${UI.esc(UI.val(c.number))}</b></td>
        <td>${UI.num(c.shared_towers)}</td>
        <td>${UI.num(c.shared_windows)}</td>
        <td><span class="badge review">lead</span></td>
      </tr>`).join("")}</tbody></table>`;
  }

  function fmtSecs(s) {
    if (s == null || isNaN(s)) return "—";
    const n = Number(s);
    const m = Math.floor(n / 60), sec = n % 60;
    return `${m}m ${sec}s`;
  }

  async function analyse() {
    const msisdn = document.getElementById("cdr-msisdn").value.trim();
    if (!msisdn) { UI.toast("Enter a number", "Type an MSISDN to analyse.", "info"); return; }
    document.getElementById("cdr-contacts").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("cdr-towers").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("cdr-coloc").innerHTML = `<div class="shimmer sk-line"></div>`;
    try {
      const d = await API.get("/cdr/contacts", { msisdn });
      renderSummary(d);
      renderContacts(d.top_contacts || []);
      renderTowers(d.common_towers || []);
      renderColoc(d.co_location || []);
    } catch (_) {
      document.getElementById("cdr-contacts").innerHTML = UI.empty("Lookup failed", "", "⚠");
      document.getElementById("cdr-towers").innerHTML = "";
      document.getElementById("cdr-coloc").innerHTML = "";
    }
  }

  function ensureSigma() {
    if (renderer) return;
    graph = new DGraph({ multi: true, type: "directed" });
    renderer = new Sigma(graph, document.getElementById("cdr-sigma"), {
      defaultEdgeColor: "rgba(230,237,245,.16)",
      labelColor: { color: "#E6EDF5" },
      labelSize: 11,
      labelFont: "Inter, Segoe UI, sans-serif",
      labelDensity: 0.4,
      labelGridCellSize: 80,
      labelRenderedSizeThreshold: 5,
      renderLabels: true,
      defaultNodeColor: "#888",
    });
  }

  function layout() {
    if (!graph.order) return;
    const nodes = graph.nodes();
    const R = Math.max(2, Math.sqrt(nodes.length)) * 3;
    nodes.forEach((n, i) => {
      const ang = (i / nodes.length) * Math.PI * 2;
      graph.setNodeAttribute(n, "x", Math.cos(ang) * R + (Math.random() - 0.5));
      graph.setNodeAttribute(n, "y", Math.sin(ang) * R + (Math.random() - 0.5));
    });
    try {
      if (DFA2 && DFA2.assign) DFA2.assign(graph, { iterations: 200, settings: { gravity: 1.2, scalingRatio: 14, slowDown: 4, barnesHutOptimize: graph.order > 200 } });
    } catch (e) { console.warn("layout", e); }
  }

  function renderNetwork(data, target) {
    ensureSigma();
    if (renderer) renderer.resize();
    graph.clear();
    const nodes = data.nodes || [], edges = data.edges || [];
    const stats = document.getElementById("cdr-net-stats");
    if (!nodes.length) { stats.textContent = "No call network found."; renderer.refresh(); return; }
    const deg = {};
    edges.forEach((e) => { deg[e.source] = (deg[e.source] || 0) + 1; deg[e.target] = (deg[e.target] || 0) + 1; });
    nodes.forEach((n) => {
      if (graph.hasNode(n.id)) return;
      const isTarget = n.id === `phone:${target}` || (n.meta && n.meta.is_target);
      const color = isTarget ? TYPE_COLOR.target : TYPE_COLOR.phone;
      const d = deg[n.id] || 1;
      graph.addNode(n.id, {
        label: n.label || n.id,
        size: Math.min(22, (isTarget ? 9 : 4) + Math.sqrt(d) * 2.2),
        color, baseColor: color, ntype: "phone", meta: n.meta || {},
      });
    });
    edges.forEach((e, i) => {
      if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(`e${i}`)) {
        try { graph.addEdgeWithKey(`e${i}`, e.source, e.target, { label: e.label, size: 1 }); } catch (_) {}
      }
    });
    layout();
    renderer.refresh();
    stats.innerHTML = `<b style="color:var(--gold-soft)">${nodes.length}</b> numbers · <b style="color:var(--gold-soft)">${edges.length}</b> call links`;
  }

  async function showNetwork() {
    const msisdn = document.getElementById("cdr-msisdn").value.trim();
    if (!msisdn) { UI.toast("Enter a number", "Type an MSISDN to build its call network.", "info"); return; }
    const panel = document.getElementById("cdr-net-panel");
    panel.style.display = "";
    document.getElementById("cdr-net-stats").innerHTML = `<span class="dim">building…</span>`;
    try {
      const data = await API.get("/cdr/network", { msisdn, depth: 1 });
      renderNetwork(data, msisdn);
    } catch (_) {
      document.getElementById("cdr-net-stats").textContent = "Could not build call network.";
    }
  }

  function renderDump(d) {
    const host = document.getElementById("cdr-dump-out");
    const nums = (d && d.numbers) || [];
    if (!nums.length) { host.innerHTML = UI.empty(`No numbers on ${UI.esc((d && d.tower) || "tower")}`, "No active records for this tower.", "⌖"); return; }
    host.innerHTML = `<div class="dim mb12" style="font-size:12px">Tower <span class="chip fir">${UI.esc(UI.val(d.tower))}</span> — ${nums.length} active number(s).</div>
      <table class="tbl"><thead><tr><th>Number</th><th>Calls</th><th>First seen</th><th>Last seen</th></tr></thead><tbody>${
      nums.map((n) => `<tr>
        <td class="mono">${UI.esc(UI.val(n.number))}</td>
        <td>${UI.num(n.calls)}</td>
        <td class="dim">${UI.esc(UI.val(n.first))}</td>
        <td class="dim">${UI.esc(UI.val(n.last))}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  async function towerDump() {
    const tower = document.getElementById("cdr-tower").value.trim();
    if (!tower) { UI.toast("Enter a tower", "Type a tower id to dump.", "info"); return; }
    document.getElementById("cdr-dump-out").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const d = await API.get("/cdr/tower-dump", { tower });
      renderDump(d);
    } catch (_) {
      document.getElementById("cdr-dump-out").innerHTML = UI.empty("Tower dump failed", "", "⚠");
    }
  }

  function bind() {
    document.getElementById("cdr-go").addEventListener("click", analyse);
    document.getElementById("cdr-net").addEventListener("click", showNetwork);
    document.getElementById("cdr-dump").addEventListener("click", towerDump);
    document.getElementById("cdr-msisdn").addEventListener("keydown", (e) => { if (e.key === "Enter") analyse(); });
    document.getElementById("cdr-tower").addEventListener("keydown", (e) => { if (e.key === "Enter") towerDump(); });
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    bind();
    // Prefill a known-good subscriber + tower so the tools work immediately.
    API.get("/cdr/sample", null, { silent: true }).then((s) => {
      if (s && s.msisdn) { document.getElementById("cdr-msisdn").value = s.msisdn; analyse(); }
      if (s && s.tower) document.getElementById("cdr-tower").value = s.tower;
    }).catch(() => {});
    mounted = true;
  }

  function onShow() { if (renderer) setTimeout(() => renderer.refresh(), 60); }

  return { mount, onShow };
})();
