/* main.js — page state, hash routing and start-up. The only script that
 * runs anything at load time; everything before it only declares.
 *
 * Route: `#/<version>/<view>/<key>` — view is `overview`, `op`,
 * `webhook` or `schema`; key is `"<METHOD> <path>"` or a schema name. */

const DATA = JSON.parse(byId("hs-data").textContent);

const state = {
  versions: DATA.versions.map(prepareVersion),
  versionIndex: 0,
  route: { view: "overview", key: undefined },
  search: "",
  collapsed: loadJson(localStorage, "hs_collapsed", {}) || {},
  drafts: {},
  files: new Map(),
  globals: loadGlobals(),
  auth: {},
  inflight: null,
};

function prepareVersion({ name, spec }) {
  const ops = collectOperations(spec);
  return { name, spec, ops, webhooks: collectWebhooks(spec), groups: groupOperations(spec, ops) };
}

function loadGlobals() {
  const saved = loadJson(localStorage, "hs_globals", null);
  if (saved && isKvList(saved.headers) && isKvList(saved.cookies)) return saved;
  return { headers: [], cookies: [] };
}

function currentVersion() {
  return state.versions[state.versionIndex];
}

/* ---------- routing ---------- */

function navigate(versionName, view, key) {
  const target = routeHref(versionName, view, key);
  if (location.hash === target) applyHash();
  else location.hash = target;
}

function applyHash() {
  const parts = location.hash.replace(/^#\/?/, "").split("/").map((part) => {
    try { return decodeURIComponent(part); } catch { return part; }
  });
  const [versionName, view, ...rest] = parts;
  const index = state.versions.findIndex((version) => version.name === versionName);
  if (index !== -1) state.versionIndex = index;
  state.route = ["op", "webhook", "schema"].includes(view)
    ? { view, key: rest.join("/") }
    : { view: "overview", key: undefined };

  renderTopbar();
  renderSidebar();
  renderMain();
  window.scrollTo(0, 0);
  const active = byId("sidebar").querySelector(".active");
  if (active) active.scrollIntoView({ block: "nearest" });
}

/* ---------- topbar ---------- */

function renderTopbar() {
  const select = byId("versionSelect");
  const many = state.versions.length > 1;
  select.classList.toggle("hidden", !many);
  byId("diffBtn").classList.toggle("hidden", !many);
  if (many) {
    select.innerHTML = state.versions.map((version, index) => (
      `<option value="${index}" ${index === state.versionIndex ? "selected" : ""}>${escapeHtml(version.name)}</option>`
    )).join("");
  }
  const info = currentVersion().spec.info || {};
  applyBrand(DATA.ui, info);
  document.title = `${DATA.ui.name || info.title || "API"} — ${currentVersion().name}`;
  updateAuthButton();
}

function initTopbar() {
  byId("brand").addEventListener("click", () => navigate(currentVersion().name, "overview"));
  byId("versionSelect").addEventListener("change", (event) => {
    const version = state.versions[Number(event.target.value)];
    // Stay on the same page if the other version has it too.
    navigate(version.name, state.route.view, state.route.key);
  });
  const search = byId("searchInput");
  search.addEventListener("input", () => {
    state.search = search.value;
    renderSidebar();
  });
  search.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      const first = byId("sidebar").querySelector(".ep-item");
      if (first) first.click();
    }
    if (event.key === "Escape") {
      search.value = "";
      state.search = "";
      renderSidebar();
      search.blur();
    }
  });

  document.addEventListener("keydown", (event) => {
    const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName || "");
    if (event.key === "/" && !typing) {
      event.preventDefault();
      search.focus();
    }
    if (event.key === "Escape") {
      closeDrawer();
      closeAuthModal();
      closeDiffModal();
    }
  });
}

/* ---------- start ---------- */

function init() {
  initTheme();
  initTopbar();
  initAuth();
  initDrawer();
  initDiff();
  window.addEventListener("hashchange", applyHash);
  if (!location.hash) {
    history.replaceState(null, "", routeHref(currentVersion().name, "overview"));
  }
  applyHash();
}

init();
