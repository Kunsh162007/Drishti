/* ============================================================
   behavioral.js — Criminal Career / Behavioral Analytics.
   Full recidivism risk profile for a named suspect.
   ============================================================ */
Views.Behavioral = (() => {
  let el, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">◉</span> Behavioral Analytics</h1>
          <div class="view-sub">Criminal career timeline, offense diversity, geographic drift, co-offender network, and recidivism risk scoring for a named suspect.</div>
        </div>
        <div class="controls">
          <div class="ctrl" style="flex:1;min-width:240px">
            <span class="ctrl-label">Suspect name</span>
            <input type="search" id="beh-name" placeholder="e.g. Ramesh Kumar" style="min-width:220px"/>
          </div>
          <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
            <button class="btn btn-primary" id="beh-run">Analyse</button></div>
        </div>
      </div>

      <div class="banner info" style="margin-bottom:14px">
        <span class="b-ico">⚖</span>
        <div><b>Decision-support only.</b> Risk scores are <b>place-and-history-based static factors</b> (Andrews &amp; Bonta 2010) and must never substitute for professional risk assessment. Scores cite no personal characteristics — only prior criminal record signals.</div>
      </div>

      <div id="beh-result">${UI.empty("Enter a suspect name above", "The engine will build a full criminal career profile from linked FIRs, resolving identity aliases automatically.", "◉")}</div>`;
  }

  function riskColor(label) {
    return label === "High" ? "#e2574c" : label === "Medium" ? "#e6932f" : "#2ba6bd";
  }

  function renderProfile(d) {
    const host = document.getElementById("beh-result");
    if (!d.found) {
      host.innerHTML = UI.empty("No records found", d.summary || "No matching person in the database.", "◉");
      return;
    }

    const rc = riskColor(d.risk_label);
    const factors = d.risk_factors || {};
    const factorEntries = [
      ["Criminal count", factors.criminal_count, 30],
      ["Type diversity", factors.type_diversity, 20],
      ["Recency", factors.recency, 20],
      ["Severity level", factors.severity_level, 15],
      ["Network breadth", factors.network_breadth, 10],
      ["Weapon use", factors.weapon_use, 5],
    ];

    host.innerHTML = `
      <!-- Header row -->
      <div class="row wrap" style="gap:14px;margin-bottom:16px;align-items:flex-start">
        <!-- Identity card -->
        <div class="panel panel-pad" style="min-width:260px;flex:0 0 auto">
          <div style="font-size:18px;font-weight:700;color:var(--fg-bright);margin-bottom:4px">${UI.esc(d.name)}</div>
          ${d.aliases && d.aliases.length ? `<div class="dim" style="font-size:11.5px;margin-bottom:8px">Also known as: ${d.aliases.slice(0,4).map((a) => `<b>${UI.esc(a)}</b>`).join(", ")}</div>` : ""}
          <div class="row wrap" style="gap:8px;margin-bottom:10px">
            ${[["FIRs", d.fir_count],["Escalation", d.escalation || "—"],["Geo drift", d.geo_drift_km != null ? d.geo_drift_km + " km" : "—"]]
              .map(([l,v]) => `<div class="kpi" style="min-width:80px;padding:7px 10px"><div class="kpi-label">${l}</div><div class="kpi-value" style="font-size:16px">${v}</div></div>`).join("")}
          </div>
          <div class="dim" style="font-size:11.5px;line-height:1.55">${UI.esc(d.summary || "")}</div>
        </div>

        <!-- Risk gauge -->
        <div class="panel panel-pad" style="min-width:220px;flex:0 0 auto;text-align:center">
          <div class="kpi-label" style="margin-bottom:4px">Recidivism Risk Score</div>
          <div style="font-size:52px;font-weight:800;color:${rc};line-height:1">${d.risk_score}</div>
          <div style="color:${rc};font-weight:700;font-size:15px;margin-bottom:10px">${d.risk_label} Risk</div>
          ${factorEntries.map(([label, val, max]) => `
            <div style="margin-bottom:5px;text-align:left">
              <div class="row" style="justify-content:space-between;font-size:11px;color:#9fb0c6"><span>${label}</span><span>${val || 0}/${max}</span></div>
              <div style="background:rgba(255,255,255,.06);border-radius:4px;height:5px;margin-top:2px">
                <div style="width:${Math.round(((val||0)/max)*100)}%;height:100%;background:${rc};border-radius:4px;transition:width .4s"></div>
              </div>
            </div>`).join("")}
        </div>

        <!-- Type distribution chart -->
        <div class="panel panel-pad" style="flex:1;min-width:220px">
          <h3 class="panel-title" style="margin-bottom:6px"><span class="dotaccent"></span> Offense type mix</h3>
          <div class="chart" id="beh-type-chart" style="height:200px"></div>
        </div>

        <!-- Top co-offenders -->
        <div class="panel panel-pad" style="flex:1;min-width:200px;max-height:280px;overflow:auto">
          <h3 class="panel-title" style="margin-bottom:6px"><span class="dotaccent"></span> Top co-offenders</h3>
          ${(d.top_co_offenders || []).length
            ? `<table class="tbl"><thead><tr><th>Name</th><th>Shared FIRs</th></tr></thead><tbody>${
                (d.top_co_offenders||[]).map((co) => `<tr><td>${UI.esc(co.name)}</td><td><span class="badge review">${co.shared_firs}</span></td></tr>`).join("")
              }</tbody></table>`
            : UI.empty("No co-offenders", "", "◉")}
        </div>
      </div>

      <!-- Activity line chart -->
      <div class="panel panel-pad" style="margin-bottom:14px">
        <h3 class="panel-title" style="margin-bottom:6px"><span class="dotaccent"></span> Monthly criminal activity timeline</h3>
        <div class="chart" id="beh-timeline-chart" style="height:200px"></div>
      </div>

      <!-- FIR history table -->
      <div class="panel panel-pad">
        <h3 class="panel-title" style="margin-bottom:8px"><span class="dotaccent"></span> Full crime history (${d.fir_count} record(s))</h3>
        <div class="tbl-wrap scroll" style="max-height:320px">
          <table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>District</th><th>Date</th><th>Severity</th><th>Weapon</th><th>Status</th></tr></thead>
          <tbody>${(d.timeline || []).map((c) => `<tr>
            <td class="mono">${UI.esc(c.fir_number || "—")}</td>
            <td>${UI.esc(UI.val(c.crime_type))}</td>
            <td class="dim">${UI.esc(UI.val(c.district))}</td>
            <td class="dim">${UI.date(c.occurred_at)}</td>
            <td style="text-align:center">${c.severity != null ? `<span class="badge ${c.severity >= 4 ? "alert" : c.severity >= 2 ? "review" : "neutral"}">${c.severity}</span>` : "—"}</td>
            <td class="dim">${UI.esc(UI.val(c.weapon_used))}</td>
            <td><span class="badge neutral">${UI.esc(UI.val(c.status))}</span></td>
          </tr>`).join("")}</tbody></table>
        </div>
      </div>`;

    // Render charts
    setTimeout(() => {
      const typeData = Object.entries(d.type_distribution || {}).map(([name, value]) => ({ name, value }));
      if (typeData.length) {
        UI.mountChart("beh-type-chart", {
          ...UI.chartBase(),
          tooltip: { trigger: "item" },
          series: [{ type: "pie", radius: ["42%", "70%"], itemStyle: { borderColor: "#0a1628", borderWidth: 2 },
            label: { color: "#E6EDF5", fontSize: 11 },
            data: typeData }],
        });
      }
      const monthly = d.monthly_activity || {};
      const months = Object.keys(monthly).sort();
      if (months.length) {
        UI.mountChart("beh-timeline-chart", {
          ...UI.chartBase(),
          tooltip: { trigger: "axis" },
          grid: { left: 8, right: 12, top: 10, bottom: 6, containLabel: true },
          xAxis: { type: "category", data: months, ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10, rotate: 30 } },
          yAxis: { type: "value", ...UI.axisCommon, minInterval: 1 },
          series: [{
            type: "line", data: months.map((m) => monthly[m]),
            smooth: true, areaStyle: { color: "rgba(201,162,39,.12)" },
            lineStyle: { color: "#C9A227", width: 2 },
            itemStyle: { color: "#C9A227" },
            symbol: "circle", symbolSize: 6,
          }],
        });
      }
    }, 30);
  }

  async function analyse() {
    const name = (document.getElementById("beh-name").value || "").trim();
    if (!name) return;
    const host = document.getElementById("beh-result");
    host.innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const d = await API.get("/suspect/behavior", { name });
      renderProfile(d);
    } catch (_) {
      host.innerHTML = UI.empty("Analysis failed", "Check that the backend is running.", "◉");
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("beh-run").addEventListener("click", analyse);
    document.getElementById("beh-name").addEventListener("keydown", (e) => { if (e.key === "Enter") analyse(); });
    mounted = true;
  }

  function onShow() { UI.resizeCharts(); }

  return { mount, onShow };
})();
