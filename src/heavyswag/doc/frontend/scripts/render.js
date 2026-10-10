/* render.js — the sidebar and every page: API overview, operation (with
 * "Try it out"), webhook, component schema; plus the global
 * headers / cookies drawer.
 *
 * Pages are rendered as HTML strings (every interpolated value goes
 * through `escapeHtml` or `renderMarkdown`) and wired up afterwards.
 * Typing into "Try it out" never re-renders the page — only the parts
 * derived from the draft (validation, headers, curl) are refreshed, so
 * focus and cursor position survive. */

/* ---------- routes ---------- */

function routeHref(view, key) {
  return "#/" + [view, key].filter((part) => part !== undefined)
    .map((part) => encodeURIComponent(part)).join("/");
}

function schemaLinkFor() {
  return (name) => routeHref("schema", name);
}

/* ---------- sidebar ---------- */

function renderSidebar() {
  const api = currentApi();
  const query = state.search.trim().toLowerCase();
  const route = state.route;
  const matches = (entry) => !query || [entry.path, entry.method, entry.op.summary, entry.op.operationId, ...entry.tags]
    .some((text) => text && String(text).toLowerCase().includes(query));

  const itemHtml = (entry, view) => {
    const active = route.view === view && route.key === entry.key;
    const secured = requiresAuth(operationSecurity(api.spec, entry.op));
    return `<div class="ep-item ${active ? "active" : ""} ${entry.deprecated ? "deprecated" : ""}" data-nav="${view}" data-key="${escapeHtml(entry.key)}" title="${escapeHtml(entry.op.summary || entry.path)}">
      <span class="m-tag ${methodClass(entry.method)}">${entry.method}</span>
      <span class="path">${escapeHtml(entry.path)}</span>
      ${entry.deprecated ? '<span class="mini-dep" title="Deprecated"></span>' : ""}
      ${secured ? `<span class="mini-lock" title="Requires authorization">${ICONS.lock}</span>` : ""}
    </div>`;
  };
  const groupHtml = (id, title, items, count, description) => {
    if (!items.length) return "";
    const collapsed = !query && state.collapsed[id] ? "collapsed" : "";
    return `<div class="group ${collapsed}">
      <div class="group-title" data-toggle-group="${escapeHtml(id)}" title="${escapeHtml(description || "")}">${ICONS.chev} <span>${escapeHtml(title)}</span><span class="count">${count}</span></div>
      <div class="group-items">${items.join("")}</div>
    </div>`;
  };

  let html = `<div class="nav-link ${route.view === "overview" ? "active" : ""}" data-nav="overview">${ICONS.home} API overview</div>`;
  for (const group of api.groups) {
    const items = group.ops.filter(matches).map((entry) => itemHtml(entry, "op"));
    html += groupHtml(`tag:${group.name}`, group.name, items, items.length, group.tag.description);
  }
  const hooks = api.webhooks.filter(matches).map((entry) => itemHtml(entry, "webhook"));
  html += groupHtml("webhooks", "Webhooks", hooks, hooks.length);

  const schemaNames = Object.keys((api.spec.components || {}).schemas || {})
    .filter((name) => !query || name.toLowerCase().includes(query));
  const schemaItems = schemaNames.map((name) => (
    `<div class="ep-item ${route.view === "schema" && route.key === name ? "active" : ""}" data-nav="schema" data-key="${escapeHtml(name)}">
      <span class="m-tag m-schema">{ }</span><span class="path">${escapeHtml(name)}</span>
    </div>`
  ));
  if (!("schemas" in state.collapsed)) state.collapsed.schemas = true;
  html += groupHtml("schemas", "Schemas", schemaItems, schemaItems.length);

  const sidebar = byId("sidebar");
  const found = api.ops.some(matches) || hooks.length || schemaItems.length;
  sidebar.innerHTML = html + (query && !found ? '<div class="sidebar-empty">Nothing found</div>' : "");

  sidebar.querySelectorAll("[data-toggle-group]").forEach((node) => node.addEventListener("click", () => {
    const id = node.dataset.toggleGroup;
    state.collapsed[id] = !state.collapsed[id];
    saveJson(localStorage, "hs_collapsed", state.collapsed);
    renderSidebar();
  }));
  sidebar.querySelectorAll("[data-nav]").forEach((node) => node.addEventListener("click", () => {
    navigate(node.dataset.nav, node.dataset.key);
  }));
}

/* ---------- page dispatch ---------- */

function renderMain() {
  const api = currentApi();
  const route = state.route;
  const main = byId("mainContent");
  if (route.view === "op" || route.view === "webhook") {
    const list = route.view === "op" ? api.ops : api.webhooks;
    const entry = list.find((item) => item.key === route.key);
    if (entry) return renderOperationPage(api, entry);
  }
  if (route.view === "schema" && ((api.spec.components || {}).schemas || {})[route.key] !== undefined) {
    return renderSchemaPage(api, route.key);
  }
  if (route.view !== "overview") {
    main.innerHTML = `<div class="callout info">${ICONS.info}<div><b>No such page</b>Pick an endpoint or a schema on the left.</div></div>`;
    return undefined;
  }
  return renderOverview(api);
}

/* ---------- overview ---------- */

