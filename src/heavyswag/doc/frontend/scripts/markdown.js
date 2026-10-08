/* markdown.js — the CommonMark subset OpenAPI `description` fields use
 * in practice: paragraphs, headings, lists, quotes, fenced code, inline
 * code, emphasis and links.
 *
 * Everything is HTML-escaped before any markup is added, so raw HTML in
 * a description is shown as text, never executed; link targets are
 * limited to http(s), mailto, fragments and relative URLs. */

const MD_BLOCK_START = /^\s*(```|#{1,6}\s|>|[-*+]\s|\d+[.)]\s|(-{3,}|\*{3,}|_{3,})\s*$)/;

function renderMarkdown(source) {
  if (source === undefined || source === null || source === "") return "";
  const lines = String(source).replace(/\r\n?/g, "\n").split("\n");
  return renderMarkdownBlocks(lines);
}

function renderMarkdownBlocks(lines) {
  const out = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (/^\s*$/.test(line)) {
      i += 1;
      continue;
    }

    const fence = line.match(/^\s*```\s*([\w+-]*)/);
    if (fence) {
      const code = [];
      i += 1;
      while (i < lines.length && !/^\s*```\s*$/.test(lines[i])) {
        code.push(lines[i]);
        i += 1;
      }
      i += 1;
      out.push(`<pre><code>${escapeHtml(code.join("\n"))}</code></pre>`);
      continue;
    }

    const heading = line.match(/^\s*(#{1,6})\s+(.*?)\s*#*\s*$/);
    if (heading) {
      // Page headings are h1/h2 — description headings start below.
      const level = Math.min(heading[1].length + 2, 6);
      out.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      i += 1;
      continue;
    }

    if (/^\s*(-{3,}|\*{3,}|_{3,})\s*$/.test(line)) {
      out.push("<hr>");
      i += 1;
      continue;
    }

    if (/^\s*>/.test(line)) {
      const quoted = [];
      while (i < lines.length && /^\s*>/.test(lines[i])) {
        quoted.push(lines[i].replace(/^\s*>\s?/, ""));
        i += 1;
      }
      out.push(`<blockquote>${renderMarkdownBlocks(quoted)}</blockquote>`);
      continue;
    }

    const listMatch = line.match(/^(\s*)([-*+]|\d+[.)])\s+/);
    if (listMatch) {
      const ordered = /\d/.test(listMatch[2]);
      const items = [];
      while (i < lines.length) {
        const itemMatch = lines[i].match(/^(\s*)([-*+]|\d+[.)])\s+(.*)$/);
        if (itemMatch && /\d/.test(itemMatch[2]) === ordered) {
          items.push(itemMatch[3]);
          i += 1;
        } else if (items.length && /^\s{2,}\S/.test(lines[i])) {
          items[items.length - 1] += " " + lines[i].trim();
          i += 1;
        } else {
          break;
        }
      }
      const tag = ordered ? "ol" : "ul";
      out.push(`<${tag}>${items.map((item) => `<li>${renderInline(item)}</li>`).join("")}</${tag}>`);
      continue;
    }

    const paragraph = [line.trim()];
    i += 1;
    while (i < lines.length && !/^\s*$/.test(lines[i]) && !MD_BLOCK_START.test(lines[i])) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    out.push(`<p>${renderInline(paragraph.join("\n")).replace(/ {2,}\n/g, "<br>").replace(/\n/g, " ")}</p>`);
  }

  return out.join("");
}

function renderInline(text) {
  // Code spans first: nothing inside backticks is formatted.
  return String(text).split(/(`+[^`]*?`+)/).map((part, index) => {
    if (index % 2 === 1) {
      return `<code>${escapeHtml(part.replace(/^`+|`+$/g, ""))}</code>`;
    }
    return renderEmphasis(escapeHtml(part));
  }).join("");
}

function renderEmphasis(escaped) {
  return escaped
    .replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+&quot;[^&]*&quot;)?\)/g, (_, label, url) => (
      `<a href="${safeUrl(url)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    ))
    .replace(/&lt;(https?:\/\/[^\s&]+)&gt;/g, (_, url) => (
      `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
    ))
    .replace(/\*\*([^*]+)\*\*|__([^_]+)__/g, (_, a, b) => `<strong>${a ?? b}</strong>`)
    .replace(/(^|[^\w*])\*([^*\s][^*]*?)\*(?!\w)/g, "$1<em>$2</em>")
    .replace(/(^|[^\w_])_([^_\s][^_]*?)_(?!\w)/g, "$1<em>$2</em>")
    .replace(/~~([^~]+)~~/g, "<del>$1</del>");
}

/* `url` arrives HTML-escaped already (it came out of `escapeHtml`), so
 * it can't break out of the attribute — this only stops `javascript:`
 * and other schemes from becoming clickable. */
function safeUrl(url) {
  const trimmed = url.trim();
  if (/^(https?:|mailto:|#|\/|\.)/i.test(trimmed)) return trimmed;
  if (!/^[a-z][a-z0-9+.-]*:/i.test(trimmed)) return trimmed;
  return "#";
}
