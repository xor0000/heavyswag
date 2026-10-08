/* spec.js — reading an OpenAPI 3.1 document: `$ref` resolution,
 * operations and their grouping, example generation and JSON Schema
 * (2020-12) validation of what the user typed into "Try it out".
 *
 * Only local references (`#/...`) are resolved — a self-contained page
 * has nothing else to fetch. An unresolvable one is kept as
 * `{ __unresolved: ref }` so the UI can say so instead of crashing. */

const HTTP_METHODS = ["get", "put", "post", "delete", "options", "head", "patch", "trace"];
const MAX_REF_HOPS = 32;

function resolvePointer(spec, ref) {
  if (typeof ref !== "string" || !ref.startsWith("#")) return undefined;
  const tokens = ref.slice(1).split("/").slice(1)
    .map((token) => decodeURIComponent(token).replace(/~1/g, "/").replace(/~0/g, "~"));
  // Own properties only: `#/__proto__/...` or `#/constructor/...` must not
  // walk off the document into an object's prototype.
  return tokens.reduce((node, token) => (
    node !== null && typeof node === "object" && Object.hasOwn(node, token) ? node[token] : undefined
  ), spec);
}

function refName(ref) {
  const tokens = String(ref).split("/");
  return decodeURIComponent(tokens[tokens.length - 1]).replace(/~1/g, "/").replace(/~0/g, "~");
}

/* The `#/components/schemas/<name>` a schema points at, if any. */
function componentSchemaName(schema) {
  if (!schema || typeof schema.$ref !== "string") return null;
  const match = schema.$ref.match(/^#\/components\/schemas\/([^/]+)$/);
  return match ? refName(schema.$ref) : null;
}

/* Follow a chain of `$ref`s. OpenAPI 3.1 allows keys next to `$ref`
 * (`description`, `summary`, or any schema keyword) — they override
 * the target's, the outermost one winning. */
function deref(spec, node) {
  if (!node || typeof node !== "object" || typeof node.$ref !== "string") return node;

  const overrides = [];
  let current = node;
  for (let hops = 0; current && typeof current.$ref === "string"; hops += 1) {
    if (hops >= MAX_REF_HOPS) return { __unresolved: node.$ref };
    const { $ref, ...siblings } = current;
    if (Object.keys(siblings).length) overrides.push(siblings);
    current = resolvePointer(spec, $ref);
    if (current === undefined) return { ...Object.assign({}, ...overrides.reverse()), __unresolved: $ref };
  }
  if (!overrides.length) return current;
  if (typeof current !== "object" || current === null) return current;
  return Object.assign({}, current, ...overrides.reverse());
}

/* ---------- operations ---------- */

function makeOperation(spec, kind, path, method, item, rawOp) {
  const op = deref(spec, rawOp) || {};
  const upper = method.toUpperCase();
  return {
    kind,
    key: `${upper} ${path}`,
    method: upper,
    path,
    op,
    item,
    params: mergeParameters(spec, item.parameters, op.parameters),
    tags: Array.isArray(op.tags) && op.tags.length ? op.tags : ["default"],
    deprecated: Boolean(op.deprecated),
  };
}

function collectOperations(spec) {
  const ops = [];
  for (const [path, rawItem] of Object.entries(spec.paths || {})) {
    const item = deref(spec, rawItem) || {};
    for (const method of HTTP_METHODS) {
      if (item[method]) ops.push(makeOperation(spec, "path", path, method, item, item[method]));
    }
  }
  return ops;
}

/* `webhooks` are requests the API sends — keyed by name, not path. */
function collectWebhooks(spec) {
  const hooks = [];
  for (const [name, rawItem] of Object.entries(spec.webhooks || {})) {
    const item = deref(spec, rawItem) || {};
    for (const method of HTTP_METHODS) {
      if (item[method]) hooks.push(makeOperation(spec, "webhook", name, method, item, item[method]));
    }
  }
  return hooks;
}

/* Path-level parameters apply to every operation of the path; an
 * operation's own parameter with the same `name` + `in` replaces one. */
function mergeParameters(spec, pathLevel, opLevel) {
  const merged = new Map();
  for (const raw of [...(pathLevel || []), ...(opLevel || [])]) {
    const param = deref(spec, raw);
    if (param && param.name && param.in) merged.set(`${param.in}:${param.name}`, param);
  }
  return [...merged.values()];
}

/* Tag groups in the order `tags` declares them, then the order tags
 * are first used in; an operation with several tags is in each. */
function groupOperations(spec, ops) {
  const declared = new Map((spec.tags || []).map((tag) => [tag.name, tag]));
  const groups = new Map();
  for (const name of declared.keys()) groups.set(name, []);
  for (const entry of ops) {
    for (const tag of entry.tags) {
      if (!groups.has(tag)) groups.set(tag, []);
      groups.get(tag).push(entry);
    }
  }
  return [...groups.entries()]
    .filter(([, entries]) => entries.length)
    .map(([name, entries]) => ({ name, tag: declared.get(name) || { name }, ops: entries }));
}

/* `security` on the operation replaces the document-level one; `[]`
 * means public, and a `{}` alternative means "optional". */
function operationSecurity(spec, op) {
  return Array.isArray(op.security) ? op.security : (spec.security || []);
}

function requiresAuth(requirements) {
  return requirements.length > 0 && !requirements.some((alt) => Object.keys(alt).length === 0);
}

function serverUrl(server, values) {
  return String(server.url).replace(/\{([^}]+)\}/g, (match, name) => {
    const variable = (server.variables || {})[name];
    const value = values && values[name] !== undefined ? values[name] : variable?.default;
    return value === undefined ? match : value;
  });
}

