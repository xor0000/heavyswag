/* server.js — where "Попробовать" sends requests: picked once, in the top
 * bar, for the whole page, and remembered in `localStorage`.
 *
 * The list is the document's `servers`; without any, the page's own
 * origin ("этот сервер"). "Свой адрес…" and server variables
 * (`{port}`, …) are edited in a small dialog. An operation — or its
 * path — that declares its own `servers` uses the first of those
 * instead: the document says that one lives elsewhere. */

const SERVER_STORAGE_KEY = "hs_server";
const CUSTOM_SERVER = -1;

function documentServers(spec) {
  return Array.isArray(spec.servers) && spec.servers.length
    ? spec.servers
    : [{ url: "/", description: "этот сервер" }];
}

function defaultVars(server) {
  return Object.fromEntries(Object.entries((server && server.variables) || {})
    .map(([name, variable]) => [name, String(variable.default ?? "")]));
}

/* The saved choice if it still fits the document, else its first server. */
function loadServerChoice(spec) {
  const servers = documentServers(spec);
  const saved = loadJson(localStorage, SERVER_STORAGE_KEY, null);
  if (saved && typeof saved === "object") {
    if (saved.index === CUSTOM_SERVER && typeof saved.custom === "string" && saved.custom) {
      return { index: CUSTOM_SERVER, custom: saved.custom, vars: {} };
    }
    if (Number.isInteger(saved.index) && saved.index >= 0 && saved.index < servers.length) {
      const vars = { ...defaultVars(servers[saved.index]), ...(saved.vars || {}) };
      return { index: saved.index, custom: saved.custom || "", vars };
    }
  }
  return { index: 0, custom: "", vars: defaultVars(servers[0]) };
}

function saveServerChoice() {
  saveJson(localStorage, SERVER_STORAGE_KEY, state.server);
}

/* The base URL (no trailing slash) a request for `entry` goes to, and
 * whether it's the operation's own server rather than the picked one. */
function requestBase(spec, entry) {
  const own = [entry.op.servers, entry.item.servers].find((list) => Array.isArray(list) && list.length);
  if (own) return { url: serverUrl(own[0]).replace(/\/+$/, ""), own: true };

  const choice = state.server;
  if (choice.index === CUSTOM_SERVER) return { url: choice.custom.replace(/\/+$/, ""), own: false };
  const servers = documentServers(spec);
  const server = servers[choice.index] || servers[0];
  return { url: serverUrl(server, choice.vars).replace(/\/+$/, ""), own: false };
}

function serverLabel(server) {
  return server.description ? `${server.url} — ${server.description}` : server.url;
}

/* ---------- top bar ---------- */

function renderServerPicker() {
  const servers = documentServers(currentApi().spec);
  const choice = state.server;
  const select = byId("serverSelect");
  select.innerHTML = servers.map((server, index) => (
    `<option value="${index}">${escapeHtml(serverLabel(server))}</option>`
  )).join("") + `<option value="${CUSTOM_SERVER}">${choice.custom ? `Свой: ${escapeHtml(choice.custom)}` : "Свой адрес…"}</option>`;
  select.value = String(choice.index);
  select.title = choice.index === CUSTOM_SERVER ? choice.custom : serverLabel(servers[choice.index]);

  const hasVariables = choice.index !== CUSTOM_SERVER && Object.keys(servers[choice.index].variables || {}).length > 0;
  const editButton = byId("serverEditBtn");
  editButton.classList.toggle("hidden", choice.index !== CUSTOM_SERVER && !hasVariables);
  editButton.title = choice.index === CUSTOM_SERVER ? "Изменить свой адрес" : "Переменные сервера";
}

/* Every page part that depends on the server is re-derived from scratch. */
function onServerChanged() {
  saveServerChoice();
  renderServerPicker();
  renderMain();
}

/* ---------- dialog ---------- */

