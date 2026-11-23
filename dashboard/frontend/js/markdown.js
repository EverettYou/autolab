// Markdown rendering: marked (GFM) with math, Obsidian wikilinks and MyST roles and directives,
// sanitized by DOMPurify, then math typeset by KaTeX. Repository links are resolved by the server:
// every payload with Markdown carries a link map ({hrefs, wikilinks, code, roles, paths}) keyed by
// the link text as written, and the renderer only looks the keys up.

import { highlightRoot } from "./highlight.js";
import { showLocalTimes } from "./ui.js";

const { marked, DOMPurify, katex } = window;

const PY_ROLES = new Set(["class", "func", "meth", "mod", "attr", "obj", "data", "exc", "const", "type"]);
const CODE_DIRECTIVES = new Set(["code-cell", "code-block", "code", "sourcecode", "literalinclude", "eval-rst",
  "mermaid", "list-table", "csv-table", "autodoc", "automodule", "autoclass", "autofunction", "raw"]);
const HIDDEN_DIRECTIVES = new Set(["toctree", "contents", "tableofcontents", "include"]);
const ALERTS = { NOTE: "note", TIP: "tip", IMPORTANT: "important", WARNING: "warning", CAUTION: "caution" };

let ctx = { links: {} };

function context(links) {
  const paths = links && links.paths;
  return { links: links || {}, paths: paths && Object.keys(paths).length ? paths : null };
}

export function slugify(text) {
  let value = String(text || "")
    .replace(/\[\[([^\]|]+)\|([^\]]+)\]\]/g, "$2")
    .replace(/\[\[([^\]]+)\]\]/g, "$1")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/(\*\*|__|\*|_|`)/g, "")
    .trim()
    .toLowerCase();
  value = value.replace(/[^\p{L}\p{N}_\- ]/gu, "");
  return value.trim().replace(/ /g, "-");
}

export function escapeHtml(text) {
  return String(text ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

function roleLabel(body) {
  const explicit = /^(.*?)\s*<([^<>]+)>$/.exec(body.trim());
  if (explicit && explicit[1]) return explicit[1].trim();
  const target = body.trim();
  if (target.startsWith("~")) {
    const bare = target.slice(1);
    const call = bare.endsWith("()");
    return bare.replace(/\(\)$/, "").split(".").pop() + (call ? "()" : "");
  }
  return target;
}

function wikiLabel(key) {
  const [target, heading] = key.split("#");
  const name = target.replace(/\.md$/, "").split("/").pop() || target;
  return heading ? `${name} \u203a ${heading}` : name;
}

function mathHtml(text, display) {
  return `<span class="math ${display ? "math-display" : "math-inline"}">${escapeHtml(text)}</span>`;
}

function codeBlock(text, language, extra) {
  const lang = (language || "").trim();
  const body = escapeHtml(String(text).replace(/\n+$/, ""));
  if (lang === "mermaid") return `<div class="diagram">${body.trim()}</div>\n`;
  const cls = lang ? ` class="language-${escapeHtml(lang)}"` : "";
  const label = lang ? ` data-lang="${escapeHtml(lang)}"` : "";
  return `<pre class="code${extra ? ` ${extra}` : ""}"${label}><code${cls}>${body}</code></pre>\n`;
}

const mathBlock = {
  name: "mathBlock",
  level: "block",
  start(src) {
    const match = /(?:^|\n) {0,3}(?:\$\$|\\\[)/.exec(src);
    return match ? match.index + (match[0].startsWith("\n") ? 1 : 0) : undefined;
  },
  tokenizer(src) {
    const match = /^ {0,3}\$\$([\s\S]+?)\$\$[ \t]*(?:\n+|$)/.exec(src)
      || /^ {0,3}\\\[([\s\S]+?)\\\][ \t]*(?:\n+|$)/.exec(src);
    if (match) return { type: "mathBlock", raw: match[0], text: match[1].trim() };
    return undefined;
  },
  renderer(token) {
    return `<div class="math-block">${mathHtml(token.text, true)}</div>\n`;
  },
};

const mathInline = {
  name: "mathInline",
  level: "inline",
  start(src) {
    const match = /\$|\\\(/.exec(src);
    return match ? match.index : undefined;
  },
  tokenizer(src) {
    let match = /^\$\$(?!\$)([^$]+?)\$\$/.exec(src);
    if (match) return { type: "mathInline", raw: match[0], text: match[1].trim(), display: true };
    match = /^\\\(([\s\S]+?)\\\)/.exec(src);
    if (match) return { type: "mathInline", raw: match[0], text: match[1], display: false };
    match = /^\$(?=[^\s$])((?:\\.|[^\\$`\n]|\n(?![ \t]*\n))+?)(?<=[^\s\\])\$(?!\d)/.exec(src);
    if (match) return { type: "mathInline", raw: match[0], text: match[1], display: false };
    return undefined;
  },
  renderer(token) {
    return mathHtml(token.text, token.display);
  },
};

