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
  };

  async function loadMeta() {
    try {
      state.meta = await API.get("/meta", null, { silent: true });
    } catch (_) {
      state.meta = { districts: [], crime_types: [], categories: [], date_range: {}, totals: {} };
    }
    return state.meta;
  }

  async function loadHealth() {
    const dot = document.getElementById("health-dot");
    const summary = document.getElementById("meta-summary");
    try {
      const h = await API.get("/health", null, { silent: true });
      state.health = h;
      dot && dot.classList.add("ok");
      const m = state.meta || {};
      const t = m.totals || {};
      const dr = m.date_range || {};
      summary && (summary.innerHTML =
        `<b style="color:var(--gold-soft)">${UI.num(t.crimes)}</b> FIRs · ` +
        `<b style="color:var(--gold-soft)">${UI.num(t.persons)}</b> persons · ` +
        `<b style="color:var(--gold-soft)">${UI.num(t.vehicles)}</b> vehicles` +
        (dr.min ? ` · ${dr.min} → ${dr.max}` : "") +
        ` · mode <span class="mono" style="color:var(--teal-bright)">${UI.esc(h.mode || "demo")}</span>`);
    } catch (_) {
      dot && dot.classList.add("err");
      summary && (summary.textContent = "Intelligence core unreachable — start the backend (uvicorn backend.main:app).");
    }
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
    if (!mod || !el) return;
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
    bindNav();
    await loadMeta();
    loadHealth();
    go("dashboard");
  }

  // populate a <select> from meta list with an "All" default
  function fillSelect(sel, items, allLabel) {
    if (!sel) return;
    sel.innerHTML = `<option value="">${allLabel || "All"}</option>` +
      (items || []).map((x) => `<option value="${UI.esc(x)}">${UI.esc(x)}</option>`).join("");
  }

  return { state, go, goWithFilter, loadMeta, fillSelect };
})();

const Views = {};
document.addEventListener("DOMContentLoaded", () => App.boot());