function renderOverview(api) {
  const spec = api.spec;
  const info = spec.info || {};
  const schemes = securitySchemesOf(spec);
  const schemaCount = Object.keys((spec.components || {}).schemas || {}).length;
  const contact = info.contact || {};
  const meta = [];
  if (contact.name || contact.email || contact.url) {
    meta.push(`Contact: ${escapeHtml(contact.name || "")} ${contact.email ? `<a href="mailto:${escapeHtml(contact.email)}">${escapeHtml(contact.email)}</a>` : ""} ${contact.url ? `<a href="${escapeHtml(safeUrl(contact.url))}" target="_blank" rel="noopener noreferrer">${escapeHtml(contact.url)}</a>` : ""}`);
  }
  if (info.license) {
    const license = info.license;
    const label = escapeHtml(license.name) + (license.identifier ? ` (${escapeHtml(license.identifier)})` : "");
    meta.push(`License: ${license.url ? `<a href="${escapeHtml(safeUrl(license.url))}" target="_blank" rel="noopener noreferrer">${label}</a>` : label}`);
  }
  if (info.termsOfService) meta.push(`<a href="${escapeHtml(safeUrl(info.termsOfService))}" target="_blank" rel="noopener noreferrer">Terms of service</a>`);

  const servers = (spec.servers || []).map((server) => `<div class="server-row">${escapeHtml(server.url)}${server.description ? ` <span class="muted">— ${escapeHtml(server.description)}</span>` : ""}
    ${Object.entries(server.variables || {}).map(([name, variable]) => `<div class="faint">{${escapeHtml(name)}} = ${escapeHtml(variable.default)}${variable.enum ? ` (${variable.enum.map(escapeHtml).join(" | ")})` : ""}${variable.description ? ` — ${escapeHtml(variable.description)}` : ""}</div>`).join("")}
  </div>`).join("");

  const tags = api.groups.map((group) => `<div class="tag-row" data-nav="op" data-key="${escapeHtml(group.ops[0].key)}">
    <span class="tag-name">${escapeHtml(group.name)}</span>
    <span class="md dim small">${renderMarkdown(group.tag.description || "")}${group.tag.externalDocs ? externalDocsHtml(group.tag.externalDocs) : ""}</span>
    <span class="faint" style="margin-left:auto;">${group.ops.length}</span>
  </div>`).join("");

  const security = schemes.map(([name, scheme]) => `<div class="tag-row" data-open-auth>
    <span class="tag-name mono">${escapeHtml(name)}</span><span class="muted">${escapeHtml(schemeTypeLabel(scheme))}</span>
  </div>`).join("");

  byId("mainContent").innerHTML = `
    <div class="ep-header">
      <h1 class="plain">${escapeHtml(info.title || "API")}</h1>
      ${info.summary ? `<p class="ep-summary">${escapeHtml(info.summary)}</p>` : ""}
      <div class="badges-row">
        ${info.version ? `<span class="badge neutral">version ${escapeHtml(info.version)}</span>` : ""}
        <span class="badge neutral mono">OpenAPI ${escapeHtml(spec.openapi || "")}</span>
        ${spec.jsonSchemaDialect ? `<span class="badge neutral mono">${escapeHtml(spec.jsonSchemaDialect)}</span>` : ""}
      </div>
    </div>
    ${info.description ? `<div class="md" style="margin-top:16px;">${renderMarkdown(info.description)}</div>` : ""}
    ${meta.length ? `<div class="muted" style="margin-top:12px;display:flex;flex-direction:column;gap:2px;">${meta.map((line) => `<div>${line}</div>`).join("")}</div>` : ""}
    ${spec.externalDocs ? `<div style="margin-top:8px;">${externalDocsHtml(spec.externalDocs)}</div>` : ""}
    <div class="section"><div class="overview-grid">
      ${statCard("Endpoints", api.ops.length)}
      ${statCard("Groups", api.groups.length)}
      ${statCard("Schemas", schemaCount)}
      ${api.webhooks.length ? statCard("Webhooks", api.webhooks.length) : ""}
    </div></div>
    ${servers ? `<div class="section"><h2>Servers</h2>${servers}</div>` : ""}
    ${tags ? `<div class="section"><h2>Groups</h2>${tags}</div>` : ""}
    ${security ? `<div class="section"><h2>Authorization</h2>${security}</div>` : ""}
    <div class="section"><h2>Specification</h2><button class="pill-btn" id="downloadSpecBtn" style="display:inline-flex;">Download openapi.json</button></div>`;

  bindNavLinks();
  byId("downloadSpecBtn").addEventListener("click", () => {
    downloadBlob(new Blob([prettyJson(spec)], { type: "application/json" }), "openapi.json");
  });
}

function statCard(title, value) {
  return `<div class="card"><div class="card-title">${escapeHtml(title)}</div><div class="card-value">${value}</div></div>`;
}

function externalDocsHtml(docs) {
  return `<a href="${escapeHtml(safeUrl(docs.url || ""))}" target="_blank" rel="noopener noreferrer">${escapeHtml(docs.description || docs.url)} ${ICONS.external}</a>`;
}

function bindNavLinks() {
  byId("mainContent").querySelectorAll("[data-nav]").forEach((node) => node.addEventListener("click", () => {
    navigate(node.dataset.nav, node.dataset.key);
  }));
  byId("mainContent").querySelectorAll("[data-open-auth]").forEach((node) => node.addEventListener("click", openAuthModal));
}

/* ---------- schema page ---------- */

function renderSchemaPage(api, name) {
  const spec = api.spec;
  const ref = { $ref: `#/components/schemas/${name.replace(/~/g, "~0").replace(/\//g, "~1")}` };
  const schema = deref(spec, ref) || {};
  const needle = JSON.stringify(ref.$ref);
  const usedBy = api.ops.filter((entry) => JSON.stringify(entry.op).includes(needle) || JSON.stringify(entry.params).includes(needle));
  const usedBySchemas = Object.entries((spec.components || {}).schemas || {})
    .filter(([other, value]) => other !== name && JSON.stringify(value).includes(needle)).map(([other]) => other);

  byId("mainContent").innerHTML = `
    <div class="ep-header">
      <h1><span class="m-tag m-schema">SCHEMA</span> ${escapeHtml(name)}</h1>
      <div class="badges-row"><span class="badge neutral mono">${escapeHtml(typeLabel(spec, schema))}</span>${schema.deprecated ? `<span class="badge deprecated">${ICONS.warn} Deprecated</span>` : ""}</div>
    </div>
    <div class="section split">
      <div><h2 class="sub-title">Structure</h2>${renderSchemaTree(spec, ref, "schema", schemaLinkFor())}</div>
      <div><h2 class="sub-title">Example</h2><pre class="example">${escapeHtml(prettyJson(exampleFromSchema(spec, ref, "response")))}</pre></div>
    </div>
    ${usedBy.length || usedBySchemas.length ? `<div class="section"><h2>Used by</h2>
      ${usedBy.map((entry) => `<div class="ep-item" data-nav="op" data-key="${escapeHtml(entry.key)}"><span class="m-tag ${methodClass(entry.method)}">${entry.method}</span><span class="path">${escapeHtml(entry.path)}</span></div>`).join("")}
      ${usedBySchemas.map((other) => `<div class="ep-item" data-nav="schema" data-key="${escapeHtml(other)}"><span class="m-tag m-schema">{ }</span><span class="path">${escapeHtml(other)}</span></div>`).join("")}
    </div>` : ""}`;
  bindNavLinks();
}

/* ---------- operation page ---------- */

function draftKeyOf(entry) {
  return `${entry.kind}|${entry.key}`;
}

function getDraft(api, entry) {
  const key = draftKeyOf(entry);
  if (!state.drafts[key]) state.drafts[key] = initialDraft(api.spec, entry);
  return state.drafts[key];
}

