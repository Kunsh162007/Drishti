/* ============================================================
   suspect.js — Suspect Intelligence: deep person profile
   across all FIRs, crimes, vehicles, and temporal patterns.
   ============================================================ */
Views.Suspect = (() => {
  let el, map, ready = false, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⚐</span> Suspect Intelligence</h1>
          <div class="view-sub">Aggregate all FIRs, crime types, districts, vehicle links, and behavioural patterns for a named individual across the entire case database.</div>
        </div>
      </div>
      <div class="banner warn"><span class="b-ico">🔒</span><div><b>Sensitive personal data.</b> Access is logged. Use only for authorised investigation — name search returns all identity-resolved records linked to this individual.</div></div>
      <div class="panel panel-pad" style="margin-bottom:16px">
        <div class="row wrap" style="justify-content:space-between">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Identity lookup</h3>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Name (partial match)</span>
              <input type="search" id="sp-name" placeholder="e.g. Ravi Kumar" style="min-width:240px"/></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="sp-run">Profile</button></div>
          </div>
        </div>
      </div>
      <div id="sp-profile">${UI.empty("Enter a name", "Search for a suspect by full or partial name to pull their complete profile.", "⚐")}</div>`;
  }

  function profileHTML(d) {
    const s = d.stats || {};
    const firs = d.firs || [];
    const vehicles = d.vehicles || [];
    const geocoded = firs.filter((f) => f.lat && f.lng);

    return `
      <div class="grid kpi-grid" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px">
        <div class="kpi accent-gold"><div class="kpi-label">Total FIRs</div><div class="kpi-value">${UI.num(s.total_firs)}</div><div class="kpi-foot">Across all identity records</div></div>
        <div class="kpi"><div class="kpi-label">Identities resolved</div><div class="kpi-value">${UI.num(s.unique_identities)}</div><div class="kpi-foot">Entity-resolved aliases</div></div>
        <div class="kpi accent-red"><div class="kpi-label">Primary offence</div><div class="kpi-value" style="font-size:16px">${UI.esc(UI.val(s.top_type))}</div><div class="kpi-foot">Most frequent crime type</div></div>
        <div class="kpi accent-teal"><div class="kpi-label">Linked vehicles</div><div class="kpi-value">${UI.num(vehicles.length)}</div><div class="kpi-foot">Vehicle-FIR links</div></div>
      </div>

      <div class="grid" style="grid-template-columns:1fr 1fr;gap:16px;margin-bottom:16px">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Crime type breakdown</h3>
          <div class="chart" id="sp-type-chart" style="height:200px"></div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Activity by hour of day</h3>
          <div class="chart" id="sp-hour-chart" style="height:200px"></div>
        </div>
      </div>

      <div class="grid" style="grid-template-columns:1.1fr .9fr;gap:16px;margin-bottom:16px">
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Crime location map</h3>
          <div class="map-shell" style="height:320px;border-radius:12px;overflow:hidden;border:1px solid var(--stroke-soft)">
            <div id="sp-map-canvas" style="position:absolute;inset:0"></div>
          </div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Districts involved</h3>
          <div class="tbl-wrap scroll" style="max-height:320px">
            ${(s.by_district || []).length ? `<table class="tbl"><thead><tr><th>District</th><th>FIRs</th></tr></thead><tbody>` +
              (s.by_district || []).map((r) => `<tr><td>${UI.esc(r.name)}</td><td>${UI.num(r.value)}</td></tr>`).join("") +
              `</tbody></table>` : UI.empty("No district data", "", "⊕")}
          </div>
          ${vehicles.length ? `<h3 class="panel-title" style="margin-top:14px"><span class="dotaccent"></span> Linked vehicles</h3>
          <div class="tbl-wrap scroll" style="max-height:180px"><table class="tbl"><thead><tr><th>Reg</th><th>Type</th><th>FIR</th></tr></thead><tbody>` +
            vehicles.map((v) => `<tr><td class="mono"><b>${UI.esc(v.reg)}</b></td><td class="dim">${UI.esc(UI.val(v.type))}</td><td class="mono dim">${UI.esc(v.fir)}</td></tr>`).join("") +
            `</tbody></table></div>` : ""}
        </div>
      </div>

      <div class="panel panel-pad">
        <h3 class="panel-title"><span class="dotaccent"></span> FIR history <span class="faint" style="margin-left:8px;font-weight:600;text-transform:none">${firs.length} record(s)</span></h3>
        <div class="tbl-wrap scroll" style="max-height:360px">
          <table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>District</th><th>Date</th><th>Status</th><th>Property value</th></tr></thead><tbody>${
            firs.map((f) => `<tr>
              <td class="mono">${UI.esc(f.fir_number)}</td>
              <td>${UI.esc(UI.val(f.crime_type))}</td>
              <td class="dim">${UI.esc(UI.val(f.district))}</td>
              <td class="dim">${UI.date(f.occurred_at)}</td>
              <td><span class="badge ${f.status === "Open" || f.status === "UnderInvestigation" ? "review" : "auto"}">${UI.esc(UI.val(f.status))}</span></td>
              <td class="dim">${UI.inr(f.property_value_inr)}</td>
            </tr>`).join("")}
          </tbody></table>
        </div>
      </div>

      ${(d.matches || []).length > 1 ? `<div class="panel panel-pad" style="margin-top:16px">
        <h3 class="panel-title"><span class="dotaccent"></span> Identity matches <span class="faint" style="margin-left:8px;font-weight:600;text-transform:none">${d.matches.length} record(s) matching "${UI.esc(d.name)}"</span></h3>
        <div class="tbl-wrap scroll" style="max-height:200px"><table class="tbl"><thead><tr><th>Name</th><th>Role</th><th>FIR</th><th>Identity ID</th></tr></thead><tbody>${
          d.matches.map((m) => `<tr><td><b>${UI.esc(m.name)}</b></td><td class="dim">${UI.esc(UI.val(m.role))}</td><td class="mono dim">${UI.esc(m.fir)}</td><td class="mono dim">${UI.esc(m.tid || "—")}</td></tr>`).join("")
        }</tbody></table></div>
      </div>` : ""}`;
  }

  function renderCharts(d) {
    const s = d.stats || {};
    const byType = s.by_type || [];
    if (byType.length) {
      UI.mountChart("sp-type-chart", {
        ...UI.chartBase(),
        tooltip: { ...UI.chartBase().tooltip, trigger: "item", formatter: "{b}: <b>{c}</b> ({d}%)" },
        series: [{ type: "pie", radius: ["40%", "68%"], center: ["50%", "48%"],
          itemStyle: { borderColor: "#0a1628", borderWidth: 2, borderRadius: 4 },
          label: { show: false }, data: byType.map((r) => ({ name: r.name, value: r.value })) }],
      });
    }
    const byHour = s.by_hour || [];
    if (byHour.length) {
      UI.mountChart("sp-hour-chart", {
        ...UI.chartBase(),
        tooltip: { ...UI.chartBase().tooltip, trigger: "axis", formatter: (p) => `${p[0].axisValue}:00 — <b>${p[0].data}</b>` },
        grid: { left: 8, right: 8, top: 10, bottom: 6, containLabel: true },
        xAxis: { type: "category", data: Array.from({ length: 24 }, (_, i) => `${i}`), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 9, interval: 1 } },
        yAxis: { type: "value", ...UI.axisCommon },
        series: [{ type: "bar", data: byHour, barWidth: "70%", itemStyle: { color: "#C9A227", borderRadius: 3 } }],
      });
    }
  }

  function renderMap2(firs) {
    if (!map) return;
    const geocoded = firs.filter((f) => f.lat && f.lng);
    if (!geocoded.length) return;
    const fc = { type: "FeatureCollection", features: geocoded.map((f) => ({ type: "Feature", geometry: { type: "Point", coordinates: [f.lng, f.lat] }, properties: f })) };
    MapKit.setHeatLayer(map, "sp-crimes", fc, true);
    const lngs = geocoded.map((f) => f.lng), lats = geocoded.map((f) => f.lat);
    map.fitBounds([[Math.min(...lngs), Math.min(...lats)], [Math.max(...lngs), Math.max(...lats)]], { padding: 40, maxZoom: 9, duration: 600 });
  }

  async function run() {
    const name = document.getElementById("sp-name").value.trim();
    if (!name) { UI.toast("Enter a name", "Type a full or partial suspect name.", "info"); return; }
    document.getElementById("sp-profile").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const d = await API.get("/suspect/profile", { name });
      if (!d.firs.length && !d.matches.length) {
        document.getElementById("sp-profile").innerHTML = UI.empty(`No records for "${UI.esc(name)}"`, "No persons matching this name in the database.", "⚐");
        return;
      }
      document.getElementById("sp-profile").innerHTML = profileHTML(d);
      renderCharts(d);
      // Init map after DOM is ready
      setTimeout(() => {
        if (!map) {
          map = MapKit.createMap("sp-map-canvas", { center: [76.4, 14.9], zoom: 6, pitch: 0 });
          map.on("load", () => { ready = true; renderMap2(d.firs || []); });
        } else {
          renderMap2(d.firs || []);
        }
      }, 0);
    } catch (_) {
      document.getElementById("sp-profile").innerHTML = UI.empty("Profile failed", "Check the API connection.", "⚠");
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("sp-run").addEventListener("click", run);
    document.getElementById("sp-name").addEventListener("keydown", (e) => { if (e.key === "Enter") run(); });
    // Prefill with a sample suspect from the network
    API.get("/network", { limit: 1 }, { silent: true }).then((r) => {
      const person = (r.nodes || []).find((n) => n.type === "person");
      if (person && document.getElementById("sp-name")) {
        document.getElementById("sp-name").placeholder = `e.g. ${person.label || "Ravi Kumar"}`;
      }
    }).catch(() => {});
    mounted = true;
  }

  function onShow() {
    if (map) setTimeout(() => map.resize(), 80);
    UI.resizeCharts();
  }

  return { mount, onShow };
})();