const wikilink = {
  name: "wikilink",
  level: "inline",
  start(src) {
    const index = src.indexOf("[[");
    return index < 0 ? undefined : index;
  },
  tokenizer(src) {
    const match = /^\[\[([^[\]\n]+?)\]\]/.exec(src);
    if (!match) return undefined;
    const [target, ...rest] = match[1].split("|");
    const key = target.trim();
    const info = (ctx.links.wikilinks || {})[key];
    if (!info) return undefined;
    return { type: "wikilink", raw: match[0], href: info.route, exists: info.exists !== false,
      label: rest.join("|").trim() || wikiLabel(key) };
  },
  renderer(token) {
    return `<a class="wikilink${token.exists ? "" : " missing"}" data-r="1" href="${escapeHtml(token.href)}">${escapeHtml(token.label)}</a>`;
  },
};

const role = {
  name: "role",
  level: "inline",
  start(src) {
    const match = /\{(?:py:)?[a-z][\w-]*\}`/.exec(src);
    return match ? match.index : undefined;
  },
  tokenizer(src) {
    const match = /^\{((?:py:)?[a-z][\w-]*)\}`([^`\n]+)`/.exec(src);
    if (!match) return undefined;
    return { type: "role", raw: match[0], role: match[1], body: match[2] };
  },
  renderer(token) {
    const name = token.role.replace(/^py:/, "");
    if (name === "math") return mathHtml(token.body, false);
    const info = (ctx.links.roles || {})[`${token.role}|${token.body}`];
    const label = escapeHtml(info && info.label ? info.label : roleLabel(token.body));
    const inner = PY_ROLES.has(name) || token.role.startsWith("py:") ? `<code>${label}</code>` : label;
    if (info && info.route) {
      return `<a class="xref${info.exists === false ? " missing" : ""}" data-r="1" href="${escapeHtml(info.route)}">${inner}</a>`;
    }
    return inner;
  },
};

// A repository-root path written as prose (labs/<id>/report.md). Keep the pattern in sync with
// BARE_PATH in dashboard/backend/links.py; the server lists the paths that exist in links.paths. Matching
// while tokenizing keeps names like __init__.py from turning into emphasis.
const PATH_AREAS = "(?:labs|references|wiki|lib|skills|dashboard|lab|notes|archive|inbox|sandbox|projects)";
const BARE_PATH_START = new RegExp(`(^|[^A-Za-z0-9_./@-])${PATH_AREAS}/`);
const BARE_PATH_AT = new RegExp(`^${PATH_AREAS}/[A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)*/?(?:#[A-Za-z0-9_-]+)?`);

const barePath = {
  name: "barePath",
  level: "inline",
  start(src) {
    if (!ctx.paths) return undefined;
    const match = BARE_PATH_START.exec(src);
    return match ? match.index + match[1].length : undefined;
  },
  tokenizer(src, tokens) {
    if (!ctx.paths || this.lexer.state.inLink) return undefined;
    const match = BARE_PATH_AT.exec(src);
    if (!match) return undefined;
    const previous = tokens.length ? tokens[tokens.length - 1].raw.slice(-1) : "";
    if (previous && /[A-Za-z0-9_./@-]/.test(previous)) return undefined;
    const key = match[0].replace(/\.+$/, "");
    const info = ctx.paths[key];
    if (!info || !info.route) return undefined;
    return { type: "barePath", raw: key, info };
  },
  renderer(token) {
    const title = token.info.legacy ? ` title="${escapeHtml(`Moved from ${token.info.legacy}`)}"` : "";
    return `<a class="path-link" data-r="1" href="${escapeHtml(token.info.route)}"${title}>${escapeHtml(token.raw)}</a>`;
  },
};

const directive = {
  name: "directive",
  level: "block",
  start(src) {
    const match = /(?:^|\n) {0,3}(?:`{3,}|~{3,}|:{3,})\{[\w:-]+\}/.exec(src);
    return match ? match.index + (match[0].startsWith("\n") ? 1 : 0) : undefined;
  },
  tokenizer(src) {
    const match = /^ {0,3}(`{3,}|~{3,}|:{3,})\{([\w:-]+)\}[ \t]*([^\n]*)(?:\n([\s\S]*?))?(?:\n {0,3}\1[ \t]*(?:\n+|$)|$)/.exec(src);
    if (!match) return undefined;
    const name = match[2].toLowerCase();
    let lines = (match[4] || "").split("\n");
    const options = {};
    if (lines[0] && lines[0].trim() === "---") {
      const end = lines.findIndex((line, index) => index > 0 && line.trim() === "---");
      if (end > 0) {
        for (const line of lines.slice(1, end)) {
          const option = /^\s*([\w-]+):\s*(.*)$/.exec(line);
          if (option) options[option[1]] = option[2];
        }
        lines = lines.slice(end + 1);
      }
    }
    while (lines.length && /^\s*:[\w-]+:/.test(lines[0])) {
      const option = /^\s*:([\w-]+):\s*(.*)$/.exec(lines.shift());
      if (option) options[option[1]] = option[2];
    }
    const body = lines.join("\n");
    const token = { type: "directive", raw: match[0], name, arg: match[3].trim(), body, options, tokens: [], titleTokens: [] };
    if (!CODE_DIRECTIVES.has(name) && !HIDDEN_DIRECTIVES.has(name) && name !== "math") {
      this.lexer.blockTokens(body, token.tokens);
      const title = name === "admonition" ? token.arg : (token.arg || name.replace(/-/g, " ").replace(/^\w/, (c) => c.toUpperCase()));
      this.lexer.inline(title, token.titleTokens);
    }
    return token;
  },
  renderer(token) {
    const { name, arg, body } = token;
    if (HIDDEN_DIRECTIVES.has(name)) return "";
    if (name === "math") return `<div class="math-block">${mathHtml(body.trim(), true)}</div>\n`;
    if (CODE_DIRECTIVES.has(name)) {
      const language = name === "eval-rst" ? "rst" : name === "mermaid" ? "mermaid"
        : name === "literalinclude" ? "" : (arg.split(/\s+/)[0] || (name === "code-cell" ? "python" : ""));
      const text = name === "literalinclude" ? `literalinclude ${arg}` : body;
      return codeBlock(text, language, name === "code-cell" ? "code-cell" : "");
    }
    const kind = name === "admonition" ? (String(token.options.class || "note").split(/\s+/)[0]) : name;
    return `<div class="admonition admonition-${escapeHtml(kind)}"><p class="admonition-title">${this.parser.parseInline(token.titleTokens)}</p>${this.parser.parse(token.tokens)}</div>\n`;
  },
};

function resolveHref(href) {
  if (!href) return null;
  const info = (ctx.links.hrefs || {})[href];
  if (info) {
    const missing = info.exists === false;
    return { href: info.route, cls: missing ? "missing" : "",
      title: missing ? `Not in the repository: ${info.path || href}` : (info.legacy ? `Moved from ${info.legacy}` : "") };
  }
  if (href.startsWith("#")) return { href };
  if (/^(https?:|mailto:)/i.test(href)) return { href, external: true };
  if (href.startsWith("/")) return { href };
  return null;
}

const renderer = {
  heading({ tokens, depth, text }) {
    const inner = this.parser.parseInline(tokens);
    return `<h${depth} data-anchor="${escapeHtml(slugify(text))}">${inner}</h${depth}>\n`;
  },
  link({ href, title, text: label, tokens }) {
    // A file name used as link text (codes/__init__.py) is shown as written, not as emphasis.
    const text = /^[A-Za-z0-9_.\/+-]+$/.test(label || "") && /[/.]/.test(label) ? escapeHtml(label) : this.parser.parseInline(tokens);
    const target = resolveHref(href);
    if (!target) return `<span class="unresolved" title="${escapeHtml(`Not resolvable: ${href}`)}">${text}</span>`;
    const attrs = [`href="${escapeHtml(target.href)}"`, 'data-r="1"'];
    if (target.cls) attrs.push(`class="${target.cls}"`);
    if (target.title || title) attrs.push(`title="${escapeHtml(target.title || title)}"`);
    return `<a ${attrs.join(" ")}>${text}</a>`;
  },
  image({ href, title, text }) {
    const info = (ctx.links.hrefs || {})[href];
    const alt = escapeHtml(text || "");
    const titleAttr = title ? ` title="${escapeHtml(title)}"` : "";
    if (info && info.raw && info.exists !== false) {
      return `<a class="img-link" data-r="1" href="${escapeHtml(info.route)}"><img src="${escapeHtml(info.raw)}" alt="${alt}" loading="lazy"${titleAttr}></a>`;
    }
    if (/^data:image\//i.test(href || "")) return `<img src="${escapeHtml(href)}" alt="${alt}"${titleAttr}>`;
    if (/^https?:/i.test(href || "")) return `<a class="external-image" href="${escapeHtml(href)}" data-r="1">${alt || escapeHtml(href)}</a>`;
    return `<span class="missing" title="${escapeHtml(`Image not found: ${href}`)}">[image: ${alt || escapeHtml(href || "")}]</span>`;
  },
  codespan({ text }) {
    const info = (ctx.links.code || {})[text];
    const code = `<code>${escapeHtml(text)}</code>`;
    if (info && info.route) {
      const title = info.legacy ? ` title="${escapeHtml(`Moved from ${info.legacy}`)}"` : "";
      return `<a class="code-link" data-r="1" href="${escapeHtml(info.route)}"${title}>${code}</a>`;
    }
    return code;
  },
  code({ text, lang }) {
    const language = (lang || "").trim().split(/\s+/)[0];
    if (language === "math") return `<div class="math-block">${mathHtml(text.trim(), true)}</div>\n`;
    return codeBlock(text, language);
  },
};

const md = new marked.Marked({ gfm: true, breaks: false });
md.use({ extensions: [directive, mathBlock, mathInline, wikilink, role, barePath], renderer });

const SANITIZE = { ADD_ATTR: ["target"], FORBID_TAGS: ["style", "form", "button", "textarea", "select", "iframe", "object", "embed"] };
function localTimes(root) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const parent = node.parentElement;
    if (!parent || parent.closest("pre, code, .math, .diagram, .katex")) continue;
    if (!node.nodeValue.includes("Z")) continue;
    const next = showLocalTimes(node.nodeValue);
    if (next !== node.nodeValue) node.nodeValue = next;
  }
}

function postProcess(root, options) {
  localTimes(root);
  const seen = new Map();
  for (const heading of root.querySelectorAll("[data-anchor]")) {
    const base = heading.dataset.anchor || "section";
    const count = seen.get(base) || 0;
    seen.set(base, count + 1);
    heading.id = count ? `${base}-${count}` : base;
    heading.removeAttribute("data-anchor");
    if (options.anchors !== false && /^H[1-4]$/.test(heading.tagName)) {
      const anchor = document.createElement("a");
      anchor.className = "anchor";
      anchor.href = `#${heading.id}`;
      anchor.setAttribute("aria-label", "Link to this section");
      anchor.textContent = "#";
      heading.append(anchor);
    }
  }
  for (const link of root.querySelectorAll("a[href]:not([data-r])")) {
    const target = resolveHref(link.getAttribute("href"));
    if (target) {
      link.setAttribute("href", target.href);
      if (target.cls) link.classList.add(target.cls);
    }
  }
  for (const img of root.querySelectorAll("img[src]")) {
    const src = img.getAttribute("src");
    if (src.startsWith("/raw/") || src.startsWith("data:") || src.startsWith("/references/")) continue;
    const info = (ctx.links.hrefs || {})[src];
    if (info && info.raw) img.setAttribute("src", info.raw);
    else img.replaceWith(Object.assign(document.createElement("span"), { className: "missing", textContent: `[image: ${img.alt || src}]` }));
  }
  for (const link of root.querySelectorAll("a[href]")) {
    link.removeAttribute("data-r");
    const href = link.getAttribute("href");
    if (/^(https?:)?\/\//i.test(href) || /^mailto:/i.test(href)) {
      link.setAttribute("target", "_blank");
      link.setAttribute("rel", "noopener noreferrer");
      link.classList.add("external");
    }
  }
  for (const table of root.querySelectorAll("table")) {
    const wrap = document.createElement("div");
    wrap.className = "table-wrap";
    table.replaceWith(wrap);
    wrap.append(table);
  }
  for (const quote of root.querySelectorAll("blockquote")) {
    const first = quote.firstElementChild;
    const match = first && first.tagName === "P" ? /^\s*\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\]\s*/i.exec(first.textContent) : null;
    if (!match) continue;
    const kind = ALERTS[match[1].toUpperCase()];
    const box = document.createElement("div");
    box.className = `admonition admonition-${kind}`;
    const title = document.createElement("p");
    title.className = "admonition-title";
    title.textContent = kind.charAt(0).toUpperCase() + kind.slice(1);
    const node = first.firstChild;
    if (node && node.nodeType === Node.TEXT_NODE) node.textContent = node.textContent.replace(/^\s*\[![A-Za-z]+\]\s*/, "");
    box.append(title, ...quote.childNodes);
    quote.replaceWith(box);
  }
  for (const el of root.querySelectorAll(".math")) {
    const display = el.classList.contains("math-display");
    const tex = el.textContent;
    try {
      katex.render(tex, el, { displayMode: display, throwOnError: false, strict: "ignore", trust: false, output: "htmlAndMathml" });
    } catch {
      el.classList.add("math-error");
      el.textContent = display ? `$$${tex}$$` : `$${tex}$`;
    }
  }
}

