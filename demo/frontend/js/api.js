/* ============================================================
   api.js — fetch helpers (same-origin, relative). Graceful errors.
   Attaches a stored bearer token; surfaces 401 for the login flow.
   ============================================================ */
const API = (() => {
  const base = "/api";
  let _token = localStorage.getItem("drishti_token") || "";

  function setToken(t) {
    _token = t || "";
    if (t) localStorage.setItem("drishti_token", t);
    else localStorage.removeItem("drishti_token");
  }
  function hasToken() { return !!_token; }
  function authHeaders() { return _token ? { Authorization: "Bearer " + _token } : {}; }

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
    if (res.status === 401 && !path.includes("/auth/")) {
      // token missing/expired during normal use -> bounce to login
      setToken("");
      window.dispatchEvent(new CustomEvent("drishti:auth-required"));
    }
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
      const res = await fetch(`${base}${path}${qs(params)}`, {
        headers: { Accept: "application/json", ...authHeaders() },
      });
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
        headers: { "Content-Type": "application/json", Accept: "application/json", ...authHeaders() },
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
      const res = await fetch(`${base}${path}`, { method: "POST", headers: { ...authHeaders() }, body: formData });
      return await handle(res, path);
    } catch (e) {
      if (!silent) UI.toast("Upload failed", `${path} — ${e.message}`, "err");
      throw e;
    }
  }

  // OAuth2 password flow (form-encoded) — works against demo and production.
  async function login(username, password) {
    const body = new URLSearchParams({ username, password });
    const res = await fetch(`${base}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", Accept: "application/json" },
      body,
    });
    if (!res.ok) {
      let detail = "Login failed";
      try { const j = await res.json(); if (j.detail) detail = j.detail; } catch (_) {}
      const err = new Error(detail); err.status = res.status; throw err;
    }
    const j = await res.json();
    setToken(j.access_token);
    return j;
  }

  async function me() { return get("/auth/me", null, { silent: true }); }

  return { get, post, postForm, qs, login, me, setToken, hasToken };
})();
