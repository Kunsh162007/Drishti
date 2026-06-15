/* ============================================================
   predictive.js — place-based risk (ranked + small deck hex)
   and explainable anomalies table.
   ============================================================ */
Views.Predictive = (() => {
  let el, map, deckOverlay, mounted = false, riskCells = [];

  const RASTER_STYLE = {
    version: 8,
    sources: { osm: { type: "raster", tiles: ["https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png","https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OSM © CARTO" } },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  };

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">◔</span> Predictive &amp; Anomaly</h1>
          <div class="view-sub">Forward-looking, explainable signals to guide patrol allocation and case triage.</div>
        </div>
      </div>

      <div class="banner info">
        <span class="b-ico">🛈</span>
        <div><b>Decision-support, not verdicts.</b> Risk scores are <b>place-based</b> (hex grid) and <b>explainable</b> — every score lists its drivers.
        DRISHTI never produces person-level risk or "predictive policing" of individuals.</div>
      </div>

      <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:16px">
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Highest-risk locations</h3>
          <div class="map-shell" style="height:300px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)">
            <div id="risk-map-canvas"></div>
          </div>
          <div class="tbl-wrap scroll mt12" style="max-height:240px" id="risk-list"></div>
        </div>

        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Flagged anomalies <span class="faint" id="anom-count" style="margin-left:auto;font-weight:600"></span></h3>
          <div class="tbl-wrap scroll" style="max-height:580px" id="anom-table"></div>
        </div>
      </div>`;
  }

  function renderRiskList(cells) {
    const host = document.getElementById("risk-list");
    if (!cells.length) { host.innerHTML = UI.empty("No risk cells", "Risk needs geocoded crimes.", "◔"); return; }
    const top = [...cells].sort((a, b) => (b.risk || 0) - (a.risk || 0)).slice(0, 40);
    host.innerHTML = `<table class="tbl"><thead><tr><th>#</th><th>Cell</th><th>Risk</th><th>Drivers</th></tr></thead><tbody>${
      top.map((c, i) => `<tr data-lat="${c.lat ?? ""}" data-lng="${c.lng ?? ""}" style="cursor:pointer">
        <td><b style="color:var(--gold)">${i + 1}</b></td>
        <td class="mono" style="font-size:10.5px">${UI.esc((c.h3 || "—").slice(0, 12))}</td>
        <td style="min-width:96px"><div class="row" style="gap:7px"><div class="score-bar" style="flex:1"><i style="width:${Math.round((c.risk || 0) * 100)}%"></i></div><span style="font-weight:700">${(c.risk ?? 0).toFixed(2)}</span></div></td>
        <td class="dim" style="font-size:11px">${(c.drivers || []).map((d) => `<span class="chip term" style="margin:1px">${UI.esc(d)}</span>`).join("") || "—"}</td>
      </tr>`).join("")}</tbody></table>`;
    host.querySelectorAll("tr[data-lat]").forEach((r) => r.addEventListener("click", () => {
      const lat = parseFloat(r.dataset.lat), lng = parseFloat(r.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng) && map) map.flyTo({ center: [lng, lat], zoom: 10, pitch: 45 });
    }));
  }

  function renderRiskMap(cells) {
    if (!deckOverlay) return;
    const valid = cells.filter((c) => c.h3);
    const layer = new deck.H3HexagonLayer({
      id: "risk-hex", data: valid, pickable: true, extruded: true, elevationScale: 600,
      getHexagon: (d) => d.h3, getElevation: (d) => (d.risk || 0),
      getFillColor: (d) => { const [r, g, b] = UI.rampColor(d.risk || 0); return [r, g, b, 210]; },
      opacity: 0.85,
    });
    deckOverlay.setProps({
      layers: [layer],
      getTooltip: ({ object }) => object ? {
        html: `<div class="deck-tip"><b>Risk ${(object.risk ?? 0).toFixed(2)}</b><br/>${(object.drivers || []).map(UI.esc).join("<br/>")}</div>`,
        style: { background: "transparent" },
      } : null,
    });
  }

  function renderAnomalies(items) {
    const host = document.getElementById("anom-table");
    document.getElementById("anom-count").textContent = items.length ? `${items.length} flagged` : "";
    if (!items.length) { host.innerHTML = UI.empty("No anomalies", "Nothing exceeded the detection thresholds.", "✓"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>District</th><th>Score</th><th>Why flagged</th></tr></thead><tbody>${
      items.map((a) => `<tr>
        <td class="mono">${UI.esc(a.fir_number)}</td>
        <td>${UI.esc(UI.val(a.crime_type))}</td>
        <td class="dim">${UI.esc(UI.val(a.district))}</td>
        <td style="min-width:90px"><div class="row" style="gap:6px"><div class="score-bar" style="flex:1"><i style="width:${Math.round((a.score || 0) * 100)}%"></i></div><span style="font-weight:700">${(a.score ?? 0).toFixed(2)}</span></div></td>
        <td>${(a.reasons || []).map((r) => `<span class="chip term" style="margin:1px">${UI.esc(r)}</span>`).join("") || "—"}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  async function load() {
    document.getElementById("anom-table").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("risk-list").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    const [risk, anom] = await Promise.allSettled([API.get("/risk", { resolution: 8 }), API.get("/anomalies", { limit: 60 })]);
    if (risk.status === "fulfilled") {
      riskCells = (risk.value.cells || []);
      renderRiskList(riskCells);
      renderRiskMap(riskCells);
    } else { document.getElementById("risk-list").innerHTML = UI.empty("Risk unavailable", "", "⚠"); }
    if (anom.status === "fulfilled") renderAnomalies(anom.value.items || []);
    else document.getElementById("anom-table").innerHTML = UI.empty("Anomalies unavailable", "", "⚠");
  }

  function initMap() {
    map = new maplibregl.Map({ container: "risk-map-canvas", style: RASTER_STYLE, center: [75.7, 15.3], zoom: 5.6, pitch: 40, attributionControl: false });
    deckOverlay = new deck.MapboxOverlay({ layers: [] });
    map.addControl(deckOverlay);
    map.on("load", () => { if (riskCells.length) renderRiskMap(riskCells); });
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    initMap();
    load();
    mounted = true;
  }
  function onShow() { if (map) setTimeout(() => map.resize(), 60); }

  return { mount, onShow };
})();