/* ---------- schema helpers ---------- */

function schemaTypes(schema) {
  if (!schema || typeof schema !== "object") return [];
  let types;
  if (Array.isArray(schema.type)) types = [...schema.type];
  else if (schema.type) types = [schema.type];
  else if (schema.properties || schema.additionalProperties || schema.patternProperties) types = ["object"];
  else if (schema.items || schema.prefixItems) types = ["array"];
  else types = [];
  // OpenAPI 3.0's `nullable` — still found in documents labelled 3.1.
  if (schema.nullable === true && types.length && !types.includes("null")) types.push("null");
  return types;
}

function isNullable(schema) {
  return schemaTypes(schema).includes("null");
}

/* A short, human type label: `string(uuid)`, `array<Pet>`, `A | B`. */
function typeLabel(spec, schema, depth = 0) {
  if (schema === undefined || schema === null || schema === true) return "any";
  if (schema === false) return "never";
  if (typeof schema.$ref === "string") {
    const target = deref(spec, schema);
    const name = refName(schema.$ref);
    return target && !target.__unresolved && isNullable(target) ? `${name} | null` : name;
  }
  if (depth > 4) return "…";
  if (schema.const !== undefined) return `const ${JSON.stringify(schema.const)}`;

  for (const [keyword, joiner] of [["oneOf", " | "], ["anyOf", " | "], ["allOf", " & "]]) {
    if (Array.isArray(schema[keyword]) && !schemaTypes(schema).length) {
      return schema[keyword].map((sub) => typeLabel(spec, sub, depth + 1)).join(joiner);
    }
  }

  const types = schemaTypes(schema);
  const labels = types.filter((type) => type !== "null").map((type) => {
    if (type === "array") {
      if (Array.isArray(schema.prefixItems)) {
        return `[${schema.prefixItems.map((sub) => typeLabel(spec, sub, depth + 1)).join(", ")}]`;
      }
      return `array<${typeLabel(spec, schema.items, depth + 1)}>`;
    }
    if (type === "object" && !schema.properties && schema.additionalProperties && typeof schema.additionalProperties === "object") {
      return `map<string, ${typeLabel(spec, schema.additionalProperties, depth + 1)}>`;
    }
    const format = schema.format || (schema.contentMediaType ? schema.contentMediaType : null);
    return format && (type === "string" || type === "integer" || type === "number") ? `${type}(${format})` : type;
  });
  if (!labels.length) labels.push(Array.isArray(schema.enum) ? "enum" : "any");
  if (types.includes("null")) labels.push("null");
  return labels.join(" | ");
}

/* ---------- examples ---------- */

const FORMAT_EXAMPLES = {
  "date-time": "2026-01-01T12:00:00Z",
  date: "2026-01-01",
  time: "12:00:00Z",
  duration: "P1D",
  email: "user@example.com",
  "idn-email": "user@example.com",
  uuid: "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  uri: "https://example.com",
  url: "https://example.com",
  "uri-reference": "/path",
  iri: "https://example.com",
  hostname: "example.com",
  ipv4: "192.0.2.1",
  ipv6: "2001:db8::1",
  byte: "U3dhZ2dlcg==",
  binary: "",
  password: "********",
  regex: "^.*$",
};

