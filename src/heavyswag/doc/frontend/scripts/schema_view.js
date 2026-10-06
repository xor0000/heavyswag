/* schema_view.js — a JSON Schema rendered as an expandable tree:
 * properties with their types, flags, constraints and descriptions,
 * nested objects / arrays / combinators one level down each.
 *
 * A `$ref` to `#/components/schemas/X` links to that schema's own page;
 * a reference back to a schema already being expanded stops there
 * instead of recursing forever. */

const SCHEMA_MAX_DEPTH = 7;

/* `schemaLink(name)` returns the href of a component schema's page —
 * provided by render.js, which knows the current version. */
function renderSchemaTree(spec, schema, mode, schemaLink) {
  if (schema === undefined) return '<div class="faint">Схема не указана</div>';
  const ctx = { spec, mode, schemaLink };
  const body = schemaChildren(ctx, schema, 0, new Set());
  const head = schemaSummary(ctx, schema);
  if (!body && !head) return `<div class="schema"><div class="sch-row"><span class="sch-type">${typeLabelHtml(ctx, schema)}</span></div></div>`;
  return `<div class="schema">${head}${body}</div>`;
}

/* Description, type and constraints of the root schema itself — shown
 * when it isn't an object whose properties already say everything. */
function schemaSummary(ctx, schema) {
  const s = deref(ctx.spec, schema);
  if (!s || typeof s !== "object") return "";
  const isPlainObject = schemaTypes(s).includes("object") && s.properties;
  const constraints = constraintList(s);
  const parts = [];
  if (!isPlainObject || componentSchemaName(schema)) {
    parts.push(`<div class="sch-head"><span class="sch-type">${typeLabelHtml(ctx, schema)}</span>${flagsHtml(s)}</div>`);
  }
  if (s.description) parts.push(`<div class="sch-desc md dim">${renderMarkdown(s.description)}</div>`);
  if (constraints.length) parts.push(`<div class="sch-cons">${escapeHtml(constraints.join(" · "))}</div>`);
  if (Array.isArray(s.enum)) parts.push(enumHtml(s.enum));
  if (s.discriminator) parts.push(discriminatorHtml(s.discriminator));
  return parts.length ? `<div class="sch-row">${parts.join("")}</div>` : "";
}

/* The rows below a schema: properties for an object, the item schema
 * for an array, one block per variant for a combinator. */
