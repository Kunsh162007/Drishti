/* ============================================================
   dashboard.js — Command Dashboard: KPIs + 4 ECharts.
   ============================================================ */
Views.Dashboard = (() => {
  let el, loaded = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">◧</span> Command Dashboard</h1>
          <div class="view-sub" id="dash-sub">Statewide crime intelligence overview — live from the authorised case database.</div>
        </div>
        <div class="controls">
          <div class="ctrl">
            <span class="ctrl-label">District</span>
            <select id="dash-district"><option value="">All districts</option></select>
          </div>
          <div class="ctrl">
            <span class="ctrl-label">From</span>
            <input type="date" id="dash-from" />
          </div>
          <div class="ctrl">
            <span class="ctrl-label">To</span>
            <input type="date" id="dash-to" />
          </div>
          <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
            <button class="btn btn-primary" id="dash-apply">Apply</button>
          </div>
        </div>
      </div>

      <div class="grid kpi-grid" id="dash-kpis">${UI.skeletonKPIs(6)}</div>

      <div class="grid charts-grid">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Crimes by category</h3>
          <div class="chart" id="dash-donut">${UI.skeletonChart()}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Top districts</h3>
          <div class="chart" id="dash-bar">${UI.skeletonChart()}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Activity by hour (24h)</h3>
          <div class="chart" id="dash-hour">${UI.skeletonChart()}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Monthly trend</h3>
          <div class="chart" id="dash-month">${UI.skeletonChart()}</div>
        </div>
      </div>

      <div class="panel panel-pad mt12">
        <div class="row wrap" style="justify-content:space-between;align-items:center;margin-bottom:6px">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Auto-drafted intelligence briefing</h3>
          <button class="btn btn-teal sm" id="dash-brief-btn">Generate briefing</button>
        </div>
        <div class="dim" style="font-size:12px;margin-bottom:8px">Grounded in the data above — every claim cites FIRs; nothing is invented.</div>
        <div id="dash-briefing">${UI.empty("No briefing yet", "Click “Generate briefing” for a grounded situational summary.", "✦")}</div>
      </div>`;
  }

  function renderBriefing(d) {
    const host = document.getElementById("dash-briefing");
    if (!d || !(d.sections || []).length) { host.innerHTML = UI.empty("Briefing unavailable", "", "✦"); return; }
    host.innerHTML = `<div style="font-family:Georgia,serif">
      <div style="font-size:15px;color:var(--gold);margin-bottom:4px">${UI.esc(UI.val(d.headline))}</div>
      <div class="dim" style="font-size:11px;margin-bottom:10px">${UI.esc((d.generated_at || "").slice(0, 19).replace("T", " "))}</div>
      ${d.sections.map((s) => `<div style="margin-bottom:12px">
        <div style="color:#E6EDF5;font-weight:600;margin-bottom:3px">${UI.esc(s.title)}</div>
        <div class="dim" style="font-size:12.5px;line-height:1.55">${UI.esc(s.text)}</div>
        ${(s.citations || []).length ? `<div style="margin-top:4px">${s.citations.map((c) => `<span class="chip fir" style="margin:1px">${UI.esc(c)}</span>`).join("")}</div>` : ""}
      </div>`).join("")}</div>`;
  }

  async function runBriefing() {
    const district = document.getElementById("dash-district").value;
    const host = document.getElementById("dash-briefing");
    host.innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try { renderBriefing(await API.get("/briefing", { district })); }
    catch (_) { host.innerHTML = UI.empty("Could not generate briefing", "", "⚠"); }
  }

  const KPI_DEFS = [
    { key: "total_crimes", label: "Total crimes", accent: "accent-gold", foot: "Across all districts", fmt: "num" },
    { key: "open_cases", label: "Open cases", accent: "", foot: "Open + under investigation", fmt: "num" },
    { key: "solved_rate", label: "Solved rate", accent: "accent-teal", foot: "Charge-sheeted or closed", fmt: "pct" },
    { key: "districts_affected", label: "Districts affected", accent: "", foot: "Distinct jurisdictions", fmt: "num" },
    { key: "cyber_share", label: "Cyber share", accent: "accent-teal", foot: "Cybercrime as % of total", fmt: "pct" },
    { key: "violent_share", label: "Violent share", accent: "accent-red", foot: "Violent as % of total", fmt: "pct" },
  ];

  function renderKPIs(kpis) {
    const host = document.getElementById("dash-kpis");
    if (!host) return;
    host.innerHTML = KPI_DEFS.map((d) => {
      const isPct = d.fmt === "pct";
      return `<div class="kpi ${d.accent}">
        <div class="kpi-label">${d.label}</div>
        <div class="kpi-value" data-k="${d.key}" data-fmt="${d.fmt}">0${isPct ? '<span class="unit">%</span>' : ""}</div>
        <div class="kpi-foot">${d.foot}</div>
      </div>`;
    }).join("");
    KPI_DEFS.forEach((d) => {
      const node = host.querySelector(`[data-k="${d.key}"]`);
      const raw = Number(kpis[d.key] || 0);
      UI.countUp(node, raw, { decimals: d.fmt === "pct" ? 1 : 0 });
    });
  }

  function donut(data) {
    if (!data || !data.length) { document.getElementById("dash-donut").innerHTML = UI.empty("No category data"); return; }
    UI.mountChart("dash-donut", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "item", formatter: "{b}: <b>{c}</b> ({d}%)" },
      legend: { bottom: 0, textStyle: { color: "#9fb0c6", fontSize: 11 }, icon: "roundRect", itemWidth: 11, itemHeight: 11 },
      series: [{
        type: "pie", radius: ["46%", "70%"], center: ["50%", "44%"], avoidLabelOverlap: true,
        itemStyle: { borderColor: "#0a1628", borderWidth: 2, borderRadius: 4 },
        label: { show: false }, labelLine: { show: false },
        data: data.map((d) => ({ name: d.name, value: d.value })),
      }],
    });
  }

  function bar(data) {
    if (!data || !data.length) { document.getElementById("dash-bar").innerHTML = UI.empty("No district data"); return; }
    const d = data.slice(0, 12).reverse();
    UI.mountChart("dash-bar", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
      grid: { left: 8, right: 24, top: 14, bottom: 6, containLabel: true },
      xAxis: { type: "value", ...UI.axisCommon },
      yAxis: { type: "category", data: d.map((x) => x.name), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10.5 } },
      series: [{
        type: "bar", data: d.map((x) => x.value), barWidth: "62%",
        itemStyle: {
          borderRadius: [0, 5, 5, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: "#1F7A8C" }, { offset: 1, color: "#C9A227" }]),
        },
      }],
    });
  }

  function hour(arr) {
    const data = (arr && arr.length === 24) ? arr : new Array(24).fill(0);
    if (!data.some((x) => x)) { document.getElementById("dash-hour").innerHTML = UI.empty("No time-of-day data"); return; }
    UI.mountChart("dash-hour", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis", formatter: (p) => `${p[0].axisValue}:00 — <b>${p[0].data}</b> crimes` },
      xAxis: { type: "category", data: data.map((_, i) => i), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10, interval: 1 } },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [{
        type: "line", data, smooth: true, symbol: "none",
        lineStyle: { color: "#C9A227", width: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(201,162,39,.42)" }, { offset: 1, color: "rgba(201,162,39,0)" }]) },
      }],
    });
  }

  function month(data) {
    if (!data || !data.length) { document.getElementById("dash-month").innerHTML = UI.empty("No monthly data"); return; }
    UI.mountChart("dash-month", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis" },
      xAxis: { type: "category", data: data.map((x) => x.period), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10, rotate: data.length > 10 ? 35 : 0 } },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [{
        type: "line", data: data.map((x) => x.count), smooth: true,
        symbol: "circle", symbolSize: 6, itemStyle: { color: "#2ba6bd" },
        lineStyle: { color: "#2ba6bd", width: 2.5 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(43,166,189,.32)" }, { offset: 1, color: "rgba(43,166,189,0)" }]) },
      }],
    });
  }

  async function load() {
    const district = document.getElementById("dash-district").value;
    const date_from = document.getElementById("dash-from").value;
    const date_to = document.getElementById("dash-to").value;
    try {
      const s = await API.get("/stats", { district, date_from, date_to });
      renderKPIs(s.kpis || {});
      donut(s.by_category);
      bar(s.by_district);
      hour(s.by_hour);
      month(s.by_month);
    } catch (_) {
      document.getElementById("dash-kpis").innerHTML = UI.empty("Could not load statistics", "Check the API connection and retry.", "⚠");
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    const meta = App.state.meta || {};
    App.fillSelect(document.getElementById("dash-district"), meta.districts, "All districts");
    const dr = meta.date_range || {};
    if (dr.min) document.getElementById("dash-from").min = dr.min;
    if (dr.max) { document.getElementById("dash-to").max = dr.max; }
    document.getElementById("dash-apply").addEventListener("click", load);
    document.getElementById("dash-brief-btn").addEventListener("click", runBriefing);
    load();
    loaded = true;
  }

  function onShow() { if (loaded) UI.resizeCharts(); }

  return { mount, onShow };
})();