function paramExampleText(spec, param) {
  if (param.content) {
    const [media, mediaObj] = Object.entries(param.content)[0] || [];
    const example = objectExamples(spec, mediaObj, "request")[0];
    if (!example) return "";
    return isJsonMedia(media || "") ? JSON.stringify(example.value) : toInputText(example.value);
  }
  const example = objectExamples(spec, param, "request")[0];
  return example ? toInputText(example.value) : "";
}

function initialDraft(spec, entry) {
  const draft = { params: {}, form: {}, media: "", bodyMode: "json", bodyText: "" };
  for (const param of entry.params) {
    // Required values are filled in; optional ones only hint.
    draft.params[paramKey(param)] = param.required || param.in === "path" ? paramExampleText(spec, param) : "";
  }
  const body = requestBodyOf(spec, entry);
  if (body) {
    const medias = Object.keys(body.content);
    resetBodyDraft(spec, entry, draft, medias.find(isJsonMedia) || medias[0]);
  }
  return draft;
}

function resetBodyDraft(spec, entry, draft, media, exampleIndex = 0) {
  const mediaObj = requestBodyOf(spec, entry).content[media] || {};
  const examples = objectExamples(spec, mediaObj, "request");
  const value = (examples[exampleIndex] || examples[0] || {}).value;
  draft.media = media;
  draft.bodyMode = "json";
  draft.bodyText = value === undefined ? "" : (typeof value === "string" && !isJsonMedia(media) ? value : prettyJson(value));
  draft.form = {};
  const s = deref(spec, mediaObj.schema) || {};
  const objectValue = value && typeof value === "object" && !Array.isArray(value) ? value : {};
  for (const [name, prop] of Object.entries(s.properties || {})) {
    if (isBinarySchema(spec, prop)) continue;
    draft.form[name] = toInputText(objectValue[name] !== undefined ? objectValue[name] : exampleFromSchema(spec, prop, "request"));
  }
}

function renderOperationPage(api, entry) {
  const spec = api.spec;
  const op = entry.op;
  const interactive = entry.kind === "path";
  const draft = getDraft(api, entry);
  const ctx = { spec, entry, draft, draftKey: draftKeyOf(entry) };
  const requirements = operationSecurity(spec, op);
  const secured = requiresAuth(requirements);

  let html = `
    <div class="ep-header">
      <h1><span class="m-tag ${methodClass(entry.method)}">${entry.method}</span> ${escapeHtml(entry.path)}</h1>
      ${op.summary ? `<p class="ep-summary">${escapeHtml(op.summary)}</p>` : ""}
      <div class="badges-row">
        ${entry.tags.map((tag) => `<span class="badge neutral">${escapeHtml(tag)}</span>`).join("")}
        ${op.operationId ? `<span class="badge neutral mono" title="operationId">${escapeHtml(op.operationId)}</span>` : ""}
        ${entry.deprecated ? `<span class="badge deprecated">${ICONS.warn} Deprecated</span>` : ""}
        ${secured ? `<span class="badge protected">${ICONS.lock} ${escapeHtml(describeRequirements(requirements))}</span>` : ""}
      </div>
    </div>
    ${op.description ? `<div class="md" style="margin-top:16px;">${renderMarkdown(op.description)}</div>` : ""}
    ${entry.item.description && entry.item.description !== op.description ? `<div class="md dim" style="margin-top:8px;">${renderMarkdown(entry.item.description)}</div>` : ""}
    ${op.externalDocs ? `<div style="margin-top:8px;">${externalDocsHtml(op.externalDocs)}</div>` : ""}`;

  if (entry.deprecated) {
    html += `<div class="callout warn">${ICONS.warn}<div><b>Deprecated</b>It still works, but may be removed in a future version.</div></div>`;
  }
  if (entry.kind === "webhook") {
    html += `<div class="callout info">${ICONS.info}<div><b>Webhook</b>The API itself sends this request — to a URL you give it. Below is what arrives and which response is expected from you.</div></div>`;
  }
  if (secured) {
    const auth = resolveAuth(spec, requirements);
    html += auth.missing.length
      ? `<div class="callout danger">${ICONS.lock}<div><b>Requires authorization</b>${escapeHtml(describeRequirements(requirements))}. <button class="link-btn" data-open-auth style="margin:0;">Authorize →</button></div></div>`
      : `<div class="callout info">${ICONS.unlock}<div><b>Authorization is applied</b>${escapeHtml(auth.used.join(" + "))}</div></div>`;
  }

  html += paramsSectionHtml(spec, entry, draft, interactive);
  html += bodySectionHtml(ctx, interactive);
  if (interactive) html += tryItSectionHtml();
  html += responsesSectionHtml(api, entry);
  html += callbacksSectionHtml(api, entry);

  const main = byId("mainContent");
  main.innerHTML = html;
  bindNavLinks();
  bindDocWidgets(main);
  if (interactive) bindTryIt(ctx);
}

/* ---------- parameters ---------- */

function paramsSectionHtml(spec, entry, draft, interactive) {
  if (!entry.params.length) return "";
  const order = { path: 0, query: 1, header: 2, cookie: 3 };
  const params = [...entry.params].sort((a, b) => (order[a.in] ?? 9) - (order[b.in] ?? 9));
  const rows = params.map((param) => {
    const key = paramKey(param);
    const schema = param.schema ?? (Object.values(param.content || {})[0] || {}).schema;
    const s = deref(spec, schema) || {};
    const required = param.required || param.in === "path";
    const constraints = constraintList(s);
    const style = param.style || param.explode !== undefined
      ? `style: ${param.style || "default"}${param.explode !== undefined ? `, explode: ${param.explode}` : ""}` : "";
    const placeholder = paramExampleText(spec, param) || typeLabel(spec, schema);
    const input = interactive
      ? (param.content
        ? `<textarea class="field-input" data-param="${escapeHtml(key)}" placeholder="${escapeHtml(placeholder)}">${escapeHtml(draft.params[key] || "")}</textarea>`
        : valueInputHtml(spec, schema, draft.params[key] || "", `data-param="${escapeHtml(key)}"`, placeholder))
      : "";
    return `<tr>
      <td>
        <div class="field-name">${escapeHtml(param.name)}${required ? '<span class="req-star"> *</span>' : ""}</div>
        <div class="field-loc">${escapeHtml(param.in)}</div>
        ${param.deprecated ? '<span class="sch-flag dep">deprecated</span>' : ""}
      </td>
      <td>
        <div class="field-type">${typeLabelHtml({ spec, schemaLink: schemaLinkFor() }, schema)}${param.content ? ` <span class="faint">${escapeHtml(Object.keys(param.content)[0])}</span>` : ""}</div>
        ${constraints.length || style ? `<div class="field-cons">${escapeHtml([...constraints, style].filter(Boolean).join(" · "))}</div>` : ""}
        ${Array.isArray(s.enum) && !interactive ? enumHtml(s.enum) : ""}
      </td>
      <td class="col-input">
        ${input}
        <div class="field-error" data-error-for="param:${escapeHtml(key)}"></div>
        ${param.description ? `<div class="field-desc md dim small">${renderMarkdown(param.description)}</div>` : ""}
      </td>
    </tr>`;
  }).join("");
  return `<div class="section"><h2>Parameters</h2>
    <table class="params"><thead><tr><th>Name</th><th>Type</th><th>${interactive ? "Value" : "Description"}</th></tr></thead><tbody>${rows}</tbody></table>
  </div>`;
}

