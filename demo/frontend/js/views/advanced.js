/* ============================================================
   advanced.js — Three cutting-edge experimental features:
   1. Criminal Network Motif Detection (triangle census)
   2. ACO Patrol Optimisation (ant colony)
   3. Differential Privacy Hotspots (Laplace mechanism)
   ============================================================ */
Views.Advanced = (() => {
  let el, map, mapReady = false, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">✶</span> Advanced Research Features</h1>
          <div class="view-sub">Experimental techniques drawn from 2023-2025 research: criminal network motif detection, ant-colony patrol routing, and differential-privacy hotspot publication.</div>
        </div>
      </div>

      <!-- ── Motif Detection ─────────────────────────────────────────────── -->
      <div class="panel panel-pad" style="margin-bottom:18px">
        <div class="row wrap" style="justify-content:space-between;margin-bottom:10px">
          <div>
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Criminal Network Motif Detection</h3>
            <div class="dim" style="font-size:11.5px;margin-top:3px">Triangle census on criminal co-accusation graph (Milo et al. 2002, Sparrow 1991). Triangles → crime rings; Stars → kingpins; Chains → recruitment paths.</div>
          </div>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Depth</span>
              <select id="mo-depth"><option value="1" selected>1 hop</option><option value="2">2 hops</option></select></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="mo-run">Detect motifs</button></div>
          </div>
        </div>
        <div id="mo-stats" style="margin-bottom:10px"></div>
        <div class="grid" style="grid-template-columns:1fr 1fr 1fr;gap:14px">
          <div>
            <h4 style="color:var(--gold);font-size:12px;margin-bottom:6px">⚠ Crime Rings (Triangles)</h4>
            <div class="tbl-wrap scroll" style="max-height:280px" id="mo-triangles">${UI.skeletonChart()}</div>
          </div>
          <div>
            <h4 style="color:var(--teal-bright);font-size:12px;margin-bottom:6px">★ Hub Nodes (Stars)</h4>
            <div class="tbl-wrap scroll" style="max-height:280px" id="mo-stars">${UI.skeletonChart()}</div>
          </div>
          <div>
            <h4 style="color:#9b7fd6;font-size:12px;margin-bottom:6px">→ Chains (4-paths)</h4>
            <div class="tbl-wrap scroll" style="max-height:280px" id="mo-chains">${UI.skeletonChart()}</div>
          </div>
        </div>
      </div>

      <!-- ── ACO Patrol ──────────────────────────────────────────────────── -->
      <div class="panel panel-pad" style="margin-bottom:18px">
        <div class="row wrap" style="justify-content:space-between;margin-bottom:10px">
          <div>
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Ant Colony Optimisation Patrol Routing</h3>
            <div class="dim" style="font-size:11.5px;margin-top:3px">Bio-inspired ACO (Dorigo & Gambardella 1997) with pheromone trails + evaporation. Outperforms greedy allocation for coverage per unit.</div>
          </div>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Units</span>
              <input type="range" id="aco-units" min="5" max="40" value="15" style="vertical-align:middle"/>
              <b id="aco-units-val" style="color:var(--gold);margin-left:6px">15</b></div>
            <div class="ctrl"><span class="ctrl-label">Ants</span>
              <select id="aco-ants"><option value="20">20</option><option value="30" selected>30</option><option value="50">50</option></select></div>
            <div class="ctrl"><span class="ctrl-label">Iterations</span>
              <select id="aco-iter"><option value="40">40</option><option value="60" selected>60</option><option value="100">100</option></select></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="aco-run">Run ACO</button></div>
          </div>
        </div>
        <div class="grid" style="grid-template-columns:1fr 1fr;gap:14px">
          <div>
            <div class="map-shell" style="height:300px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)">
              <div id="aco-map-canvas" style="position:absolute;inset:0"></div>
            </div>
            <div id="aco-cov" class="dim" style="font-size:12px;margin-top:6px"></div>
          </div>
          <div class="tbl-wrap scroll" style="max-height:320px" id="aco-table">${UI.skeletonChart()}</div>
        </div>
      </div>

      <!-- ── Differential Privacy ────────────────────────────────────────── -->
      <div class="panel panel-pad">
        <div class="row wrap" style="justify-content:space-between;margin-bottom:10px">
          <div>
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Differential Privacy Hotspot Publication</h3>
            <div class="dim" style="font-size:11.5px;margin-top:3px">Laplace mechanism (Dwork et al. 2006) adds calibrated noise before public release. Lower ε = stronger privacy, higher utility loss.</div>
          </div>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">ε (epsilon)</span>
              <select id="dp-eps">
                <option value="0.1">0.1 — very strong</option>
                <option value="0.5">0.5 — strong</option>
                <option value="1.0" selected>1.0 — balanced</option>
                <option value="2.0">2.0 — moderate</option>
                <option value="5.0">5.0 — light</option>
              </select></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="dp-run">Apply DP</button></div>
          </div>
        </div>
        <div id="dp-info" style="margin-bottom:10px"></div>
        <div class="tbl-wrap scroll" style="max-height:320px" id="dp-table">${UI.skeletonChart()}</div>
      </div>`;
  }

  // ── Motif Detection ──────────────────────────────────────────────────────
  async function runMotifs() {
    const depth = document.getElementById("mo-depth").value;
    ["mo-triangles","mo-stars","mo-chains"].forEach((id) => {
      document.getElementById(id).innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    });
    document.getElementById("mo-stats").innerHTML = "";
    try {
      const d = await API.get("/network/motifs", { depth, limit: 400 });
      const st = d.stats || {};
      document.getElementById("mo-stats").innerHTML = `
        <div class="row wrap" style="gap:10px">
          ${[["Nodes",st.nodes],["Edges",st.edges],["Triangles",st.triangle_count],["Hubs",st.hub_count],["Chains",st.chain_count]]
            .map(([l,v]) => `<div class="kpi" style="min-width:90px;padding:8px 12px"><div class="kpi-label">${l}</div><div class="kpi-value" style="font-size:20px">${UI.num(v)}</div></div>`).join("")}
        </div>
        <div class="dim" style="font-size:11.5px;margin-top:6px">${UI.esc(d.summary || "")}</div>`;

      const tri = d.triangles || [];
      document.getElementById("mo-triangles").innerHTML = tri.length
        ? `<table class="tbl"><thead><tr><th>Members</th><th>Score</th></tr></thead><tbody>${
            tri.slice(0,60).map((t) => `<tr style="background:rgba(201,162,39,.06)">
              <td style="font-size:11px">${(t.labels || []).map((l) => `<span class="chip term" style="margin:1px">${UI.esc(l)}</span>`).join("")}</td>
              <td style="color:var(--gold)">${t.score}</td>
            </tr>`).join("")}</tbody></table>`
        : UI.empty("No triangles found", "No 3-cliques in this network.", "✓");

      const st2 = d.stars || [];
      document.getElementById("mo-stars").innerHTML = st2.length
        ? `<table class="tbl"><thead><tr><th>Node</th><th>Degree</th></tr></thead><tbody>${
            st2.slice(0,60).map((s) => `<tr>
              <td><b>${UI.esc(s.label)}</b><div class="faint" style="font-size:10px">${UI.esc(s.type)}</div></td>
              <td><span class="badge review">${s.degree}</span></td>
            </tr>`).join("")}</tbody></table>`
        : UI.empty("No hub nodes", "No high-degree nodes found.", "✓");

      const ch = d.chains || [];
      document.getElementById("mo-chains").innerHTML = ch.length
        ? `<table class="tbl"><thead><tr><th>Chain (4-path)</th></tr></thead><tbody>${
            ch.slice(0,40).map((c) => `<tr><td style="font-size:11px">${(c.labels || []).map((l,i) => `${i>0?` <span style="color:var(--gold)">→</span> `:""}${UI.esc(l)}`).join("")}</td></tr>`).join("")}</tbody></table>`
        : UI.empty("No chains", "No 4-person chain paths found.", "✓");
    } catch (_) {
      document.getElementById("mo-triangles").innerHTML = UI.empty("Detection failed","","⚠");
    }
  }

  // ── ACO Patrol ───────────────────────────────────────────────────────────
  async function runACO() {
    const units = document.getElementById("aco-units").value;
    const n_ants = document.getElementById("aco-ants").value;
    const n_iter = document.getElementById("aco-iter").value;
    document.getElementById("aco-table").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("aco-cov").textContent = "Running ACO…";
    try {
      const r = await API.get("/patrol/aco", { units, n_ants, n_iter, resolution: 8 });
      const asgn = r.assignments || [];
      document.getElementById("aco-cov").innerHTML = `ACO coverage: <b style="color:var(--gold)">${(r.coverage_pct||0).toFixed(1)}%</b> · ${UI.esc(r.summary||"")}`;
      document.getElementById("aco-table").innerHTML = asgn.length
        ? `<table class="tbl"><thead><tr><th>#</th><th>Location</th><th>Share</th><th>Pheromone</th></tr></thead><tbody>${
            asgn.map((a,i) => `<tr>
              <td><b style="color:var(--gold)">${a.aco_rank||i+1}</b></td>
              <td>${UI.esc(a.label||a.district||"—")}</td>
              <td class="dim">${((a.expected_share||0)*100).toFixed(1)}%</td>
              <td class="dim">${a.aco_pheromone||"—"}</td>
            </tr>`).join("")}</tbody></table>`
        : UI.empty("No assignments", "ACO returned no results.", "◈");
      renderACOMap(asgn);
    } catch (_) {
      document.getElementById("aco-table").innerHTML = UI.empty("ACO failed","","⚠");
    }
  }

  function renderACOMap(asgn) {
    if (!mapReady || !asgn.length) return;
    const pts = { type:"FeatureCollection", features: asgn.filter(a=>a.lat&&a.lng).map(a=>({
      type:"Feature", geometry:{type:"Point",coordinates:[a.lng,a.lat]}, properties:{_w:a.aco_pheromone||1}
    }))};
    MapKit.setHeatLayer(map, "aco-pts", pts, true);
    const lngs = asgn.map(a=>a.lng).filter(x=>x), lats = asgn.map(a=>a.lat).filter(x=>x);
    if (lngs.length) map.fitBounds([[Math.min(...lngs),Math.min(...lats)],[Math.max(...lngs),Math.max(...lats)]],{padding:40,maxZoom:9,duration:600});
  }

  // ── Differential Privacy ─────────────────────────────────────────────────
  async function runDP() {
    const epsilon = document.getElementById("dp-eps").value;
    document.getElementById("dp-table").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("dp-info").innerHTML = "";
    try {
      const d = await API.get("/hotspots/dp", { epsilon, resolution: 8 });
      document.getElementById("dp-info").innerHTML = `
        <div class="row wrap" style="gap:10px;margin-bottom:6px">
          ${[["ε",d.epsilon],["Noise scale",d.noise_scale],["True total",d.original_total],["DP total",d.dp_total]]
            .map(([l,v]) => `<div class="kpi" style="min-width:90px;padding:8px 12px"><div class="kpi-label">${l}</div><div class="kpi-value" style="font-size:18px">${v}</div></div>`).join("")}
        </div>
        <div class="banner info" style="margin-bottom:0"><span class="b-ico">🔒</span><div><b>Privacy guarantee:</b> ${UI.esc(d.privacy_guarantee||"")} — (ε=${d.epsilon}, δ=0)-DP via Laplace mechanism with sensitivity=${d.sensitivity||1}.</div></div>`;
      const cells = (d.cells||[]).slice(0,60);
      document.getElementById("dp-table").innerHTML = cells.length
        ? `<table class="tbl"><thead><tr><th>H3 cell</th><th>District</th><th>True count</th><th>DP count (noisy)</th><th>Noise</th></tr></thead><tbody>${
            cells.map((c) => {
              const orig = c.count_orig != null ? c.count_orig : (c.count_dp != null ? "hidden" : c.count);
              const dp = c.count_dp != null ? c.count_dp : c.count;
              const noise = (typeof orig === "number" && typeof dp === "number") ? (dp-orig).toFixed(2) : "—";
              return `<tr>
                <td class="mono" style="font-size:10px">${UI.esc((c.h3||"").slice(0,12))}</td>
                <td class="dim">${UI.esc(UI.val(c.district))}</td>
                <td>${UI.num(c.count_orig!=null?c.count_orig:"—")}</td>
                <td style="color:var(--gold)">${dp}</td>
                <td class="dim" style="font-size:11px">${noise}</td>
              </tr>`;
            }).join("")}</tbody></table>`
        : UI.empty("No hotspot data","","⊕");
    } catch (_) {
      document.getElementById("dp-table").innerHTML = UI.empty("DP failed","","⚠");
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    const sl = document.getElementById("aco-units");
    sl.addEventListener("input", () => { document.getElementById("aco-units-val").textContent = sl.value; });
    document.getElementById("mo-run").addEventListener("click", runMotifs);
    document.getElementById("aco-run").addEventListener("click", runACO);
    document.getElementById("dp-run").addEventListener("click", runDP);
    // Init ACO map
    map = MapKit.createMap("aco-map-canvas", { center: [76.4, 14.9], zoom: 5.6, pitch: 0 });
    map.on("load", () => { mapReady = true; });
    // Auto-load all three on mount
    runMotifs();
    runACO();
    runDP();
    mounted = true;
  }

  function onShow() { if (map) setTimeout(() => map.resize(), 80); UI.resizeCharts(); }

  return { mount, onShow };
})();
