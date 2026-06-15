/* ============================================================
   hotspots.js — MapLibre native 3D hex + heatmap (deck.gl-free).
   Click any cell to see its location + recent FIRs.
   ============================================================ */
Views.Hotspots = (() => {
  let el, map, mounted = false, ready = false;
  let mode = "hotspots";      // 'hotspots' | 'emerging'
  let layerType = "hex";      // 'hex' | 'heat'
  let lastCells = [];

  const EMERGING_RGB = {
    new: "rgb(226,87,76)", intensifying: "rgb(230,147,47)",
    persistent: "rgb(61,127,214)", diminishing: "rgb(59,167,118)",
    sporadic: "rgb(155,127,214)", none: "rgb(120,130,150)",
  };

  function shell() {
    return `
      <div class="map-shell">
        <div id="map-canvas"></div>
        <div class="map-overlay map-controls">
          <div class="panel">
            <div class="toggle-group" id="hs-mode">
              <button class="active" data-mode="hotspots">Hotspots</button>
              <button data-mode="emerging">Emerging trends</button>
            </div>
          </div>
          <div class="panel" id="hs-filters">
            <div class="controls">
              <div class="ctrl"><span class="ctrl-label">Crime type</span>
                <select id="hs-type"><option value="">All types</option></select></div>
              <div class="ctrl"><span class="ctrl-label">Resolution</span>
                <select id="hs-res"><option value="7">R7 (coarse)</option><option value="8" selected>R8</option><option value="9">R9 (fine)</option></select></div>
              <div class="ctrl"><span class="ctrl-label">From</span><input type="date" id="hs-from" /></div>
              <div class="ctrl"><span class="ctrl-label">To</span><input type="date" id="hs-to" /></div>
              <div class="ctrl"><span class="ctrl-label">Layer</span>
                <div class="toggle-group" id="hs-layer">
                  <button class="active" data-layer="hex">3D Hex</button>
                  <button data-layer="heat">Heatmap</button>
                </div></div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary" id="hs-apply">Apply</button></div>
            </div>
          </div>
        </div>
        <div class="map-overlay map-side">
          <div class="panel panel-pad" style="flex:0 0 auto">
            <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> <span id="hs-legend-title">Intensity</span></h3>
            <div class="legend" id="hs-legend"></div>
            <div class="faint" style="font-size:10.5px;margin-top:8px">Tip: click any cell on the map to see that location's recent FIRs.</div>
          </div>
          <div class="panel panel-pad" style="flex:1 1 auto;min-height:0;display:flex;flex-direction:column">
            <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> Top locations <span class="faint" id="hs-count" style="margin-left:auto;font-weight:600"></span></h3>
            <div class="hot-list scroll" id="hs-list"></div>
          </div>
        </div>
      </div>`;
  }

  function legendHTML() {
    if (mode === "emerging") {
      document.getElementById("hs-legend-title").textContent = "Trend";
      return Object.entries({ new: "New", intensifying: "Intensifying", persistent: "Persistent", diminishing: "Diminishing", sporadic: "Sporadic" })
        .map(([k, lbl]) => `<div class="legend-row"><span class="legend-sw" style="background:${EMERGING_RGB[k]}"></span>${lbl}</div>`).join("");
    }
    document.getElementById("hs-legend-title").textContent = "Intensity";
    const stops = [["Low", 0.05], ["", 0.35], ["Medium", 0.6], ["", 0.8], ["High / hotspot", 1]];
    return stops.map(([lbl, t]) => `<div class="legend-row"><span class="legend-sw" style="background:${MapKit.ramp(t)}"></span>${lbl || "&nbsp;"}</div>`).join("");
  }

  function valOf(c) { return mode === "hotspots" ? (c.count || 0) : (c.recent || 0); }

  function render() {
    if (!ready) return;
    const cells = lastCells;
    const max = Math.max(1, ...cells.map(valOf));
    const hex = MapKit.hexFC(cells, valOf, (c, v) => ({
      _height: (v / max) * 6500,
      _color: mode === "hotspots" ? MapKit.ramp(v / max) : (EMERGING_RGB[c.category] || EMERGING_RGB.none),
    }));
    const pts = MapKit.pointFC(cells, valOf);
    map.getSource("hshex").setData(hex);
    map.getSource("hspts").setData(pts);
    MapKit.setVisible(map, "hshex-fill", layerType === "hex");
    MapKit.setVisible(map, "hshex-line", layerType === "hex");
    MapKit.setVisible(map, "hsheat", layerType === "heat");
    renderSide();
  }

  function renderSide() {
    document.getElementById("hs-legend").innerHTML = legendHTML();
    const list = document.getElementById("hs-list");
    const cnt = document.getElementById("hs-count");
    cnt.textContent = lastCells.length ? `${lastCells.length} cells` : "";
    if (!lastCells.length) { list.innerHTML = UI.empty("No cells for these filters", "Try a coarser resolution or wider date range.", "⬡"); return; }
    const sorted = [...lastCells].sort((a, b) => valOf(b) - valOf(a));
    list.innerHTML = sorted.slice(0, 40).map((c, i) => {
      const right = mode === "hotspots"
        ? `<div class="hc-count">${UI.num(c.count)}</div>`
        : `<span class="badge ${c.category === "new" || c.category === "intensifying" ? "review" : "neutral"}">${UI.title(c.category)}</span>`;
      const sub = mode === "hotspots" ? `Gi* ${UI.val(c.gi_score)} · ${UI.title(c.level || "—")}` : `${UI.num(c.recent)} recent · ${UI.num(c.baseline)} base`;
      return `<div class="hot-cell" data-lat="${c.lat ?? ""}" data-lng="${c.lng ?? ""}" data-h3="${UI.esc(c.h3 || "")}">
        <div class="hc-rank">${i + 1}</div>
        <div class="hc-meta"><div class="hc-h3">${UI.esc(c.label || c.district || "Unmapped area")}</div><div class="faint" style="font-size:10.5px">${sub}</div></div>
        ${right}</div>`;
    }).join("");
    list.querySelectorAll(".hot-cell").forEach((row) => row.addEventListener("click", () => {
      const lat = parseFloat(row.dataset.lat), lng = parseFloat(row.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng) && map) {
        map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 9.5), pitch: 50 });
        const c = lastCells.find((x) => x.h3 === row.dataset.h3);
        if (c) showDetail(c, [lng, lat]);
      }
    }));
  }

  async function showDetail(c, lngLat) {
    const label = c.label || c.district || "Selected location";
    const head = mode === "hotspots"
      ? `<div class="lp-row"><span>Incidents</span><span>${UI.num(c.count)}</span></div><div class="lp-row"><span>Gi* score</span><span>${UI.val(c.gi_score)}</span></div><div class="lp-row"><span>Level</span><span>${UI.title(c.level || "—")}</span></div>`
      : `<div class="lp-row"><span>Trend</span><span>${UI.title(c.category)}</span></div><div class="lp-row"><span>Recent</span><span>${UI.num(c.recent)}</span></div><div class="lp-row"><span>Baseline</span><span>${UI.num(c.baseline)}</span></div>`;
    const popup = new maplibregl.Popup({ closeButton: true, maxWidth: "300px" })
      .setLngLat(lngLat).setHTML(`<div class="loc-pop"><b>${UI.esc(label)}</b>${head}<div class="dim" style="margin-top:6px">Loading FIRs…</div></div>`).addTo(map);
    try {
      const ct = document.getElementById("hs-type").value;
      const r = await API.get("/crimes", { h3: c.h3, crime_type: ct, limit: 6 }, { silent: true });
      const items = r.items || [];
      const list = items.length
        ? items.map((x) => `<div class="lp-fir">${UI.esc(x.fir_number)} · ${UI.esc(x.crime_type)} · ${UI.date(x.occurred_at)}</div>`).join("")
        : `<div class="dim">No FIRs in this cell for the current filter.</div>`;
      popup.setHTML(`<div class="loc-pop"><b>${UI.esc(label)}</b>${head}<div style="margin-top:6px;border-top:1px solid rgba(255,255,255,.12);padding-top:6px"><div class="dim" style="margin-bottom:3px">Recent FIRs here:</div>${list}</div></div>`);
    } catch (_) {}
  }

  function ensureLayers() {
    const empty = { type: "FeatureCollection", features: [] };
    map.addSource("hshex", { type: "geojson", data: empty });
    map.addSource("hspts", { type: "geojson", data: empty });
    map.addLayer({
      id: "hshex-fill", type: "fill-extrusion", source: "hshex",
      paint: { "fill-extrusion-color": ["coalesce", ["get", "_color"], "#1F7A8C"], "fill-extrusion-height": ["coalesce", ["get", "_height"], 0], "fill-extrusion-opacity": 0.8 },
    });
    map.addLayer({ id: "hshex-line", type: "line", source: "hshex", paint: { "line-color": ["coalesce", ["get", "_color"], "#1F7A8C"], "line-width": 0.6, "line-opacity": 0.5 } });
    map.addLayer({
      id: "hsheat", type: "heatmap", source: "hspts", layout: { visibility: "none" },
      paint: {
        "heatmap-weight": ["interpolate", ["linear"], ["get", "_w"], 0, 0, 30, 1],
        "heatmap-radius": 36, "heatmap-intensity": 1.1, "heatmap-opacity": 0.85,
        "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"], 0, "rgba(0,0,0,0)", 0.2, "rgb(31,122,140)", 0.45, "rgb(43,166,189)", 0.65, "rgb(201,162,39)", 0.82, "rgb(230,147,47)", 1, "rgb(226,87,76)"],
      },
    });
    map.addLayer({ id: "hshit", type: "circle", source: "hspts", paint: { "circle-radius": 15, "circle-color": "#ffffff", "circle-opacity": 0.01 } });
    map.on("click", "hshit", (e) => { const f = e.features && e.features[0]; if (f) { const c = lastCells.find((x) => x.h3 === f.properties.h3) || f.properties; showDetail(c, e.lngLat); } });
    map.on("mouseenter", "hshit", () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "hshit", () => { map.getCanvas().style.cursor = ""; });
    ready = true;
  }

  async function load() {
    const list = document.getElementById("hs-list");
    list && (list.innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`);
    try {
      const res = document.getElementById("hs-res").value;
      if (mode === "hotspots") {
        const r = await API.get("/hotspots", {
          resolution: res, crime_type: document.getElementById("hs-type").value,
          date_from: document.getElementById("hs-from").value, date_to: document.getElementById("hs-to").value,
        });
        lastCells = (r.cells || []);
      } else {
        const r = await API.get("/emerging", { resolution: res, period_days: 90 });
        lastCells = (r.cells || []);
      }
    } catch (_) { lastCells = []; }
    render();
  }

  function initMap() {
    map = MapKit.createMap("map-canvas", { center: [76.0, 14.9], zoom: 6, pitch: 45 });
    map.on("load", () => { ensureLayers(); load(); });
  }

  function bind() {
    document.querySelectorAll("#hs-mode button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("#hs-mode button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active"); mode = b.dataset.mode;
      document.getElementById("hs-filters").style.opacity = mode === "emerging" ? ".55" : "1";
      load();
    }));
    document.querySelectorAll("#hs-layer button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("#hs-layer button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active"); layerType = b.dataset.layer; render();
    }));
    document.getElementById("hs-apply").addEventListener("click", load);
    document.getElementById("hs-res").addEventListener("change", load);
    document.getElementById("hs-type").addEventListener("change", load);
  }

  function applyExternalFilter(f) {
    if (!f) return;
    mode = "hotspots";
    document.querySelectorAll("#hs-mode button").forEach((x) => x.classList.toggle("active", x.dataset.mode === "hotspots"));
    if (f.crime_type) document.getElementById("hs-type").value = f.crime_type;
    if (f.date_from) document.getElementById("hs-from").value = f.date_from;
    if (f.date_to) document.getElementById("hs-to").value = f.date_to;
    load();
  }

  function mount(node) {
    el = node; el.classList.add("fullbleed"); el.innerHTML = shell();
    const meta = App.state.meta || {};
    App.fillSelect(document.getElementById("hs-type"), meta.crime_types, "All types");
    const dr = meta.date_range || {};
    if (dr.min) document.getElementById("hs-from").min = dr.min;
    if (dr.max) document.getElementById("hs-to").max = dr.max;
    document.getElementById("hs-legend").innerHTML = legendHTML();
    bind(); initMap(); mounted = true;
  }

  function onShow() {
    if (map) setTimeout(() => map.resize(), 80);
    if (App.state.pendingFilter) { applyExternalFilter(App.state.pendingFilter); App.state.pendingFilter = null; }
  }

  return { mount, onShow };
})();
