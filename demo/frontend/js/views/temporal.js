/* ============================================================
   temporal.js — Day × Hour crime heatmap, calendar heatmap,
   and weekly pattern bar chart. Filter by district + type.
   ============================================================ */
Views.Temporal = (() => {
  let el, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⏱</span> Temporal Analysis</h1>
          <div class="view-sub">Day-of-week × hour-of-day crime concentration, annual calendar heatmap, and peak shift identification for targeted patrol scheduling.</div>
        </div>
      </div>
      <div class="panel panel-pad" style="margin-bottom:16px">
        <div class="row wrap" style="justify-content:space-between">
          <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Filters</h3>
          <div class="controls">
            <div class="ctrl"><span class="ctrl-label">District</span>
              <select id="tm-district"><option value="">All districts</option></select></div>
            <div class="ctrl"><span class="ctrl-label">Crime type</span>
              <select id="tm-type"><option value="">All types</option></select></div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span>
              <button class="btn btn-primary sm" id="tm-run">Analyse</button></div>
          </div>
        </div>
      </div>
      <div class="grid kpi-grid" id="tm-kpis" style="grid-template-columns:repeat(4,1fr);margin-bottom:16px"></div>
      <div class="panel panel-pad" style="margin-bottom:16px">
        <h3 class="panel-title"><span class="dotaccent"></span> Day × Hour crime concentration heatmap</h3>
        <div class="dim" style="font-size:11.5px;margin-bottom:8px">Each cell = crime count at that day/hour combination. Darker = more crimes. Use to schedule patrol shifts and identify peak windows.</div>
        <div class="chart" id="tm-heatmap" style="height:240px">${UI.skeletonChart()}</div>
      </div>
      <div class="grid charts-grid" style="grid-template-columns:1fr 1fr">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Day-of-week pattern</h3>
          <div class="chart" id="tm-dow" style="height:220px">${UI.skeletonChart()}</div>
        </div>
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Hour-of-day pattern</h3>
          <div class="chart" id="tm-hour" style="height:220px">${UI.skeletonChart()}</div>
        </div>
      </div>
      <div class="panel panel-pad" style="margin-top:16px">
        <h3 class="panel-title"><span class="dotaccent"></span> Annual crime calendar</h3>
        <div class="dim" style="font-size:11.5px;margin-bottom:8px">Daily crime count over the full dataset — intensity shows seasonal and event-driven spikes.</div>
        <div class="chart" id="tm-calendar" style="height:180px">${UI.skeletonChart()}</div>
      </div>`;
  }

  function peakHour(matrix) {
    let max = 0, ph = 0, pd = 0;
    matrix.forEach((row, d) => row.hours.forEach((v, h) => { if (v > max) { max = v; ph = h; pd = d; } }));
    const days = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"];
    return max ? `${days[pd]} ${ph}:00–${ph + 1}:00` : "—";
  }

  function renderKPIs(d) {
    const host = document.getElementById("tm-kpis");
    const matrix = d.matrix || [];
    const hourTotals = new Array(24).fill(0);
    const dowTotals = matrix.map((row) => ({ day: row.day, total: row.hours.reduce((a, b) => a + b, 0) }));
    matrix.forEach((row) => row.hours.forEach((v, h) => { hourTotals[h] += v; }));
    const peakDow = dowTotals.reduce((a, b) => b.total > a.total ? b : a, { day: "—", total: 0 });
    const peakH = hourTotals.indexOf(Math.max(...hourTotals));
    const nightCrimes = hourTotals.slice(20).concat(hourTotals.slice(0, 6)).reduce((a, b) => a + b, 0);
    const total = hourTotals.reduce((a, b) => a + b, 0) || 1;
    host.innerHTML = `
      <div class="kpi accent-gold"><div class="kpi-label">Total crimes</div><div class="kpi-value">${UI.num(d.total)}</div><div class="kpi-foot">In filtered dataset</div></div>
      <div class="kpi"><div class="kpi-label">Peak day</div><div class="kpi-value" style="font-size:22px">${UI.esc(peakDow.day)}</div><div class="kpi-foot">${UI.num(peakDow.total)} crimes</div></div>
      <div class="kpi accent-teal"><div class="kpi-label">Peak hour</div><div class="kpi-value" style="font-size:22px">${peakH}:00</div><div class="kpi-foot">Highest crime count</div></div>
      <div class="kpi accent-red"><div class="kpi-label">Night crimes</div><div class="kpi-value">${Math.round(nightCrimes * 100 / total)}%</div><div class="kpi-foot">20:00–05:59</div></div>`;
  }

  function renderHeatmap(matrix) {
    if (!matrix.length) { document.getElementById("tm-heatmap").innerHTML = UI.empty("No data"); return; }
    const hours = Array.from({ length: 24 }, (_, i) => `${i}h`);
    const days = matrix.map((r) => r.day);
    const data = [];
    let maxVal = 0;
    matrix.forEach((row, di) => row.hours.forEach((v, h) => { data.push([h, di, v]); if (v > maxVal) maxVal = v; }));
    UI.mountChart("tm-heatmap", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "item", formatter: (p) => `${days[p.data[1]]} ${p.data[0]}:00 — <b>${p.data[2]}</b> crimes` },
      grid: { left: 48, right: 10, top: 10, bottom: 30 },
      xAxis: { type: "category", data: hours, splitArea: { show: true }, axisLabel: { color: "#9fb0c6", fontSize: 9 }, axisLine: { lineStyle: { color: "rgba(230,237,245,.18)" } } },
      yAxis: { type: "category", data: days, splitArea: { show: true }, axisLabel: { color: "#9fb0c6", fontSize: 11 }, axisLine: { lineStyle: { color: "rgba(230,237,245,.18)" } } },
      visualMap: { min: 0, max: maxVal || 1, calculable: false, orient: "horizontal", show: false,
        inRange: { color: ["rgba(31,122,140,0.08)", "rgba(43,166,189,.55)", "rgba(201,162,39,.8)", "rgba(226,87,76,1)"] } },
      series: [{ type: "heatmap", data, label: { show: maxVal < 80, color: "#E6EDF5", fontSize: 9 }, emphasis: { itemStyle: { shadowBlur: 10, shadowColor: "rgba(0,0,0,.5)" } } }],
    });
  }

  function renderDow(matrix) {
    if (!matrix.length) { document.getElementById("tm-dow").innerHTML = UI.empty("No data"); return; }
    const days = matrix.map((r) => r.day);
    const vals = matrix.map((r) => r.hours.reduce((a, b) => a + b, 0));
    const maxV = Math.max(...vals) || 1;
    UI.mountChart("tm-dow", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis" },
      grid: { left: 8, right: 8, top: 10, bottom: 6, containLabel: true },
      xAxis: { type: "category", data: days, ...UI.axisCommon },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [{ type: "bar", data: vals.map((v) => ({ value: v, itemStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: v / maxV > 0.8 ? "#e2574c" : "#C9A227" }, { offset: 1, color: v / maxV > 0.8 ? "rgba(226,87,76,.3)" : "rgba(201,162,39,.3)" }]) } })), barWidth: "62%", borderRadius: 4 }],
    });
  }

  function renderHour(matrix) {
    if (!matrix.length) { document.getElementById("tm-hour").innerHTML = UI.empty("No data"); return; }
    const hourTotals = new Array(24).fill(0);
    matrix.forEach((row) => row.hours.forEach((v, h) => { hourTotals[h] += v; }));
    UI.mountChart("tm-hour", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, trigger: "axis", formatter: (p) => `${p[0].axisValue}:00 — <b>${p[0].data}</b> crimes` },
      grid: { left: 8, right: 8, top: 10, bottom: 6, containLabel: true },
      xAxis: { type: "category", data: Array.from({ length: 24 }, (_, i) => `${i}`), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 9, interval: 1 } },
      yAxis: { type: "value", ...UI.axisCommon },
      series: [{ type: "line", data: hourTotals, smooth: true, symbol: "none", lineStyle: { color: "#2ba6bd", width: 2.5 }, areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: "rgba(43,166,189,.38)" }, { offset: 1, color: "rgba(43,166,189,0)" }]) } }],
    });
  }

  function renderCalendar(calData) {
    if (!calData.length) { document.getElementById("tm-calendar").innerHTML = UI.empty("No calendar data"); return; }
    const firstYear = calData[0].date.slice(0, 4);
    const lastYear = calData[calData.length - 1].date.slice(0, 4);
    const maxC = Math.max(...calData.map((d) => d.count)) || 1;
    UI.mountChart("tm-calendar", {
      ...UI.chartBase(),
      tooltip: { ...UI.chartBase().tooltip, formatter: (p) => `${p.data[0]}: <b>${p.data[1]}</b> crimes` },
      visualMap: { min: 0, max: maxC, calculable: false, show: false,
        inRange: { color: ["rgba(31,122,140,0.1)", "rgba(43,166,189,.6)", "rgba(201,162,39,.8)", "rgba(226,87,76,1)"] } },
      calendar: { range: [firstYear, lastYear], cellSize: ["auto", 14], left: 50, right: 10, top: 10, bottom: 10,
        dayLabel: { color: "#9fb0c6", fontSize: 9 }, monthLabel: { color: "#9fb0c6", fontSize: 10 },
        yearLabel: { color: "#C9A227", fontSize: 11 } },
      series: [{ type: "heatmap", coordinateSystem: "calendar", data: calData.map((d) => [d.date, d.count]) }],
    });
  }

  async function run() {
    const district = document.getElementById("tm-district").value;
    const crime_type = document.getElementById("tm-type").value;
    document.getElementById("tm-heatmap").innerHTML = UI.skeletonChart();
    document.getElementById("tm-dow").innerHTML = UI.skeletonChart();
    document.getElementById("tm-hour").innerHTML = UI.skeletonChart();
    document.getElementById("tm-calendar").innerHTML = UI.skeletonChart();
    document.getElementById("tm-kpis").innerHTML = UI.skeletonKPIs(4);
    try {
      const d = await API.get("/temporal", { district, crime_type });
      renderKPIs(d);
      renderHeatmap(d.matrix || []);
      renderDow(d.matrix || []);
      renderHour(d.matrix || []);
      renderCalendar(d.calendar || []);
    } catch (_) {
      document.getElementById("tm-heatmap").innerHTML = UI.empty("Could not load temporal data", "", "⚠");
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    const meta = App.state.meta || {};
    App.fillSelect(document.getElementById("tm-district"), meta.districts, "All districts");
    App.fillSelect(document.getElementById("tm-type"), meta.crime_types, "All types");
    document.getElementById("tm-run").addEventListener("click", run);
    run();
    mounted = true;
  }

  function onShow() { UI.resizeCharts(); }

  return { mount, onShow };
})();
