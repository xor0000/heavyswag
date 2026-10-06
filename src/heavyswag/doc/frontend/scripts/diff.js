/* diff.js — what changed between two versions of the API: operations
 * added / removed / changed (parameters, request body, responses,
 * security, deprecation) and component schemas added / removed /
 * changed.
 *
 * Inline schemas are compared with `$ref`s left as names — a change
 * inside a referenced component shows up once, under "Схемы", rather
 * than under every operation that uses it. */

function diffSpecs(fromSpec, toSpec) {
  const fromOps = new Map(collectOperations(fromSpec).map((entry) => [entry.key, entry]));
  const toOps = new Map(collectOperations(toSpec).map((entry) => [entry.key, entry]));
  const result = { added: [], removed: [], changed: [], schemas: { added: [], removed: [], changed: [] } };

  for (const [key, entry] of toOps) {
    if (!fromOps.has(key)) result.added.push({ entry, notes: [entry.op.summary || ""] });
  }
  for (const [key, entry] of fromOps) {
    if (!toOps.has(key)) result.removed.push({ entry, notes: [entry.op.summary || ""] });
  }
  for (const [key, entry] of toOps) {
    const before = fromOps.get(key);
    if (!before) continue;
    const notes = compareOperations(fromSpec, before, toSpec, entry);
    if (notes.length) result.changed.push({ entry, notes });
  }

  const fromSchemas = (fromSpec.components || {}).schemas || {};
  const toSchemas = (toSpec.components || {}).schemas || {};
  for (const name of Object.keys(toSchemas)) {
    if (!(name in fromSchemas)) result.schemas.added.push(name);
    else if (stableStringify(fromSchemas[name]) !== stableStringify(toSchemas[name])) {
      result.schemas.changed.push({ name, notes: compareSchemaProperties(fromSpec, fromSchemas[name], toSpec, toSchemas[name]) });
    }
  }
  for (const name of Object.keys(fromSchemas)) {
    if (!(name in toSchemas)) result.schemas.removed.push(name);
  }
  return result;
}

function compareOperations(fromSpec, before, toSpec, after) {
  const notes = [];
  if (before.deprecated !== after.deprecated) notes.push(after.deprecated ? "помечен deprecated" : "больше не deprecated");

  const describeParam = (param) => `${param.in} «${param.name}»`;
  const fromParams = new Map(before.params.map((p) => [paramKey(p), p]));
  const toParams = new Map(after.params.map((p) => [paramKey(p), p]));
  for (const [key, param] of toParams) {
    const old = fromParams.get(key);
    if (!old) {
      notes.push(`добавлен ${param.required ? "обязательный " : ""}параметр ${describeParam(param)}: ${typeLabel(toSpec, param.schema)}`);
      continue;
    }
    if (Boolean(old.required) !== Boolean(param.required)) {
      notes.push(`параметр ${describeParam(param)} стал ${param.required ? "обязательным" : "необязательным"}`);
    }
    const oldType = typeLabel(fromSpec, old.schema);
    const newType = typeLabel(toSpec, param.schema);
    if (oldType !== newType) notes.push(`параметр ${describeParam(param)}: тип ${oldType} → ${newType}`);
    else if (stableStringify(old.schema) !== stableStringify(param.schema)) notes.push(`параметр ${describeParam(param)}: изменены ограничения`);
  }
  for (const [key, param] of fromParams) {
    if (!toParams.has(key)) notes.push(`удалён параметр ${describeParam(param)}`);
  }

  const oldBody = requestBodyOf(fromSpec, before);
  const newBody = requestBodyOf(toSpec, after);
  if (!oldBody && newBody) notes.push("добавлено тело запроса");
  else if (oldBody && !newBody) notes.push("удалено тело запроса");
  else if (oldBody && newBody) {
    if (Boolean(oldBody.required) !== Boolean(newBody.required)) notes.push(`тело запроса стало ${newBody.required ? "обязательным" : "необязательным"}`);
    notes.push(...compareContent(fromSpec, oldBody.content, toSpec, newBody.content, "тело запроса"));
  }

  const oldResponses = before.op.responses || {};
  const newResponses = after.op.responses || {};
  for (const code of Object.keys(newResponses)) {
    if (!(code in oldResponses)) notes.push(`добавлен ответ ${code}`);
    else {
      const oldResponse = deref(fromSpec, oldResponses[code]) || {};
      const newResponse = deref(toSpec, newResponses[code]) || {};
      notes.push(...compareContent(fromSpec, oldResponse.content, toSpec, newResponse.content, `ответ ${code}`));
    }
  }
  for (const code of Object.keys(oldResponses)) {
    if (!(code in newResponses)) notes.push(`удалён ответ ${code}`);
  }

  const oldSecurity = describeRequirements(operationSecurity(fromSpec, before.op));
  const newSecurity = describeRequirements(operationSecurity(toSpec, after.op));
  if (oldSecurity !== newSecurity) notes.push(`авторизация: ${oldSecurity || "нет"} → ${newSecurity || "нет"}`);
  return notes;
}

function compareContent(fromSpec, oldContent, toSpec, newContent, label) {
  const notes = [];
  const before = oldContent || {};
  const after = newContent || {};
  for (const media of Object.keys(after)) {
    if (!(media in before)) notes.push(`${label}: добавлен ${media}`);
    else if (stableStringify(before[media].schema) !== stableStringify(after[media].schema)) {
      const oldType = typeLabel(fromSpec, before[media].schema);
      const newType = typeLabel(toSpec, after[media].schema);
      const fields = compareSchemaProperties(fromSpec, before[media].schema, toSpec, after[media].schema);
      notes.push(oldType !== newType ? `${label} (${media}): ${oldType} → ${newType}` : `${label} (${media}): изменена схема${fields.length ? ` — ${fields.join("; ")}` : ""}`);
    }
  }
  for (const media of Object.keys(before)) {
    if (!(media in after)) notes.push(`${label}: удалён ${media}`);
  }
  return notes;
}