let mermaidReady = false;
let diagramSeq = 0;

function diagramColors() {
  const style = getComputedStyle(document.documentElement);
  const pick = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  return {
    fontSize: "15px",
    primaryColor: pick("--info-bg", "#e8f0fc"),
    primaryTextColor: pick("--text", "#1c2129"),
    primaryBorderColor: pick("--accent-fill", "#2f5bd3"),
    lineColor: pick("--muted", "#6a737f"),
    background: pick("--surface", "#ffffff"),
    secondaryColor: pick("--surface-2", "#f9fafb"),
    tertiaryColor: pick("--bg", "#f6f7f9"),
    textColor: pick("--text", "#1c2129"),
  };
}

function ensureMermaid() {
  window.mermaid.initialize({
    startOnLoad: false,
    securityLevel: "strict",
    fontFamily: "system-ui, sans-serif",
    theme: "base",
    themeVariables: diagramColors(),
  });
  mermaidReady = true;
}

async function drawOne(node) {
  const source = node.dataset.diagram || node.textContent.trim();
  node.dataset.diagram = source;
  const id = `lab-diagram-${diagramSeq += 1}`;
  try {
    const { svg } = await window.mermaid.render(id, source);
    node.innerHTML = svg;
    node.classList.add("is-drawn");
    node.classList.remove("is-error");
  } catch {
    node.classList.add("is-error");
  }
}

