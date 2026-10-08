/* set_barier.js — "Authorize": credentials for the document's
 * `components.securitySchemes`, and applying them to a request according
 * to the operation's `security` requirements.
 *
 * Credentials live in `sessionStorage` only — they're secrets, and
 * shouldn't outlive the tab. They're keyed by scheme name. */

const AUTH_STORAGE_KEY = "hs_auth";

function securitySchemesOf(spec) {
  return Object.entries((spec.components || {}).securitySchemes || {})
    .map(([name, raw]) => [name, deref(spec, raw) || {}]);
}

function schemeKind(scheme) {
  if (scheme.type === "http") return (scheme.scheme || "").toLowerCase() === "basic" ? "basic" : "token";
  if (scheme.type === "apiKey") return "apiKey";
  if (scheme.type === "oauth2" || scheme.type === "openIdConnect") return "token";
  return "none";
}

function schemeTypeLabel(scheme) {
  if (scheme.type === "http") {
    const name = scheme.scheme || "http";
    return `HTTP ${name}${scheme.bearerFormat ? ` (${scheme.bearerFormat})` : ""}`;
  }
  if (scheme.type === "apiKey") return `API key · ${scheme.in} “${scheme.name}”`;
  if (scheme.type === "oauth2") return "OAuth 2.0";
  if (scheme.type === "openIdConnect") return "OpenID Connect";
  if (scheme.type === "mutualTLS") return "Mutual TLS";
  return scheme.type || "unknown";
}

function isSchemeAuthorized(name, scheme) {
  const cred = state.auth[name];
  if (!cred) return false;
  const kind = schemeKind(scheme);
  if (kind === "basic") return Boolean(cred.username);
  if (kind === "apiKey") return Boolean(cred.value);
  if (kind === "token") return Boolean(cred.token);
  return false;
}

function updateAuthButton() {
  const button = byId("authBtn");
  const schemes = securitySchemesOf(currentApi().spec);
  button.classList.toggle("hidden", schemes.length === 0);
  if (!schemes.length) return;
  const authorized = schemes.filter(([name, scheme]) => isSchemeAuthorized(name, scheme)).length;
  button.classList.toggle("authorized", authorized === schemes.length);
  button.classList.toggle("partial", authorized > 0 && authorized < schemes.length);
  button.innerHTML = `${authorized ? ICONS.unlock : ICONS.lock} Authorize${authorized ? ` ${authorized}/${schemes.length}` : ""}`;
}

/* ---------- modal ---------- */

function openAuthModal() {
  renderAuthModal();
  byId("authModalBackdrop").classList.add("open");
  const first = byId("authModalBody").querySelector("input");
  if (first) first.focus();
}

function closeAuthModal() {
  byId("authModalBackdrop").classList.remove("open");
}

function renderAuthModal() {
  const spec = currentApi().spec;
  const body = byId("authModalBody");
  const schemes = securitySchemesOf(spec);
  body.innerHTML = schemes.map(([name, scheme]) => authCardHtml(name, scheme)).join("")
    || '<div class="faint">The document has no securitySchemes.</div>';
}

function authCardHtml(name, scheme) {
  const cred = state.auth[name] || {};
  const kind = schemeKind(scheme);
  const authorized = isSchemeAuthorized(name, scheme);
  const field = (key, placeholder, type = "text") => (
    `<input class="field-input" type="${type}" data-auth="${escapeHtml(name)}" data-auth-key="${key}" placeholder="${escapeHtml(placeholder)}" value="${escapeHtml(cred[key] || "")}" autocomplete="off">`
  );

  let inputs = "";
  if (kind === "basic") inputs = field("username", "username") + field("password", "password", "password");
  else if (kind === "apiKey") inputs = field("value", `${scheme.name} value`, "password");
  else if (kind === "token") inputs = field("token", scheme.type === "http" && (scheme.scheme || "").toLowerCase() !== "bearer" ? `${scheme.scheme} credentials` : "access token", "password");
  else inputs = '<div class="faint">The browser itself picks the client certificate — it can\'t be set from the page.</div>';

  return `<div class="auth-card ${authorized ? "authorized" : ""}">
    <div class="auth-card-head">${authorized ? ICONS.unlock : ICONS.lock}<b>${escapeHtml(name)}</b><span class="badge neutral">${escapeHtml(schemeTypeLabel(scheme))}</span></div>
    ${scheme.description ? `<div class="md dim small">${renderMarkdown(scheme.description)}</div>` : ""}
    ${oauthDetailsHtml(scheme)}
    ${inputs}
    ${kind === "token" && scheme.type !== "http" ? '<div class="faint">Get a token from the provider and paste it here — it\'s sent as <code>Authorization: Bearer …</code>.</div>' : ""}
  </div>`;
}

