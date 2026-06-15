/* ============================================================
   investigations.js — Entity Resolution + MO Linkage tools.
   ============================================================ */
Views.Investigations = (() => {
  let el, mounted = false;

  function shell() {
    return `
      <div class="view-head">
        <div>
          <h1 class="view-title"><span class="vt-ico">⚖</span> Investigations</h1>
          <div class="view-sub">Two evidence-linkage tools: de-duplicate identities across FIRs, and surface crimes sharing a modus operandi.</div>
        </div>
      </div>

      <div class="grid" style="grid-template-columns:1fr;gap:18px">
        <!-- Entity resolution -->
        <div class="panel panel-pad">
          <div class="row wrap" style="justify-content:space-between;margin-bottom:14px">
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Entity resolution — candidate duplicate identities</h3>
            <div class="controls">
              <div class="ctrl"><span class="ctrl-label">Threshold</span>
                <select id="er-threshold"><option value="0.75">0.75</option><option value="0.82" selected>0.82</option><option value="0.88">0.88</option><option value="0.95">0.95</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary sm" id="er-run">Run</button></div>
            </div>
          </div>
          <div class="banner info" style="margin-bottom:12px"><span class="b-ico">🛈</span><div>Pairs in the <b>review</b> band are highlighted for an officer's confirmation — never auto-merged. <b>auto</b> = phone-match or near-identical name.</div></div>
          <div class="tbl-wrap scroll" style="max-height:380px" id="er-table"></div>
        </div>

        <!-- MO linkage -->
        <div class="panel panel-pad">
          <div class="row wrap" style="justify-content:space-between;margin-bottom:14px">
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> MO linkage — find crimes with a similar method</h3>
            <div class="controls">
              <div class="ctrl"><span class="ctrl-label">FIR number</span>
                <input type="search" id="mo-fir" placeholder="e.g. FIR-2024-000001" style="min-width:190px"/>
              </div>
              <div class="ctrl"><span class="ctrl-label">Top K</span>
                <select id="mo-topk"><option>5</option><option selected>10</option><option>15</option><option>25</option></select>
              </div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-teal sm" id="mo-run">Link</button></div>
            </div>
          </div>
          <div id="mo-result">${UI.empty("Enter a FIR number", "We will surface other FIRs sharing modus-operandi terms, ranked by similarity.", "⚖")}</div>
        </div>

        <!-- NLP narrative extraction -->
        <div class="panel panel-pad">
          <div class="row wrap" style="justify-content:space-between;margin-bottom:14px">
            <h3 class="panel-title" style="margin:0"><span class="dotaccent"></span> Narrative intelligence — extract entities from an FIR</h3>
            <div class="controls">
              <div class="ctrl"><span class="ctrl-label">FIR number</span>
                <input type="search" id="nlp-fir" placeholder="e.g. FIR-2024-000001" style="min-width:190px"/></div>
              <div class="ctrl"><span class="ctrl-label">&nbsp;</span><button class="btn btn-primary sm" id="nlp-run">Extract</button></div>
            </div>
          </div>
          <div class="banner info" style="margin-bottom:12px"><span class="b-ico">🛈</span><div>Rule-based extraction — only what is <b>literally present</b> in the narrative is shown; nothing is inferred or invented.</div></div>
          <div id="nlp-result">${UI.empty("Enter a FIR number", "Pull vehicles, phones, weapons, methods, amounts and locations out of the FIR narrative.", "✦")}</div>
        </div>
      </div>`;
  }

  function chipGroup(label, arr) {
    if (!arr || !arr.length) return "";
    return `<div style="margin:7px 0"><span class="dim" style="font-size:10.5px;text-transform:uppercase;letter-spacing:.06em">${UI.esc(label)}</span><div style="margin-top:3px">${arr.map((x) => `<span class="chip term" style="margin:2px">${UI.esc(x)}</span>`).join("")}</div></div>`;
  }

  function renderNLP(d) {
    const host = document.getElementById("nlp-result");
    const e = d.entities || {};
    const any = Object.values(e).some((v) => v && v.length) || (d.keywords || []).length;
    host.innerHTML = `
      <div class="dim mb12" style="font-size:12px">FIR <span class="chip fir">${UI.esc(d.fir)}</span> — ${UI.esc(UI.val(d.summary))}</div>
      ${chipGroup("Vehicles", e.vehicles)}${chipGroup("Phones", e.phones)}${chipGroup("Weapons", e.weapons)}
      ${chipGroup("Methods", e.methods)}${chipGroup("Amounts", e.amounts)}${chipGroup("Locations", e.locations)}
      ${chipGroup("Keywords", d.keywords)}
      ${any ? "" : UI.empty("No structured entities", "The narrative contained nothing recognisable to extract.", "✦")}`;
  }

  async function runNLP() {
    const fir = document.getElementById("nlp-fir").value.trim();
    if (!fir) { UI.toast("Enter a FIR", "Type a FIR number to extract entities.", "info"); return; }
    const host = document.getElementById("nlp-result");
    host.innerHTML = `<div class="shimmer sk-line"></div>`;
    try { renderNLP(await API.get("/nlp/extract", { fir })); }
    catch (_) { host.innerHTML = UI.empty("Could not extract", "", "⚠"); }
  }

  function decisionBadge(d) {
    const cls = d === "auto" ? "auto" : d === "reject" ? "reject" : "review";
    return `<span class="badge ${cls}">${UI.esc(d || "review")}</span>`;
  }

  function renderER(pairs) {
    const host = document.getElementById("er-table");
    if (!pairs.length) { host.innerHTML = UI.empty("No candidate pairs", "No identities crossed the similarity threshold.", "✓"); return; }
    host.innerHTML = `<table class="tbl"><thead><tr><th>Identity A</th><th>Identity B</th><th>Score</th><th>Evidence</th><th>Decision</th></tr></thead><tbody>${
      pairs.map((p) => {
        const reviewRow = p.decision === "review" ? ' style="background:rgba(230,147,47,.06)"' : "";
        return `<tr${reviewRow}>
          <td><b>${UI.esc(UI.val(p.a))}</b><div class="faint mono" style="font-size:10px">${UI.esc(UI.val(p.a_fir))}</div></td>
          <td><b>${UI.esc(UI.val(p.b))}</b><div class="faint mono" style="font-size:10px">${UI.esc(UI.val(p.b_fir))}</div></td>
          <td style="min-width:96px"><div class="row" style="gap:6px"><div class="score-bar" style="flex:1"><i style="width:${Math.round((p.score || 0) * 100)}%"></i></div><span style="font-weight:700">${(p.score ?? 0).toFixed(2)}</span></div></td>
          <td>${(p.evidence || []).map((e) => `<span class="chip term" style="margin:1px">${UI.esc(e)}</span>`).join("") || "—"}</td>
          <td>${decisionBadge(p.decision)}</td>
        </tr>`;
      }).join("")}</tbody></table>`;
  }

  async function runER() {
    const host = document.getElementById("er-table");
    host.innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const r = await API.get("/entity-resolution", { threshold: document.getElementById("er-threshold").value });
      renderER(r.pairs || []);
    } catch (_) { host.innerHTML = UI.empty("Could not run resolution", "", "⚠"); }
  }

  function renderMO(target, matches) {
    const host = document.getElementById("mo-result");
    if (!matches.length) {
      host.innerHTML = UI.empty(`No linked crimes for ${UI.esc(target)}`, "Either the FIR was not found or no other crime shares its MO terms.", "⚖");
      return;
    }
    host.innerHTML = `
      <div class="dim mb12" style="font-size:12px">Target FIR <span class="chip fir">${UI.esc(target)}</span> — ${matches.length} similar crime(s) ranked by MO similarity.</div>
      <div class="tbl-wrap scroll" style="max-height:420px"><table class="tbl"><thead><tr><th>FIR</th><th>Type</th><th>District</th><th>Date</th><th>Similarity</th><th>Shared MO terms</th></tr></thead><tbody>${
        matches.map((m) => `<tr>
          <td class="mono">${UI.esc(m.fir_number)}</td>
          <td>${UI.esc(UI.val(m.crime_type))}</td>
          <td class="dim">${UI.esc(UI.val(m.district))}</td>
          <td class="dim">${UI.date(m.occurred_at)}</td>
          <td style="min-width:96px"><div class="row" style="gap:6px"><div class="score-bar" style="flex:1"><i style="width:${Math.round((m.similarity || 0) * 100)}%"></i></div><span style="font-weight:700">${(m.similarity ?? 0).toFixed(2)}</span></div></td>
          <td>${(m.shared_terms || []).map((t) => `<span class="chip term" style="margin:1px">${UI.esc(t)}</span>`).join("") || "—"}</td>
        </tr>`).join("")}</tbody></table></div>`;
  }

  async function runMO() {
    const fir = document.getElementById("mo-fir").value.trim();
    if (!fir) { UI.toast("Enter a FIR", "Type a FIR number to find linked crimes.", "info"); return; }
    const host = document.getElementById("mo-result");
    host.innerHTML = `<div class="shimmer sk-line"></div><div class="shimmer sk-line"></div>`;
    try {
      const r = await API.get("/mo-linkage", { fir, top_k: document.getElementById("mo-topk").value });
      renderMO(r.target || fir, r.matches || []);
    } catch (_) { host.innerHTML = UI.empty("Could not run linkage", "", "⚠"); }
  }

  function mount(node) {
    el = node;
    el.innerHTML = shell();
    document.getElementById("er-run").addEventListener("click", runER);
    document.getElementById("mo-run").addEventListener("click", runMO);
    document.getElementById("mo-fir").addEventListener("keydown", (e) => { if (e.key === "Enter") runMO(); });
    document.getElementById("nlp-run").addEventListener("click", runNLP);
    document.getElementById("nlp-fir").addEventListener("keydown", (e) => { if (e.key === "Enter") runNLP(); });
    runER();
    mounted = true;
  }

  return { mount };
})();