function openServerModal(mode) {
  const body = byId("serverModalBody");
  const backdrop = byId("serverModalBackdrop");
  backdrop.dataset.mode = mode;

  if (mode === "custom") {
    byId("serverModalTitle").textContent = "Свой адрес сервера";
    body.innerHTML = `
      <input class="field-input" type="url" id="customServerInput" placeholder="http://localhost:8000" value="${escapeHtml(state.server.custom)}" autocomplete="off">
      <div class="field-error" id="serverModalError"></div>
      <div class="faint" style="margin-top:8px;">Схема, хост, порт и общий префикс API, без пути эндпоинта — например <code>https://api.example.com/v1</code>.</div>`;
  } else {
    const server = documentServers(currentApi().spec)[state.server.index];
    byId("serverModalTitle").textContent = "Переменные сервера";
    body.innerHTML = `<div class="faint" style="margin-bottom:8px;"><code>${escapeHtml(server.url)}</code></div>` +
      Object.entries(server.variables || {}).map(([name, variable]) => {
        const value = state.server.vars[name] ?? String(variable.default ?? "");
        const input = Array.isArray(variable.enum)
          ? `<select class="field-input" data-server-var="${escapeHtml(name)}">${variable.enum.map((option) => (
            `<option ${String(option) === value ? "selected" : ""}>${escapeHtml(option)}</option>`
          )).join("")}</select>`
          : `<input class="field-input" type="text" data-server-var="${escapeHtml(name)}" value="${escapeHtml(value)}">`;
        return `<div style="margin-bottom:10px;"><div class="field-name">{${escapeHtml(name)}}</div>${input}${variable.description ? `<div class="faint">${escapeHtml(variable.description)}</div>` : ""}</div>`;
      }).join("");
  }

  backdrop.classList.add("open");
  const first = body.querySelector("input, select");
  if (first) first.focus();
}

/* Closing without saving puts the top-bar select back on the server
 * that was in use — picking "Свой адрес…" and cancelling changes nothing. */
function closeServerModal() {
  byId("serverModalBackdrop").classList.remove("open");
  renderServerPicker();
}

function saveServerModal() {
  const backdrop = byId("serverModalBackdrop");
  if (backdrop.dataset.mode === "custom") {
    const value = byId("customServerInput").value.trim();
    let url = null;
    try { url = new URL(value); } catch { url = null; }
    if (!url || (url.protocol !== "http:" && url.protocol !== "https:")) {
      byId("serverModalError").textContent = "Нужен полный адрес: http://… или https://…";
      return;
    }
    state.server = { index: CUSTOM_SERVER, custom: value.replace(/\/+$/, ""), vars: {} };
  } else {
    byId("serverModalBody").querySelectorAll("[data-server-var]").forEach((input) => {
      state.server.vars[input.dataset.serverVar] = input.value;
    });
  }
  backdrop.classList.remove("open");
  onServerChanged();
}

function initServerPicker() {
  state.server = loadServerChoice(currentApi().spec);
  byId("serverEditBtn").innerHTML = ICONS.edit;
  byId("serverCloseBtn").innerHTML = ICONS.close;

  byId("serverSelect").addEventListener("change", (event) => {
    const index = Number(event.target.value);
    if (index === CUSTOM_SERVER) {
      openServerModal("custom");
      return;
    }
    const server = documentServers(currentApi().spec)[index];
    state.server = { index, custom: state.server.custom, vars: defaultVars(server) };
    onServerChanged();
  });
  byId("serverEditBtn").addEventListener("click", () => {
    openServerModal(state.server.index === CUSTOM_SERVER ? "custom" : "vars");
  });
  byId("serverSaveBtn").addEventListener("click", saveServerModal);
  byId("serverCancelBtn").addEventListener("click", closeServerModal);
  byId("serverCloseBtn").addEventListener("click", closeServerModal);
  byId("serverModalBackdrop").addEventListener("click", (event) => {
    if (event.target.id === "serverModalBackdrop") closeServerModal();
  });
  byId("serverModalBody").addEventListener("keydown", (event) => {
    if (event.key === "Enter") saveServerModal();
  });
  renderServerPicker();
}