function oauthDetailsHtml(scheme) {
  if (scheme.type === "openIdConnect") {
    return `<div class="faint">Discovery: <a href="${escapeHtml(safeUrl(scheme.openIdConnectUrl || ""))}" target="_blank" rel="noopener noreferrer">${escapeHtml(scheme.openIdConnectUrl || "")}</a></div>`;
  }
  if (scheme.type !== "oauth2") return "";
  return Object.entries(scheme.flows || {}).map(([flow, details]) => {
    const urls = ["authorizationUrl", "tokenUrl", "refreshUrl"]
      .filter((key) => details[key])
      .map((key) => `<div class="faint">${key}: <code>${escapeHtml(details[key])}</code></div>`).join("");
    const scopes = Object.entries(details.scopes || {})
      .map(([scope, text]) => `<li><code>${escapeHtml(scope)}</code> — ${escapeHtml(text)}</li>`).join("");
    return `<div class="sub-title">flow: ${escapeHtml(flow)}</div>${urls}${scopes ? `<ul class="scope-list">${scopes}</ul>` : ""}`;
  }).join("");
}

function saveAuthFromModal() {
  byId("authModalBody").querySelectorAll("[data-auth]").forEach((input) => {
    const name = input.dataset.auth;
    state.auth[name] = { ...(state.auth[name] || {}), [input.dataset.authKey]: input.value };
  });
  saveJson(sessionStorage, AUTH_STORAGE_KEY, state.auth);
  closeAuthModal();
  updateAuthButton();
  renderMain();
  showToast("Credentials saved until the tab is closed");
}

function logoutAll() {
  state.auth = {};
  saveJson(sessionStorage, AUTH_STORAGE_KEY, state.auth);
  renderAuthModal();
  updateAuthButton();
  renderMain();
  showToast("Credentials cleared");
}

function initAuth() {
  state.auth = loadJson(sessionStorage, AUTH_STORAGE_KEY, {}) || {};
  byId("authBtn").addEventListener("click", openAuthModal);
  byId("authCloseBtn").innerHTML = ICONS.close;
  byId("authCloseBtn").addEventListener("click", closeAuthModal);
  byId("authSaveBtn").addEventListener("click", saveAuthFromModal);
  byId("authLogoutAllBtn").addEventListener("click", logoutAll);
  byId("authModalBackdrop").addEventListener("click", (event) => {
    if (event.target.id === "authModalBackdrop") closeAuthModal();
  });
  byId("authModalBody").addEventListener("keydown", (event) => {
    if (event.key === "Enter") saveAuthFromModal();
  });
}

/* ---------- applying to a request ---------- */

/* The first alternative of `requirements` whose every scheme has
 * credentials — or, failing that, the first one, reported as missing.
 * Returns what to add to the request plus what's still missing. */
function resolveAuth(spec, requirements) {
  const result = { headers: [], query: [], cookies: [], used: [], missing: [], optional: false };
  if (!requirements.length) return result;
  if (requirements.some((alt) => Object.keys(alt).length === 0)) result.optional = true;

  const schemes = Object.fromEntries(securitySchemesOf(spec));
  const candidates = requirements.filter((alt) => Object.keys(alt).length);
  const ready = candidates.find((alt) => Object.keys(alt).every((name) => schemes[name] && isSchemeAuthorized(name, schemes[name])));

  if (!ready) {
    if (!result.optional && candidates.length) {
      result.missing = Object.keys(candidates[0]).filter((name) => !schemes[name] || !isSchemeAuthorized(name, schemes[name]));
    }
    return result;
  }

  for (const name of Object.keys(ready)) {
    const scheme = schemes[name];
    const cred = state.auth[name];
    const kind = schemeKind(scheme);
    if (kind === "basic") {
      result.headers.push(["Authorization", `Basic ${base64Utf8(`${cred.username}:${cred.password || ""}`)}`]);
    } else if (kind === "token") {
      const prefix = scheme.type === "http" ? capitalizeScheme(scheme.scheme || "Bearer") : "Bearer";
      result.headers.push(["Authorization", `${prefix} ${cred.token}`]);
    } else if (kind === "apiKey") {
      const target = { header: result.headers, query: result.query, cookie: result.cookies }[scheme.in];
      if (target) target.push([scheme.name, cred.value]);
    }
    result.used.push(name);
  }
  return result;
}

function capitalizeScheme(name) {
  return name.toLowerCase() === "bearer" ? "Bearer" : name;
}

/* Requirements as readable text: alternatives joined by "or",
 * schemes within one by "+", scopes in brackets. */
function describeRequirements(requirements) {
  return requirements.map((alt) => {
    const names = Object.entries(alt).map(([name, scopes]) => (
      scopes && scopes.length ? `${name} [${scopes.join(", ")}]` : name
    ));
    return names.length ? names.join(" + ") : "no authorization";
  }).join(" or ");
}