/* An input fitting `schema`: a select for enums and booleans, a
 * textarea for objects, a text field otherwise. */
function valueInputHtml(spec, schema, value, attrs, placeholder) {
  const s = deref(spec, schema) || {};
  const types = schemaTypes(s);
  const itemSchema = types.includes("array") ? deref(spec, s.items) || {} : null;
  const options = Array.isArray(s.enum) ? s.enum : (types.includes("boolean") ? [true, false] : null);

  if (options) {
    return `<select class="field-input" ${attrs}>
      <option value="" ${value === "" ? "selected" : ""}>— not set —</option>
      ${options.filter((option) => option !== null).map((option) => (
        `<option value="${escapeHtml(toInputText(option))}" ${toInputText(option) === value ? "selected" : ""}>${escapeHtml(toInputText(option))}</option>`
      )).join("")}
      ${options.includes(null) ? `<option value="null" ${value === "null" ? "selected" : ""}>null</option>` : ""}
    </select>`;
  }
  const complex = types.includes("object") || (itemSchema && schemaTypes(itemSchema).includes("object"));
  if (complex) {
    return `<textarea class="field-input" ${attrs} placeholder="${escapeHtml(placeholder)}">${escapeHtml(value)}</textarea>`;
  }
  const hint = itemSchema ? `${placeholder} (comma-separated)` : placeholder;
  return `<input class="field-input" type="text" ${attrs} value="${escapeHtml(value)}" placeholder="${escapeHtml(hint)}" autocomplete="off">`;
}

/* ---------- request body ---------- */

function bodySectionHtml(ctx, interactive) {
  const { spec, entry, draft } = ctx;
  const body = requestBodyOf(spec, entry);
  if (!body) return "";
  const medias = Object.keys(body.content);
  const media = interactive ? draft.media : medias[0];
  const mediaObj = body.content[media] || {};
  const link = schemaLinkFor();

  let html = `<div class="section"><h2>Request body ${body.required ? '<span class="badge protected">required</span>' : '<span class="badge neutral">optional</span>'}</h2>
    ${body.description ? `<div class="md dim" style="margin-bottom:10px;">${renderMarkdown(body.description)}</div>` : ""}`;

  if (!interactive) {
    return html + contentBlocksHtml(spec, body.content, "request", link, "wh-body") + "</div>";
  }

  html += `<div class="inline-row">
    ${medias.length > 1 ? `<select class="field-input" id="mediaSelect" style="flex:none;width:auto;">${medias.map((m) => `<option ${m === media ? "selected" : ""}>${escapeHtml(m)}</option>`).join("")}</select>` : `<span class="badge neutral mono">${escapeHtml(media)}</span>`}`;

  const schema = deref(spec, mediaObj.schema) || {};
  const formable = schemaTypes(schema).includes("object") && schema.properties;
  if (isJsonMedia(media) && formable) {
    html += `<div class="body-toggle">
      <button data-body-mode="json" class="${draft.bodyMode === "json" ? "active" : ""}">JSON</button>
      <button data-body-mode="form" class="${draft.bodyMode === "form" ? "active" : ""}">Form</button>
    </div>`;
  }
  const examples = objectExamples(spec, mediaObj, "request");
  if (examples.length > 1) {
    html += `<select class="field-input" id="bodyExampleSelect" style="flex:none;width:auto;" title="Examples">${examples.map((ex, index) => `<option value="${index}">${escapeHtml(ex.summary || ex.name)}</option>`).join("")}</select>`;
  }
  if (!isFormMedia(media) || isJsonMedia(media)) html += '<button class="pill-btn" id="resetBodyBtn">Insert example</button>';
  html += "</div>";

  if (isJsonMedia(media) && draft.bodyMode === "form" && formable) {
    html += formFieldsHtml(ctx, schema);
  } else if (isJsonMedia(media) || isTextMedia(media)) {
    html += `<textarea class="json-editor" id="bodyText" spellcheck="false">${escapeHtml(draft.bodyText)}</textarea>`;
  } else if (isFormMedia(media)) {
    html += schema.properties ? formFieldsHtml(ctx, schema) : '<div class="faint">The form schema is not described</div>';
  } else {
    html += `<input class="field-input" type="file" data-body-file>${state.files.get(`${ctx.draftKey}|__body__`) ? `<div class="faint">Selected: ${escapeHtml(state.files.get(`${ctx.draftKey}|__body__`)[0].name)}</div>` : ""}`;
  }
  html += `<div class="field-error" data-error-for="body"></div>
    <details class="sch-nested" style="margin-top:12px;"><summary>Body schema</summary><div style="margin-top:8px;">${renderSchemaTree(spec, mediaObj.schema, "request", link)}</div></details>
    ${encodingHtml(mediaObj)}
  </div>`;
  return html;
}