function schemaChildren(ctx, schema, depth, seen) {
  if (schema === undefined || schema === null || typeof schema !== "object") return "";
  let visited = seen;
  if (typeof schema.$ref === "string") {
    if (seen.has(schema.$ref)) {
      return `<div class="sch-row sch-recursive">↺ рекурсивная ссылка на ${escapeHtml(refName(schema.$ref))}</div>`;
    }
    visited = new Set(seen).add(schema.$ref);
  }
  const s = deref(ctx.spec, schema);
  if (!s || typeof s !== "object") return "";
  if (s.__unresolved) return `<div class="sch-row sch-recursive">не удалось разрешить ${escapeHtml(s.__unresolved)}</div>`;
  if (depth > SCHEMA_MAX_DEPTH) return "";

  const rows = [];
  const required = new Set(s.required || []);
  for (const [name, prop] of Object.entries(s.properties || {})) {
    if (!isPropertyVisible(ctx.spec, prop, ctx.mode)) continue;
    rows.push(propertyRow(ctx, name, prop, required.has(name), depth, visited));
  }
  for (const [pattern, prop] of Object.entries(s.patternProperties || {})) {
    rows.push(propertyRow(ctx, `/${pattern}/`, prop, false, depth, visited, "ключи по шаблону"));
  }
  if (s.additionalProperties && typeof s.additionalProperties === "object") {
    rows.push(propertyRow(ctx, "{ключ}", s.additionalProperties, false, depth, visited, "любые другие ключи"));
  }

  const types = schemaTypes(s);
  if (types.includes("array")) {
    (s.prefixItems || []).forEach((item, index) => {
      rows.push(propertyRow(ctx, `[${index}]`, item, true, depth, visited));
    });
    if (s.items && typeof s.items === "object") {
      const itemRows = schemaChildren(ctx, s.items, depth + 1, visited);
      rows.push(itemRows || propertyRow(ctx, "[ ]", s.items, false, depth, visited, "элемент массива"));
    }
  }

  for (const keyword of ["allOf", "oneOf", "anyOf"]) {
    if (!Array.isArray(s[keyword])) continue;
    const title = { allOf: "все из", oneOf: "ровно один из", anyOf: "любой из" }[keyword];
    if (keyword === "allOf") {
      // allOf composes one object — its parts' properties belong together.
      s.allOf.forEach((sub) => rows.push(schemaChildren(ctx, sub, depth + 1, visited)));
      continue;
    }
    rows.push(`<div class="sch-row"><div class="sch-variant-title">${keyword} — ${title}</div>${s[keyword].map((sub, index) => (
      `<div class="sch-variant"><details class="sch-nested"${index === 0 ? " open" : ""}><summary>Вариант ${index + 1}: <span class="sch-type">${typeLabelHtml(ctx, sub)}</span></summary><div class="sch-children">${variantBody(ctx, sub, depth, visited)}</div></details></div>`
    )).join("")}</div>`);
  }
  if (s.not !== undefined) {
    rows.push(`<div class="sch-row"><div class="sch-variant-title">not — не должно подходить под</div><div class="sch-type">${typeLabelHtml(ctx, s.not)}</div></div>`);
  }
  return rows.join("");
}

function variantBody(ctx, sub, depth, seen) {
  const children = schemaChildren(ctx, sub, depth + 1, seen);
  const resolved = deref(ctx.spec, sub) || {};
  const constraints = constraintList(resolved);
  const desc = resolved.description ? `<div class="sch-desc md dim">${renderMarkdown(resolved.description)}</div>` : "";
  const cons = constraints.length ? `<div class="sch-cons">${escapeHtml(constraints.join(" · "))}</div>` : "";
  return children || desc || cons ? `${desc}${cons}${children}` : `<div class="faint">${escapeHtml(typeLabel(ctx.spec, sub))}</div>`;
}

function propertyRow(ctx, name, prop, isRequired, depth, seen, note) {
  const s = deref(ctx.spec, prop) || {};
  const constraints = constraintList(s);
  const recursive = typeof prop?.$ref === "string" && seen.has(prop.$ref);
  const children = recursive ? "" : schemaChildren(ctx, prop, depth + 1, seen);

  let nested = "";
  if (recursive) {
    nested = `<div class="sch-recursive">↺ рекурсивная ссылка на ${escapeHtml(refName(prop.$ref))}</div>`;
  } else if (children) {
    nested = `<details class="sch-nested"${depth < 1 ? " open" : ""}><summary>${escapeHtml(nestedLabel(ctx, prop))}</summary><div class="sch-children">${children}</div></details>`;
  }

  return `<div class="sch-row">
    <div class="sch-head">
      <span class="sch-name">${escapeHtml(name)}</span>${isRequired ? '<span class="req-star">*</span>' : ""}
      <span class="sch-type">${typeLabelHtml(ctx, prop)}</span>
      ${flagsHtml(s)}
      ${note ? `<span class="faint">${escapeHtml(note)}</span>` : ""}
    </div>
    ${s.title ? `<div class="sch-desc"><b>${escapeHtml(s.title)}</b></div>` : ""}
    ${s.description ? `<div class="sch-desc md dim">${renderMarkdown(s.description)}</div>` : ""}
    ${constraints.length ? `<div class="sch-cons">${escapeHtml(constraints.join(" · "))}</div>` : ""}
    ${Array.isArray(s.enum) ? enumHtml(s.enum) : ""}
    ${s.discriminator ? discriminatorHtml(s.discriminator) : ""}
    ${nested}
  </div>`;
}

