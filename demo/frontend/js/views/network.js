/* ============================================================
   network.js — sigma.js v3 + graphology. Node search, depth,
   community detection, click -> side panel.
   ============================================================ */
Views.Network = (() => {
  let el, graph, renderer, mounted = false;
  let highlighted = null;

  const TYPE_COLOR = {
    person: "#2ba6bd", crime: "#C9A227", vehicle: "#8794a6", station: "#3d7fd6",
  };

  function shell() {
    return `
      <div class="map-shell">
        <div id="sigma-canvas"></div>

        <div class="map-overlay map-controls" style="max-width:none">
          <div class="panel">
            <div class="controls">
              <div class="ctrl"><span class="ctrl-label">Focus person / FIR</span>
                <input type="search" id="net-search" placeholder="name or FIR number…" style="min-width:200px"/>
              </div>
              <div class="ctrl"><span class="ctrl-label">Search by</span>
                <select id="net-mode"><option value="person">Person</option><option value="fir">FIR</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">Depth</span>
                <select id="net-depth"><option value="1" selected>1 hop</option><option value="2">2 hops</option><option value="3">3 hops</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary" id="net-go">Build graph</button></div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-teal" id="net-comm">⚇ Detect communities</button></div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn ghost sm" id="net-reset">Reset</button></div>
            </div>
          </div>
        </div>

        <div class="map-overlay map-side net-side">
          <div class="panel panel-pad">
            <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> Legend</h3>
            <div class="legend">
              <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.person}"></span>Person</div>
              <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.crime}"></span>Crime / FIR</div>
              <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.vehicle}"></span>Vehicle</div>
              <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.station}"></span>Police station</div>
            </div>
            <div class="faint mt12" id="net-stats" style="font-size:11px"></div>
          </div>
          <div class="panel panel-pad" style="flex:1 1 auto;min-height:0;overflow:auto" id="net-panel">
            ${UI.empty("Click a node", "Select any node to inspect its metadata, or detect communities to surface brokers.", "⚇")}
          </div>
        </div>
      </div>`;
  }

  function ensureSigma() {
    if (renderer) return;
    if (typeof DGraph !== "function") throw new Error("graphology not loaded — hard-refresh (Ctrl+Shift+R)");
    if (typeof Sigma !== "function") throw new Error("sigma.js not loaded — hard-refresh (Ctrl+Shift+R)");
    const container = document.getElementById("sigma-canvas");
    if (!container) throw new Error("sigma-canvas element missing");
    graph = new DGraph({ multi: true, type: "directed" });
    renderer = new Sigma(graph, container, {
      defaultEdgeColor: "rgba(230,237,245,.14)",
      labelColor: { color: "#E6EDF5" },
      labelSize: 12,
      labelFont: "Inter, Segoe UI, sans-serif",
      labelDensity: 0.35,
      labelGridCellSize: 80,
      labelRenderedSizeThreshold: 6,
      renderLabels: true,
      defaultNodeColor: "#888",
    });
    renderer.on("clickNode", ({ node }) => selectNode(node));
    renderer.on("clickStage", () => clearHighlight());
  }

  function layout() {
    if (!graph.order) return;
    // circular seed then forceAtlas2
    const nodes = graph.nodes();
    const R = Math.max(2, Math.sqrt(nodes.length)) * 3;
    nodes.forEach((n, i) => {
      const ang = (i / nodes.length) * Math.PI * 2;
      graph.setNodeAttribute(n, "x", Math.cos(ang) * R + (Math.random() - 0.5));
      graph.setNodeAttribute(n, "y", Math.sin(ang) * R + (Math.random() - 0.5));
    });
    try {
      if (DFA2 && DFA2.assign) DFA2.assign(graph, { iterations: 220, settings: { gravity: 1.2, scalingRatio: 14, slowDown: 4, barnesHutOptimize: graph.order > 200 } });
    } catch (e) { console.warn("layout", e); }
  }

  function renderData(data) {
    ensureSigma();
    graph.clear();
    const nodes = data.nodes || [], edges = data.edges || [];
    if (!nodes.length) {
      document.getElementById("net-stats").textContent = "No nodes returned.";
      renderer.refresh();
      document.getElementById("net-panel").innerHTML = UI.empty("Empty network", "No linked entities for that query.", "⚇");
      return;
    }
    // degree
    const deg = {};
    edges.forEach((e) => { deg[e.source] = (deg[e.source] || 0) + 1; deg[e.target] = (deg[e.target] || 0) + 1; });
    // Sigma v3 requires x,y at addNode time — seed circular positions immediately.
    const R = Math.max(2, Math.sqrt(nodes.length)) * 4;
    nodes.forEach((n, i) => {
      if (graph.hasNode(n.id)) return;
      const d = deg[n.id] || 1;
      const ang = (i / Math.max(1, nodes.length)) * Math.PI * 2;
      graph.addNode(n.id, {
        label: n.label || n.id,
        x: Math.cos(ang) * R,
        y: Math.sin(ang) * R,
        size: Math.min(22, 4 + Math.sqrt(d) * 2.4),
        color: TYPE_COLOR[n.type] || "#8794a6",
        ntype: n.type, meta: n.meta || {}, degree: d, baseColor: TYPE_COLOR[n.type] || "#8794a6",
      });
    });
    edges.forEach((e, i) => {
      if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(`e${i}`)) {
        try { graph.addEdgeWithKey(`e${i}`, e.source, e.target, { label: e.label, size: 1 }); } catch (_) {}
      }
    });
    layout();
    renderer.refresh();
    document.getElementById("net-stats").innerHTML =
      `<b style="color:var(--gold-soft)">${nodes.length}</b> nodes · <b style="color:var(--gold-soft)">${edges.length}</b> links`;
  }

  function selectNode(id) {
    if (!graph.hasNode(id)) return;
    highlighted = id;
    const neighbors = new Set([id, ...graph.neighbors(id)]);
    graph.forEachNode((n, attr) => {
      const on = neighbors.has(n);
      graph.setNodeAttribute(n, "color", on ? attr.baseColor : "rgba(230,237,245,.08)");
      graph.setNodeAttribute(n, "zIndex", on ? 1 : 0);
    });
    graph.forEachEdge((e, attr, s, t) => {
      graph.setEdgeAttribute(e, "color", (s === id || t === id) ? "rgba(201,162,39,.55)" : "rgba(230,237,245,.04)");
    });
    renderer.refresh();
    const a = graph.getNodeAttributes(id);
    const meta = a.meta || {};
    const rows = Object.entries(meta).map(([k, v]) =>
      `<div class="node-meta-row"><span class="k">${UI.esc(UI.title(k))}</span><span class="v">${UI.esc(UI.val(v))}</span></div>`).join("");
    document.getElementById("net-panel").innerHTML = `
      <h3 class="panel-title" style="margin-bottom:6px"><span class="dotaccent" style="background:${a.baseColor}"></span> ${UI.title(a.ntype || "node")}</h3>
      <div style="font-size:16px;font-weight:700;margin-bottom:4px">${UI.esc(a.label)}</div>
      <div class="faint mb12" style="font-size:11px">degree ${a.degree} · ${graph.neighbors(id).length} direct links</div>
      ${rows || UI.empty("No metadata", "", "·")}`;
  }

  function clearHighlight() {
    if (!highlighted) return;
    highlighted = null;
    graph.forEachNode((n, attr) => { graph.setNodeAttribute(n, "color", attr.baseColor); });
    graph.forEachEdge((e) => graph.setEdgeAttribute(e, "color", "rgba(230,237,245,.14)"));
    renderer.refresh();
  }

  async function build() {
    const q = document.getElementById("net-search").value.trim();
    const searchMode = document.getElementById("net-mode").value;
    const depth = document.getElementById("net-depth").value;
    const params = { depth };
    if (q) params[searchMode] = q;
    document.getElementById("net-stats").innerHTML = `<span class="dim">building…</span>`;
    try {
      const data = await API.get("/network", params);
      renderData(data);
    } catch (err) {
      console.error("[Network] build failed:", err);
      document.getElementById("net-stats").textContent = "Error: " + (err.message || err);
    }
  }

  async function detectCommunities() {
    document.getElementById("net-panel").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const r = await API.get("/network/communities");
      const comms = r.communities || [];
      if (!comms.length) { document.getElementById("net-panel").innerHTML = UI.empty("No communities", "Not enough connected structure to cluster.", "⚇"); return; }
      const palette = UI.palette;
      const memberToComm = {};
      comms.forEach((c, i) => (c.members || []).forEach((m) => (memberToComm[m] = i)));
      // recolor by community
      graph.forEachNode((n, attr) => {
        const ci = memberToComm[n];
        graph.setNodeAttribute(n, "baseColor", ci != null ? palette[ci % palette.length] : "rgba(230,237,245,.12)");
        graph.setNodeAttribute(n, "color", ci != null ? palette[ci % palette.length] : "rgba(230,237,245,.12)");
      });
      renderer.refresh();
      document.getElementById("net-panel").innerHTML = `
        <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> ${comms.length} communities</h3>
        <div class="dim mb12" style="font-size:11px">Brokers (high-degree key nodes) are likely coordinators. Click to focus.</div>
        ${comms.map((c, i) => `
          <div class="comm-item" data-key="${UI.esc((c.key_nodes || [])[0] || "")}">
            <div class="row" style="justify-content:space-between">
              <span style="font-weight:700;color:${palette[i % palette.length]}">Cluster ${i + 1}</span>
              <span class="badge neutral">${c.size} nodes</span>
            </div>
            <div class="faint mt12" style="font-size:11px;margin-top:6px">Key: ${(c.key_nodes || []).map((k) => {
              const lbl = graph.hasNode(k) ? graph.getNodeAttribute(k, "label") : k;
              return `<span class="chip term" style="margin:2px">${UI.esc(lbl)}</span>`;
            }).join("") || "—"}</div>
          </div>`).join("")}`;
      document.querySelectorAll(".comm-item").forEach((it) => it.addEventListener("click", () => {
        const k = it.dataset.key;
        if (k && graph.hasNode(k)) { selectNode(k); const cam = renderer.getCamera(); const pos = renderer.getNodeDisplayData(k); }
      }));
      UI.toast("Communities detected", `${comms.length} clusters surfaced — nodes recolored by membership.`, "ok");
    } catch (_) {}
  }

  function bind() {
    document.getElementById("net-go").addEventListener("click", build);
    document.getElementById("net-comm").addEventListener("click", detectCommunities);
    document.getElementById("net-reset").addEventListener("click", () => {
      document.getElementById("net-search").value = "";
      build();
    });
    document.getElementById("net-search").addEventListener("keydown", (e) => { if (e.key === "Enter") build(); });
  }

  function mount(node) {
    el = node;
    el.classList.add("fullbleed");
    el.innerHTML = shell();
    bind();
    build();
    mounted = true;
  }

  function onShow() { if (renderer) setTimeout(() => renderer.refresh(), 60); }

  return { mount, onShow };
})();
