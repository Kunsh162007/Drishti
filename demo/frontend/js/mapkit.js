/* ============================================================
   mapkit.js — robust MapLibre helpers for the hex maps.
   Replaces deck.gl (which failed to render with MapLibre on
   these CDN builds) with native MapLibre 3D fill-extrusion
   hexagons + heatmap + clickable locations.
   Loaded before the view scripts.
   ============================================================ */
// Resolve graphology / forceatlas2 UMD globals (names vary across CDN builds).
window.DGraph = (typeof graphology !== "undefined" && graphology) ? (graphology.Graph || graphology) : null;
window.DFA2 = (typeof forceAtlas2 !== "undefined") ? forceAtlas2
  : (typeof graphologyLayoutForceAtlas2 !== "undefined" ? graphologyLayoutForceAtlas2 : null);

const MapKit = (() => {
  const rasterStyle = {
    version: 8,
    sources: {
      carto: {
        type: "raster",
        tiles: [
          "https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
          "https://b.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
          "https://c.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}.png",
        ],
        tileSize: 256,
        attribution: "© OpenStreetMap, © CARTO",
      },
    },
    layers: [{ id: "carto", type: "raster", source: "carto" }],
  };

  function createMap(container, opts = {}) {
    const map = new maplibregl.Map({
      container,
      style: rasterStyle,
      center: opts.center || [76.4, 14.9],
      zoom: opts.zoom != null ? opts.zoom : 6,
      pitch: opts.pitch != null ? opts.pitch : 45,
      bearing: opts.bearing != null ? opts.bearing : -12,
      attributionControl: false,
      antialias: true,
    });
    map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), "bottom-left");
    return map;
  }

  // Build a FeatureCollection of hexagon polygons (via global h3) for the cells.
  // propsFn(cell, value) returns extra feature properties (e.g. _color, _height).
  function hexFC(cells, valFn, propsFn) {
    const hasH3 = typeof h3 !== "undefined" && h3 && h3.cellToBoundary;
    const features = [];
    for (const c of cells || []) {
      const v = Number(valFn(c)) || 0;
      let geom = null;
      if (hasH3 && c.h3) {
        try {
          let ring = h3.cellToBoundary(c.h3, true); // [lng,lat] pairs
          if (ring && ring.length) {
            const a = ring[0], z = ring[ring.length - 1];
            if (a[0] !== z[0] || a[1] !== z[1]) ring = ring.concat([a]);
            geom = { type: "Polygon", coordinates: [ring] };
          }
        } catch (_) {}
      }
      if (!geom && c.lat != null && c.lng != null) geom = { type: "Point", coordinates: [c.lng, c.lat] };
      if (!geom) continue;
      features.push({ type: "Feature", geometry: geom, properties: Object.assign({}, c, { _val: v }, propsFn ? propsFn(c, v) : {}) });
    }
    return { type: "FeatureCollection", features };
  }

  function pointFC(cells, valFn) {
    return {
      type: "FeatureCollection",
      features: (cells || []).filter((c) => c.lat != null && c.lng != null).map((c) => ({
        type: "Feature", geometry: { type: "Point", coordinates: [c.lng, c.lat] },
        properties: Object.assign({}, c, { _w: Number(valFn(c)) || 1 }),
      })),
    };
  }

  function ramp(t) { const [r, g, b] = UI.rampColor(Math.max(0, Math.min(1, t))); return `rgb(${r},${g},${b})`; }

  // Add (or refresh) a 3D hex fill-extrusion + outline. Idempotent per srcId.
  function setHexLayers(map, srcId, fc, { heightProp = "_height", colorProp = "_color", onClick } = {}) {
    const lyrFill = srcId + "-fill", lyrLine = srcId + "-line";
    if (map.getSource(srcId)) {
      map.getSource(srcId).setData(fc);
      return;
    }
    map.addSource(srcId, { type: "geojson", data: fc });
    map.addLayer({
      id: lyrFill, type: "fill-extrusion", source: srcId,
      paint: {
        "fill-extrusion-color": ["coalesce", ["get", colorProp], "#1F7A8C"],
        "fill-extrusion-height": ["coalesce", ["get", heightProp], 0],
        "fill-extrusion-base": 0,
        "fill-extrusion-opacity": 0.78,
      },
    });
    map.addLayer({
      id: lyrLine, type: "line", source: srcId,
      paint: { "line-color": ["coalesce", ["get", colorProp], "#1F7A8C"], "line-width": 0.6, "line-opacity": 0.5 },
    });
    if (onClick) {
      map.on("click", lyrFill, (e) => { if (e.features && e.features[0]) onClick(e.features[0].properties, e.lngLat); });
      map.on("mouseenter", lyrFill, () => { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", lyrFill, () => { map.getCanvas().style.cursor = ""; });
    }
  }

  function setHeatLayer(map, srcId, fc, visible) {
    const lyr = srcId + "-heat";
    if (map.getSource(srcId)) { map.getSource(srcId).setData(fc); }
    else {
      map.addSource(srcId, { type: "geojson", data: fc });
      map.addLayer({
        id: lyr, type: "heatmap", source: srcId,
        paint: {
          "heatmap-weight": ["interpolate", ["linear"], ["get", "_w"], 0, 0, 30, 1],
          "heatmap-intensity": 1.1,
          "heatmap-radius": 34,
          "heatmap-opacity": 0.85,
          "heatmap-color": ["interpolate", ["linear"], ["heatmap-density"],
            0, "rgba(0,0,0,0)", 0.2, "rgb(31,122,140)", 0.45, "rgb(43,166,189)",
            0.65, "rgb(201,162,39)", 0.82, "rgb(230,147,47)", 1, "rgb(226,87,76)"],
        },
      });
    }
    if (map.getLayer(lyr)) map.setLayoutProperty(lyr, "visibility", visible ? "visible" : "none");
  }

  function setVisible(map, layerId, visible) {
    if (map.getLayer(layerId)) map.setLayoutProperty(layerId, "visibility", visible ? "visible" : "none");
  }

  return { rasterStyle, createMap, hexFC, pointFC, ramp, setHexLayers, setHeatLayer, setVisible };
})();
