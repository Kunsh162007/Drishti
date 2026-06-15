/* ============================================================
   api.js — fetch helpers (same-origin, relative). Graceful errors.
   ============================================================ */
const API = (() => {
  const base = "/api";

  function qs(params) {
    if (!params) return "";
    const p = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== "") p.append(k, v);
    });
    const s = p.toString();
    return s ? `?${s}` : "";
  }

  async function handle(res, path) {
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (_) {}
      const err = new Error(detail);
      err.status = res.status;
      throw err;
    }
    return res.json();
  }

  async function get(path, params, { silent = false } = {}) {
    try {
      const res = await fetch(`${base}${path}${qs(params)}`, { headers: { Accept: "application/json" } });
      return await handle(res, path);
    } catch (e) {
      if (!silent) UI.toast("Request failed", `${path} — ${e.message}`, "err");
      throw e;
    }
  }

  async function post(path, body, { silent = false } = {}) {
    try {
      const res = await fetch(`${base}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body || {}),
      });
      return await handle(res, path);
    } catch (e) {
      if (!silent) UI.toast("Request failed", `${path} — ${e.message}`, "err");
      throw e;
    }
  }

  async function postForm(path, formData, { silent = false } = {}) {
    try {
      const res = await fetch(`${base}${path}`, { method: "POST", body: formData });
      return await handle(res, path);
    } catch (e) {
      if (!silent) UI.toast("Upload failed", `${path} — ${e.message}`, "err");
      throw e;
    }
  }

  return { get, post, postForm, qs };
})();
