/* ============================================================
   ingestion.js — connect-your-own-data: drag/drop or pick a file,
   POST /api/ingest, render inserted/skipped + missing-fields report.
   ============================================================ */
Views.Ingestion = (() => {
  let el, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⤓</span> Data &amp; Ingestion</h1>
          <div class="view-sub">DRISHTI runs on a canonical FIR schema — crimes, persons and vehicles geocoded to H3 hex cells. Connect your own dataset and every analysis keeps working.</div>
        </div>
      </div>

      <div class="grid" style="grid-template-columns:1.1fr .9fr;gap:18px">
        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Upload a dataset</h3>
          <div class="dropzone" id="dz">
            <div class="dz-ico">⤓</div>
            <div class="dz-main">Drag &amp; drop a file here, or click to browse</div>
            <div class="dz-sub">Supported formats:</div>
            <div class="mt12">
              <span class="fmt-pill">CSV</span><span class="fmt-pill">JSON</span><span class="fmt-pill">NDJSON</span>
              <span class="fmt-pill">GeoJSON</span><span class="fmt-pill">XLSX</span>
            </div>
            <input type="file" id="dz-input" accept=".csv,.json,.ndjson,.geojson,.xlsx,.xls" style="display:none"/>
          </div>

          <div class="banner warn mt16"><span class="b-ico">⚠</span><div><b>Zero-fabrication policy.</b> Missing fields are <b>reported</b>, never auto-filled. Column names that differ from the canonical schema can be remapped with an optional mapping (see <span class="mono">data/samples/MAPPING_EXAMPLE.json</span>).</div></div>

          <div class="row wrap mt16">
            <button class="btn btn-teal" id="ing-sample">Try the bundled new-incidents demo</button>
            <span class="faint" style="font-size:11px;flex:1">Upload <span class="mono">demo/data/samples/new_incidents.csv</span> to prove "add new data, everything still works".</span>
          </div>

          <div id="ing-result" class="mt16"></div>
        </div>

        <div class="panel panel-pad">
          <h3 class="panel-title"><span class="dotaccent"></span> Canonical schema</h3>
          <div class="dim mb12" style="font-size:12px">Your file is mapped to these fields. Anything missing is flagged in the report, not invented.</div>
          <div class="tbl-wrap scroll" style="max-height:520px"><table class="tbl"><thead><tr><th>Field</th><th>Meaning</th></tr></thead><tbody>${
            SCHEMA.map((s) => `<tr><td class="mono" style="color:var(--gold-soft)">${UI.esc(s[0])}</td><td class="dim">${UI.esc(s[1])}</td></tr>`).join("")
          }</tbody></table></div>
          <div class="dim mt12" style="font-size:11px">Start from <span class="mono">data/samples/connect_your_own_TEMPLATE.csv</span> for a ready-to-fill header row.</div>
        </div>
      </div>`;
  }

  const SCHEMA = [
    ["fir_number", "Unique case identifier"],
    ["district", "Karnataka district / jurisdiction"],
    ["police_station", "Reporting station"],
    ["crime_type", "Specific offence (e.g. Vehicle Theft)"],
    ["crime_category", "Group (Violent / Property / Cybercrime…)"],
    ["severity", "1–5 severity scale"],
    ["latitude · longitude", "Geolocation (auto-binned to H3 r7/r8/r9)"],
    ["occurred_at · reported_at", "ISO8601 timestamps"],
    ["hour · day_of_week", "Derived time features"],
    ["modus_operandi", "Free-text method description"],
    ["status", "Open / UnderInvestigation / ChargeSheeted / Closed"],
    ["victim_count · accused_count", "Counts"],
    ["property_value_inr", "Property value (nullable)"],
    ["weapon_used · source", "Optional metadata"],
  ];

  function renderResult(r) {
    const host = document.getElementById("ing-result");
    const missing = r.missing_report || {};
    const missEntries = Object.entries(missing).sort((a, b) => b[1] - a[1]);
    const errs = r.errors || [];
    host.innerHTML = `
      <div class="panel panel-pad" style="background:rgba(59,167,118,.06);border-color:rgba(59,167,118,.25)">
        <div class="row wrap" style="gap:24px;justify-content:space-around;text-align:center">
          <div><div class="kpi-value" style="font-size:26px;color:#6ddaa6">${UI.num(r.inserted)}</div><div class="kpi-label">Inserted</div></div>
          <div><div class="kpi-value" style="font-size:26px;color:var(--text-dim)">${UI.num(r.skipped)}</div><div class="kpi-label">Skipped (dupes)</div></div>
          <div><div class="kpi-value" style="font-size:26px;color:${errs.length ? "var(--red)" : "var(--text-dim)"}">${UI.num(errs.length)}</div><div class="kpi-label">Errors</div></div>
        </div>
      </div>
      <div class="panel panel-pad mt16">
        <h3 class="panel-title"><span class="dotaccent"></span> Missing-fields report</h3>
        <div class="dim mb12" style="font-size:11.5px">${r.note ? UI.esc(r.note) : "Missing fields are reported, never auto-filled."}</div>
        ${missEntries.length
          ? `<div class="tbl-wrap"><table class="tbl"><thead><tr><th>Field</th><th>Rows missing</th></tr></thead><tbody>${
              missEntries.map(([k, v]) => `<tr><td class="mono">${UI.esc(k)}</td><td><span class="badge ${v ? "review" : "auto"}">${UI.num(v)}</span></td></tr>`).join("")
            }</tbody></table></div>`
          : UI.empty("No missing fields", "Every row was complete against the canonical schema.", "✓")}
        ${errs.length ? `<div class="banner warn mt12"><span class="b-ico">⚠</span><div>${errs.map(UI.esc).join("<br/>")}</div></div>` : ""}
      </div>`;
    if ((r.inserted || 0) > 0) {
      UI.toast("Ingestion complete", `${r.inserted} record(s) added. Refreshing meta…`, "ok");
      App.loadMeta(); // refresh cached districts/types/totals
    }
  }

  async function upload(file) {
    if (!file) return;
    const host = document.getElementById("ing-result");
    host.innerHTML = `<div class="panel panel-pad"><div class="row" style="gap:10px"><span class="typing"><i></i><i></i><i></i></span><span class="dim">Ingesting <b>${UI.esc(file.name)}</b>…</span></div></div>`;
    const fd = new FormData();
    fd.append("file", file);
    fd.append("mapping", "{}");
    try {
      const r = await API.postForm("/ingest", fd);
      renderResult(r);
    } catch (_) {
      host.innerHTML = `<div class="panel panel-pad">${UI.empty("Ingestion failed", "Check the file format and that the backend is running.", "⚠")}</div>`;
    }
  }

  function bind() {
    const dz = document.getElementById("dz");
    const input = document.getElementById("dz-input");
    dz.addEventListener("click", () => input.click());
    input.addEventListener("change", () => upload(input.files[0]));
    ["dragover", "dragenter"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
    ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
    dz.addEventListener("drop", (e) => { if (e.dataTransfer.files[0]) upload(e.dataTransfer.files[0]); });
    document.getElementById("ing-sample").addEventListener("click", () => {
      UI.toast("Upload new_incidents.csv", "Only / and /api are served, so the sample can't be auto-fetched. Drag demo/data/samples/new_incidents.csv into the dropzone.", "info", 7000);
      document.getElementById("dz").classList.add("drag");
      setTimeout(() => document.getElementById("dz").classList.remove("drag"), 1400);
    });
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    bind();
    mounted = true;
  }

  return { mount };
})();
