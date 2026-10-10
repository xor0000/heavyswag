/* main.js — page state, hash routing and start-up. The only script that
 * runs anything at load time; everything before it only declares.
 *
 * Route: `#/<view>/<key>` — view is `overview`, `op`, `webhook` or
 * `schema`; key is `"<METHOD> <path>"` or a schema name. */

const DATA = JSON.parse(byId("hs-data").textContent);

const state = {
  api: prepareApi(DATA.spec),
  route: { view: "overview", key: undefined },
  search: "",
  collapsed: loadJson(localStorage, "hs_collapsed", {}) || {},
  drafts: {},
  files: new Map(),
  globals: loadGlobals(),
  auth: {},
  inflight: null,
  curlExpanded: null,
};

/* The document plus everything the pages derive from it, parsed once. */
function prepareApi(spec) {
  const ops = collectOperations(spec);
  return { spec, ops, webhooks: collectWebhooks(spec), groups: groupOperations(spec, ops) };
}

function loadGlobals() {
  const saved = loadJson(localStorage, "hs_globals", null);
  if (saved && isKvList(saved.headers) && isKvList(saved.cookies)) return saved;
  return { headers: [], cookies: [] };
}

function currentApi() {
  return state.api;
}

/* ---------- routing ---------- */

function navigate(view, key) {
  const target = routeHref(view, key);
  if (location.hash === target) applyHash();
  else location.hash = target;
}

function applyHash() {
  const [view, ...rest] = location.hash.replace(/^#\/?/, "").split("/").map((part) => {
    try { return decodeURIComponent(part); } catch { return part; }
  });
  state.route = ["op", "webhook", "schema"].includes(view)
    ? { view, key: rest.join("/") }
    : { view: "overview", key: undefined };

  renderSidebar();
  renderMain();
  window.scrollTo(0, 0);
  const active = byId("sidebar").querySelector(".active");
  if (active) active.scrollIntoView({ block: "nearest" });
}

/* ---------- topbar ---------- */

function initTopbar() {
  const info = state.api.spec.info || {};
  applyBrand(DATA.ui, info);
  document.title = DATA.ui.name || info.title || "API";
  updateAuthButton();

  byId("brand").addEventListener("click", () => navigate("overview"));
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
      if (byId("serverModalBackdrop").classList.contains("open")) closeServerModal();
    }
  });
}

/* ---------- start ---------- */

function init() {
  initTheme();
  initAuth();
  initServerPicker();
  initTopbar();
  initDrawer();
  window.addEventListener("hashchange", applyHash);
  if (!location.hash) history.replaceState(null, "", routeHref("overview"));
  applyHash();
}

init();