function formFieldsHtml(ctx, schema) {
  const { spec, draft } = ctx;
  const required = new Set(schema.required || []);
  const rows = Object.entries(schema.properties || {}).filter(([, prop]) => isPropertyVisible(spec, prop, "request")).map(([name, prop]) => {
    const s = deref(spec, prop) || {};
    const binary = isBinarySchema(spec, prop);
    const files = state.files.get(`${ctx.draftKey}|${name}`) || [];
    const input = binary
      ? `<input class="field-input" type="file" data-form-file="${escapeHtml(name)}" ${schemaTypes(s).includes("array") ? "multiple" : ""}>${files.length ? `<div class="faint">Selected: ${files.map((file) => escapeHtml(file.name)).join(", ")}</div>` : ""}`
      : valueInputHtml(spec, prop, draft.form[name] ?? "", `data-form-field="${escapeHtml(name)}"`, typeLabel(spec, prop));
    return `<tr>
      <td><div class="field-name">${escapeHtml(name)}${required.has(name) ? '<span class="req-star"> *</span>' : ""}</div>${s.deprecated ? '<span class="sch-flag dep">deprecated</span>' : ""}</td>
      <td><div class="field-type">${escapeHtml(typeLabel(spec, prop))}</div>${constraintList(s).length ? `<div class="field-cons">${escapeHtml(constraintList(s).join(" · "))}</div>` : ""}</td>
      <td class="col-input">${input}<div class="field-error" data-error-for="form:${escapeHtml(name)}"></div>${s.description ? `<div class="field-desc md dim small">${renderMarkdown(s.description)}</div>` : ""}</td>
    </tr>`;
  }).join("");
  return `<table class="params"><thead><tr><th>Field</th><th>Type</th><th>Value</th></tr></thead><tbody>${rows}</tbody></table>`;
}

/* `encoding` of a multipart / urlencoded body: per-property content
 * type, headers and serialization style. */
function encodingHtml(mediaObj) {
  const entries = Object.entries(mediaObj.encoding || {});
  if (!entries.length) return "";
  return `<div class="sub-title" style="margin-top:12px;">Field encoding</div>${entries.map(([name, encoding]) => (
    `<div class="field-cons"><b>${escapeHtml(name)}</b>: ${escapeHtml([
      encoding.contentType && `contentType ${encoding.contentType}`,
      encoding.style && `style ${encoding.style}`,
      encoding.explode !== undefined && `explode ${encoding.explode}`,
      encoding.allowReserved && "allowReserved",
      encoding.headers && `headers ${Object.keys(encoding.headers).join(", ")}`,
    ].filter(Boolean).join(" · "))}</div>`
  )).join("")}`;
}

/* ---------- try it ---------- */

function tryItSectionHtml() {
  return `<div class="section"><h2>Try it out</h2>
    <div class="sub-title">Request headers and cookies <span class="sub-hint">click a name or a value to copy it</span></div>
    <div class="headers-preview" id="headersPreview"></div>
    <div class="exec-row">
      <button class="exec-btn" id="executeBtn">▶ Send</button>
      <span class="exec-hint" id="execHint"></span>
    </div>
    <div class="code-box">
      <button class="copy-btn" id="copyCurlBtn">${ICONS.copy} copy</button>
      <div class="curl-clip" id="curlClip"><pre id="curlPreview"></pre></div>
      <button class="link-btn hidden" id="curlToggleBtn"></button>
    </div>
    <div class="response-panel" id="responsePanel"><div class="rp-placeholder">Click “Send” to run the request</div></div>
  </div>`;
}

function bindTryIt(ctx) {
  const { spec, entry, draft } = ctx;
  const main = byId("mainContent");
  const refresh = debounce(() => refreshTryIt(ctx), 120);

  main.querySelectorAll("[data-param]").forEach((input) => {
    input.addEventListener("input", () => { draft.params[input.dataset.param] = input.value; refresh(); });
  });
  main.querySelectorAll("[data-form-field]").forEach((input) => {
    input.addEventListener("input", () => { draft.form[input.dataset.formField] = input.value; refresh(); });
  });
  main.querySelectorAll("[data-form-file]").forEach((input) => {
    input.addEventListener("change", () => { state.files.set(`${ctx.draftKey}|${input.dataset.formFile}`, [...input.files]); refresh(); });
  });
  const bodyFile = main.querySelector("[data-body-file]");
  if (bodyFile) bodyFile.addEventListener("change", () => { state.files.set(`${ctx.draftKey}|__body__`, [...bodyFile.files]); refresh(); });
  const bodyText = byId("bodyText");
  if (bodyText) {
    bodyText.addEventListener("input", () => { draft.bodyText = bodyText.value; refresh(); });
    bodyText.addEventListener("keydown", (event) => {
      if (event.key !== "Tab") return;
      event.preventDefault();
      bodyText.setRangeText("  ", bodyText.selectionStart, bodyText.selectionEnd, "end");
      draft.bodyText = bodyText.value;
    });
  }

  const mediaSelect = byId("mediaSelect");
  if (mediaSelect) mediaSelect.addEventListener("change", () => { resetBodyDraft(spec, entry, draft, mediaSelect.value); renderMain(); });
  const exampleSelect = byId("bodyExampleSelect");
  if (exampleSelect) exampleSelect.addEventListener("change", () => { resetBodyDraft(spec, entry, draft, draft.media, Number(exampleSelect.value)); renderMain(); });
  const resetBody = byId("resetBodyBtn");
  if (resetBody) resetBody.addEventListener("click", () => { resetBodyDraft(spec, entry, draft, draft.media, exampleSelect ? Number(exampleSelect.value) : 0); renderMain(); });
  main.querySelectorAll("[data-body-mode]").forEach((button) => button.addEventListener("click", () => switchBodyMode(ctx, button.dataset.bodyMode)));

  byId("copyCurlBtn").addEventListener("click", () => copyText(byId("curlPreview").textContent, "curl copied"));
  byId("curlToggleBtn").addEventListener("click", () => {
    state.curlExpanded = state.curlExpanded === ctx.draftKey ? null : ctx.draftKey;
    renderCurl(ctx, byId("curlPreview").textContent);
  });
  byId("executeBtn").addEventListener("click", () => {
    if (refreshTryIt(ctx)) executeRequest(ctx, byId("responsePanel"));
  });
  refreshTryIt(ctx);
}

function switchBodyMode(ctx, mode) {
  const { spec, entry, draft } = ctx;
  if (mode === draft.bodyMode) return;
  const schema = (requestBodyOf(spec, entry).content[draft.media] || {}).schema;
  if (mode === "form") {
    let parsed;
    try { parsed = JSON.parse(draft.bodyText || "{}"); } catch {
      showToast("The JSON doesn't parse — fix it before switching");
      return;
    }
    const s = deref(spec, schema) || {};
    for (const name of Object.keys(s.properties || {})) {
      if (parsed && parsed[name] !== undefined) draft.form[name] = toInputText(parsed[name]);
    }
  } else {
    draft.bodyText = prettyJson(Object.fromEntries(formValues(ctx, schema)));
  }
  draft.bodyMode = mode;
  renderMain();
}

/* Every problem with the draft, keyed by the `data-error-for` it's
 * shown under; `blocking` problems have no input of their own. */