/* An example value for `schema`: its own `const` / `examples` /
 * `example` / `default` / first `enum` if present, otherwise built from
 * the type. `mode` is `request` or `response` — read-only properties
 * are left out of a request, write-only ones out of a response. */
function exampleFromSchema(spec, schema, mode = "request", depth = 0, seen = new Set()) {
  if (schema === undefined || schema === null || schema === true) return null;
  if (schema === false || depth > 10) return undefined;

  let visited = seen;
  if (typeof schema.$ref === "string") {
    if (seen.has(schema.$ref)) return undefined;
    visited = new Set(seen).add(schema.$ref);
  }
  const s = deref(spec, schema);
  if (!s || s.__unresolved) return null;

  if (s.const !== undefined) return s.const;
  if (Array.isArray(s.examples) && s.examples.length) return s.examples[0];
  if (s.example !== undefined) return s.example;
  if (s.default !== undefined) return s.default;
  if (Array.isArray(s.enum) && s.enum.length) return s.enum.find((value) => value !== null) ?? s.enum[0];

  if (Array.isArray(s.allOf) && s.allOf.length) {
    let merged;
    for (const sub of s.allOf) {
      const value = exampleFromSchema(spec, sub, mode, depth + 1, visited);
      if (value && typeof value === "object" && !Array.isArray(value)) merged = { ...(merged || {}), ...value };
      else if (merged === undefined && value !== undefined) merged = value;
    }
    const own = s.properties ? objectExample(spec, s, mode, depth, visited) : undefined;
    return own && merged && typeof merged === "object" ? { ...merged, ...own } : (merged ?? own ?? null);
  }

  const variants = s.oneOf || s.anyOf;
  if (Array.isArray(variants) && variants.length) {
    const nonNull = variants.find((sub) => !schemaTypes(deref(spec, sub)).every((type) => type === "null")) || variants[0];
    const value = exampleFromSchema(spec, nonNull, mode, depth + 1, visited);
    if (s.properties && value && typeof value === "object") return { ...value, ...objectExample(spec, s, mode, depth, visited) };
    return value;
  }

  const type = schemaTypes(s).find((t) => t !== "null");
  switch (type) {
    case "object":
      return objectExample(spec, s, mode, depth, visited);
    case "array": {
      if (Array.isArray(s.prefixItems)) {
        return s.prefixItems.map((sub) => exampleFromSchema(spec, sub, mode, depth + 1, visited));
      }
      const item = exampleFromSchema(spec, s.items, mode, depth + 1, visited);
      return item === undefined ? [] : [item];
    }
    case "string": {
      if (s.format && FORMAT_EXAMPLES[s.format] !== undefined) return FORMAT_EXAMPLES[s.format];
      const base = "string";
      const min = s.minLength || 0;
      const text = base.length >= min ? base : base.padEnd(min, "x");
      return s.maxLength !== undefined ? text.slice(0, Math.max(s.maxLength, 0)) : text;
    }
    case "integer":
    case "number": {
      let value = 0;
      if (typeof s.minimum === "number") value = s.minimum;
      else if (typeof s.exclusiveMinimum === "number") value = s.exclusiveMinimum + (type === "integer" ? 1 : 0.5);
      if (typeof s.maximum === "number" && value > s.maximum) value = s.maximum;
      if (typeof s.multipleOf === "number" && s.multipleOf > 0) value = Math.ceil(value / s.multipleOf) * s.multipleOf;
      return type === "integer" ? Math.round(value) : value;
    }
    case "boolean":
      return true;
    case "null":
      return null;
    default:
      return s.properties ? objectExample(spec, s, mode, depth, visited) : null;
  }
}

function objectExample(spec, s, mode, depth, seen) {
  const result = {};
  for (const [name, prop] of Object.entries(s.properties || {})) {
    if (!isPropertyVisible(spec, prop, mode)) continue;
    const value = exampleFromSchema(spec, prop, mode, depth + 1, seen);
    if (value !== undefined) result[name] = value;
  }
  const extra = s.additionalProperties;
  if (!s.properties && extra && typeof extra === "object") {
    const value = exampleFromSchema(spec, extra, mode, depth + 1, seen);
    if (value !== undefined) result.key = value;
  }
  return result;
}

