/* ============================================================
   correlate.js — Case Correlation Engine.
   Multi-signal clustering of related FIRs.
   ============================================================ */
Views.Correlate = (() => {
  let el, charts = {}, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⚯</span> Case Correlation Engine</h1>
          <div class="view-sub">Automatically groups FIRs sharing spatial, temporal, MO, weapon, person, and vehicle signals into clusters of potentially related crimes.</div>
        </div>
        <div class="controls">
          <div class="ctrl"><span class="ctrl-label">Crime type</span>
            <select id="cc-type"><option value="">All types</option></select></div>
          <div class="ctrl"><span class="ctrl-label">District</span>
            <select id="cc-district"><option value="">All districts</option></select></div>
          <div class="ctrl"><span class="ctrl-label">Link threshold</span>
            <select id="cc-thresh">
              <option value="3">3 — loose</option>
              <option value="4" selected>4 — balanced</option>
              <option value="5">5 — strict</option>
              <option value="7">7 — very strict</option>
            </select></div>
          <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
            <button class="btn btn-primary" id="cc-run">Correlate cases</button></div>
        </div>
      </div>

      <div id="cc-kpis" style="margin-bottom:14px"></div>

      <div class="banner info" style="margin-bottom:14px">
        <span class="b-ico">🛈</span>
        <div>Similarity is computed from <b>7 signals</b>: spatial proximity, date proximity, crime type, weapon, modus-operandi keyword overlap, shared persons, and shared vehicles. Clusters show crimes that <b>may</b> be connected — officer review is always required.</div>
      </div>

      <div class="grid" style="grid-template-columns:1fr 1fr;gap:14px;margin-bottom:14px">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Cluster size distribution</h3>
          <div class="chart" id="cc-size-chart" style="height:220px">${UI.skeletonChart()}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Crime type mix in clusters</h3>
          <div class="chart" id="cc-type-chart" style="height:220px">${UI.skeletonChart()}</div>
        </div>
      </div>

      <div class="panel panel-pad">
        <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> Correlation clusters <span class="faint" id="cc-count" style="margin-left:auto;font-weight:600"></span></h3>
        <div id="cc-clusters"></div>
      </div>`;
  }

  async function load() {
    const type = document.getElementById("cc-type").value;
    const district = document.getElementById("cc-district").value;
    const threshold = document.getElementById("cc-thresh").value;
    document.getElementById("cc-clusters").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("cc-kpis").innerHTML = "";
    try {
      const d = await API.get("/cases/correlate", { crime_type: type || undefined, district: district || undefined, threshold, limit: 500 });
      renderKPIs(d);
      renderCharts(d);
      renderClusters(d.clusters || []);
    } catch (_) {
      document.getElementById("cc-clusters").innerHTML = UI.empty("Correlation failed", "Try a looser threshold or smaller filter.", "⚯");
    }
  }

  function renderKPIs(d) {
    const linked_pct = d.total_crimes > 0 ? ((d.total_linked / d.total_crimes) * 100).toFixed(1) : 0;
    document.getElementById("cc-kpis").innerHTML = `
      <div class="row wrap" style="gap:10px">
        ${[["FIRs analysed", d.total_crimes], ["FIRs linked", d.total_linked], ["Clusters found", (d.clusters||[]).length], ["Linked %", linked_pct + "%"]]
          .map(([l,v]) => `<div class="kpi" style="min-width:100px;padding:10px 14px"><div class="kpi-label">${l}</div><div class="kpi-value" style="font-size:22px">${v}</div></div>`).join("")}
      </div>`;
  }

  function renderCharts(d) {
    const clusters = d.clusters || [];
    const sizeBuckets = {};
    clusters.forEach((c) => {
      const k = c.size <= 2 ? "2" : c.size <= 4 ? "3-4" : c.size <= 8 ? "5-8" : "9+";
      sizeBuckets[k] = (sizeBuckets[k] || 0) + 1;
    });
    UI.mountChart("cc-size-chart", {
      ...UI.chartBase(),
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 8, right: 12, top: 10, bottom: 6, containLabel: true },
      xAxis: { type: "category", data: ["2", "3-4", "5-8", "9+"], ...UI.axisCommon },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [{ type: "bar", data: ["2", "3-4", "5-8", "9+"].map((k) => sizeBuckets[k] || 0),
        barWidth: "55%", itemStyle: { borderRadius: [4, 4, 0, 0], color: "#C9A227" } }],
    });
    const typeCounts = {};
    clusters.forEach((c) => (c.crime_types || []).forEach((t) => { typeCounts[t] = (typeCounts[t] || 0) + 1; }));
    const typeEntries = Object.entries(typeCounts).sort((a,b)=>b[1]-a[1]).slice(0, 8);
    UI.mountChart("cc-type-chart", {
      ...UI.chartBase(),
      tooltip: { trigger: "item" },
      series: [{ type: "pie", radius: ["40%", "70%"], itemStyle: { borderColor: "#0a1628", borderWidth: 2 },
        label: { color: "#E6EDF5", fontSize: 11 },
        data: typeEntries.map(([name, value]) => ({ name, value })) }],
    });
  }

  function renderClusters(clusters) {
    document.getElementById("cc-count").textContent = `${clusters.length} cluster(s)`;
    if (!clusters.length) {
      document.getElementById("cc-clusters").innerHTML = UI.empty("No clusters found", "Try lowering the threshold or removing filters.", "⚯");
      return;
    }
    document.getElementById("cc-clusters").innerHTML = clusters.map((c) => `
      <div class="panel" style="padding:12px 16px;margin-bottom:12px;border:1px solid rgba(201,162,39,.25)">
        <div class="row wrap" style="justify-content:space-between;margin-bottom:8px">
          <div>
            <b style="color:var(--gold)">${UI.esc(c.id)}</b>
            <span class="badge review" style="margin-left:8px">${c.size} FIRs</span>
            <span class="dim" style="font-size:11px;margin-left:8px">score ${c.score}</span>
          </div>
          <div>${(c.signals || []).map((s) => `<span class="chip term" style="margin:1px">${UI.esc(s)}</span>`).join("")}</div>
        </div>
        <div class="tbl-wrap scroll" style="max-height:200px">
          <table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>District</th><th>Date</th><th>Status</th></tr></thead>
          <tbody>${(c.firs || []).slice(0, 12).map((f) => `<tr>
            <td class="mono">${UI.esc(f.fir_number || "—")}</td>
            <td class="dim">${UI.esc(UI.val(f.crime_type))}</td>
            <td class="dim">${UI.esc(UI.val(f.district))}</td>
            <td class="dim">${UI.date(f.occurred_at)}</td>
            <td><span class="badge neutral">${UI.esc(UI.val(f.status))}</span></td>
          </tr>`).join("")}
          ${c.size > 12 ? `<tr><td colspan="5" class="dim" style="text-align:center;font-size:11px">+ ${c.size - 12} more FIRs in this cluster</td></tr>` : ""}
          </tbody></table>
        </div>
      </div>`).join("");
  }

  async function populateFilters() {
    try {
      const m = await API.get("/meta");
      const types = (m.crime_types || []);
      const districts = (m.districts || []);
      const ts = document.getElementById("cc-type");
      const ds = document.getElementById("cc-district");
      types.forEach((t) => { const o = document.createElement("option"); o.value = t; o.textContent = t; ts.appendChild(o); });
      districts.forEach((d) => { const o = document.createElement("option"); o.value = d; o.textContent = d; ds.appendChild(o); });
    } catch (_) {}
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("cc-run").addEventListener("click", load);
    populateFilters().then(() => load());
    mounted = true;
  }

  function onShow() { UI.resizeCharts(); }

  return { mount, onShow };
})();