function validateDraft(ctx) {
  const { spec, entry, draft } = ctx;
  const errors = new Map();
  const blocking = [];

  for (const param of entry.params) {
    const key = paramKey(param);
    const raw = draft.params[key];
    const empty = raw === undefined || String(raw).trim() === "";
    if (empty) {
      if (param.required || param.in === "path") errors.set(`param:${key}`, "Required parameter");
      continue;
    }
    if (param.content) {
      const media = Object.keys(param.content)[0] || "";
      if (isJsonMedia(media)) {
        try { JSON.parse(raw); } catch (error) { errors.set(`param:${key}`, `Invalid JSON: ${error.message}`); }
      }
      continue;
    }
    const problems = validateSchema(spec, param.schema, coerceInput(spec, param.schema, raw), "request", "");
    if (problems.length) errors.set(`param:${key}`, problems.slice(0, 3).map((p) => p.replace(/^value: /, "")).join("\n"));
  }

  const body = requestBodyOf(spec, entry);
  if (body) {
    const mediaObj = body.content[draft.media] || {};
    const schema = deref(spec, mediaObj.schema) || {};
    const built = buildBody(ctx);
    if (built.kind === "none" && body.required) errors.set("body", "The request body is required");
    if (isJsonMedia(draft.media) && draft.bodyMode === "json" && draft.bodyText.trim()) {
      try {
        const problems = validateSchema(spec, mediaObj.schema, JSON.parse(draft.bodyText), "request");
        if (problems.length) errors.set("body", problems.slice(0, 6).join("\n"));
      } catch (error) {
        errors.set("body", `Invalid JSON: ${error.message}`);
      }
    }
    if ((isFormMedia(draft.media) && !isJsonMedia(draft.media)) || (isJsonMedia(draft.media) && draft.bodyMode === "form")) {
      const required = new Set(schema.required || []);
      for (const [name, prop] of Object.entries(schema.properties || {})) {
        if (!isPropertyVisible(spec, prop, "request")) continue;
        if (isBinarySchema(spec, prop)) {
          if (required.has(name) && !(state.files.get(`${ctx.draftKey}|${name}`) || []).length) errors.set(`form:${name}`, "Choose a file");
          continue;
        }
        const raw = draft.form[name];
        if (raw === undefined || String(raw).trim() === "") {
          if (required.has(name)) errors.set(`form:${name}`, "Required field");
          continue;
        }
        const problems = validateSchema(spec, prop, coerceInput(spec, prop, raw), "request", "");
        if (problems.length) errors.set(`form:${name}`, problems.slice(0, 3).map((p) => p.replace(/^value: /, "")).join("\n"));
      }
    }
  }

  const target = requestBase(spec, entry);
  if (!target.url && state.server.index === CUSTOM_SERVER) {
    blocking.push("Enter your URL in the “Server” menu at the top");
  } else if (!absoluteUrl(target.url || "/")) {
    blocking.push("The server is a relative URL, but the page was opened as a file — pick “Custom URL…” in the “Server” menu at the top");
  }
  return { errors, blocking };
}

/* Re-derive everything shown from the draft; `true` when it can be sent. */
function refreshTryIt(ctx) {
  const main = byId("mainContent");
  const { errors, blocking } = validateDraft(ctx);

  main.querySelectorAll("[data-error-for]").forEach((box) => {
    box.textContent = errors.get(box.dataset.errorFor) || "";
  });
  main.querySelectorAll("[data-param], [data-form-field]").forEach((input) => {
    const key = input.dataset.param ? `param:${input.dataset.param}` : `form:${input.dataset.formField}`;
    input.classList.toggle("invalid", errors.has(key));
    input.classList.toggle("valid-ok", !errors.has(key) && input.value.trim() !== "");
  });
  const bodyText = byId("bodyText");
  if (bodyText) bodyText.classList.toggle("invalid", errors.has("body"));

  const req = buildRequest(ctx);
  renderHeadersPreview(req);
  renderCurl(ctx, buildCurl(req));

  const ok = !errors.size && !blocking.length;
  const hint = byId("execHint");
  const warnings = req.auth.missing.length ? [`No credentials for: ${req.auth.missing.join(", ")}`] : [];
  hint.textContent = ok ? (warnings[0] || "The request matches the schema") : (blocking[0] || "Fix the highlighted fields");
  hint.classList.toggle("ok", ok && !warnings.length);
  byId("executeBtn").disabled = !ok;
  return ok;
}

/* One line per header / cookie, long values cut with an ellipsis. The
 * name and the value each copy on click; a secret stays masked on
 * screen but copies whole — `copies` holds the real text behind every
 * copyable piece. */
function renderHeadersPreview(req) {
  const tagFor = { global: '<span class="src-tag">GLOBAL</span>', auth: '<span class="src-tag auth">AUTH</span>', auto: '<span class="src-tag">AUTO</span>', param: "" };
  const copies = [];
  const piece = (cls, shown, real) => {
    copies.push(real);
    return `<span class="kv-copy ${cls}" data-copy-index="${copies.length - 1}" title="${escapeHtml(shown)}">${escapeHtml(shown)}</span>`;
  };
  const row = (key, value, source, tags) => (
    `<div class="row">${piece("kv-key", key, key)}<span class="kv-sep">:</span>${piece("kv-val", source === "auth" ? maskSecret(value) : value, value)}${tags}</div>`
  );

  const rows = req.headers.map(([key, value, source]) => row(key, value, source, tagFor[source] || ""));
  for (const [key, value, source] of req.cookies) {
    rows.push(row(key, value, source, '<span class="src-tag">COOKIE</span><span class="src-tag warn">curl only</span>'));
  }
  for (const name of req.auth.missing) {
    rows.push(`<div class="row">${piece("kv-key", name, name)}<span class="kv-sep">:</span><span class="kv-val unset">not set</span><span class="src-tag warn">AUTH</span></div>`);
  }

  const box = byId("headersPreview");
  box.innerHTML = rows.join("") || '<div class="faint">No headers</div>';
  box.querySelectorAll("[data-copy-index]").forEach((element) => element.addEventListener("click", () => {
    copyWithFlash(element, copies[Number(element.dataset.copyIndex)]);
  }));
}

const CURL_MAX_LINES = 10;

/* A curl longer than `CURL_MAX_LINES` lines on screen — wrapped lines
 * count, it's the height that matters — starts collapsed to that many.
 * Expanding sticks while the user stays on this route, through every
 * re-render as they type; another route starts collapsed again. */