function isPropertyVisible(spec, prop, mode) {
  const resolved = deref(spec, prop);
  if (!resolved || typeof resolved !== "object") return true;
  if (mode === "request" && resolved.readOnly) return false;
  if (mode === "response" && resolved.writeOnly) return false;
  return true;
}

/* The examples of a Media Type / Parameter / Header object, in
 * priority order: named `examples`, a single `example`, then one
 * generated from `schema`. */
function objectExamples(spec, owner, mode) {
  if (!owner) return [];
  if (owner.examples && typeof owner.examples === "object" && !Array.isArray(owner.examples)) {
    const list = Object.entries(owner.examples).map(([name, raw]) => {
      const ex = deref(spec, raw) || {};
      const value = ex.value !== undefined ? ex.value : (ex.externalValue ? `<${ex.externalValue}>` : undefined);
      return { name, summary: ex.summary, description: ex.description, value };
    }).filter((ex) => ex.value !== undefined);
    if (list.length) return list;
  }
  if (owner.example !== undefined) return [{ name: "example", value: owner.example }];
  if (owner.schema !== undefined) {
    return [{ name: "generated", value: exampleFromSchema(spec, owner.schema, mode), generated: true }];
  }
  return [];
}

/* ---------- validation ---------- */

const FORMAT_CHECKS = {
  email: (v) => /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(v),
  uuid: (v) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(v),
  "date-time": (v) => /^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:?\d{2})?$/.test(v) && !Number.isNaN(Date.parse(v)),
  date: (v) => /^\d{4}-\d{2}-\d{2}$/.test(v) && !Number.isNaN(Date.parse(v)),
  time: (v) => /^\d{2}:\d{2}(:\d{2}(\.\d+)?)?([Zz]|[+-]\d{2}:?\d{2})?$/.test(v),
  uri: (v) => { try { new URL(v); return true; } catch { return false; } },
  ipv4: (v) => /^(25[0-5]|2[0-4]\d|1?\d?\d)(\.(25[0-5]|2[0-4]\d|1?\d?\d)){3}$/.test(v),
  int32: (v) => Number.isInteger(v) && v >= -(2 ** 31) && v < 2 ** 31,
  int64: (v) => Number.isInteger(v),
};

const TYPE_NAMES = {
  string: "a string", integer: "an integer", number: "a number", boolean: "true/false",
  array: "an array", object: "an object", null: "null",
};

function matchesType(type, value) {
  switch (type) {
    case "null": return value === null;
    case "boolean": return typeof value === "boolean";
    case "integer": return typeof value === "number" && Number.isInteger(value);
    case "number": return typeof value === "number" && Number.isFinite(value);
    case "string": return typeof value === "string";
    case "array": return Array.isArray(value);
    case "object": return value !== null && typeof value === "object" && !Array.isArray(value);
    default: return true;
  }
}

/* Every way `value` breaks `schema`, as readable messages prefixed with
 * the JSON path of the offending part. An empty list means valid. */
function validateSchema(spec, schema, value, mode = "request", path = "", depth = 0) {
  const errors = [];
  if (schema === undefined || schema === null || schema === true || depth > 24) return errors;
  const at = path || "value";
  if (schema === false) return [`${at}: no value is allowed by the schema`];

  const s = deref(spec, schema);
  if (!s || typeof s !== "object" || s.__unresolved) return errors;

  const types = schemaTypes(s);
  if (types.length && !types.some((type) => matchesType(type, value))) {
    return [`${at}: expected ${types.map((type) => TYPE_NAMES[type] || type).join(" or ")}`];
  }
  if (s.const !== undefined && !deepEqual(s.const, value)) {
    errors.push(`${at}: must be ${JSON.stringify(s.const)}`);
  }
  if (Array.isArray(s.enum) && !s.enum.some((option) => deepEqual(option, value))) {
    errors.push(`${at}: must be one of ${s.enum.map((option) => JSON.stringify(option)).join(", ")}`);
  }

  if (typeof value === "string") validateString(s, value, at, errors);
  if (typeof value === "number") validateNumber(s, value, at, errors);
  if (Array.isArray(value)) validateArray(spec, s, value, mode, path, depth, errors);
  else if (value !== null && typeof value === "object") validateObject(spec, s, value, mode, path, depth, errors);

  for (const sub of s.allOf || []) errors.push(...validateSchema(spec, sub, value, mode, path, depth + 1));
  if (Array.isArray(s.anyOf) && !s.anyOf.some((sub) => !validateSchema(spec, sub, value, mode, path, depth + 1).length)) {
    errors.push(`${at}: matches none of the anyOf variants`);
  }
  if (Array.isArray(s.oneOf)) {
    const matching = s.oneOf.filter((sub) => !validateSchema(spec, sub, value, mode, path, depth + 1).length).length;
    if (matching !== 1) {
      errors.push(matching ? `${at}: matches ${matching} oneOf variants, must match exactly one` : `${at}: matches none of the oneOf variants`);
    }
  }
  if (s.not !== undefined && !validateSchema(spec, s.not, value, mode, path, depth + 1).length) {
    errors.push(`${at}: the value is forbidden by the schema (not)`);
  }
  if (s.if !== undefined) {
    const branch = validateSchema(spec, s.if, value, mode, path, depth + 1).length ? s.else : s.then;
    if (branch !== undefined) errors.push(...validateSchema(spec, branch, value, mode, path, depth + 1));
  }
  return errors;
}

