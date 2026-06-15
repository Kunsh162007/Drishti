/* ============================================================
   auth.js — login gate. Same screen for demo and production:
   demo accepts officer/drishti; production uses real JWT creds.
   ============================================================ */
const Auth = (() => {
  let booted = false;

  function el(id) { return document.getElementById(id); }

  function show() { el("login-overlay").classList.remove("hidden"); }
  function hide() { el("login-overlay").classList.add("hidden"); }

  function setError(msg) {
    const e = el("login-error");
    e.textContent = msg || "";
    e.style.display = msg ? "block" : "none";
  }

  async function detectMode() {
    try {
      const h = await fetch("/api/health").then((r) => r.json());
      return (h.mode || h.env || "").toLowerCase();
    } catch (_) { return ""; }
  }

  async function bootApp() {
    if (booted) return;
    booted = true;
    hide();
    el("topbar-actions") && (el("topbar-actions").style.display = "flex");
    App.boot();
  }

  async function doLogin(ev) {
    ev && ev.preventDefault();
    setError("");
    const btn = el("login-btn");
    const u = el("login-user").value.trim();
    const p = el("login-pass").value;
    if (!u || !p) { setError("Enter username and password."); return; }
    btn.disabled = true; btn.textContent = "Signing in…";
    try {
      const j = await API.login(u, p);
      UI.toast("Welcome", `Signed in as ${j.username || u} (${j.role || "user"})`, "ok");
      await bootApp();
    } catch (e) {
      setError(e.status === 401 ? (e.message || "Invalid credentials") : `Sign-in failed: ${e.message}`);
    } finally {
      btn.disabled = false; btn.textContent = "Sign in";
    }
  }

  function logout() {
    API.setToken("");
    location.reload();
  }

  async function init() {
    el("login-form").addEventListener("submit", doLogin);
    el("logout-btn") && el("logout-btn").addEventListener("click", logout);
    window.addEventListener("drishti:auth-required", () => {
      if (booted) { UI.toast("Session expired", "Please sign in again.", "err"); setTimeout(logout, 800); }
    });

    // If we already have a session token, boot straight in (optimistic — a 401 on
    // the first API call will bounce back to the login screen).
    if (API.hasToken()) {
      bootApp();
    } else {
      show();
      setTimeout(() => el("login-user").focus(), 50);
    }

    // Detect mode in the background (non-blocking) so the login screen appears
    // INSTANTLY even while a free-tier server is cold-starting.
    detectMode().then((mode) => {
      el("login-modechip").textContent = mode === "demo" ? "DEMO" : (mode ? mode.toUpperCase() : "SECURE");
      if (mode === "demo") {
        el("login-hint").style.display = "block";
        if (!el("login-user").value) el("login-user").value = "officer";
        if (!el("login-pass").value) el("login-pass").value = "drishti";
      }
    });
  }

  return { init, show, hide, logout };
})();

document.addEventListener("DOMContentLoaded", () => Auth.init());
