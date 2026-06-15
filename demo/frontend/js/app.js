/* ============================================================
   app.js — router, shared state (meta cache), boot sequence.
   Each view exposes a global with .mount(el) and optional
   .onShow() / .onHide(). View modules register into App.views.
   ============================================================ */
const App = (() => {
  const state = {
    meta: null,        // /api/meta cached
    health: null,
    mounted: {},       // view -> true once mounted
    current: "dashboard",
    pendingFilter: null, // cross-view (assistant -> hotspots)
  };

  const views = {
    dashboard: () => Views.Dashboard,
    hotspots: () => Views.Hotspots,
    network: () => Views.Network,
    cdr: () => Views.CDR,
    cyber: () => Views.Cyber,
    predictive: () => Views.Predictive,
    patrol: () => Views.Patrol,
    missing: () => Views.Missing,
    investigations: () => Views.Investigations,
    assistant: () => Views.Assistant,
    oversight: () => Views.Oversight,
    myshield: () => Views.MyShield,
    ingestion: () => Views.Ingestion,
    temporal: () => Views.Temporal,
    geoprofiler: () => Views.Geoprofiler,
    forecast: () => Views.Forecast,
    suspect: () => Views.Suspect,
  };

  async function loadMeta() {
    try {
      state.meta = await API.get("/meta", null, { silent: true });
    } catch (_) {
      state.meta = { districts: [], crime_types: [], categories: [], date_range: {}, totals: {} };
    }
    return state.meta;
  }

  function renderStatus(h) {
    const dot = document.getElementById("health-dot");
    const summary = document.getElementById("meta-summary");
    dot && dot.classList.remove("err");
    dot && dot.classList.add("ok");
    const m = state.meta || {};
    const t = m.totals || {};
    const dr = m.date_range || {};
    summary && (summary.innerHTML =
      `<b style="color:var(--gold-soft)">${UI.num(t.crimes)}</b> FIRs · ` +
      `<b style="color:var(--gold-soft)">${UI.num(t.persons)}</b> persons · ` +
      `<b style="color:var(--gold-soft)">${UI.num(t.vehicles)}</b> vehicles` +
      (dr.min ? ` · ${dr.min} → ${dr.max}` : "") +
      ` · mode <span class="mono" style="color:var(--teal-bright)">${UI.esc((h && h.mode) || "demo")}</span>`);
  }

  function go(viewName) {
    if (!views[viewName]) return;
    state.current = viewName;
    // nav highlight
    document.querySelectorAll(".nav-item").forEach((n) =>
      n.classList.toggle("active", n.dataset.view === viewName));
    // hide prior view's onHide
    document.querySelectorAll(".view").forEach((v) => {
      const isThis = v.dataset.view === viewName;
      v.classList.toggle("hidden", !isThis);
    });
    const mod = views[viewName] && views[viewName]();
    const el = document.getElementById(`view-${viewName}`);
    if (!el) return;
    if (!mod) {
      el.innerHTML = UI.empty("View not loaded", `${viewName} module missing — try a hard refresh (Ctrl+Shift+R).`, "⚠");
      return;
    }
    if (!state.mounted[viewName]) {
      try { mod.mount(el); } catch (e) { console.error(e); el.innerHTML = UI.empty("View failed to load", String(e.message)); }
      state.mounted[viewName] = true;
    }
    try { mod.onShow && mod.onShow(); } catch (e) { console.error(e); }
    UI.resizeCharts();
  }

  // Cross-view navigation with a payload (e.g., assistant -> hotspots with filter)
  function goWithFilter(viewName, filter) {
    state.pendingFilter = filter;
    go(viewName);
  }

  function bindNav() {
    document.querySelectorAll(".nav-item").forEach((n) =>
      n.addEventListener("click", () => go(n.dataset.view)));
  }

  async function boot() {
    bindNav();              // tabs are clickable immediately
    go("dashboard");        // render UI right away (views show their own loaders)
    const summary = document.getElementById("meta-summary");
    const dot = document.getElementById("health-dot");
    // Wake the server with retries (Render free tier can cold-start for ~50s).
    for (let attempt = 0; attempt < 15; attempt++) {
      try {
        const h = await API.get("/health", null, { silent: true });
        state.health = h;
        await loadMeta();
        renderStatus(h);
        state.mounted.dashboard = false;   // re-mount dashboard now that data is live
        go("dashboard");
        return;
      } catch (_) {
        dot && dot.classList.remove("ok");
        summary && (summary.textContent =
          `Waking server… (free tier — first load can take ~60s) · attempt ${attempt + 1}`);
        await new Promise((r) => setTimeout(r, 6000));
      }
    }
    dot && dot.classList.add("err");
    summary && (summary.textContent = "Intelligence core unreachable — please refresh the page.");
  }

  // populate a <select> from meta list with an "All" default
  function fillSelect(sel, items, allLabel) {
    if (!sel) return;
    sel.innerHTML = `<option value="">${allLabel || "All"}</option>` +
      (items || []).map((x) => `<option value="${UI.esc(x)}">${UI.esc(x)}</option>`).join("");
  }

  return { state, go, goWithFilter, loadMeta, fillSelect, boot };
})();

// NOTE: `window.Views = {}` is initialised in index.html BEFORE the view scripts
// load, so view modules can register onto it. Boot is triggered by auth.js.
window.Views = window.Views || {};