function validateString(s, value, at, errors) {
  const length = [...value].length;
  if (typeof s.minLength === "number" && length < s.minLength) errors.push(`${at}: at least ${s.minLength} characters`);
  if (typeof s.maxLength === "number" && length > s.maxLength) errors.push(`${at}: at most ${s.maxLength} characters`);
  if (typeof s.pattern === "string") {
    const regex = compilePattern(s.pattern);
    if (regex && !regex.test(value)) errors.push(`${at}: doesn't match the pattern ${s.pattern}`);
  }
  const check = FORMAT_CHECKS[s.format];
  if (check && typeof value === "string" && !["int32", "int64"].includes(s.format) && !check(value)) {
    errors.push(`${at}: not a valid ${s.format}`);
  }
}

function validateNumber(s, value, at, errors) {
  // 3.1 uses numeric `exclusiveMinimum`; 3.0's boolean form still turns up.
  const exclusiveMin = typeof s.exclusiveMinimum === "number" ? s.exclusiveMinimum : (s.exclusiveMinimum === true ? s.minimum : undefined);
  const exclusiveMax = typeof s.exclusiveMaximum === "number" ? s.exclusiveMaximum : (s.exclusiveMaximum === true ? s.maximum : undefined);
  if (typeof s.minimum === "number" && s.exclusiveMinimum !== true && value < s.minimum) errors.push(`${at}: must be ≥ ${s.minimum}`);
  if (typeof s.maximum === "number" && s.exclusiveMaximum !== true && value > s.maximum) errors.push(`${at}: must be ≤ ${s.maximum}`);
  if (exclusiveMin !== undefined && value <= exclusiveMin) errors.push(`${at}: must be > ${exclusiveMin}`);
  if (exclusiveMax !== undefined && value >= exclusiveMax) errors.push(`${at}: must be < ${exclusiveMax}`);
  if (typeof s.multipleOf === "number" && s.multipleOf > 0) {
    const ratio = value / s.multipleOf;
    if (Math.abs(ratio - Math.round(ratio)) > 1e-9) errors.push(`${at}: must be a multiple of ${s.multipleOf}`);
  }
  if (FORMAT_CHECKS[s.format] && ["int32", "int64"].includes(s.format) && !FORMAT_CHECKS[s.format](value)) {
    errors.push(`${at}: doesn't fit in ${s.format}`);
  }
}

function validateArray(spec, s, value, mode, path, depth, errors) {
  const at = path || "value";
  if (typeof s.minItems === "number" && value.length < s.minItems) errors.push(`${at}: at least ${s.minItems} items`);
  if (typeof s.maxItems === "number" && value.length > s.maxItems) errors.push(`${at}: at most ${s.maxItems} items`);
  if (s.uniqueItems) {
    const seen = new Set(value.map(stableStringify));
    if (seen.size !== value.length) errors.push(`${at}: items must be unique`);
  }
  const prefix = Array.isArray(s.prefixItems) ? s.prefixItems : [];
  value.forEach((item, index) => {
    const itemPath = `${path}[${index}]`;
    if (index < prefix.length) {
      errors.push(...validateSchema(spec, prefix[index], item, mode, itemPath, depth + 1));
    } else if (s.items === false) {
      errors.push(`${itemPath}: unexpected item`);
    } else if (s.items !== undefined) {
      errors.push(...validateSchema(spec, s.items, item, mode, itemPath, depth + 1));
    }
  });
}

