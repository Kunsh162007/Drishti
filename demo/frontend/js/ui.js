/* ============================================================
   ui.js — shared UI helpers: toasts, formatting, skeletons,
   number count-up, ECharts theme, null-safety.
   ============================================================ */
const UI = (() => {
  /* ---- null-safe display ---- */
  const val = (v, dash = "—") =>
    (v === null || v === undefined || v === "" || (typeof v === "number" && isNaN(v))) ? dash : v;

  const num = (v) => {
    if (v === null || v === undefined || isNaN(v)) return "—";
    return Number(v).toLocaleString("en-IN");
  };

  const inr = (v) => {
    if (v === null || v === undefined || isNaN(v) || v === 0) return "—";
    const n = Number(v);
    if (n >= 1e7) return "₹" + (n / 1e7).toFixed(2) + " Cr";
    if (n >= 1e5) return "₹" + (n / 1e5).toFixed(2) + " L";
    return "₹" + n.toLocaleString("en-IN");
  };

  const date = (v) => (v ? String(v).slice(0, 10) : "—");

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  const title = (s) => String(s ?? "").replace(/\b\w/g, (c) => c.toUpperCase());

  /* ---- toasts ---- */
  function toast(titleTxt, body, kind = "info", ms = 4800) {
    const host = document.getElementById("toast-host");
    if (!host) return;
    const el = document.createElement("div");
    el.className = `toast ${kind}`;
    const ico = kind === "err" ? "⚠" : kind === "ok" ? "✓" : "ℹ";
    el.innerHTML = `<span class="t-ico">${ico}</span><div><div class="t-title">${esc(titleTxt)}</div>${body ? `<div class="t-body">${esc(body)}</div>` : ""}</div>`;
    host.appendChild(el);
    setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(30px)"; el.style.transition = ".3s"; setTimeout(() => el.remove(), 320); }, ms);
  }

  /* ---- count-up animation ---- */
  function countUp(el, to, { suffix = "", decimals = 0, dur = 900 } = {}) {
    if (!el) return;
    const start = performance.now();
    const from = 0;
    function step(t) {
      const p = Math.min(1, (t - start) / dur);
      const e = 1 - Math.pow(1 - p, 3); // easeOutCubic
      const v = from + (to - from) * e;
      el.firstChild ? (el.childNodes[0].nodeValue =
        (decimals ? v.toFixed(decimals) : Math.round(v).toLocaleString("en-IN")))
        : (el.textContent = decimals ? v.toFixed(decimals) : Math.round(v).toLocaleString("en-IN"));
      if (p < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  /* ---- skeleton loaders ---- */
  function skeletonKPIs(n = 6) {
    return Array.from({ length: n }, () => `<div class="shimmer sk-kpi"></div>`).join("");
  }
  function skeletonChart() { return `<div class="shimmer sk-chart"></div>`; }
  function loadbar() { return `<div class="loadbar"></div>`; }

  function empty(main, sub, icon = "◎") {
    return `<div class="empty"><div class="e-ico">${icon}</div><div class="e-main">${esc(main)}</div>${sub ? `<div class="e-sub">${esc(sub)}</div>` : ""}</div>`;
  }

  /* ---- ECharts shared theme/options ---- */
  const palette = ["#C9A227", "#1F7A8C", "#2ba6bd", "#e2c25a", "#3d7fd6", "#3ba776", "#e6932f", "#e2574c", "#9b7fd6", "#6ddaa6"];
  const axisCommon = {
    axisLine: { lineStyle: { color: "rgba(230,237,245,.18)" } },
    axisLabel: { color: "#9fb0c6", fontSize: 11 },
    splitLine: { lineStyle: { color: "rgba(230,237,245,.06)" } },
  };
  function chartBase() {
    return {
      color: palette,
      backgroundColor: "transparent",
      textStyle: { fontFamily: "Inter, Segoe UI, sans-serif", color: "#E6EDF5" },
      tooltip: {
        backgroundColor: "rgba(16,32,54,.96)", borderColor: "rgba(201,162,39,.3)",
        textStyle: { color: "#E6EDF5", fontSize: 12 }, borderWidth: 1,
      },
      grid: { left: 8, right: 16, top: 26, bottom: 6, containLabel: true },
    };
  }

  const charts = new Map();
  function mountChart(elId, option) {
    const el = document.getElementById(elId);
    if (!el) return null;
    let inst = charts.get(elId);
    if (inst) { inst.dispose(); }
    inst = echarts.init(el, null, { renderer: "canvas" });
    inst.setOption(option);
    charts.set(elId, inst);
    return inst;
  }
  window.addEventListener("resize", () => charts.forEach((c) => c && c.resize()));
  function resizeCharts() { charts.forEach((c) => c && c.resize()); }

  /* color helpers for deck.gl (returns [r,g,b]) */
  function rampColor(t) {
    // teal -> gold -> red ramp by t in [0,1]
    t = Math.max(0, Math.min(1, t));
    const stops = [
      [31, 122, 140], [43, 166, 189], [201, 162, 39], [230, 147, 47], [226, 87, 76],
    ];
    const seg = t * (stops.length - 1);
    const i = Math.floor(seg), f = seg - i;
    const a = stops[i], b = stops[Math.min(i + 1, stops.length - 1)];
    return [0, 1, 2].map((k) => Math.round(a[k] + (b[k] - a[k]) * f));
  }

  return {
    val, num, inr, date, esc, title, toast, countUp,
    skeletonKPIs, skeletonChart, loadbar, empty,
    chartBase, axisCommon, palette, mountChart, resizeCharts, rampColor,
  };
})();