function nestedLabel(ctx, prop) {
  const s = deref(ctx.spec, prop) || {};
  if (schemaTypes(s).includes("array")) return "элементы массива";
  if (s.oneOf || s.anyOf) return "варианты";
  return componentSchemaName(prop) ? `поля ${refName(prop.$ref)}` : "поля";
}

/* The type label, with every component schema name turned into a
 * link to its page. */
function typeLabelHtml(ctx, schema) {
  const label = escapeHtml(typeLabel(ctx.spec, schema));
  const names = new Set();
  collectRefNames(schema, names, 0);
  if (!names.size || !ctx.schemaLink) return label;
  return label.replace(/[A-Za-z_][\w.-]*/g, (word) => (
    names.has(word) ? `<a href="${escapeHtml(ctx.schemaLink(word))}">${word}</a>` : word
  ));
}

function collectRefNames(schema, names, depth) {
  if (!schema || typeof schema !== "object" || depth > 4) return;
  const name = componentSchemaName(schema);
  if (name) {
    names.add(name);
    return;
  }
  for (const key of ["items", "additionalProperties"]) collectRefNames(schema[key], names, depth + 1);
  for (const key of ["oneOf", "anyOf", "allOf", "prefixItems"]) {
    (schema[key] || []).forEach((sub) => collectRefNames(sub, names, depth + 1));
  }
}

function flagsHtml(s) {
  const flags = [];
  if (s.readOnly) flags.push('<span class="sch-flag ro">read-only</span>');
  if (s.writeOnly) flags.push('<span class="sch-flag wo">write-only</span>');
  if (s.deprecated) flags.push('<span class="sch-flag dep">deprecated</span>');
  return flags.join("");
}

function enumHtml(values) {
  return `<div class="sch-enum">${values.map((value) => `<code>${escapeHtml(JSON.stringify(value))}</code>`).join("")}</div>`;
}

function discriminatorHtml(discriminator) {
  const mapping = Object.entries(discriminator.mapping || {})
    .map(([value, ref]) => `${value} → ${refName(ref)}`).join(", ");
  return `<div class="sch-cons">discriminator: ${escapeHtml(discriminator.propertyName)}${mapping ? escapeHtml(` (${mapping})`) : ""}</div>`;
}

/* Every validation keyword of a schema as `name: value` text. */
function constraintList(s) {
  if (!s || typeof s !== "object") return [];
  const out = [];
  const add = (label, value) => { if (value !== undefined) out.push(`${label}: ${typeof value === "string" ? value : JSON.stringify(value)}`); };
  if (s.const !== undefined) add("const", s.const);
  add("default", s.default);
  add("minLength", s.minLength);
  add("maxLength", s.maxLength);
  add("pattern", s.pattern);
  // 3.1 has a numeric `exclusiveMinimum`; 3.0's boolean form still turns up.
  if (typeof s.exclusiveMinimum === "number") out.push(`> ${s.exclusiveMinimum}`);
  else if (s.minimum !== undefined) out.push(`${s.exclusiveMinimum === true ? ">" : "≥"} ${s.minimum}`);
  if (typeof s.exclusiveMaximum === "number") out.push(`< ${s.exclusiveMaximum}`);
  else if (s.maximum !== undefined) out.push(`${s.exclusiveMaximum === true ? "<" : "≤"} ${s.maximum}`);
  add("multipleOf", s.multipleOf);
  add("minItems", s.minItems);
  add("maxItems", s.maxItems);
  if (s.uniqueItems) out.push("uniqueItems");
  add("minProperties", s.minProperties);
  add("maxProperties", s.maxProperties);
  add("contentMediaType", s.contentMediaType);
  add("contentEncoding", s.contentEncoding);
  if (Array.isArray(s.examples) && s.examples.length) add("пример", s.examples[0]);
  else if (s.example !== undefined) add("пример", s.example);
  return out;
}