function validateObject(spec, s, value, mode, path, depth, errors) {
  const at = path || "value";
  const properties = s.properties || {};
  for (const name of s.required || []) {
    if (value[name] !== undefined) continue;
    // A read-only property is sent by the server, never by the client.
    if (mode === "request" && properties[name] && !isPropertyVisible(spec, properties[name], "request")) continue;
    errors.push(`${joinPath(path, name)}: required field`);
  }
  const keys = Object.keys(value);
  if (typeof s.minProperties === "number" && keys.length < s.minProperties) errors.push(`${at}: at least ${s.minProperties} fields`);
  if (typeof s.maxProperties === "number" && keys.length > s.maxProperties) errors.push(`${at}: at most ${s.maxProperties} fields`);

  const patterns = Object.entries(s.patternProperties || {})
    .map(([pattern, sub]) => [compilePattern(pattern), sub])
    .filter(([regex]) => regex !== null);

  for (const key of keys) {
    const keyPath = joinPath(path, key);
    let matched = false;
    if (Object.prototype.hasOwnProperty.call(properties, key)) {
      matched = true;
      errors.push(...validateSchema(spec, properties[key], value[key], mode, keyPath, depth + 1));
    }
    for (const [regex, sub] of patterns) {
      if (regex.test(key)) {
        matched = true;
        errors.push(...validateSchema(spec, sub, value[key], mode, keyPath, depth + 1));
      }
    }
    if (matched) continue;
    if (s.additionalProperties === false) errors.push(`${keyPath}: unknown field`);
    else if (s.additionalProperties && typeof s.additionalProperties === "object") {
      errors.push(...validateSchema(spec, s.additionalProperties, value[key], mode, keyPath, depth + 1));
    }
  }
}

/* A schema `pattern` as a RegExp — with the `u` flag first (JSON Schema
 * patterns are Unicode), without it if that fails, `null` if it doesn't
 * compile at all.
 *
 * It can't be a literal: the pattern *is* the document's validation
 * rule. It comes from the API's own validators (which the server runs
 * on the same input anyway), and is only ever tested against what the
 * user types into their own tab — the worst a slow pattern can do is
 * slow down that one page. */
function compilePattern(pattern) {
  for (const flags of ["u", ""]) {
    try {
      return new RegExp(pattern, flags); // nosemgrep: javascript.lang.security.audit.detect-non-literal-regexp.detect-non-literal-regexp
    } catch {
      /* not valid with this flag — try the next one */
    }
  }
  return null;
}

function joinPath(path, key) {
  return /^[A-Za-z_$][\w$]*$/.test(key) ? (path ? `${path}.${key}` : key) : `${path}[${JSON.stringify(key)}]`;
}

/* ---------- typed values from text inputs ---------- */

/* What the text of a parameter/form input means under `schema`:
 * `"42"` is `42` for an integer, `"a, b"` is `["a", "b"]` for an array.
 * Text that doesn't fit stays a string, so validation can point at it.
 * Empty text is `undefined` — "not sent". */
function coerceInput(spec, schema, raw) {
  if (raw === undefined || raw === null) return undefined;
  const text = String(raw);
  if (text.trim() === "") return undefined;

  const s = deref(spec, schema) || {};
  const types = schemaTypes(s);
  const want = (type) => types.includes(type);

  if (text.trim() === "null" && want("null")) return null;
  if (want("array")) {
    const trimmed = text.trim();
    if (trimmed.startsWith("[")) {
      try { return JSON.parse(trimmed); } catch { /* fall through to a list */ }
    }
    return trimmed.split(",").map((part) => coerceInput(spec, s.items, part.trim())).filter((item) => item !== undefined);
  }
  if (want("object")) {
    try { return JSON.parse(text); } catch { return text; }
  }
  if ((want("integer") || want("number")) && /^\s*-?\d+(\.\d+)?([eE][+-]?\d+)?\s*$/.test(text)) {
    return Number(text);
  }
  if (want("boolean") && /^(true|false)$/i.test(text.trim())) return text.trim().toLowerCase() === "true";
  if (!types.length && s.enum) {
    const match = s.enum.find((option) => String(option) === text);
    if (match !== undefined) return match;
  }
  return text;
}
