/* ============================================================
   forecast.js — Crime Forecasting: Holt ETS with 95% CI bands.
   Also shows near-repeat victimisation risk alerts.
   ============================================================ */
Views.Forecast = (() => {
  let el, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">↗</span> Crime Forecasting</h1>
          <div class="view-sub">Holt double-exponential smoothing on monthly crime counts — forward projections with 95% confidence bands and near-repeat victimisation alerts.</div>
        </div>
      </div>
      <div class="banner info"><span class="b-ico">🛈</span><div><b>Forecasts are probabilistic, not deterministic.</b> They are decision-support tools — shaded bands show 95% prediction intervals. Forecasts must be reviewed by an officer before any allocation decision.</div></div>
      <div class="panel panel-pad" style="margin-bottom:16px">
        <div class="row wrap" style="justify-content:space-between">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Forecast parameters</h3>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">Crime type</span>
              <select id="fc-type"><option value="">All types</option></select></div>
            <div class="ctrl"><span class="ctrl-label">District</span>
              <select id="fc-district"><option value="">All districts</option></select></div>
            <div class="ctrl"><span class="ctrl-label">Horizon</span>
              <select id="fc-months"><option value="3" selected>3 months</option><option value="6">6 months</option><option value="12">12 months</option></select></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="fc-run">Forecast</button></div>
          </div>
        </div>
      </div>
      <div class="grid kpi-grid" id="fc-kpis" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px"></div>
      <div class="panel panel-pad" style="margin-bottom:16px">
        <h3 class="panel-title"><span class="dotaccent"></span> Monthly trend &amp; forecast</h3>
        <div class="chart" id="fc-chart" style="height:340px">${UI.skeletonChart()}</div>
      </div>
      <div class="panel panel-pad">
        <h3 class="panel-title"><span class="dotaccent"></span> Near-repeat risk alerts <span class="faint" style="margin-left:8px;font-weight:600;text-transform:none;letter-spacing:0">crimes within 500m &amp; 14 days of a prior incident</span></h3>
        <div class="dim" style="font-size:11.5px;margin-bottom:10px">Based on Johnson (2008) near-repeat victimisation theory — elevated risk after a crime at a nearby location within a short time window.</div>
        <div id="fc-nr" style="max-height:300px" class="tbl-wrap scroll">${UI.skeletonChart()}</div>
      </div>`;
  }

  const TREND_ICON = { rising: "↑", falling: "↓", stable: "→" };
  const TREND_COLOR = { rising: "var(--red)", falling: "var(--teal-bright)", stable: "var(--gold)" };

  function renderKPIs(d) {
    const host = document.getElementById("fc-kpis");
    if (!d) { host.innerHTML = ""; return; }
    const dir = d.trend || "stable";
    host.innerHTML = `
      <div class="kpi accent-gold"><div class="kpi-label">Forecast (next month)</div><div class="kpi-value">${d.forecast && d.forecast[0] ? Math.round(d.forecast[0].count) : "—"}</div><div class="kpi-foot">Point estimate</div></div>
      <div class="kpi"><div class="kpi-label">Trend</div><div class="kpi-value" style="color:${TREND_COLOR[dir]}">${TREND_ICON[dir]} ${UI.esc(dir)}</div><div class="kpi-foot">Recent 3-month direction</div></div>
      <div class="kpi accent-teal"><div class="kpi-label">Peak month</div><div class="kpi-value" style="font-size:20px">${UI.esc(d.peak_period || "—")}</div><div class="kpi-foot">${UI.num(d.peak_count)} crimes</div></div>
      <div class="kpi"><div class="kpi-label">Forecast RMSE</div><div class="kpi-value" style="font-size:22px">${d.rmse != null ? d.rmse.toFixed(1) : "—"}</div><div class="kpi-foot">In-sample error (${UI.esc(d.model || "")})</div></div>`;
  }

  function renderChart(d) {
    const hist = d.history || [], fc = d.forecast || [];
    if (!hist.length) { document.getElementById("fc-chart").innerHTML = UI.empty("No data", "No monthly records for this filter.", "↗"); return; }
    const periods = hist.map((x) => x.period).concat(fc.map((x) => x.period));
    const histVals = hist.map((x) => x.count);
    const fcVals = new Array(hist.length).fill(null).concat(fc.map((x) => x.count));
    const lo = new Array(hist.length).fill(null).concat(fc.map((x) => x.lo));
    const hi = new Array(hist.length).fill(null).concat(fc.map((x) => x.hi));
    UI.mountChart("fc-chart", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis" },
      legend: { bottom: 0, textStyle: { color: "#9fb0c6", fontSize: 11 } },
      xAxis: { type: "category", data: periods, ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10, rotate: periods.length > 14 ? 35 : 0 } },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [
        { name: "Historical", type: "line", data: histVals, smooth: true, symbol: "circle", symbolSize: 5, itemStyle: { color: "#2ba6bd" }, lineStyle: { color: "#2ba6bd", width: 2.5 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(43,166,189,.28)" }, { offset: 1, color: "rgba(43,166,189,0)" }]) } },
        { name: "Forecast", type: "line", data: fcVals, smooth: true, symbol: "diamond", symbolSize: 7, itemStyle: { color: "#C9A227" }, lineStyle: { color: "#C9A227", width: 2.5, type: "dashed" } },
        { name: "95% CI upper", type: "line", data: hi, smooth: true, symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: "rgba(201,162,39,.18)" }, stack: "ci" },
        { name: "95% CI lower", type: "line", data: lo, smooth: true, symbol: "none", lineStyle: { opacity: 0 }, areaStyle: { color: "rgba(201,162,39,0)" }, stack: "ci" },
      ],
    });
  }

  function renderNearRepeat(alerts) {
    const host = document.getElementById("fc-nr");
    if (!alerts.length) { host.innerHTML = UI.empty("No near-repeat alerts", "No crimes within the 500m / 14-day risk window.", "✓"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>Days since trigger</th><th>Distance</th><th>Trigger FIR</th></tr></thead><tbody>${
      alerts.slice(0, 80).map((a) => `<tr style="background:rgba(226,87,76,.06)">
        <td class="mono">${UI.esc(a.fir_number)}</td>
        <td>${UI.esc(UI.val(a.crime_type))}</td>
        <td><span class="badge review">${a.days_since}d</span></td>
        <td class="dim">${(a.distance_km || 0).toFixed(3)} km</td>
        <td class="mono dim">${UI.esc(a.trigger_fir)}</td>
      </tr>`).join("")}</tbody></table>`;
  }

  async function run() {
    const crime_type = document.getElementById("fc-type").value;
    const district = document.getElementById("fc-district").value;
    const months = document.getElementById("fc-months").value;
    document.getElementById("fc-chart").innerHTML = UI.skeletonChart();
    document.getElementById("fc-nr").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    document.getElementById("fc-kpis").innerHTML = UI.skeletonKPIs(4);
    const [fc, nr] = await Promise.allSettled([
      API.get("/forecast", { crime_type, district, months }),
      API.get("/near-repeat", { crime_type }),
    ]);
    if (fc.status === "fulfilled") { renderKPIs(fc.value); renderChart(fc.value); }
    else { document.getElementById("fc-chart").innerHTML = UI.empty("Forecast failed", "", "⚠"); }
    if (nr.status === "fulfilled") renderNearRepeat(nr.value.alerts || []);
    else document.getElementById("fc-nr").innerHTML = UI.empty("Near-repeat unavailable", "", "⚠");
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    const meta = App.state.meta || {};
    App.fillSelect(document.getElementById("fc-type"), meta.crime_types, "All types");
    App.fillSelect(document.getElementById("fc-district"), meta.districts, "All districts");
    document.getElementById("fc-run").addEventListener("click", run);
    run();
    mounted = true;
  }

  function onShow() { UI.resizeCharts(); }

  return { mount, onShow };
})();
