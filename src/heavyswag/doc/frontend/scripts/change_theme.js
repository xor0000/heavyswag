/* change_theme.js — light / dark theme and the `DocUI` branding (name,
 * logo, accent color, favicon). */

const THEME_STORAGE_KEY = "hs_theme";

function initTheme() {
  const saved = loadJson(localStorage, THEME_STORAGE_KEY, null);
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  applyTheme(saved === "light" || saved === "dark" ? saved : (prefersLight ? "light" : "dark"));

  byId("themeToggleBtn").addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    applyTheme(next);
    saveJson(localStorage, THEME_STORAGE_KEY, next);
  });
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  byId("themeToggleBtn").innerHTML = theme === "dark" ? ICONS.sun : ICONS.moon;
}

/* An image reference rather than text: a URL, a path or a data URI. */
function isImageSource(value) {
  return /^(https?:\/\/|data:image\/|\/|\.{1,2}\/)/i.test(value) || /\.(png|svg|jpe?g|gif|webp|ico)(\?.*)?$/i.test(value);
}

function initials(name) {
  const words = String(name).trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] || "API").slice(0, 2);
  return letters.toUpperCase();
}

/* `#rgb` / `#rrggbb` mixed with white — the logo gradient's second
 * stop when `DocUI.accent_soft` isn't set. */
function lighten(hex, amount) {
  let value = hex.replace("#", "");
  if (value.length === 3) value = value.split("").map((c) => c + c).join("");
  const channels = [0, 2, 4].map((i) => parseInt(value.slice(i, i + 2), 16));
  const mixed = channels.map((c) => Math.round(c + (255 - c) * amount));
  return "#" + mixed.map((c) => c.toString(16).padStart(2, "0")).join("");
}

function applyBrand(ui, info) {
  const name = ui.name || info.title || "API";
  const root = document.documentElement.style;
  root.setProperty("--accent", ui.accent);
  root.setProperty("--accent-soft", ui.accent_soft || lighten(ui.accent, 0.45));

  const logo = byId("brandLogo");
  if (ui.logo && isImageSource(ui.logo)) {
    logo.innerHTML = `<img src="${escapeHtml(ui.logo)}" alt="">`;
  } else {
    logo.textContent = ui.logo || initials(name);
  }
  byId("brandName").textContent = name;
  setFavicon(ui.favicon || ui.logo || initials(name), ui.accent);
}

function setFavicon(source, accent) {
  const link = byId("favicon");
  if (isImageSource(source)) {
    link.href = source;
    return;
  }
  const text = escapeHtml(source);
  const size = [...source].length > 2 ? 22 : 34;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="${accent}"/><text x="32" y="43" font-size="${size}" font-family="sans-serif" font-weight="700" fill="#fff" text-anchor="middle">${text}</text></svg>`;
  link.href = "data:image/svg+xml," + encodeURIComponent(svg);
}