function renderCurl(ctx, text) {
  const pre = byId("curlPreview");
  const clip = byId("curlClip");
  const toggle = byId("curlToggleBtn");
  pre.textContent = text;

  clip.classList.remove("collapsed");
  const style = getComputedStyle(pre);
  const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  const lines = Math.round((pre.scrollHeight - padding) / parseFloat(style.lineHeight));
  const long = lines > CURL_MAX_LINES;
  const expanded = state.curlExpanded === ctx.draftKey;

  clip.classList.toggle("collapsed", long && !expanded);
  toggle.classList.toggle("hidden", !long);
  toggle.textContent = expanded ? "Collapse" : `Show all · ${lines} lines`;
}

function maskSecret(value) {
  const text = String(value);
  const [scheme, ...rest] = text.split(" ");
  const secret = rest.length ? rest.join(" ") : text;
  const masked = secret.length > 8 ? `${secret.slice(0, 4)}…${secret.slice(-2)}` : "•••";
  return rest.length ? `${scheme} ${masked}` : masked;
}

/* ---------- responses / content ---------- */

function sortedResponseCodes(responses) {
  const rank = (code) => {
    if (/^\d{3}$/.test(code)) return Number(code);
    if (/^\dXX$/i.test(code)) return Number(code[0]) * 100 + 99;
    return 1000;
  };
  return Object.keys(responses || {}).sort((a, b) => rank(a) - rank(b));
}

function responsesSectionHtml(api, entry) {
  const spec = api.spec;
  const responses = entry.op.responses || {};
  const codes = sortedResponseCodes(responses);
  if (!codes.length) return "";
  const link = schemaLinkFor();
  const firstSuccess = codes.find((code) => /^2/.test(code));
  const idBase = `resp-${entry.kind}-${entry.key}`.replace(/[^\w-]/g, "_");

  const items = codes.map((code, index) => {
    const response = deref(spec, responses[code]) || {};
    const description = response.description || "";
    const firstLine = description.split("\n")[0];
    const headers = Object.entries(response.headers || {}).map(([name, raw]) => {
      const header = deref(spec, raw) || {};
      const schema = header.schema ?? (Object.values(header.content || {})[0] || {}).schema;
      return `<tr><td><span class="field-name">${escapeHtml(name)}</span>${header.required ? '<span class="req-star"> *</span>' : ""}${header.deprecated ? ' <span class="sch-flag dep">deprecated</span>' : ""}</td>
        <td class="field-type">${escapeHtml(typeLabel(spec, schema))}</td>
        <td>${header.description ? `<div class="md dim small">${renderMarkdown(header.description)}</div>` : ""}${header.example !== undefined ? `<div class="field-cons">example: ${escapeHtml(toInputText(header.example))}</div>` : ""}</td></tr>`;
    }).join("");
    const links = Object.entries(response.links || {}).map(([name, raw]) => linkHtml(api, name, deref(spec, raw) || {})).join("");
    const content = response.content && Object.keys(response.content).length
      ? contentBlocksHtml(spec, response.content, "response", link, `${idBase}-${index}`)
      : '<div class="faint">No body</div>';
    return `<details class="resp-doc" ${code === firstSuccess ? "open" : ""}>
      <summary><span class="status-chip ${statusClass(code)}">${escapeHtml(code)}</span><span>${escapeHtml(firstLine)}</span>${ICONS.chev}</summary>
      <div class="resp-body">
        ${description.includes("\n") ? `<div class="md dim small" style="margin-bottom:10px;">${renderMarkdown(description)}</div>` : ""}
        ${headers ? `<div class="sub-title">Headers</div><table class="params"><tbody>${headers}</tbody></table>` : ""}
        <div class="sub-title">Body</div>${content}
        ${links ? `<div class="sub-title">Links</div>${links}` : ""}
      </div>
    </details>`;
  }).join("");
  return `<div class="section"><h2>Responses</h2>${items}</div>`;
}

/* Media types of a Request Body / Response as tabs, each with its
 * schema tree and example(s). */
function contentBlocksHtml(spec, content, mode, link, idBase) {
  const medias = Object.keys(content || {});
  if (!medias.length) return "";
  const tabs = medias.length > 1
    ? `<div class="media-tabs">${medias.map((media, index) => `<button class="${index === 0 ? "active" : ""}" data-media-tab="${idBase}" data-index="${index}">${escapeHtml(media)}</button>`).join("")}</div>`
    : `<div class="media-tabs"><span class="badge neutral mono">${escapeHtml(medias[0])}</span></div>`;
  const blocks = medias.map((media, index) => {
    const mediaObj = content[media] || {};
    const examples = objectExamples(spec, mediaObj, mode);
    const exampleSelect = examples.length > 1
      ? `<select class="field-input" data-example-group="${idBase}-${index}" style="margin-bottom:6px;">${examples.map((ex, i) => `<option value="${i}">${escapeHtml(ex.summary || ex.name)}</option>`).join("")}</select>`
      : "";
    const examplePres = examples.map((ex, i) => {
      const text = typeof ex.value === "string" && !isJsonMedia(media) ? ex.value : prettyJson(ex.value);
      return `<pre class="example ${i ? "hidden" : ""}" data-example-of="${idBase}-${index}" data-index="${i}">${escapeHtml(text)}</pre>`;
    }).join("");
    return `<div class="${index ? "hidden" : ""}" data-media-block="${idBase}" data-index="${index}">
      <div class="split">
        <div>${mediaObj.schema !== undefined ? renderSchemaTree(spec, mediaObj.schema, mode, link) : '<div class="faint">No schema</div>'}</div>
        <div>${exampleSelect}${examplePres || '<div class="faint">No example</div>'}</div>
      </div>
      ${encodingHtml(mediaObj)}
    </div>`;
  }).join("");
  return tabs + blocks;
}

function linkHtml(api, name, link) {
  const target = link.operationId && api.ops.find((entry) => entry.op.operationId === link.operationId);
  const targetHtml = target
    ? `<a href="${escapeHtml(routeHref("op", target.key))}">${escapeHtml(link.operationId)}</a>`
    : escapeHtml(link.operationId || link.operationRef || "");
  const params = Object.entries(link.parameters || {}).map(([key, value]) => `${key} = ${toInputText(value)}`).join(", ");
  return `<div class="field-cons" style="margin-bottom:4px;"><b>${escapeHtml(name)}</b> → ${targetHtml}${params ? ` (${escapeHtml(params)})` : ""}${link.requestBody !== undefined ? escapeHtml(` · body = ${toInputText(link.requestBody)}`) : ""}</div>
    ${link.description ? `<div class="md dim small">${renderMarkdown(link.description)}</div>` : ""}`;
}