function drawDiagrams(root) {
  const nodes = [...root.querySelectorAll(".diagram")];
  if (!nodes.length || !window.mermaid) return;
  if (!mermaidReady) ensureMermaid();
  for (const node of nodes) drawOne(node);
}

window.addEventListener("lab-theme", () => {
  mermaidReady = false;
  const nodes = [...document.querySelectorAll(".diagram[data-diagram]")];
  if (!nodes.length || !window.mermaid) return;
  ensureMermaid();
  for (const node of nodes) {
    node.classList.remove("is-drawn", "is-error");
    drawOne(node);
  }
});

// When page chrome already shows the document title (Auto Research notes, Skills), drop the
// leading H1 stack from the rendered body. Consecutive leading H1s are title rewrites left in
// the file, not body sections — those use H2+.
export function dropLeadingTitles(root) {
  while (root && root.firstElementChild && root.firstElementChild.tagName === "H1") {
    root.firstElementChild.remove();
  }
  return root;
}

// Render Markdown into a new element. `links` is the server's link map for this text.
export function renderMarkdown(text, links, options = {}) {
  const container = document.createElement("div");
  container.className = options.className || "markdown";
  ctx = context(links);
  let html = "";
  try {
    html = md.parse(String(text || ""), { async: false });
  } catch (error) {
    html = `<pre class="code">${escapeHtml(text)}</pre>`;
  }
  const clean = DOMPurify.sanitize(html, { ...SANITIZE, RETURN_DOM_FRAGMENT: true });
  container.append(clean);
  postProcess(container, options);
  highlightRoot(container);
  drawDiagrams(container);
  if (options.dropLeadingTitles) dropLeadingTitles(container);
  ctx = { links: {} };
  return container;
}

