/* send_request.js — "Попробовать": turning what the user typed into an
 * HTTP request (OpenAPI parameter serialization: `style` / `explode`),
 * its curl equivalent, and actually sending it with `fetch`.
 *
 * A draft holds raw input text only — typed values are derived from it
 * by the parameter/property schema at send time (`coerceInput`). */

const RESERVED_CHARS = /%(3A|2F|3F|23|5B|5D|40|21|24|26|27|28|29|2A|2B|2C|3B|3D)/gi;

function paramKey(param) {
  return `${param.in}:${param.name}`;
}

function isJsonMedia(media) {
  return /(^application\/json\b|\+json\b|^\*\/\*$)/i.test(media);
}

function isTextMedia(media) {
  return /^text\/|xml|javascript|yaml|csv/i.test(media);
}

function isFormMedia(media) {
  return /^application\/x-www-form-urlencoded/i.test(media) || /^multipart\//i.test(media);
}

/* A schema whose value is a file rather than text. */
function isBinarySchema(spec, schema) {
  const s = deref(spec, schema);
  if (!s || typeof s !== "object") return false;
  if (schemaTypes(s).includes("array")) return isBinarySchema(spec, s.items);
  return Boolean(s.contentMediaType || s.contentEncoding || s.format === "binary" || s.format === "base64");
}

function requestBodyOf(spec, entry) {
  const body = deref(spec, entry.op.requestBody);
  return body && body.content ? body : null;
}

/* ---------- parameter values ---------- */

/* The typed value of a parameter — `undefined` when left empty. A
 * parameter described by `content` (not `schema`) is sent as the raw
 * text of that media type. */
function paramValue(spec, param, raw) {
  if (raw === undefined || raw === null || String(raw).trim() === "") return undefined;
  if (param.content) return String(raw);
  return coerceInput(spec, param.schema, raw);
}

function encodePart(value, allowReserved) {
  const text = value === null ? "" : (typeof value === "object" ? JSON.stringify(value) : String(value));
  const encoded = encodeURIComponent(text);
  return allowReserved ? encoded.replace(RESERVED_CHARS, decodeURIComponent) : encoded;
}

function valueShape(value) {
  if (Array.isArray(value)) return "array";
  if (value !== null && typeof value === "object") return "object";
  return "primitive";
}

function serializePath(param, value) {
  const style = param.style || "simple";
  const explode = param.explode ?? false;
  const enc = (v) => encodePart(v, false);
  const shape = valueShape(value);
  const entries = shape === "object" ? Object.entries(value) : [];

  if (style === "label") {
    if (shape === "array") return "." + value.map(enc).join(explode ? "." : ",");
    if (shape === "object") return "." + (explode ? entries.map(([k, v]) => `${enc(k)}=${enc(v)}`).join(".") : entries.flat().map(enc).join(","));
    return "." + enc(value);
  }
  if (style === "matrix") {
    const name = enc(param.name);
    if (shape === "array") return explode ? value.map((v) => `;${name}=${enc(v)}`).join("") : `;${name}=${value.map(enc).join(",")}`;
    if (shape === "object") return explode ? entries.map(([k, v]) => `;${enc(k)}=${enc(v)}`).join("") : `;${name}=${entries.flat().map(enc).join(",")}`;
    return `;${name}=${enc(value)}`;
  }
  if (shape === "array") return value.map(enc).join(",");
  if (shape === "object") return explode ? entries.map(([k, v]) => `${enc(k)}=${enc(v)}`).join(",") : entries.flat().map(enc).join(",");
  return enc(value);
}

/* Query parameters as ready `name=value` pairs. */
function serializeQuery(param, value) {
  const style = param.style || "form";
  const explode = param.explode ?? style === "form";
  const enc = (v) => encodePart(v, Boolean(param.allowReserved));
  const name = enc(param.name);
  const shape = valueShape(value);

  if (style === "deepObject" && shape === "object") {
    return Object.entries(value).map(([k, v]) => `${name}%5B${enc(k)}%5D=${enc(v)}`);
  }
  if (shape === "array") {
    if (style === "spaceDelimited") return [`${name}=${value.map(enc).join("%20")}`];
    if (style === "pipeDelimited") return [`${name}=${value.map(enc).join("%7C")}`];
    return explode ? value.map((v) => `${name}=${enc(v)}`) : [`${name}=${value.map(enc).join(",")}`];
  }
  if (shape === "object") {
    const entries = Object.entries(value);
    if (explode) return entries.map(([k, v]) => `${enc(k)}=${enc(v)}`);
    const joiner = style === "spaceDelimited" ? "%20" : style === "pipeDelimited" ? "%7C" : ",";
    return [`${name}=${entries.flat().map(enc).join(joiner)}`];
  }
  if (value === "" && param.allowEmptyValue) return [name];
  return [`${name}=${enc(value)}`];
}

