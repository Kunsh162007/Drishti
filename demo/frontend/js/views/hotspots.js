/* ============================================================
   hotspots.js — full-bleed MapLibre + deck.gl H3HexagonLayer.
   Modes: "hotspots" (count/gi) and "emerging" (trend category).
   ============================================================ */
Views.Hotspots = (() => {
  let el, map, deckOverlay, mounted = false;
  let mode = "hotspots";          // 'hotspots' | 'emerging'
  let layerType = "hex";          // 'hex' | 'heat'
  let lastCells = [];

  // Free OSM raster style (no key)
  const RASTER_STYLE = {
    version: 8,
    sources: {
      osm: {
        type: "raster",
        tiles: ["https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
                "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
                "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png"],
        tileSize: 256,
        attribution: "© OpenStreetMap, © CARTO",
      },
    },
    layers: [{ id: "osm", type: "raster", source: "osm" }],
  };

  const EMERGING_COLORS = {
    new: [226, 87, 76], intensifying: [230, 147, 47],
    persistent: [61, 127, 214], diminishing: [59, 167, 118],
    sporadic: [155, 127, 214], none: [120, 130, 150],
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
                <select id="hs-type"><option value="">All types</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">Resolution</span>
                <select id="hs-res"><option value="7">R7 (coarse)</option><option value="8" selected>R8</option><option value="9">R9 (fine)</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">From</span><input type="date" id="hs-from" /></div>
              <div class="ctrl"><span class="ctrl-label">To</span><input type="date" id="hs-to" /></div>
              <div class="ctrl"><span class="ctrl-label">Layer</span>
                <div class="toggle-group" id="hs-layer">
                  <button class="active" data-layer="hex">3D Hex</button>
                  <button data-layer="heat">Heatmap</button>
                </div>
              </div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary" id="hs-apply">Apply</button></div>
            </div>
          </div>
        </div>

        <div class="map-overlay map-side">
          <div class="panel panel-pad" style="flex:0 0 auto">
            <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> <span id="hs-legend-title">Intensity</span></h3>
            <div class="legend" id="hs-legend"></div>
          </div>
          <div class="panel panel-pad" style="flex:1 1 auto;min-height:0;display:flex;flex-direction:column">
            <h3 class="panel-title" style="margin-bottom:10px"><span class="dotaccent"></span> Top cells <span class="faint" id="hs-count" style="margin-left:auto;font-weight:600"></span></h3>
            <div class="hot-list scroll" id="hs-list"></div>
          </div>
        </div>
      </div>`;
  }

  function legendHTML() {
    if (mode === "emerging") {
      document.getElementById("hs-legend-title").textContent = "Trend";
      return Object.entries({ new: "New", intensifying: "Intensifying", persistent: "Persistent", diminishing: "Diminishing", sporadic: "Sporadic" })
        .map(([k, lbl]) => {
          const c = EMERGING_COLORS[k];
          return `<div class="legend-row"><span class="legend-sw" style="background:rgb(${c.join(",")})"></span>${lbl}</div>`;
        }).join("");
    }
    document.getElementById("hs-legend-title").textContent = "Intensity";
    const stops = [["Low", UI.rampColor(0.05)], ["", UI.rampColor(0.35)], ["Medium", UI.rampColor(0.6)], ["", UI.rampColor(0.8)], ["High / hotspot", UI.rampColor(1)]];
    return stops.map(([lbl, c]) => `<div class="legend-row"><span class="legend-sw" style="background:rgb(${c.join(",")})"></span>${lbl || "&nbsp;"}</div>`).join("");
  }

  function cellsToHex(cells) {
    // deck.gl H3HexagonLayer needs a valid h3 index. Fall back to scatter via h3 from lat/lng if missing.
    return cells.filter((c) => c.h3 && (typeof h3 === "undefined" || h3.isValidCell ? (typeof h3 === "undefined" ? true : h3.isValidCell(c.h3)) : true));
  }

  function buildLayers() {
    if (!window.deck) return [];
    const cells = lastCells;
    if (!cells.length) return [];

    if (mode === "hotspots") {
      const counts = cells.map((c) => c.count || 0);
      const max = Math.max(1, ...counts);
      if (layerType === "heat") {
        return [new deck.HeatmapLayer({
          id: "heat",
          data: cells.filter((c) => c.lat != null && c.lng != null),
          getPosition: (d) => [d.lng, d.lat],
          getWeight: (d) => d.count || 1,
          radiusPixels: 46, intensity: 1.1, threshold: 0.04,
          colorRange: [[31,122,140],[43,166,189],[201,162,39],[230,147,47],[226,87,76],[255,210,120]],
        })];
      }
      return [new deck.H3HexagonLayer({
        id: "hex",
        data: cellsToHex(cells),
        pickable: true, extruded: true, wireframe: false,
        elevationScale: 22,
        getHexagon: (d) => d.h3,
        getElevation: (d) => d.count || 0,
        getFillColor: (d) => {
          const t = (d.count || 0) / max;
          const [r, g, b] = UI.rampColor(t);
          return [r, g, b, 205];
        },
        opacity: 0.86,
        material: { ambient: 0.6, diffuse: 0.6, shininess: 32 },
        updateTriggers: { getFillColor: [max], getElevation: [max] },
      })];
    }

    // emerging mode
    if (layerType === "heat") {
      return [new deck.HeatmapLayer({
        id: "heat-em",
        data: cells.filter((c) => c.lat != null && c.lng != null),
        getPosition: (d) => [d.lng, d.lat],
        getWeight: (d) => (d.recent || 1),
        radiusPixels: 46, intensity: 1.1,
      })];
    }
    return [new deck.H3HexagonLayer({
      id: "hex-em",
      data: cellsToHex(cells),
      pickable: true, extruded: true,
      elevationScale: 26,
      getHexagon: (d) => d.h3,
      getElevation: (d) => (d.recent || 0),
      getFillColor: (d) => {
        const c = EMERGING_COLORS[d.category] || EMERGING_COLORS.none;
        return [c[0], c[1], c[2], 210];
      },
      opacity: 0.88,
    })];
  }

  function getTooltip({ object }) {
    if (!object) return null;
    if (mode === "hotspots") {
      return {
        html: `<div class="deck-tip"><b>Hotspot cell</b><br/>Count: <b>${UI.num(object.count)}</b><br/>Gi* score: ${UI.val(object.gi_score)}<br/>Level: ${UI.title(object.level || "—")}</div>`,
        style: { background: "transparent" },
      };
    }
    return {
      html: `<div class="deck-tip"><b>${UI.title(object.category)}</b><br/>Recent: <b>${UI.num(object.recent)}</b> · Baseline: ${UI.num(object.baseline)}<br/>Change: ${object.change_pct == null ? "—" : object.change_pct + "%"}</div>`,
      style: { background: "transparent" },
    };
  }

  function refreshDeck() {
    if (!deckOverlay) return;
    deckOverlay.setProps({ layers: buildLayers() });
  }

  function renderSide() {
    document.getElementById("hs-legend").innerHTML = legendHTML();
    const list = document.getElementById("hs-list");
    const cnt = document.getElementById("hs-count");
    cnt.textContent = lastCells.length ? `${lastCells.length} cells` : "";
    if (!lastCells.length) { list.innerHTML = UI.empty("No cells for these filters", "Try a coarser resolution or wider date range.", "⬡"); return; }
    const sorted = mode === "hotspots"
      ? [...lastCells].sort((a, b) => (b.count || 0) - (a.count || 0))
      : [...lastCells].sort((a, b) => (b.recent || 0) - (a.recent || 0));
    list.innerHTML = sorted.slice(0, 40).map((c, i) => {
      const right = mode === "hotspots"
        ? `<div class="hc-count">${UI.num(c.count)}</div>`
        : `<span class="badge ${c.category === "new" || c.category === "intensifying" ? "review" : "neutral"}">${UI.title(c.category)}</span>`;
      const sub = mode === "hotspots"
        ? `Gi* ${UI.val(c.gi_score)} · ${UI.title(c.level || "—")}`
        : `${UI.num(c.recent)} recent · ${UI.num(c.baseline)} base`;
      return `<div class="hot-cell" data-lat="${c.lat ?? ""}" data-lng="${c.lng ?? ""}">
        <div class="hc-rank">${i + 1}</div>
        <div class="hc-meta"><div class="hc-h3">${UI.esc(c.h3 || "—")}</div><div class="faint" style="font-size:10.5px">${sub}</div></div>
        ${right}
      </div>`;
    }).join("");
    list.querySelectorAll(".hot-cell").forEach((row) => row.addEventListener("click", () => {
      const lat = parseFloat(row.dataset.lat), lng = parseFloat(row.dataset.lng);
      if (!isNaN(lat) && !isNaN(lng) && map) map.flyTo({ center: [lng, lat], zoom: Math.max(map.getZoom(), 9.5), pitch: 45 });
    }));
  }

  async function load() {
    const list = document.getElementById("hs-list");
    list && (list.innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`);
    try {
      if (mode === "hotspots") {
        const res = document.getElementById("hs-res").value;
        const crime_type = document.getElementById("hs-type").value;
        const date_from = document.getElementById("hs-from").value;
        const date_to = document.getElementById("hs-to").value;
        const r = await API.get("/hotspots", { resolution: res, crime_type, date_from, date_to });
        lastCells = (r.cells || []).filter((c) => c.h3);
      } else {
        const res = document.getElementById("hs-res").value;
        const r = await API.get("/emerging", { resolution: res, period_days: 90 });
        lastCells = (r.cells || []).filter((c) => c.h3);
      }
    } catch (_) { lastCells = []; }
    refreshDeck();
    renderSide();
    // pulse animation flag for emerging new/intensifying handled via CSS-less repaint loop
  }

  function initMap() {
    map = new maplibregl.Map({
      container: "map-canvas",
      style: RASTER_STYLE,
      center: [75.7, 15.3],
      zoom: 6,
      pitch: 38,
      bearing: -8,
      attributionControl: true,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-left");
    deckOverlay = new deck.MapboxOverlay({
      interleaved: false,
      layers: [],
      getTooltip,
    });
    map.addControl(deckOverlay);
    map.on("load", () => load());

    // gentle pulse for emerging mode: recolor 'new'/'intensifying' alpha over time
    let t = 0;
    setInterval(() => {
      if (App.state.current !== "hotspots" || mode !== "emerging" || layerType !== "hex") return;
      t += 0.12;
      const a = 150 + Math.round(80 * (0.5 + 0.5 * Math.sin(t)));
      deckOverlay.setProps({
        layers: [new deck.H3HexagonLayer({
          id: "hex-em",
          data: cellsToHex(lastCells),
          pickable: true, extruded: true, elevationScale: 26,
          getHexagon: (d) => d.h3,
          getElevation: (d) => (d.recent || 0),
          getFillColor: (d) => {
            const c = EMERGING_COLORS[d.category] || EMERGING_COLORS.none;
            const al = (d.category === "new" || d.category === "intensifying") ? a : 200;
            return [c[0], c[1], c[2], al];
          },
          updateTriggers: { getFillColor: [a] },
          opacity: 0.9,
        })],
      });
    }, 90);
  }

  function bind() {
    document.querySelectorAll("#hs-mode button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("#hs-mode button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      mode = b.dataset.mode;
      document.getElementById("hs-filters").style.opacity = mode === "emerging" ? ".55" : "1";
      load();
    }));
    document.querySelectorAll("#hs-layer button").forEach((b) => b.addEventListener("click", () => {
      document.querySelectorAll("#hs-layer button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      layerType = b.dataset.layer;
      refreshDeck();
    }));
    document.getElementById("hs-apply").addEventListener("click", load);
    document.getElementById("hs-res").addEventListener("change", load);
  }

  function applyExternalFilter(f) {
    if (!f) return;
    mode = "hotspots";
    document.querySelectorAll("#hs-mode button").forEach((x) => x.classList.toggle("active", x.dataset.mode === "hotspots"));
    const typeSel = document.getElementById("hs-type");
    if (f.crime_type && typeSel) typeSel.value = f.crime_type;
    if (f.date_from) document.getElementById("hs-from").value = f.date_from;
    if (f.date_to) document.getElementById("hs-to").value = f.date_to;
    load();
  }

  function mount(node) {
    el = node;
    el.classList.add("fullbleed");
    el.innerHTML = shell();
    const meta = App.state.meta || {};
    App.fillSelect(document.getElementById("hs-type"), meta.crime_types, "All types");
    const dr = meta.date_range || {};
    if (dr.min) { document.getElementById("hs-from").min = dr.min; }
    if (dr.max) { document.getElementById("hs-to").max = dr.max; }
    document.getElementById("hs-legend").innerHTML = legendHTML();
    bind();
    initMap();
    mounted = true;
  }

  function onShow() {
    if (map) setTimeout(() => map.resize(), 60);
    if (App.state.pendingFilter) { applyExternalFilter(App.state.pendingFilter); App.state.pendingFilter = null; }
  }

  return { mount, onShow };
})();