// Inline Markdown (a title or a short field) rendered into a span.
export function renderInline(text, links) {
  const span = document.createElement("span");
  span.className = "md-inline";
  ctx = context(links);
  let html = "";
  try {
    html = md.parseInline(String(text || ""), { async: false });
  } catch {
    html = escapeHtml(text);
  }
  span.append(DOMPurify.sanitize(html, { ...SANITIZE, RETURN_DOM_FRAGMENT: true }));
  postProcess(span, { anchors: false });
  ctx = { links: {} };
  return span;
}

// Inline Markdown for a label that sits inside a link: code spans and emphasis, no nested links.
export function renderLabel(text) {
  const span = renderInline(text);
  for (const link of span.querySelectorAll("a")) link.replaceWith(...link.childNodes);
  return span;
}

// A title for places that cannot hold markup (document.title, tooltips).
export function plainText(text) {
  return showLocalTimes(String(text || "").replace(/`+([^`]+)`+/g, "$1"));
}

export function tableOfContents(container, levels = ["H2", "H3"]) {
  return [...container.querySelectorAll(levels.join(","))]
    .filter((heading) => heading.id)
    .map((heading) => ({ id: heading.id, level: Number(heading.tagName.slice(1)),
      text: [...heading.childNodes].filter((node) => !(node.classList && node.classList.contains("anchor")))
        .map((node) => node.textContent).join("").trim() }));
}
