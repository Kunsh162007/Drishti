/* ============================================================
   registry.js — Case Registry (KSP FIR schema).
   Legal, court and officer analytics served directly from the
   official CCTNS-aligned normalized tables (CaseMaster,
   ActSectionAssociation, Court, Employee, Unit ...).
   Endpoints: /ksp/legal · /ksp/court-pendency · /ksp/officer-workload
   ============================================================ */
Views.Registry = (() => {
  let el;

  function kpi(label, key, foot, accent = "", fmt = "num") {
    const isPct = fmt === "pct";
    return `<div class="kpi ${accent}">
      <div class="kpi-label">${label}</div>
      <div class="kpi-value" data-k="${key}" data-fmt="${fmt}">0${isPct ? '<span class="unit">%</span>' : ""}</div>
      <div class="kpi-foot">${UI.esc(foot)}</div></div>`;
  }

  function shell() {
    return `
      <div class="view-head"><div>
        <h1 class="view-title"><span class="vt-ico">⚖</span> Case Registry <span class="badge" style="background:#1F7A8C22;color:#2ba6bd;border-color:#1F7A8C55;margin-left:8px">KSP FIR schema</span></h1>
        <div class="view-sub">Legal, court and officer analytics served live from the official CCTNS-aligned normalized tables — <span class="mono">CaseMaster · ActSectionAssociation · Court · Employee</span>.</div>
      </div></div>

      <!-- ============ Act & Section ============ -->
      <h3 class="panel-title mt4"><span class="dotaccent"></span> Legal charges — Acts &amp; Sections</h3>
      <div class="grid kpi-grid" id="reg-legal-kpis">${UI.skeletonKPIs(4)}</div>
      <div class="grid mt12" style="grid-template-columns:1fr 1.2fr;gap:16px">
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> Charges by Act</h3>
          <div class="chart" id="reg-acts" style="height:300px"></div></div>
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Top charged sections</h3>
          <div class="scroll" style="max-height:300px" id="reg-sections"></div></div>
      </div>

      <!-- ============ Court pendency ============ -->
      <h3 class="panel-title mt12"><span class="dotaccent"></span> Court pendency &amp; disposal</h3>
      <div class="grid kpi-grid" id="reg-court-kpis">${UI.skeletonKPIs(4)}</div>
      <div class="grid mt12" style="grid-template-columns:.8fr 1.2fr;gap:16px">
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> Case-status funnel</h3>
          <div class="chart" id="reg-status" style="height:300px"></div></div>
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> Pending vs disposed by court</h3>
          <div class="chart" id="reg-courts" style="height:300px"></div></div>
      </div>

      <!-- ============ Officer workload ============ -->
      <h3 class="panel-title mt12"><span class="dotaccent"></span> Officer &amp; station workload</h3>
      <div class="grid kpi-grid" id="reg-off-kpis">${UI.skeletonKPIs(4)}</div>
      <div class="grid mt12" style="grid-template-columns:1.15fr .85fr;gap:16px">
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Registering officers by caseload</h3>
          <div class="tbl-wrap scroll" style="max-height:320px" id="reg-officers"></div></div>
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> Busiest stations</h3>
          <div class="chart" id="reg-stations" style="height:320px"></div></div>
      </div>`;
  }

  function fillKpis(hostId, kpis) {
    const host = document.getElementById(hostId);
    if (!host) return;
    host.querySelectorAll("[data-k]").forEach((node) => {
      const k = node.dataset.k;
      const fmt = node.dataset.fmt;
      const raw = kpis[k];
      if (typeof raw === "number") UI.countUp(node, raw, { decimals: fmt === "pct" ? 1 : 0 });
      else node.textContent = UI.val(raw);
    });
  }

  function hbar(elId, rows, valueKey, color) {
    const top = (rows || []).slice(0, 12);
    UI.mountChart(elId, Object.assign(UI.chartBase(), {
      grid: { left: 8, right: 40, top: 12, bottom: 6, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: Object.assign({ type: "value" }, UI.axisCommon),
      yAxis: Object.assign({ type: "category", inverse: true, data: top.map((d) => d.name) }, UI.axisCommon),
      series: [{ type: "bar", data: top.map((d) => d[valueKey]), barWidth: "60%",
        itemStyle: { color, borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: "#9fb0c6", formatter: (p) => UI.num(top[p.dataIndex][valueKey]) } }],
    }));
  }

  async function loadLegal() {
    try {
      const d = await API.get("/ksp/legal");
      const k = document.getElementById("reg-legal-kpis");
      k.innerHTML = kpi("Total charges", "total_charges", "Act-section rows across all FIRs") +
        kpi("Distinct Acts", "distinct_acts", "IPC, IT Act, NDPS, POCSO …") +
        kpi("Distinct Sections", "distinct_sections", "Unique charged sections") +
        kpi("Top Act", "top_act", "Most-applied statute", "gold");
      fillKpis("reg-legal-kpis", d.kpis || {});
      hbar("reg-acts", (d.by_act || []).map((r) => ({ name: r.name, value: r.value })), "value", "#C9A227");
      const host = document.getElementById("reg-sections");
      const secs = d.by_section || [];
      host.innerHTML = secs.length ? `<table class="tbl"><thead><tr><th>Act</th><th>Section</th><th>Description</th><th style="text-align:right">FIRs</th></tr></thead><tbody>${
        secs.map((r) => `<tr><td><span class="chip">${UI.esc(r.act)}</span></td>
          <td><b style="color:var(--gold)">${UI.esc(r.section)}</b></td>
          <td class="dim" style="font-size:11.5px">${UI.esc(UI.val(r.description))}</td>
          <td style="text-align:right"><b>${UI.num(r.value)}</b></td></tr>`).join("")}</tbody></table>`
        : UI.empty("No section data", "", "⚖");
    } catch (_) {
      document.getElementById("reg-legal-kpis").innerHTML = UI.empty("Legal data unavailable", "Run build_ksp_schema.py", "⚠");
    }
  }

  async function loadCourt() {
    try {
      const d = await API.get("/ksp/court-pendency");
      const k = document.getElementById("reg-court-kpis");
      k.innerHTML = kpi("Total cases", "total_cases", "Registered FIRs (CaseMaster)") +
        kpi("Pending", "pending", "Open / Under Investigation", "red") +
        kpi("Disposed", "disposed", "Charge-sheeted or closed", "teal") +
        kpi("Disposal rate", "disposal_rate", "Share of cases disposed", "gold", "pct");
      fillKpis("reg-court-kpis", d.kpis || {});
      // status funnel
      const st = d.by_status || [];
      UI.mountChart("reg-status", Object.assign(UI.chartBase(), {
        tooltip: { trigger: "item" },
        series: [{ type: "funnel", left: 8, right: 8, top: 8, bottom: 8, minSize: "18%",
          sort: "descending", gap: 3, label: { color: "#E6EDF5", fontSize: 11, formatter: "{b}: {c}" },
          data: st.map((r) => ({ name: r.name, value: r.value })) }],
      }));
      // stacked pending vs disposed
      const co = d.by_court || [];
      UI.mountChart("reg-courts", Object.assign(UI.chartBase(), {
        grid: { left: 8, right: 16, top: 30, bottom: 6, containLabel: true },
        legend: { data: ["Disposed", "Pending"], textStyle: { color: "#9fb0c6" }, top: 0 },
        tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
        xAxis: Object.assign({ type: "value" }, UI.axisCommon),
        yAxis: Object.assign({ type: "category", inverse: true, data: co.map((r) => (r.name || "").replace("District & Sessions Court, ", "")) }, UI.axisCommon),
        series: [
          { name: "Disposed", type: "bar", stack: "t", data: co.map((r) => r.disposed), itemStyle: { color: "#3ba776" } },
          { name: "Pending", type: "bar", stack: "t", data: co.map((r) => r.pending), itemStyle: { color: "#e2574c" } },
        ],
      }));
    } catch (_) {
      document.getElementById("reg-court-kpis").innerHTML = UI.empty("Court data unavailable", "", "⚠");
    }
  }

  async function loadOfficer() {
    try {
      const d = await API.get("/ksp/officer-workload");
      const k = document.getElementById("reg-off-kpis");
      k.innerHTML = kpi("Registering officers", "officers", "Distinct officers on FIRs") +
        kpi("Stations", "stations", "Police stations with cases") +
        kpi("Avg caseload", "avg_caseload", "Cases per officer", "teal") +
        kpi("Busiest station", "busiest_station", "Highest FIR volume", "gold");
      fillKpis("reg-off-kpis", d.kpis || {});
      const rows = d.by_officer || [];
      const host = document.getElementById("reg-officers");
      host.innerHTML = rows.length ? `<table class="tbl"><thead><tr><th>Officer</th><th>Rank</th><th>Station</th><th style="text-align:right">Cases</th><th style="text-align:right">Clearance</th></tr></thead><tbody>${
        rows.map((r) => `<tr><td><b>${UI.esc(UI.val(r.name))}</b></td>
          <td class="dim" style="font-size:11px">${UI.esc(UI.val(r.rank))}</td>
          <td class="dim" style="font-size:11px">${UI.esc(UI.val(r.station))}</td>
          <td style="text-align:right"><b style="color:var(--gold)">${UI.num(r.cases)}</b></td>
          <td style="text-align:right">${UI.val(r.clearance)}%</td></tr>`).join("")}</tbody></table>`
        : UI.empty("No officer data", "", "⚐");
      hbar("reg-stations", (d.by_station || []).map((r) => ({ name: r.name, value: r.value })), "value", "#1F7A8C");
    } catch (_) {
      document.getElementById("reg-off-kpis").innerHTML = UI.empty("Officer data unavailable", "", "⚠");
    }
  }

  function load() { loadLegal(); loadCourt(); loadOfficer(); }

  function mount(node) { el = node; el.innerHTML = shell(); load(); }
  function onShow() { UI.resizeCharts(); }

  return { mount, onShow };
})();