function plainText(value) {
  if (value === null) return "";
  return typeof value === "object" ? JSON.stringify(value) : String(value);
}

function serializeHeader(param, value) {
  const shape = valueShape(value);
  if (shape === "array") return value.map(plainText).join(",");
  if (shape === "object") {
    const entries = Object.entries(value);
    return param.explode ? entries.map(([k, v]) => `${k}=${plainText(v)}`).join(",") : entries.flat().map(plainText).join(",");
  }
  return plainText(value);
}

/* Cookie values as `[name, value]` pairs — `explode` turns an array
 * into one cookie per item. */
function serializeCookie(param, value) {
  const shape = valueShape(value);
  if (shape === "array") {
    return param.explode ? value.map((v) => [param.name, plainText(v)]) : [[param.name, value.map(plainText).join(",")]];
  }
  if (shape === "object") return [[param.name, Object.entries(value).flat().map(plainText).join(",")]];
  return [[param.name, plainText(value)]];
}

/* ---------- the request ---------- */

/* An absolute URL the browser can actually reach — a relative server
 * (`/`, `/api`) only works when the page itself is served over HTTP. */
function absoluteUrl(url) {
  if (/^[a-z][a-z0-9+.-]*:\/\//i.test(url)) return url;
  if (location.protocol === "http:" || location.protocol === "https:") return new URL(url, location.href).href;
  return null;
}

function hasHeader(headers, name) {
  const lower = name.toLowerCase();
  return headers.some(([key]) => key.toLowerCase() === lower);
}

/* Everything `executeRequest` and `buildCurl` need. Header sources are
 * kept (`auth`, `param`, `global`, `auto`) for the preview; earlier
 * sources win over later ones with the same name. */
function buildRequest(ctx) {
  const { spec, entry, draft } = ctx;
  const req = { method: entry.method, url: "", headers: [], cookies: [], body: { kind: "none" } };
  const query = [];
  let path = entry.path;

  const auth = resolveAuth(spec, operationSecurity(spec, entry.op));
  auth.headers.forEach(([k, v]) => req.headers.push([k, v, "auth"]));
  auth.query.forEach(([k, v]) => query.push(`${encodePart(k)}=${encodePart(v)}`));
  auth.cookies.forEach(([k, v]) => req.cookies.push([k, v, "auth"]));
  req.auth = auth;

  for (const param of entry.params) {
    const value = paramValue(spec, param, draft.params[paramKey(param)]);
    if (value === undefined) continue;
    if (param.in === "path") {
      path = path.split(`{${param.name}}`).join(serializePath(param, value));
    } else if (param.in === "query") {
      query.push(...serializeQuery(param, value));
    } else if (param.in === "header" && !hasHeader(req.headers, param.name)) {
      req.headers.push([param.name, serializeHeader(param, value), "param"]);
    } else if (param.in === "cookie") {
      serializeCookie(param, value).forEach(([k, v]) => req.cookies.push([k, v, "param"]));
    }
  }

  for (const header of state.globals.headers) {
    if (header.enabled && header.key && !hasHeader(req.headers, header.key)) {
      req.headers.push([header.key, header.value, "global"]);
    }
  }
  for (const cookie of state.globals.cookies) {
    if (cookie.enabled && cookie.key && !req.cookies.some(([key]) => key === cookie.key)) {
      req.cookies.push([cookie.key, cookie.value, "global"]);
    }
  }

  req.body = buildBody(ctx);
  const contentType = { json: draft.media, text: draft.media, urlencoded: "application/x-www-form-urlencoded" }[req.body.kind]
    || (req.body.kind === "binary" && !draft.media.includes("*") ? draft.media : null);
  if (contentType && !hasHeader(req.headers, "Content-Type")) req.headers.push(["Content-Type", contentType, "auto"]);
  if (req.body.kind === "multipart") req.headers.push(["Content-Type", "multipart/form-data; boundary=…", "auto"]);

  const base = requestBase(spec, entry).url;
  req.url = base + path + (query.length ? "?" + query.join("&") : "");
  return req;
}

/* The typed value of every form field (a JSON object body shown as a
 * form, urlencoded, multipart) — files from `state.files`. */
function formValues(ctx, schema) {
  const { spec, draft } = ctx;
  const s = deref(spec, schema) || {};
  const values = [];
  for (const [name, prop] of Object.entries(s.properties || {})) {
    if (!isPropertyVisible(spec, prop, "request")) continue;
    if (isBinarySchema(spec, prop)) {
      const files = state.files.get(`${ctx.draftKey}|${name}`) || [];
      files.forEach((file) => values.push([name, file]));
      continue;
    }
    const value = coerceInput(spec, prop, draft.form[name]);
    if (value !== undefined) values.push([name, value]);
  }
  return values;
}

function buildBody(ctx) {
  const { spec, entry, draft } = ctx;
  const requestBody = requestBodyOf(spec, entry);
  if (!requestBody || !draft.media) return { kind: "none" };
  const media = requestBody.content[draft.media] || {};

  if (isJsonMedia(draft.media)) {
    if (draft.bodyMode === "form") {
      const object = Object.fromEntries(formValues(ctx, media.schema));
      return { kind: "json", text: JSON.stringify(object, null, 2) };
    }
    return draft.bodyText.trim() ? { kind: "json", text: draft.bodyText } : { kind: "none" };
  }
  if (/^application\/x-www-form-urlencoded/i.test(draft.media)) {
    const pairs = formValues(ctx, media.schema).flatMap(([name, value]) => (
      Array.isArray(value) ? value.map((item) => [name, plainText(item)]) : [[name, plainText(value)]]
    ));
    return pairs.length ? { kind: "urlencoded", text: new URLSearchParams(pairs).toString() } : { kind: "none" };
  }
  if (/^multipart\//i.test(draft.media)) {
    const parts = formValues(ctx, media.schema).flatMap(([name, value]) => (
      Array.isArray(value) ? value.map((item) => [name, plainText(item)]) : [[name, value instanceof File ? value : plainText(value)]]
    ));
    return parts.length ? { kind: "multipart", parts } : { kind: "none" };
  }
  if (isTextMedia(draft.media)) {
    return draft.bodyText ? { kind: "text", text: draft.bodyText } : { kind: "none" };
  }
  const [file] = state.files.get(`${ctx.draftKey}|__body__`) || [];
  return file ? { kind: "binary", file } : { kind: "none" };
}

function fetchBody(body) {
  if (body.kind === "json" || body.kind === "text" || body.kind === "urlencoded") return body.text;
  if (body.kind === "binary") return body.file;
  if (body.kind === "multipart") {
    const form = new FormData();
    body.parts.forEach(([name, value]) => form.append(name, value));
    return form;
  }
  return undefined;
}

/* ---------- curl ---------- */

function buildCurl(req) {
  const parts = [`curl -X ${req.method} ${shellQuote(req.url || "<адрес сервера>")}`];
  for (const [key, value] of req.headers) {
    if (req.body.kind === "multipart" && key === "Content-Type") continue;
    parts.push(`-H ${shellQuote(`${key}: ${value}`)}`);
  }
  if (req.cookies.length) parts.push(`-b ${shellQuote(req.cookies.map(([k, v]) => `${k}=${v}`).join("; "))}`);

  const body = req.body;
  if (body.kind === "json" || body.kind === "text" || body.kind === "urlencoded") {
    parts.push(`--data-raw ${shellQuote(body.kind === "json" ? compactJson(body.text) : body.text)}`);
  } else if (body.kind === "multipart") {
    for (const [name, value] of body.parts) {
      parts.push(value instanceof File ? `-F ${shellQuote(`${name}=@${value.name}`)}` : `--form-string ${shellQuote(`${name}=${value}`)}`);
    }
  } else if (body.kind === "binary") {
    parts.push(`--data-binary ${shellQuote(`@${body.file.name}`)}`);
  }
  return parts.join(" \\\n  ");
}

function compactJson(text) {
  try {
    return JSON.stringify(JSON.parse(text));
  } catch {
    return text;
  }
}

/* ---------- sending ---------- */

/* The documented response for a status: the exact code, then its
 * `NXX` range, then `default`. */
function documentedResponse(spec, op, status) {
  const responses = op.responses || {};
  const code = String(status);
  const range = `${code[0]}XX`;
  const key = [code, range, range.toLowerCase(), "default"].find((candidate) => responses[candidate] !== undefined);
  return key ? { key, response: deref(spec, responses[key]) || {} } : null;
}

async function executeRequest(ctx, panel) {
  const req = buildRequest(ctx);
  const url = absoluteUrl(req.url);
  if (!url) {
    panel.innerHTML = `<div class="rp-error">Адрес <code>${escapeHtml(req.url || "/")}</code> относительный, а страница открыта как файл — выберите сервер с абсолютным URL или укажите свой адрес.</div>`;
    return;
  }

  const headers = new Headers();
  const skipped = [];
  for (const [key, value] of req.headers) {
    if (req.body.kind === "multipart" && key === "Content-Type") continue;
    try {
      headers.append(key, value);
    } catch {
      skipped.push(key);
    }
  }

  if (state.inflight) state.inflight.abort();
  const controller = new AbortController();
  state.inflight = controller;
  panel.innerHTML = `<div class="rp-head"><span>Отправка ${escapeHtml(req.method)} ${escapeHtml(url)}…</span><button class="pill-btn rp-meta" id="cancelRequestBtn">Отменить</button></div>`;
  byId("cancelRequestBtn").addEventListener("click", () => controller.abort());

  const started = performance.now();
  let response;
  let blob;
  try {
    response = await fetch(url, { method: req.method, headers, body: fetchBody(req.body), signal: controller.signal, redirect: "follow" });
    blob = await response.blob();
  } catch (error) {
    if (state.inflight === controller) state.inflight = null;
    panel.innerHTML = error.name === "AbortError"
      ? '<div class="rp-placeholder">Запрос отменён</div>'
      : `<div class="rp-error"><b>Запрос не дошёл до ответа.</b><br>${escapeHtml(error.message)}<br><br>Обычно это CORS (сервер не разрешил запросы с этой страницы), недоступный сервер или смешанный контент (страница по https, API по http). Проверьте запрос через curl ниже.</div>`;
    return;
  }
  if (state.inflight === controller) state.inflight = null;

  const elapsed = Math.round(performance.now() - started);
  panel.innerHTML = await responseHtml(ctx, req, response, blob, elapsed, skipped);
  const download = panel.querySelector("[data-download]");
  if (download) download.addEventListener("click", () => downloadBlob(blob, "response"));
}

async function responseHtml(ctx, req, response, blob, elapsed, skipped) {
  const contentType = response.headers.get("content-type") || "";
  const documented = documentedResponse(ctx.spec, ctx.entry.op, response.status);
  const notes = [];
  if (!documented) notes.push(`Статус ${response.status} не описан в спецификации`);
  if (skipped.length) notes.push(`Браузер не принял заголовки: ${skipped.join(", ")}`);
  if (req.cookies.length) notes.push("Куки не отправлены — браузер не даёт странице задать Cookie (они есть в curl)");

  let bodyHtml;
  if (!blob.size) {
    bodyHtml = '<div class="rp-placeholder">Пустое тело ответа</div>';
  } else if (isJsonMedia(contentType) || /json/i.test(contentType)) {
    const text = await blob.text();
    let shown = text;
    try {
      const parsed = JSON.parse(text);
      shown = prettyJson(parsed);
      notes.push(...responseSchemaNotes(ctx, documented, contentType, parsed));
    } catch {
      notes.push("Тело помечено как JSON, но не разбирается");
    }
    bodyHtml = `<pre>${escapeHtml(shown)}</pre>`;
  } else if (!contentType || isTextMedia(contentType)) {
    bodyHtml = `<pre>${escapeHtml(await blob.text())}</pre>`;
  } else if (/^image\//i.test(contentType)) {
    bodyHtml = `<div class="rp-placeholder"><img src="${URL.createObjectURL(blob)}" alt="" style="max-width:100%"><br><button class="link-btn" data-download>Скачать</button></div>`;
  } else {
    bodyHtml = `<div class="rp-placeholder">Бинарные данные (${escapeHtml(contentType)}, ${formatBytes(blob.size)}) — <button class="link-btn" data-download>скачать</button></div>`;
  }

  const headerRows = [...response.headers.entries()]
    .map(([key, value]) => `<div class="row"><b>${escapeHtml(key)}:</b> ${escapeHtml(value)}</div>`).join("");

  return `
    <div class="rp-head">
      <span class="status-chip ${statusClass(response.status)}">${response.status}</span>
      <span>${escapeHtml(response.statusText || (documented ? (documented.response.description || "").split("\n")[0] : ""))}</span>
      <span class="rp-meta">${elapsed} ms · ${formatBytes(blob.size)}</span>
    </div>
    ${notes.length ? `<div class="callout warn" style="margin:0;border-radius:0;border-width:1px 0 0;">${ICONS.warn}<div>${notes.map(escapeHtml).join("<br>")}</div></div>` : ""}
    ${bodyHtml}
    <details><summary>Заголовки ответа</summary><div class="headers-preview" style="margin:0 14px 12px;">${headerRows || "Браузер показывает только заголовки, разрешённые через Access-Control-Expose-Headers"}</div></details>`;
}

/* A JSON response checked against the schema the spec documents for
 * it — a mismatch is a bug in the API or in its docs, worth showing. */
function responseSchemaNotes(ctx, documented, contentType, value) {
  if (!documented || !documented.response.content) return [];
  const content = documented.response.content;
  const mediaKey = Object.keys(content).find((key) => contentType.toLowerCase().startsWith(key.toLowerCase()))
    || Object.keys(content).find((key) => isJsonMedia(key));
  const schema = mediaKey && content[mediaKey].schema;
  if (schema === undefined) return [];
  const errors = validateSchema(ctx.spec, schema, value, "response");
  if (!errors.length) return [];
  return [`Ответ не соответствует документированной схеме (${documented.key}):`, ...errors.slice(0, 8).map((error) => `• ${error}`)];
}
