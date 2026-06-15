/* ============================================================
   patrol.js — Patrol Planning: place-based unit allocation to
   forecast risk, with a coverage gauge and a deck.gl hex map.
   ============================================================ */
Views.Patrol = (() => {
  let el, map, deckOverlay, assignments = [];

  const RASTER_STYLE = {
    version: 8,
    sources: { osm: { type: "raster", tiles: ["https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png", "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OSM © CARTO" } },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  };

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
          <h3 class="panel-title"><span class="dotaccent"></span> Recommended deployment</h3>
          <div class="map-shell" style="height:300px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)"><div id="patrol-map-canvas"></div></div>
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
    if (!deckOverlay) return;
    const valid = assignments.filter((a) => a.h3);
    const maxU = Math.max(1, ...valid.map((a) => a.units || 1));
    const layer = new deck.H3HexagonLayer({
      id: "patrol-hex", data: valid, pickable: true, extruded: true, elevationScale: 800,
      getHexagon: (d) => d.h3, getElevation: (d) => (d.expected_share || 0.05) * 10,
      getFillColor: (d) => { const [r, g, b] = UI.rampColor((d.units || 1) / maxU); return [r, g, b, 220]; },
      opacity: 0.85,
    });
    deckOverlay.setProps({
      layers: [layer],
      getTooltip: ({ object }) => object ? {
        html: `<div class="deck-tip"><b>${object.units} unit(s)</b><br/>${UI.esc(object.top_type || "")}<br/>${UI.esc(object.rationale || "")}</div>`,
        style: { background: "transparent" },
      } : null,
    });
  }

  function table() {
    const host = document.getElementById("pt-table");
    if (!assignments.length) { host.innerHTML = UI.empty("No assignments", "Run the optimiser.", "◈"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>#</th><th>Cell</th><th>Units</th><th>Coverage</th><th>Top type</th><th>Rationale</th></tr></thead><tbody>${
      assignments.map((a, i) => `<tr data-lat="${a.lat ?? ""}" data-lng="${a.lng ?? ""}" style="cursor:pointer">
        <td><b style="color:var(--gold)">${i + 1}</b></td>
        <td class="mono" style="font-size:10.5px">${UI.esc((a.h3 || "—").slice(0, 12))}</td>
        <td><span class="badge" style="background:#C9A22722;color:#C9A227;border-color:#C9A22755">${a.units || 1}</span></td>
        <td class="dim">${((a.expected_share || 0) * 100).toFixed(1)}%</td>
        <td>${UI.esc(UI.val(a.top_type))}</td>
        <td class="dim" style="font-size:11.5px">${UI.esc(UI.val(a.rationale))}</td>
      </tr>`).join("")}</tbody></table>`;
    host.querySelectorAll("tr[data-lat]").forEach((r) => r.addEventListener("click", () => {
      const lat = parseFloat(r.dataset.lat), lng = parseFloat(r.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng) && map) map.flyTo({ center: [lng, lat], zoom: 11, pitch: 45 });
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
    } catch (e) {
      document.getElementById("pt-table").innerHTML = UI.empty("Failed", String(e.message), "⚠");
    }
  }

  function initMap() {
    map = new maplibregl.Map({ container: "patrol-map-canvas", style: RASTER_STYLE, center: [76.5, 14.5], zoom: 5.4, pitch: 42, attributionControl: false });
    deckOverlay = new deck.MapboxOverlay({ layers: [] });
    map.addControl(deckOverlay);
    map.on("load", () => { if (assignments.length) renderMap(); });
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    const sl = document.getElementById("pt-units");
    sl.addEventListener("input", () => { document.getElementById("pt-units-val").textContent = sl.value; });
    document.getElementById("pt-run").addEventListener("click", run);
    initMap();
    run();
  }
  function onShow() { if (map) setTimeout(() => map.resize(), 60); UI.resizeCharts(); }

  return { mount, onShow };
})();