/* Tabs and example selects inside documentation blocks. */
function bindDocWidgets(root) {
  root.querySelectorAll("[data-media-tab]").forEach((button) => button.addEventListener("click", () => {
    const group = button.dataset.mediaTab;
    root.querySelectorAll(`[data-media-tab="${group}"]`).forEach((other) => other.classList.toggle("active", other === button));
    root.querySelectorAll(`[data-media-block="${group}"]`).forEach((block) => block.classList.toggle("hidden", block.dataset.index !== button.dataset.index));
  }));
  root.querySelectorAll("[data-example-group]").forEach((select) => select.addEventListener("change", () => {
    root.querySelectorAll(`[data-example-of="${select.dataset.exampleGroup}"]`).forEach((pre) => pre.classList.toggle("hidden", pre.dataset.index !== select.value));
  }));
  root.querySelectorAll("[data-open-auth]").forEach((node) => node.addEventListener("click", openAuthModal));
}

/* ---------- callbacks ---------- */

function callbacksSectionHtml(api, entry) {
  const spec = api.spec;
  const callbacks = Object.entries(entry.op.callbacks || {});
  if (!callbacks.length) return "";
  const blocks = callbacks.map(([name, raw]) => {
    const callback = deref(spec, raw) || {};
    const operations = Object.entries(callback).flatMap(([expression, rawItem]) => {
      const item = deref(spec, rawItem) || {};
      return HTTP_METHODS.filter((method) => item[method]).map((method) => makeOperation(spec, "callback", expression, method, item, item[method]));
    });
    return `<div class="sub-title">${escapeHtml(name)}</div>${operations.map((cb) => {
      const body = requestBodyOf(spec, cb);
      return `<details class="resp-doc">
        <summary><span class="m-tag ${methodClass(cb.method)}">${cb.method}</span><span class="mono">${escapeHtml(cb.path)}</span>${cb.op.summary ? `<span class="muted">${escapeHtml(cb.op.summary)}</span>` : ""}${ICONS.chev}</summary>
        <div class="resp-body">
          ${cb.op.description ? `<div class="md dim small">${renderMarkdown(cb.op.description)}</div>` : ""}
          ${body ? `<div class="sub-title">Body</div>${contentBlocksHtml(spec, body.content, "request", schemaLinkFor(), `cb-${name}-${cb.method}`.replace(/[^\w-]/g, "_"))}` : ""}
          ${responsesSectionHtml(api, cb).replace('<div class="section"><h2>Responses</h2>', '<div><div class="sub-title">Expected responses</div>')}
        </div>
      </details>`;
    }).join("")}`;
  }).join("");
  return `<div class="section"><h2>Callbacks</h2><div class="faint" style="margin-bottom:8px;">Requests the API sends back in response to this call.</div>${blocks}</div>`;
}

/* ---------- global headers / cookies drawer ---------- */

function renderKvList(containerId, list, keyPlaceholder) {
  const container = byId(containerId);
  container.innerHTML = list.map((row, index) => `<div class="kv-row" data-index="${index}">
    <input type="checkbox" ${row.enabled ? "checked" : ""} title="Send with every request">
    <input type="text" class="kv-key" placeholder="${keyPlaceholder}" value="${escapeHtml(row.key)}">
    <input type="text" class="kv-val" placeholder="value" value="${escapeHtml(row.value)}">
    <button class="rm" title="Remove">✕</button>
  </div>`).join("");
  container.querySelectorAll(".kv-row").forEach((node) => {
    const row = list[Number(node.dataset.index)];
    node.querySelector("input[type=checkbox]").addEventListener("change", (event) => { row.enabled = event.target.checked; });
    node.querySelector(".kv-key").addEventListener("input", (event) => { row.key = event.target.value.trim(); });
    node.querySelector(".kv-val").addEventListener("input", (event) => { row.value = event.target.value; });
    node.querySelector(".rm").addEventListener("click", () => {
      list.splice(Number(node.dataset.index), 1);
      renderKvList(containerId, list, keyPlaceholder);
    });
  });
}

function renderDrawer() {
  renderKvList("headersList", state.globals.headers, "Header-Name");
  renderKvList("cookiesList", state.globals.cookies, "cookie_name");
}

function openDrawer() {
  renderDrawer();
  byId("drawer").classList.add("open");
  byId("drawerBackdrop").classList.add("open");
}

function closeDrawer() {
  byId("drawer").classList.remove("open");
  byId("drawerBackdrop").classList.remove("open");
}

function isKvList(value) {
  return Array.isArray(value) && value.every((row) => row && typeof row.key === "string" && typeof row.value === "string");
}

function initDrawer() {
  byId("globalSettingsBtn").innerHTML = ICONS.key;
  byId("drawerCloseBtn").innerHTML = ICONS.close;
  byId("globalSettingsBtn").addEventListener("click", openDrawer);
  byId("drawerCloseBtn").addEventListener("click", closeDrawer);
  byId("drawerBackdrop").addEventListener("click", closeDrawer);
  byId("addHeaderBtn").addEventListener("click", () => { state.globals.headers.push({ key: "", value: "", enabled: true }); renderDrawer(); });
  byId("addCookieBtn").addEventListener("click", () => { state.globals.cookies.push({ key: "", value: "", enabled: true }); renderDrawer(); });
  byId("saveGlobalBtn").addEventListener("click", () => {
    saveJson(localStorage, "hs_globals", state.globals);
    closeDrawer();
    renderMain();
    showToast("Global headers and cookies saved");
  });
  byId("exportGlobalBtn").addEventListener("click", () => {
    downloadBlob(new Blob([prettyJson(state.globals)], { type: "application/json" }), "heavyswag-docs-preset.json");
  });
  byId("importGlobalInput").addEventListener("change", (event) => {
    const [file] = event.target.files;
    event.target.value = "";
    if (!file) return;
    file.text().then((text) => {
      const data = JSON.parse(text);
      if (!isKvList(data.headers || []) || !isKvList(data.cookies || [])) throw new Error("bad preset");
      state.globals = {
        headers: (data.headers || []).map((row) => ({ key: row.key, value: row.value, enabled: row.enabled !== false })),
        cookies: (data.cookies || []).map((row) => ({ key: row.key, value: row.value, enabled: row.enabled !== false })),
      };
      renderDrawer();
      showToast("Preset imported — click “Save”");
    }).catch(() => showToast("The file isn't a headers preset (JSON with headers / cookies)"));
  });
}
