/* ============================================================
   missing.js — Missing Persons: risk-tiered triage + summaries.
   ============================================================ */
Views.Missing = (() => {
  let el, items = [];

  const RISK_COLOR = { High: "#e2574c", Medium: "#e6932f", Low: "#6b7c93" };

  function shell() {
    return `
      <div class="view-head"><div>
        <h1 class="view-title"><span class="vt-ico">⚲</span> Missing Persons</h1>
        <div class="view-sub">Risk-tiered triage of missing-person cases, with repeat-disappearance flags.</div>
      </div></div>

      <div class="banner info"><span class="b-ico">🛈</span><div>
        <b>Triage aid.</b> Risk tiers prioritise response. Null fields show as “—” and are never fabricated.</div></div>

      <div class="controls">
        <div class="ctrl"><span class="ctrl-label">Status</span>
          <select id="mp-status"><option value="">All</option><option>Open</option><option>Traced</option><option>Closed</option></select></div>
        <div class="ctrl"><span class="ctrl-label">Risk tier</span>
          <select id="mp-risk"><option value="">All</option><option>High</option><option>Medium</option><option>Low</option></select></div>
        <span class="dim" id="mp-count" style="margin-left:auto;align-self:center"></span>
      </div>

      <div class="kpi-grid" id="mp-kpis" style="margin-top:12px"></div>

      <div class="grid" style="grid-template-columns:1fr 1fr;gap:16px;margin-top:4px">
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> By risk tier</h3><div class="chart" id="mp-chart-risk" style="height:220px"></div></div>
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> By status</h3><div class="chart" id="mp-chart-status" style="height:220px"></div></div>
      </div>

      <div class="panel panel-pad mt12"><h3 class="panel-title"><span class="dotaccent"></span> Cases</h3>
        <div class="tbl-wrap scroll" style="max-height:460px" id="mp-table"></div></div>`;
  }

  function kpis() {
    const total = items.length;
    const high = items.filter((x) => x.risk_tier === "High").length;
    const open = items.filter((x) => x.status === "Open").length;
    const repeat = items.filter((x) => (x.repeat_count || 0) > 0).length;
    const data = [
      ["Total cases", total, "in current filter"],
      ["High risk", high, "priority response"],
      ["Open", open, "not yet traced"],
      ["Repeat disappearances", repeat, "≥1 prior episode"],
    ];
    document.getElementById("mp-kpis").innerHTML = data.map(([l, v, f]) =>
      `<div class="kpi"><div class="kpi-label">${l}</div><div class="kpi-value">${UI.num(v)}</div><div class="kpi-foot">${f}</div></div>`).join("");
  }

  function charts() {
    const byRisk = {}; const byStatus = {};
    items.forEach((x) => { byRisk[x.risk_tier] = (byRisk[x.risk_tier] || 0) + 1; byStatus[x.status] = (byStatus[x.status] || 0) + 1; });
    UI.mountChart("mp-chart-risk", Object.assign(UI.chartBase(), {
      tooltip: { trigger: "item" },
      series: [{ type: "pie", radius: ["45%", "72%"], itemStyle: { borderColor: "#0a1628", borderWidth: 2 },
        label: { color: "#E6EDF5" },
        data: ["High", "Medium", "Low"].filter((k) => byRisk[k]).map((k) => ({ name: k, value: byRisk[k], itemStyle: { color: RISK_COLOR[k] } })) }],
    }));
    const sk = Object.keys(byStatus);
    UI.mountChart("mp-chart-status", Object.assign(UI.chartBase(), {
      xAxis: Object.assign({ type: "category", data: sk }, UI.axisCommon),
      yAxis: Object.assign({ type: "value" }, UI.axisCommon),
      series: [{ type: "bar", data: sk.map((k) => byStatus[k]), barWidth: "46%",
        itemStyle: { color: "#1F7A8C", borderRadius: [4, 4, 0, 0] } }],
    }));
  }

  function table() {
    const host = document.getElementById("mp-table");
    if (!items.length) { host.innerHTML = UI.empty("No cases", "Adjust the filters above.", "⚲"); return; }
    const order = { High: 0, Medium: 1, Low: 2 };
    const rows = [...items].sort((a, b) => (order[a.risk_tier] ?? 3) - (order[b.risk_tier] ?? 3));
    host.innerHTML = `<table class="tbl"><thead><tr><th>FIR</th><th>Name</th><th>Age</th><th>Risk</th><th>Last seen</th><th>Location</th><th>District</th><th>Status</th><th>Repeat</th></tr></thead><tbody>${
      rows.map((m) => `<tr>
        <td class="mono">${UI.esc(UI.val(m.fir_number))}</td>
        <td>${UI.esc(UI.val(m.name))}</td>
        <td>${UI.val(m.age)}</td>
        <td><span class="badge" style="background:${RISK_COLOR[m.risk_tier] || "#445"}22;color:${RISK_COLOR[m.risk_tier] || "#9fb0c6"};border-color:${RISK_COLOR[m.risk_tier] || "#445"}55">${UI.esc(UI.val(m.risk_tier))}</span></td>
        <td class="dim">${UI.date(m.last_seen_date)}</td>
        <td class="dim">${UI.esc(UI.val(m.last_seen_location))}</td>
        <td>${UI.esc(UI.val(m.district))}</td>
        <td>${UI.esc(UI.val(m.status))}</td>
        <td>${(m.repeat_count || 0) > 0 ? `<span class="chip" style="color:#e6932f">×${m.repeat_count}</span>` : "—"}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  async function load() {
    document.getElementById("mp-table").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    const status = document.getElementById("mp-status").value;
    const risk = document.getElementById("mp-risk").value;
    try {
      const r = await API.get("/missing/cases", { status, risk });
      items = r.items || [];
      document.getElementById("mp-count").textContent = `${items.length} case(s)`;
      kpis(); charts(); table();
    } catch (e) {
      document.getElementById("mp-table").innerHTML = UI.empty("Failed to load", String(e.message), "⚠");
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("mp-status").addEventListener("change", load);
    document.getElementById("mp-risk").addEventListener("change", load);
    load();
  }
  function onShow() { UI.resizeCharts(); }

  return { mount, onShow };
})();
