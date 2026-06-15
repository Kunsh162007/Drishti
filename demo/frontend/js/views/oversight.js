/* ============================================================
   oversight.js — Oversight & Audit: recording-coverage fairness
   diagnostics + the tamper-evident audit ledger with integrity.
   ============================================================ */
Views.Oversight = (() => {
  let el;

  function shell() {
    return `
      <div class="view-head"><div>
        <h1 class="view-title"><span class="vt-ico">⚙</span> Oversight &amp; Audit</h1>
        <div class="view-sub">Accountability layer: recording-coverage diagnostics and a tamper-evident access ledger.</div>
      </div></div>

      <div class="banner warn"><span class="b-ico">⚠</span><div>
        <b>Diagnostics, not proof of bias.</b> District coverage reflects <i>recording</i> patterns and policing intensity —
        review flagged districts; do not treat them as conclusions.</div></div>

      <div class="grid" style="grid-template-columns:1.1fr .9fr;gap:16px">
        <div class="panel panel-pad"><h3 class="panel-title"><span class="dotaccent"></span> Record coverage by district</h3>
          <div class="chart" id="ov-coverage" style="height:340px"></div></div>
        <div class="panel panel-pad" style="display:flex;flex-direction:column">
          <h3 class="panel-title"><span class="dotaccent"></span> Disparity flags to review</h3>
          <div class="scroll" style="max-height:340px" id="ov-flags"></div></div>
      </div>

      <div class="panel panel-pad mt12">
        <h3 class="panel-title"><span class="dotaccent"></span> Tamper-evident audit ledger
          <span id="ov-integrity" style="margin-left:auto"></span></h3>
        <div class="dim" style="font-size:12px;margin:-4px 0 8px">Every API access is hash-chained: <span class="mono">entry_hash = SHA-256(prev_hash + entry)</span>. Any edit or deletion breaks the chain.</div>
        <div class="tbl-wrap scroll" style="max-height:360px" id="ov-audit"></div>
      </div>`;
  }

  function renderCoverage(rows) {
    const top = (rows || []).slice(0, 18);
    UI.mountChart("ov-coverage", Object.assign(UI.chartBase(), {
      grid: { left: 8, right: 24, top: 16, bottom: 6, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
      xAxis: Object.assign({ type: "value" }, UI.axisCommon),
      yAxis: Object.assign({ type: "category", inverse: true, data: top.map((d) => d.name) }, UI.axisCommon),
      series: [{ type: "bar", data: top.map((d) => d.records), barWidth: "62%",
        itemStyle: { color: "#1F7A8C", borderRadius: [0, 4, 4, 0] },
        label: { show: true, position: "right", color: "#9fb0c6", formatter: (p) => `${top[p.dataIndex].share_pct}%` } }],
    }));
  }

  function renderFlags(flags) {
    const host = document.getElementById("ov-flags");
    if (!flags || !flags.length) { host.innerHTML = UI.empty("No disparity flags", "Coverage is within expected bounds.", "✓"); return; }
    host.innerHTML = flags.map((f) =>
      `<div class="banner warn" style="margin:0 0 8px"><span class="b-ico">⚑</span><div><b>${UI.esc(UI.title(f.type || "flag"))}</b><br/><span class="dim">${UI.esc(UI.val(f.detail))}</span></div></div>`).join("");
  }

  function renderAudit(d) {
    const intg = d.integrity || {};
    const badge = document.getElementById("ov-integrity");
    if (intg.valid) {
      badge.innerHTML = `<span class="badge" style="background:#2E7D3222;color:#6ddaa6;border-color:#2E7D3255">✓ chain verified · ${UI.num(intg.count)} entries</span>`;
    } else {
      badge.innerHTML = `<span class="badge" style="background:#B3261E22;color:#e2574c;border-color:#B3261E55">✗ tampering detected @ #${UI.val(intg.broken_at)}</span>`;
    }
    const host = document.getElementById("ov-audit");
    const rows = d.entries || [];
    if (!rows.length) { host.innerHTML = UI.empty("No audit entries yet", "Use the app — every access is logged here.", "⚙"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>#</th><th>Time (UTC)</th><th>User</th><th>Action</th><th>Resource</th><th>Entry hash</th></tr></thead><tbody>${
      rows.map((r) => `<tr>
        <td><b style="color:var(--gold)">${r.seq}</b></td>
        <td class="dim mono" style="font-size:10.5px">${UI.esc((r.ts || "").slice(0, 19).replace("T", " "))}</td>
        <td>${UI.esc(UI.val(r.user))}</td>
        <td><span class="chip">${UI.esc(UI.val(r.action))}</span></td>
        <td class="mono" style="font-size:10.5px">${UI.esc(UI.val(r.resource))}</td>
        <td class="mono dim" style="font-size:10px" title="${UI.esc(r.entry_hash)}">${UI.esc((r.entry_hash || "").slice(0, 16))}…</td>
      </tr>`).join("")}</tbody></table>`;
  }

  async function load() {
    document.getElementById("ov-audit").innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    const [fair, aud] = await Promise.allSettled([API.get("/oversight/fairness"), API.get("/oversight/audit", { limit: 60 })]);
    if (fair.status === "fulfilled") { renderCoverage(fair.value.coverage_by_district); renderFlags(fair.value.disparity_flags); }
    else document.getElementById("ov-flags").innerHTML = UI.empty("Unavailable", "", "⚠");
    if (aud.status === "fulfilled") renderAudit(aud.value);
    else document.getElementById("ov-audit").innerHTML = UI.empty("Audit unavailable", "", "⚠");
  }

  function mount(node) { el = node; el.innerHTML = shell(); load(); }
  function onShow() { load(); UI.resizeCharts(); }

  return { mount, onShow };
})();
