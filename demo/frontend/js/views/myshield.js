/* ============================================================
   myshield.js — citizen self-check. Shows ONLY the requester's
   own records + de-identified area stats. Privacy-first.
   ============================================================ */
Views.MyShield = (() => {
  let el, mounted = false;

  function shell() {
    return `
      <div class="shield-wrap">
        <div class="view-head" style="margin-bottom:14px">
          <div>
            <h1 class="view-title"><span class="vt-ico">🛡</span> MyShield · Citizen Safety</h1>
            <div class="view-sub">Check whether your own identifier appears in any case, and see de-identified safety stats for your area.</div>
          </div>
        </div>

        <div class="shield-card mb12">
          <div class="controls">
            <div class="ctrl" style="flex:1;min-width:220px">
              <span class="ctrl-label">Your phone, vehicle registration, or name</span>
              <input type="text" id="ms-id" placeholder="e.g. 9876543210  ·  KA01AB1234  ·  Ramesh Kumar" style="width:100%"/>
            </div>
            <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary" id="ms-check">Check my records</button></div>
          </div>
        </div>

        <div class="privacy-note mb12">
          <span class="pn-ico">🔒</span>
          <div id="ms-disclaimer"><b>Privacy first.</b> MyShield only ever returns records matching the identifier you enter, plus de-identified, aggregated area statistics. No one else's personal data is exposed.</div>
        </div>

        <div id="ms-result"></div>
      </div>`;
  }

  function renderMatches(matches) {
    if (!matches.length) {
      return `<div class="panel panel-pad mb12">${UI.empty("No records found", "Good news — your identifier does not appear in any case in the dataset.", "✓")}</div>`;
    }
    return `<div class="panel panel-pad mb12">
      <h3 class="panel-title"><span class="dotaccent"></span> Records linked to you (${matches.length})</h3>
      <div class="tbl-wrap"><table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>Station</th><th>Date</th><th>Status</th></tr></thead><tbody>${
        matches.map((m) => `<tr>
          <td class="mono">${UI.esc(m.fir_number)}</td>
          <td>${UI.esc(UI.val(m.crime_type))}</td>
          <td class="dim">${UI.esc(UI.val(m.police_station))}</td>
          <td class="dim">${UI.date(m.date)}</td>
          <td><span class="badge neutral">${UI.esc(UI.val(m.status))}</span></td>
        </tr>`).join("")}</tbody></table></div>
    </div>`;
  }

  function renderArea(area) {
    if (!area || !area.district) return "";
    const counts = area.counts_by_type || {};
    const entries = Object.entries(counts);
    const chartId = "ms-area-chart";
    setTimeout(() => {
      if (!entries.length) return;
      UI.mountChart(chartId, {
        ...UI.chartBase(),
        tooltip: { ...UI.chartBase().tooltip, trigger: "axis", axisPointer: { type: "shadow" } },
        grid: { left: 8, right: 18, top: 12, bottom: 6, containLabel: true },
        xAxis: { type: "value", ...UI.axisCommon },
        yAxis: { type: "category", data: entries.map((e) => e[0]).reverse(), ...UI.axisCommon, axisLabel: { color: "#9fb0c6", fontSize: 10.5 } },
        series: [{ type: "bar", data: entries.map((e) => e[1]).reverse(), barWidth: "60%",
          itemStyle: { borderRadius: [0, 5, 5, 0], color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [{ offset: 0, color: "#1F7A8C" }, { offset: 1, color: "#2ba6bd" }]) } }],
      });
    }, 30);
    return `<div class="panel panel-pad">
      <h3 class="panel-title"><span class="dotaccent"></span> Area safety · ${UI.esc(area.district)}
        <span class="faint" style="margin-left:auto;font-weight:600">${UI.num(area.total_in_district)} cases in district</span></h3>
      <div class="dim mb12" style="font-size:11.5px">De-identified, aggregate counts only — no individual records.</div>
      ${entries.length ? `<div class="chart" id="${chartId}" style="height:240px"></div>` : UI.empty("No area data", "", "·")}
    </div>`;
  }

  async function check() {
    const id = document.getElementById("ms-id").value.trim();
    if (!id) { UI.toast("Enter an identifier", "Type your phone, vehicle reg, or name.", "info"); return; }
    const host = document.getElementById("ms-result");
    host.innerHTML = `<div class="panel panel-pad"><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div></div>`;
    try {
      const r = await API.get("/myshield", { identifier: id, token: "demo" });
      if (r.disclaimer) document.getElementById("ms-disclaimer").innerHTML = `<b>Privacy first.</b> ${UI.esc(r.disclaimer)}`;
      host.innerHTML = renderMatches(r.matches || []) + renderArea(r.area_safety || {});
    } catch (_) {
      host.innerHTML = `<div class="panel panel-pad">${UI.empty("Could not check records", "Please retry shortly.", "⚠")}</div>`;
    }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("ms-check").addEventListener("click", check);
    document.getElementById("ms-id").addEventListener("keydown", (e) => { if (e.key === "Enter") check(); });
    mounted = true;
  }

  return { mount };
})();
