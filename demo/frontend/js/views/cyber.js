/* ============================================================
   cyber.js — Cybercrime overview (KPIs + ECharts), mule list,
   and a sigma.js follow-the-money flow explorer.
   ============================================================ */
Views.Cyber = (() => {
  let el, graph, renderer, mounted = false;

  const TYPE_COLOR = { account: "#2ba6bd", mule: "#e2574c" };

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⛓</span> Cybercrime</h1>
          <div class="view-sub">Financial-fraud intelligence — typologies, mule-account detection, and money-flow tracing across banks.</div>
        </div>
      </div>

      <div class="banner warn">
        <span class="b-ico">⚠</span>
        <div><b>Bengaluru is India's cyber-fraud hub.</b> The city accounts for an outsized share of national financial-cybercrime FIRs — concentrated detection and money-flow tracing matter here more than anywhere.</div>
      </div>

      <div class="grid kpi-grid" id="cy-kpis">${UI.skeletonKPIs(4)}</div>

      <div class="grid charts-grid">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Fraud by type</h3>
          <div class="chart" id="cy-donut">${UI.skeletonChart()}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Top districts</h3>
          <div class="chart" id="cy-bar">${UI.skeletonChart()}</div>
        </div>
      </div>

      <div class="grid" style="grid-template-columns:1fr;margin-top:16px">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Fraud trend</h3>
          <div class="chart" id="cy-trend" style="height:220px">${UI.skeletonChart()}</div>
        </div>
      </div>

      <div class="grid" style="grid-template-columns:1fr;gap:18px;margin-top:16px">
        <div class="panel panel-pad">
          <div class="row wrap" style="justify-content:space-between;margin-bottom:14px">
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Flagged mule accounts <span class="faint" id="cy-mule-count" style="margin-left:8px;font-weight:600"></span></h3>
            <div class="faint" style="font-size:11px">Click a row to trace its money flow ▸</div>
          </div>
          <div class="tbl-wrap scroll" style="max-height:420px" id="cy-mules"></div>
        </div>

        <div class="panel panel-pad">
          <div class="row wrap" style="justify-content:space-between;margin-bottom:14px">
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Money-flow explorer — follow the money</h3>
            <div class="controls">
              <div class="ctrl"><span class="ctrl-label">Account id</span>
                <input type="search" id="cy-acct" placeholder="e.g. ACC-000123" style="min-width:190px"/>
              </div>
              <div class="ctrl"><span class="ctrl-label">Depth</span>
                <select id="cy-depth"><option value="1">1 hop</option><option value="2" selected>2 hops</option><option value="3">3 hops</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary sm" id="cy-trace">Trace flow</button></div>
            </div>
          </div>
          <div class="map-shell" style="height:440px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)">
            <div id="cy-sigma" style="position:absolute;inset:0"></div>
            <div class="map-overlay map-side" style="top:14px;right:14px;width:240px;bottom:14px">
              <div class="panel panel-pad" style="background:rgba(11,31,58,.82);backdrop-filter:blur(14px)">
                <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> Legend</h3>
                <div class="legend">
                  <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.account}"></span>Account</div>
                  <div class="legend-row"><span class="legend-sw" style="background:${TYPE_COLOR.mule}"></span>Mule (flagged)</div>
                </div>
                <div class="faint mt12" id="cy-flow-stats" style="font-size:11px">Enter an account or click a mule above.</div>
              </div>
            </div>
          </div>
        </div>
      </div>`;
  }

  const KPI_DEFS = [
    { key: "total_cases", label: "Cyber FIRs", fmt: "num", accent: "accent-gold", foot: "Financial-fraud cases" },
    { key: "total_loss", label: "Total loss", fmt: "inr", accent: "accent-red", foot: "Reported amount lost" },
    { key: "mule_accounts", label: "Mule accounts", fmt: "num", accent: "accent-teal", foot: "Flagged conduits" },
    { key: "recovery_rate", label: "Recovery rate", fmt: "pct", accent: "", foot: "Funds frozen / recovered" },
  ];

  function renderKPIs(kpis) {
    const k = kpis || {};
    const host = document.getElementById("cy-kpis");
    if (!host) return;
    host.innerHTML = KPI_DEFS.map((d) => {
      if (d.fmt === "inr") {
        return `<div class="kpi ${d.accent}">
          <div class="kpi-label">${d.label}</div>
          <div class="kpi-value" style="font-size:24px">${UI.inr(k[d.key])}</div>
          <div class="kpi-foot">${d.foot}</div>
        </div>`;
      }
      const isPct = d.fmt === "pct";
      return `<div class="kpi ${d.accent}">
        <div class="kpi-label">${d.label}</div>
        <div class="kpi-value" data-k="${d.key}">0${isPct ? '<span class="unit">%</span>' : ""}</div>
        <div class="kpi-foot">${d.foot}</div>
      </div>`;
    }).join("");
    KPI_DEFS.forEach((d) => {
      if (d.fmt === "inr") return;
      const node = host.querySelector(`[data-k="${d.key}"]`);
      UI.countUp(node, Number(k[d.key] || 0), { decimals: d.fmt === "pct" ? 1 : 0 });
    });
  }

  function donut(data) {
    if (!data || !data.length) { document.getElementById("cy-donut").innerHTML = UI.empty("No type data"); return; }
    UI.mountChart("cy-donut", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "item", formatter: "{b}: <b>{c}</b> ({d}%)" },
      legend: { bottom: 0, textStyle: { color: "#9fb0c6", fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
      series: [{
        type: "pie", radius: ["46%", "70%"], center: ["50%", "44%"], avoidLabelOverlap: true,
        itemStyle: { borderColor: "#0a1628", borderWidth: 2, borderRadius: 4 },
        label: { show: false }, labelLine: { show: false },
        data: data.map((d) => ({ name: d.name, value: d.value })),
      }],
    });
  }

  function bar(data) {
    if (!data || !data.length) { document.getElementById("cy-bar").innerHTML = UI.empty("No district data"); return; }
    const d = data.slice(0, 12).reverse();
    UI.mountChart("cy-bar", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 8, right: 24, top: 14, bottom: 6, containLabel: true },
      xAxis: { type: "value", ...UI.axisCommon },
      yAxis: { type: "category", data: d.map((x) => x.name), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10.5 } },
      series: [{
        type: "bar", data: d.map((x) => x.value), barWidth: "62%",
        itemStyle: {
          borderRadius: [0, 5, 5, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: "#1F7A8C" }, { offset: 1, color: "#e2574c" }]),
        },
      }],
    });
  }

  function trend(data) {
    if (!data || !data.length) { document.getElementById("cy-trend").innerHTML = UI.empty("No trend data"); return; }
    UI.mountChart("cy-trend", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis" },
      xAxis: { type: "category", data: data.map((x) => x.period), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10, rotate: data.length > 10 ? 35 : 0 } },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [{
        type: "line", data: data.map((x) => x.count), smooth: true,
        symbol: "circle", symbolSize: 6, itemStyle: { color: "#e2574c" },
        lineStyle: { color: "#e2574c", width: 2.5 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(226,87,76,.3)" }, { offset: 1, color: "rgba(226,87,76,0)" }]) },
      }],
    });
  }

  function renderMules(items) {
    const host = document.getElementById("cy-mules");
    document.getElementById("cy-mule-count").textContent = items.length ? `${items.length}` : "";
    if (!items.length) { host.innerHTML = UI.empty("No flagged mules", "No accounts crossed the mule-risk threshold.", "✓"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>Account</th><th>Bank</th><th>Score</th><th>Flagged txns</th><th>Reasons</th></tr></thead><tbody>${
      items.map((m) => `<tr data-acct="${UI.esc(UI.val(m.account_id, ""))}" style="cursor:pointer">
        <td><b>${UI.esc(UI.val(m.account_id))}</b><div class="faint" style="font-size:10px">${UI.esc(UI.val(m.holder_name))}</div></td>
        <td class="dim">${UI.esc(UI.val(m.bank))}</td>
        <td style="min-width:96px"><div class="row" style="gap:6px"><div class="score-bar" style="flex:1"><i style="width:${Math.round((m.score || 0) * 100)}%"></i></div><span style="font-weight:700">${(m.score ?? 0).toFixed(2)}</span></div></td>
        <td>${UI.num(m.flagged_txns)}</td>
        <td>${(m.reasons || []).map((r) => `<span class="chip term" style="margin:1px">${UI.esc(r)}</span>`).join("") || "—"}</td>
      </tr>`).join("")}</tbody></table>`;
    host.querySelectorAll("tr[data-acct]").forEach((r) => r.addEventListener("click", () => {
      const a = r.dataset.acct;
      if (!a) return;
      document.getElementById("cy-acct").value = a;
      traceFlow();
    }));
  }

  function ensureSigma() {
    if (renderer) return;
    graph = new DGraph({ multi: true, type: "directed" });
    renderer = new Sigma(graph, document.getElementById("cy-sigma"), {
      defaultEdgeColor: "rgba(230,237,245,.16)",
      labelColor: { color: "#E6EDF5" },
      labelSize: 11,
      labelFont: "Inter, Segoe UI, sans-serif",
      labelDensity: 0.4,
      labelGridCellSize: 80,
      labelRenderedSizeThreshold: 5,
      renderLabels: true,
      renderEdgeLabels: true,
      edgeLabelColor: { color: "#9fb0c6" },
      edgeLabelSize: 10,
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
      if (DFA2 && DFA2.assign) DFA2.assign(graph, { iterations: 200, settings: { gravity: 1.2, scalingRatio: 16, slowDown: 4, barnesHutOptimize: graph.order > 200 } });
    } catch (e) { console.warn("layout", e); }
  }

  function renderFlow(data) {
    ensureSigma();
    if (renderer) renderer.resize();
    graph.clear();
    const nodes = data.nodes || [], edges = data.edges || [];
    const stats = document.getElementById("cy-flow-stats");
    if (!nodes.length) {
      stats.textContent = "No flow found for that account.";
      renderer.refresh();
      return;
    }
    const deg = {};
    edges.forEach((e) => { deg[e.source] = (deg[e.source] || 0) + 1; deg[e.target] = (deg[e.target] || 0) + 1; });
    nodes.forEach((n) => {
      if (graph.hasNode(n.id)) return;
      const meta = n.meta || {};
      const isMule = meta.is_mule || n.type === "mule";
      const color = isMule ? TYPE_COLOR.mule : TYPE_COLOR.account;
      const d = deg[n.id] || 1;
      graph.addNode(n.id, {
        label: n.label || n.id,
        size: Math.min(22, 5 + Math.sqrt(d) * 2.4),
        color, baseColor: color, ntype: isMule ? "mule" : "account", meta,
      });
    });
    edges.forEach((e, i) => {
      if (graph.hasNode(e.source) && graph.hasNode(e.target) && !graph.hasEdge(`e${i}`)) {
        const lbl = e.label != null ? String(e.label) : (e.weight != null ? UI.inr(e.weight) : "");
        try { graph.addEdgeWithKey(`e${i}`, e.source, e.target, { label: lbl, size: 1.2, type: "arrow" }); } catch (_) {}
      }
    });
    layout();
    renderer.refresh();
    const mules = nodes.filter((n) => (n.meta && n.meta.is_mule) || n.type === "mule").length;
    stats.innerHTML = `<b style="color:var(--gold-soft)">${nodes.length}</b> accounts · <b style="color:var(--gold-soft)">${edges.length}</b> transfers · <b style="color:#ef897f">${mules}</b> mule(s)`;
  }

  async function traceFlow() {
    const acct = document.getElementById("cy-acct").value.trim();
    if (!acct) { UI.toast("Enter an account", "Type or pick an account id to trace.", "info"); return; }
    const depth = document.getElementById("cy-depth").value;
    document.getElementById("cy-flow-stats").innerHTML = `<span class="dim">tracing…</span>`;
    try {
      const data = await API.get("/cyber/money-flow", { account: acct, depth });
      renderFlow(data);
    } catch (_) {
      document.getElementById("cy-flow-stats").textContent = "Could not trace this account.";
    }
  }

  async function load() {
    document.getElementById("cy-mules").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    const [ov, mu] = await Promise.allSettled([
      API.get("/cyber/overview"),
      API.get("/cyber/mules", { limit: 50 }),
    ]);
    if (ov.status === "fulfilled") {
      const o = ov.value || {};
      renderKPIs(o.kpis);
      donut(o.by_type);
      bar(o.top_districts);
      trend(o.trend);
    } else {
      document.getElementById("cy-kpis").innerHTML = UI.empty("Could not load cyber overview", "Check the API connection.", "⚠");
    }
    if (mu.status === "fulfilled") renderMules((mu.value && mu.value.items) || []);
    else document.getElementById("cy-mules").innerHTML = UI.empty("Mules unavailable", "", "⚠");
  }

  function bind() {
    document.getElementById("cy-trace").addEventListener("click", traceFlow);
    document.getElementById("cy-acct").addEventListener("keydown", (e) => { if (e.key === "Enter") traceFlow(); });
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    bind();
    load();
    // Prefill a traceable account so "Trace flow" works immediately.
    API.get("/cyber/sample", null, { silent: true }).then((s) => {
      if (s && s.account) document.getElementById("cy-acct").value = s.account;
    }).catch(() => {});
    mounted = true;
  }

  function onShow() {
    if (renderer) setTimeout(() => { renderer.resize(); renderer.refresh(); }, 60);
    UI.resizeCharts();
  }

  return { mount, onShow };
})();
