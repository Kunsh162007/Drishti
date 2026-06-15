/* ============================================================
   predictive.js — place-based risk (MapLibre 3D hex, clickable)
   + explainable anomalies table.
   ============================================================ */
Views.Predictive = (() => {
  let el, map, ready = false, riskCells = [];

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
        <div><b>Decision-support, not verdicts.</b> Risk is <b>place-based</b> (hex grid) and <b>explainable</b> — every score lists its drivers. DRISHTI never produces person-level risk.</div>
      </div>
      <div class="grid" style="grid-template-columns:1.05fr .95fr;gap:16px">
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Highest-risk locations <span class="faint" style="margin-left:auto;font-weight:600;text-transform:none;letter-spacing:0">click a hex for details</span></h3>
          <div class="map-shell" style="height:320px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)"><div id="risk-map-canvas"></div></div>
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
    host.innerHTML = `<table class="tbl"><thead><tr><th>#</th><th>Location</th><th>Risk</th><th>Drivers</th></tr></thead><tbody>${
      top.map((c, i) => `<tr data-lat="${c.lat ?? ""}" data-lng="${c.lng ?? ""}" data-h3="${UI.esc(c.h3 || "")}" style="cursor:pointer">
        <td><b style="color:var(--gold)">${i + 1}</b></td>
        <td>${UI.esc(c.label || c.district || "Unmapped area")}</td>
        <td style="min-width:96px"><div class="row" style="gap:7px"><div class="score-bar" style="flex:1"><i style="width:${Math.round((c.risk || 0) * 100)}%"></i></div><span style="font-weight:700">${(c.risk ?? 0).toFixed(2)}</span></div></td>
        <td class="dim" style="font-size:11px">${(c.drivers || []).map((d) => `<span class="chip term" style="margin:1px">${UI.esc(d)}</span>`).join("") || "—"}</td>
      </tr>`).join("")}</tbody></table>`;
    host.querySelectorAll("tr[data-lat]").forEach((r) => r.addEventListener("click", () => {
      const lat = parseFloat(r.dataset.lat), lng = parseFloat(r.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng) && map) {
        map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 9.5), pitch: 50 });
        const c = riskCells.find((x) => x.h3 === r.dataset.h3);
        if (c) showDetail(c, [lng, lat]);
      }
    }));
  }

  function renderRiskMap(cells) {
    if (!ready) return;
    const max = Math.max(0.01, ...cells.map((c) => c.risk || 0));
    const hex = MapKit.hexFC(cells, (c) => c.risk || 0, (c, v) => ({ _height: (v / max) * 6000, _color: MapKit.ramp(v / max) }));
    map.getSource("rkhex").setData(hex);
    map.getSource("rkpts").setData(MapKit.pointFC(cells, (c) => c.risk || 0));
  }

  async function showDetail(c, lngLat) {
    const label = c.label || c.district || "Selected location";
    const head = `<div class="lp-row"><span>Risk</span><span>${(c.risk ?? 0).toFixed(2)}</span></div>` +
      `<div style="margin-top:4px" class="dim">${(c.drivers || []).map((d) => `<span class="chip term" style="margin:1px">${UI.esc(d)}</span>`).join("") || ""}</div>`;
    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
      .setLngLat(lngLat).setHTML(`<div class="loc-pop"><b>${UI.esc(label)}</b>${head}<div class="dim" style="margin-top:6px">Loading FIRs…</div></div>`).addTo(map);
    try {
      const r = await API.get("/crimes", { h3: c.h3, limit: 6 }, { silent: true });
      const items = r.items || [];
      const list = items.length ? items.map((x) => `<div class="lp-fir">${UI.esc(x.fir_number)} · ${UI.esc(x.crime_type)} · ${UI.date(x.occurred_at)}</div>`).join("") : `<div class="dim">No FIRs in this cell.</div>`;
      popup.setHTML(`<div class="loc-pop"><b>${UI.esc(label)}</b>${head}<div style="margin-top:6px;border-top:1px solid rgba(255,255,255,.12);padding-top:6px"><div class="dim" style="margin-bottom:3px">Recent FIRs here:</div>${list}</div></div>`);
    } catch (_) {}
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
    document.getElementById("anom-table").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("risk-list").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    const [risk, anom] = await Promise.allSettled([API.get("/risk", { resolution: 8 }), API.get("/anomalies", { limit: 60 })]);
    if (risk.status === "fulfilled") { riskCells = risk.value.cells || []; renderRiskList(riskCells); renderRiskMap(riskCells); }
    else document.getElementById("risk-list").innerHTML = UI.empty("Risk unavailable", "", "⚠");
    if (anom.status === "fulfilled") renderAnomalies(anom.value.items || []);
    else document.getElementById("anom-table").innerHTML = UI.empty("Anomalies unavailable", "", "⚠");
  }

  function ensureLayers() {
    const empty = { type: "FeatureCollection", features: [] };
    map.addSource("rkhex", { type: "geojson", data: empty });
    map.addSource("rkpts", { type: "geojson", data: empty });
    map.addLayer({ id: "rkhex-fill", type: "fill-extrusion", source: "rkhex", paint: { "fill-extrusion-color": ["coalesce", ["get", "_color"], "#1F7A8C"], "fill-extrusion-height": ["coalesce", ["get", "_height"], 0], "fill-extrusion-opacity": 0.82 } });
    map.addLayer({ id: "rkhex-line", type: "line", source: "rkhex", paint: { "line-color": ["coalesce", ["get", "_color"], "#1F7A8C"], "line-width": 0.5, "line-opacity": 0.45 } });
    map.addLayer({ id: "rkhit", type: "circle", source: "rkpts", paint: { "circle-radius": 14, "circle-color": "#fff", "circle-opacity": 0.01 } });
    map.on("click", "rkhit", (e) => { const f = e.features && e.features[0]; if (f) { const c = riskCells.find((x) => x.h3 === f.properties.h3) || f.properties; showDetail(c, e.lngLat); } });
    map.on("mouseenter", "rkhit", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "rkhit", () => { map.getCanvas().style.cursor = ""; });
    ready = true;
  }

  function initMap() {
    map = MapKit.createMap("risk-map-canvas", { center: [76.0, 14.9], zoom: 5.6, pitch: 45 });
    map.on("load", () => { ensureLayers(); if (riskCells.length) renderRiskMap(riskCells); });
  }

  function mount(node) {
    el = node; el.innerHTML = shell();
    initMap(); load();
  }
  function onShow() { if (map) setTimeout(() => map.resize(), 80); }

  return { mount, onShow };
})();
