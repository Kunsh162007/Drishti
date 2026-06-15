/* ============================================================
   patrol.js — Patrol Planning: place-based unit allocation,
   coverage gauge, and a MapLibre 3D hex deployment map.
   ============================================================ */
Views.Patrol = (() => {
  let el, map, ready = false, assignments = [];

  function shell() {
    return `
      <div class="view-head"><div>
        <h1 class="view-title"><span class="vt-ico">◈</span> Patrol Planning</h1>
        <div class="view-sub">Allocate patrol units to forecast-risk locations to maximise coverage.</div>
      </div></div>
      <div class="banner info"><span class="b-ico">🛈</span><div>
        <b>Place-based allocation.</b> Units are assigned to high-risk <b>locations</b> (hex grid), never to target individuals.</div></div>
      <div class="controls">
        <div class="ctrl"><span class="ctrl-label">Patrol units</span>
          <input type="range" id="pt-units" min="5" max="50" value="15" style="vertical-align:middle">
          <b id="pt-units-val" style="color:var(--gold);margin-left:8px">15</b></div>
        <button class="btn btn-primary" id="pt-run">Optimise allocation</button>
        <span class="dim" id="pt-cov" style="margin-left:auto;align-self:center"></span>
      </div>
      <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:16px;margin-top:12px">
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Recommended deployment <span class="faint" style="margin-left:auto;font-weight:600;text-transform:none;letter-spacing:0">click a hex for details</span></h3>
          <div class="map-shell" style="height:320px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)"><div id="patrol-map-canvas"></div></div>
          <div class="row mt12" style="gap:16px;align-items:center">
            <div class="chart" id="pt-gauge" style="height:150px;width:180px"></div>
            <div class="dim" id="pt-summary" style="flex:1;font-size:12.5px"></div>
          </div>
        </div>
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Assignments</h3>
          <div class="tbl-wrap scroll" style="max-height:560px" id="pt-table"></div>
        </div>
      </div>`;
  }

  function gauge(pct) {
    UI.mountChart("pt-gauge", {
      series: [{
        type: "gauge", radius: "100%", startAngle: 210, endAngle: -30, min: 0, max: 100,
        progress: { show: true, width: 10, itemStyle: { color: "#C9A227" } },
        axisLine: { lineStyle: { width: 10, color: [[1, "rgba(230,237,245,.12)"]] } },
        axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, pointer: { show: false },
        anchor: { show: false }, title: { show: false },
        detail: { valueAnimation: true, formatter: "{value}%", color: "#E6EDF5", fontSize: 22, offsetCenter: [0, 0] },
        data: [{ value: Math.round(pct || 0) }],
      }],
    });
  }

  function renderMap() {
    if (!ready) return;
    const maxU = Math.max(1, ...assignments.map((a) => a.units || 1));
    const hex = MapKit.hexFC(assignments, (a) => a.units || 1, (a, v) => ({ _height: (v / maxU) * 6000 + 800, _color: MapKit.ramp(v / maxU) }));
    map.getSource("pthex").setData(hex);
    map.getSource("ptpts").setData(MapKit.pointFC(assignments, (a) => a.units || 1));
  }

  function showDetail(a, lngLat) {
    const label = a.label || a.district || "Selected location";
    new maplibregl.Popup({ closeButton: true, maxWidth: "300px" }).setLngLat(lngLat).setHTML(
      `<div class="loc-pop"><b>${UI.esc(label)}</b>
       <div class="lp-row"><span>Units</span><span>${a.units || 1}</span></div>
       <div class="lp-row"><span>Coverage</span><span>${((a.expected_share || 0) * 100).toFixed(1)}%</span></div>
       <div class="lp-row"><span>Top type</span><span>${UI.esc(UI.val(a.top_type))}</span></div>
       <div class="dim" style="margin-top:6px">${UI.esc(UI.val(a.rationale))}</div></div>`).addTo(map);
  }

  function table() {
    const host = document.getElementById("pt-table");
    if (!assignments.length) { host.innerHTML = UI.empty("No assignments", "Run the optimiser.", "◈"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>#</th><th>Location</th><th>Units</th><th>Coverage</th><th>Top type</th></tr></thead><tbody>${
      assignments.map((a, i) => `<tr data-lat="${a.lat ?? ""}" data-lng="${a.lng ?? ""}" data-h3="${UI.esc(a.h3 || "")}" style="cursor:pointer">
        <td><b style="color:var(--gold)">${i + 1}</b></td>
        <td>${UI.esc(a.label || a.district || "Unmapped area")}</td>
        <td><span class="badge" style="background:#C9A22722;color:#C9A227;border-color:#C9A22755">${a.units || 1}</span></td>
        <td class="dim">${((a.expected_share || 0) * 100).toFixed(1)}%</td>
        <td>${UI.esc(UI.val(a.top_type))}</td>
      </tr>`).join("")}</tbody></table>`;
    host.querySelectorAll("tr[data-lat]").forEach((r) => r.addEventListener("click", () => {
      const lat = parseFloat(r.dataset.lat), lng = parseFloat(r.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng) && map) { map.flyTo({ center: [lng, lat], zoom: 11, pitch: 50 }); const a = assignments.find((x) => x.h3 === r.dataset.h3); if (a) showDetail(a, [lng, lat]); }
    }));
  }

  async function run() {
    const units = +document.getElementById("pt-units").value;
    document.getElementById("pt-table").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const r = await API.get("/patrol/optimize", { resolution: 8, units });
      assignments = r.assignments || [];
      document.getElementById("pt-cov").textContent = `${(r.coverage_pct ?? 0).toFixed(1)}% of recent incidents covered`;
      document.getElementById("pt-summary").textContent = r.summary || "";
      gauge(r.coverage_pct || 0); renderMap(); table();
    } catch (e) { document.getElementById("pt-table").innerHTML = UI.empty("Failed", String(e.message), "⚠"); }
  }

  function ensureLayers() {
    const empty = { type: "FeatureCollection", features: [] };
    map.addSource("pthex", { type: "geojson", data: empty });
    map.addSource("ptpts", { type: "geojson", data: empty });
    map.addLayer({ id: "pthex-fill", type: "fill-extrusion", source: "pthex", paint: { "fill-extrusion-color": ["coalesce", ["get", "_color"], "#C9A227"], "fill-extrusion-height": ["coalesce", ["get", "_height"], 0], "fill-extrusion-opacity": 0.85 } });
    map.addLayer({ id: "pthex-line", type: "line", source: "pthex", paint: { "line-color": "#C9A227", "line-width": 0.6, "line-opacity": 0.5 } });
    map.addLayer({ id: "pthit", type: "circle", source: "ptpts", paint: { "circle-radius": 16, "circle-color": "#fff", "circle-opacity": 0.01 } });
    map.on("click", "pthit", (e) => { const f = e.features && e.features[0]; if (f) { const a = assignments.find((x) => x.h3 === f.properties.h3) || f.properties; showDetail(a, e.lngLat); } });
    map.on("mouseenter", "pthit", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "pthit", () => { map.getCanvas().style.cursor = ""; });
    ready = true;
  }

  function initMap() {
    map = MapKit.createMap("patrol-map-canvas", { center: [76.0, 14.9], zoom: 5.6, pitch: 45 });
    map.on("load", () => { ensureLayers(); if (assignments.length) renderMap(); });
  }

  function mount(node) {
    el = node; el.innerHTML = shell();
    const sl = document.getElementById("pt-units");
    sl.addEventListener("input", () => { document.getElementById("pt-units-val").textContent = sl.value; });
    document.getElementById("pt-run").addEventListener("click", run);
    initMap(); run();
  }
  function onShow() { if (map) setTimeout(() => map.resize(), 80); UI.resizeCharts(); }

  return { mount, onShow };
})();
