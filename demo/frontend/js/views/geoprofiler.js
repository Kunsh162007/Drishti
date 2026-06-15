/* ============================================================
   geoprofiler.js — Rossmo CGT geographic profiling.
   Probability surface + predicted anchor point on MapLibre.
   ============================================================ */
Views.Geoprofiler = (() => {
  let el, map, ready = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⊕</span> Geographic Profiling</h1>
          <div class="view-sub">Rossmo's Criminal Geographic Targeting — predicts offender anchor points from linked crime locations. Used by 30+ national police forces.</div>
        </div>
      </div>
      <div class="banner info"><span class="b-ico">🛈</span><div><b>Place-based inference only.</b> The probability surface identifies likely <em>activity nodes</em> (home, workplace, associate's address) from the spatial pattern of crimes. It is an investigative lead — not evidence.</div></div>
      <div class="panel panel-pad" style="margin-bottom:16px">
        <div class="row wrap" style="justify-content:space-between">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Profile configuration</h3>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Crime type</span>
              <select id="gp-type"><option value="">All types</option></select></div>
            <div class="ctrl"><span class="ctrl-label">From</span>
              <input type="date" id="gp-from"/></div>
            <div class="ctrl"><span class="ctrl-label">To</span>
              <input type="date" id="gp-to"/></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="gp-run">Build Profile</button></div>
          </div>
        </div>
      </div>
      <div class="grid" style="grid-template-columns:1.4fr .6fr;gap:16px">
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> CGT Probability Surface <span class="faint" style="margin-left:8px;font-weight:600;text-transform:none">warm = high anchor-point probability</span></h3>
          <div class="map-shell" style="height:460px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)">
            <div id="gp-map-canvas" style="position:absolute;inset:0"></div>
          </div>
        </div>
        <div class="panel panel-pad" style="display:flex;flex-direction:column;gap:14px">
          <h3 class="panel-title"><span class="dotaccent"></span> Results</h3>
          <div id="gp-stats">${UI.empty("Run a profile", "Select a crime type and date range, then click Build Profile.", "⊕")}</div>
        </div>
      </div>`;
  }

  function renderStats(d) {
    const host = document.getElementById("gp-stats");
    if (!d || !d.anchor) { host.innerHTML = UI.empty("No anchor found", "Insufficient geocoded crimes for this filter.", "⊕"); return; }
    const p = d.params || {};
    host.innerHTML = `
      <div class="kpi accent-gold" style="margin-bottom:10px">
        <div class="kpi-label">Predicted anchor</div>
        <div class="kpi-value" style="font-size:16px">${d.anchor.lat.toFixed(4)}°N, ${d.anchor.lng.toFixed(4)}°E</div>
        <div class="kpi-foot">Highest-probability location</div>
      </div>
      <div class="grid" style="grid-template-columns:1fr 1fr;gap:8px;margin-bottom:12px">
        <div class="kpi accent-teal"><div class="kpi-label">Crimes profiled</div><div class="kpi-value">${UI.num(d.total_crimes)}</div></div>
        <div class="kpi"><div class="kpi-label">Unique locations</div><div class="kpi-value">${UI.num(d.unique_locs)}</div></div>
      </div>
      <div class="panel panel-pad" style="background:rgba(255,255,255,.04);font-size:12px">
        <div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="dim">Algorithm</span><span>Rossmo CGT</span></div>
        <div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="dim">Buffer zone</span><span>${p.buffer_km || 1.5} km</span></div>
        <div class="row" style="justify-content:space-between;margin-bottom:6px"><span class="dim">Decay exponent (f)</span><span>${p.f || 1.2}</span></div>
        <div class="row" style="justify-content:space-between"><span class="dim">Grid steps</span><span>${p.grid_steps || 60}</span></div>
      </div>
      <div class="banner warn" style="margin-top:12px;font-size:11.5px"><span class="b-ico">⚠</span><div>Investigative lead only. Verify through standard evidence procedures before any operational action.</div></div>`;
  }

  function renderMap(d) {
    if (!ready) return;
    // Heatmap source for probability surface
    const fc = {
      type: "FeatureCollection",
      features: (d.points || []).map((p) => ({
        type: "Feature",
        geometry: { type: "Point", coordinates: [p.lng, p.lat] },
        properties: { _w: p.score },
      })),
    };
    MapKit.setHeatLayer(map, "gp-surface", fc, true);

    // Remove old anchor marker
    document.querySelectorAll(".gp-anchor-marker").forEach((m) => m.remove());
    if (d.anchor) {
      const el2 = document.createElement("div");
      el2.className = "gp-anchor-marker";
      el2.style.cssText = "width:22px;height:22px;border-radius:50%;background:#C9A227;border:3px solid #fff;box-shadow:0 0 16px rgba(201,162,39,.8);cursor:pointer";
      el2.title = "Predicted anchor point";
      new maplibregl.Marker({ element: el2 })
        .setLngLat([d.anchor.lng, d.anchor.lat])
        .setPopup(new maplibregl.Popup({ offset: 14 }).setHTML(
          `<div class="loc-pop"><b>Predicted Anchor Point</b>
           <div class="lp-row"><span>Lat</span><span>${d.anchor.lat.toFixed(5)}</span></div>
           <div class="lp-row"><span>Lng</span><span>${d.anchor.lng.toFixed(5)}</span></div>
           <div class="dim" style="margin-top:6px;font-size:10.5px">Highest CGT probability cell. Investigate nearby addresses, workplaces, and habitual locations.</div></div>`
        ))
        .addTo(map);
      map.flyTo({ center: [d.anchor.lng, d.anchor.lat], zoom: 8, pitch: 0, duration: 1200 });
    }
  }

  async function run() {
    const crime_type = document.getElementById("gp-type").value;
    const date_from = document.getElementById("gp-from").value;
    const date_to = document.getElementById("gp-to").value;
    document.getElementById("gp-stats").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const d = await API.get("/geo-profile", { crime_type, date_from, date_to, resolution: 60 });
      renderStats(d);
      renderMap(d);
    } catch (_) {
      document.getElementById("gp-stats").innerHTML = UI.empty("Profile failed", "Check API connection.", "⚠");
    }
  }

  function ensureLayers() {
    const empty = { type: "FeatureCollection", features: [] };
    if (!map.getSource("gp-surface")) {
      map.addSource("gp-surface", { type: "geojson", data: empty });
      map.addLayer({
        id: "gp-surface-heat", type: "heatmap", source: "gp-surface",
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "_w"], 0, 0, 1, 1],
          "heatmap-intensity": 1.4,
          "heatmap-radius": 28,
          "heatmap-opacity": 0.82,
          "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(0,0,0,0)", 0.15, "rgb(31,60,140)", 0.35, "rgb(31,122,140)",
            0.55, "rgb(43,166,189)", 0.72, "rgb(201,162,39)", 0.88, "rgb(226,87,76)", 1, "rgb(255,50,50)"],
        },
      });
    }
    ready = true;
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    const meta = App.state.meta || {};
    App.fillSelect(document.getElementById("gp-type"), meta.crime_types, "All types");
    const dr = meta.date_range || {};
    if (dr.min) document.getElementById("gp-from").value = dr.min;
    if (dr.max) document.getElementById("gp-to").value = dr.max;
    document.getElementById("gp-run").addEventListener("click", run);
    map = MapKit.createMap("gp-map-canvas", { center: [76.4, 14.9], zoom: 5.6, pitch: 0 });
    map.on("load", () => { ensureLayers(); run(); });
  }

  function onShow() { if (map) setTimeout(() => map.resize(), 80); }

  return { mount, onShow };
})();