/* Property-level changes of two object schemas (one level deep). */
function compareSchemaProperties(fromSpec, oldSchema, toSpec, newSchema) {
  const before = deref(fromSpec, oldSchema) || {};
  const after = deref(toSpec, newSchema) || {};
  const oldProps = before.properties || {};
  const newProps = after.properties || {};
  const oldRequired = new Set(before.required || []);
  const newRequired = new Set(after.required || []);
  const notes = [];
  for (const name of Object.keys(newProps)) {
    if (!(name in oldProps)) notes.push(`+ ${name}: ${typeLabel(toSpec, newProps[name])}${newRequired.has(name) ? " (обязательное)" : ""}`);
    else {
      const oldType = typeLabel(fromSpec, oldProps[name]);
      const newType = typeLabel(toSpec, newProps[name]);
      if (oldType !== newType) notes.push(`${name}: ${oldType} → ${newType}`);
      else if (stableStringify(oldProps[name]) !== stableStringify(newProps[name])) notes.push(`${name}: изменены ограничения`);
      if (oldRequired.has(name) !== newRequired.has(name)) notes.push(`${name} стало ${newRequired.has(name) ? "обязательным" : "необязательным"}`);
    }
  }
  for (const name of Object.keys(oldProps)) {
    if (!(name in newProps)) notes.push(`− ${name}`);
  }
  return notes;
}

/* ---------- modal ---------- */

function openDiffModal() {
  const fromSelect = byId("diffFromSelect");
  const toSelect = byId("diffToSelect");
  const options = state.versions.map((version, index) => `<option value="${index}">${escapeHtml(version.name)}</option>`).join("");
  fromSelect.innerHTML = options;
  toSelect.innerHTML = options;
  const current = state.versionIndex;
  toSelect.value = String(current);
  fromSelect.value = String(current > 0 ? current - 1 : Math.min(1, state.versions.length - 1));
  renderDiffModal();
  byId("diffModalBackdrop").classList.add("open");
}

function renderDiffModal() {
  const from = state.versions[Number(byId("diffFromSelect").value)];
  const to = state.versions[Number(byId("diffToSelect").value)];
  const body = byId("diffModalBody");
  if (from === to) {
    body.innerHTML = '<div class="diff-empty">Выберите две разные версии</div>';
    return;
  }
  const diff = diffSpecs(from.spec, to.spec);
  const opItem = (item, linkable) => `<div class="diff-item">
      <span class="m-tag ${methodClass(item.entry.method)}">${item.entry.method}</span>
      <div>
        <div class="path">${linkable ? `<a href="${escapeHtml(routeHref(to.name, "op", item.entry.key))}" data-close-diff>${escapeHtml(item.entry.path)}</a>` : escapeHtml(item.entry.path)}</div>
        ${item.notes.filter(Boolean).length ? `<ul class="note">${item.notes.filter(Boolean).map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : ""}
      </div>
    </div>`;
  const section = (cls, title, items) => (items.length ? `<div class="diff-group ${cls}"><h4>${title} (${items.length})</h4>${items.join("")}</div>` : "");
  const schemaItem = (name, notes, linkable) => `<div class="diff-item"><span class="m-tag m-schema">SCHEMA</span><div>
      <div class="path">${linkable ? `<a href="${escapeHtml(routeHref(to.name, "schema", name))}" data-close-diff>${escapeHtml(name)}</a>` : escapeHtml(name)}</div>
      ${notes && notes.length ? `<ul class="note">${notes.map((note) => `<li>${escapeHtml(note)}</li>`).join("")}</ul>` : ""}
    </div></div>`;

  const html = section("diff-added", `＋ Добавлено в ${escapeHtml(to.name)}`, [
    ...diff.added.map((item) => opItem(item, true)),
    ...diff.schemas.added.map((name) => schemaItem(name, null, true)),
  ]) + section("diff-removed", `－ Удалено в ${escapeHtml(to.name)}`, [
    ...diff.removed.map((item) => opItem(item, false)),
    ...diff.schemas.removed.map((name) => schemaItem(name, null, false)),
  ]) + section("diff-changed", "✎ Изменено", [
    ...diff.changed.map((item) => opItem(item, true)),
    ...diff.schemas.changed.map((item) => schemaItem(item.name, item.notes, true)),
  ]);
  body.innerHTML = html || '<div class="diff-empty">Версии не отличаются</div>';
  body.querySelectorAll("[data-close-diff]").forEach((link) => link.addEventListener("click", closeDiffModal));
}

function closeDiffModal() {
  byId("diffModalBackdrop").classList.remove("open");
}

function initDiff() {
  byId("diffBtn").addEventListener("click", openDiffModal);
  byId("diffCloseBtn").innerHTML = ICONS.close;
  byId("diffCloseBtn").addEventListener("click", closeDiffModal);
  byId("diffFromSelect").addEventListener("change", renderDiffModal);
  byId("diffToSelect").addEventListener("change", renderDiffModal);
  byId("diffModalBackdrop").addEventListener("click", (event) => {
    if (event.target.id === "diffModalBackdrop") closeDiffModal();
  });
}
