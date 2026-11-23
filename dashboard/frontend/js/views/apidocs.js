// API manual of the configured package, generated live on the server from the source (never imported).

import { api } from "../api.js";
import { renderMarkdown } from "../markdown.js";
import { badge, debounce, empty, h, setTitle } from "../ui.js";
import { searchField } from "./common.js";
import { browsePage, sideSearch } from "./browse.js";

const NAV_KEY = "lab.api.nav";

function moduleRoute(name) {
  return `/apidocs/${encodeURIComponent(name)}`;
}

function moduleTree(tree, current) {
  const byParent = new Map();
  for (const mod of tree.modules) {
    const parent = mod.name.includes(".") ? mod.name.slice(0, mod.name.lastIndexOf(".")) : "";
    if (!byParent.has(parent)) byParent.set(parent, []);
    byParent.get(parent).push(mod);
  }
  const node = (mod) => {
    const children = byParent.get(mod.name) || [];
    const link = h("a", { href: moduleRoute(mod.name), class: mod.name === current ? "current" : null,
      title: mod.summary || mod.name }, mod.name.split(".").pop());
    if (!children.length) return h("li", null, link);
    const open = current === mod.name || (current || "").startsWith(`${mod.name}.`) || !mod.name.includes(".");
    return h("li", null, h("details", { open: open || null }, h("summary", null, link), h("ul", null, children.map(node))));
  };
  const roots = tree.modules.filter((mod) => !tree.modules.some((other) => mod.name.startsWith(`${other.name}.`)));
  const list = h("ul", { class: "api-tree nav-tree" }, roots.map(node));
  const flat = h("ul", { class: "api-tree nav-tree flat", hidden: true });
  const filter = h("input", { type: "search", class: "filter-input wide", placeholder: "Filter modules", "aria-label": "Filter modules" });
  filter.addEventListener("input", () => {
    const q = filter.value.trim().toLowerCase();
    list.hidden = Boolean(q);
    flat.hidden = !q;
    if (q) {
      flat.replaceChildren(...tree.modules.filter((mod) => mod.name.toLowerCase().includes(q)).slice(0, 200)
        .map((mod) => h("li", null, h("a", { href: moduleRoute(mod.name), class: mod.name === current ? "current" : null }, mod.name))));
    }
  });
  return h("nav", { class: "browse-nav", "aria-label": "Modules" }, sideSearch(filter), list, flat);
}

function signature(name, sig, returns) {
  return h("code", { class: "signature" }, h("span", { class: "sig-name" }, name), sig || "", returns ? h("span", { class: "sig-return" }, ` -> ${returns}`) : null);
}

function memberBadges(item) {
  return [item.kind && !["method", "function"].includes(item.kind) ? badge(item.kind, "type") : null,
    item.async ? badge("async", "type") : null, item.abstract ? badge("abstract", "warn") : null,
    item.settable ? badge("settable", "type") : null];
}

function functionItem(item, level) {
  const decorators = item.decorators.filter((text) => !/^(staticmethod|classmethod|property|overload)$/.test(text));
  const title = h(level === 3 ? "h3" : "h4", { class: "api-member-title" },
    signature(item.name, item.kind === "property" ? "" : item.signature, item.returns),
    h("span", { class: "api-badges" }, memberBadges(item)),
    h("a", { class: "anchor", href: `#${item.anchor}`, "aria-label": "Link" }, "#"));
  return h("details", { class: `api-member level-${level}`, id: item.anchor, open: true },
    h("summary", null, title, h("span", { class: "api-attr-mark", "aria-hidden": "true" })),
    h("div", { class: "api-member-body" },
      decorators.length ? h("div", { class: "decorators" }, decorators.map((text) => h("code", null, `@${text}`))) : null,
      item.overloads && item.overloads.length ? h("details", { class: "overloads" }, h("summary", null, `${item.overloads.length} overloads`),
        h("ul", null, item.overloads.map((text) => h("li", null, h("code", null, `${item.name}${text}`))))) : null,
      item.doc ? renderMarkdown(item.doc, {}, { anchors: false, className: "markdown doc" }) : h("p", { class: "muted small" }, "No docstring.")));
}

function attributeLead(item) {
  return h("code", { class: "signature" }, h("span", { class: "sig-name" }, item.name),
    item.annotation ? h("span", { class: "muted" }, `: ${item.annotation}`) : null,
    item.value ? h("span", { class: "muted" }, ` = ${item.value}`) : null);
}

function attributeList(items) {
  if (!items.length) return null;
  let hash = "";
  try { hash = decodeURIComponent(window.location.hash.slice(1)); } catch { hash = ""; }
  return h("div", { class: "api-attrs" }, items.map((item) => {
    const lead = attributeLead(item);
    if (!item.doc) return h("div", { class: "api-attr", id: item.anchor }, h("div", { class: "api-attr-lead" }, lead));
    return h("details", { class: "api-attr", id: item.anchor, open: hash === item.anchor || null },
      h("summary", null, lead, h("span", { class: "api-attr-mark", "aria-hidden": "true" })),
      h("div", { class: "api-attr-doc" }, renderMarkdown(item.doc, {}, { anchors: false, className: "markdown doc" })));
  }));
}

function classItem(cls) {
  const methods = cls.methods;
  return h("section", { class: "api-class", id: cls.anchor },
    h("h3", { class: "api-head" }, h("span", { class: "kw" }, cls.kind === "class" ? "class" : cls.kind), " ", signature(cls.name, cls.signature),
      h("a", { class: "anchor", href: `#${cls.anchor}`, "aria-label": "Link" }, "#")),
    cls.bases.length ? h("div", { class: "bases" }, "Bases: ", cls.bases.map((base, index) => [index ? ", " : "",
      base.route ? h("a", { href: base.route }, h("code", null, base.text)) : h("code", null, base.text)])) : null,
    cls.decorators.length ? h("div", { class: "decorators" }, cls.decorators.map((text) => h("code", null, `@${text}`))) : null,
    cls.doc ? renderMarkdown(cls.doc, {}, { anchors: false, className: "markdown doc" }) : h("p", { class: "muted small" }, "No docstring."),
    cls.attributes.length ? h("div", { class: "api-sub" }, h("div", { class: "api-sub-title" }, cls.kind === "enum" ? "Members" : "Attributes"), attributeList(cls.attributes)) : null,
    cls.nested.length ? h("div", { class: "api-sub" }, h("div", { class: "api-sub-title" }, "Nested classes"),
      h("ul", null, cls.nested.map((item) => h("li", null, h("code", null, item.name), item.summary ? ` \u2014 ${item.summary}` : "")))) : null,
    methods.length ? h("div", { class: "api-sub" }, h("div", { class: "api-sub-title" }, "Methods"), methods.map((item) => functionItem(item, 4))) : null);
}

function searchBox() {
  const results = h("ul", { class: "api-results" });
  const input = h("input", { type: "search", class: "filter-input wide", placeholder: "Search qualified names",
    "aria-label": "Search the API" });
  const run = debounce(async () => {
    const q = input.value.trim();
    if (!q) { results.replaceChildren(); return; }
    const data = await api("apidocs/search", { q });
    results.replaceChildren(...(data.results.length ? data.results.map((item) => h("li", null,
      item.route ? h("a", { href: item.route }, h("code", null, item.qualname)) : h("code", null, item.qualname), " ", badge(item.kind, "type"),
      item.summary ? h("div", { class: "muted small" }, item.summary) : null)) : [h("li", { class: "muted" }, "No matching names.")]));
  }, 150);
  input.addEventListener("input", run);
  return h("div", { class: "api-search" }, searchField(input), results);
}

async function modulePage(name, signal, withSearch) {
  const [tree, data] = await Promise.all([api("apidocs", {}, { signal }),
    name ? api(`apidocs/${encodeURIComponent(name)}`, {}, { signal }) : Promise.resolve(null)]);
  if (data && data.redirect) return { redirect: data.redirect };
  if (!tree.available) {
    setTitle("API");
    return h("div", { class: "page narrow" }, h("h1", null, "API"), empty("The package cannot be located", tree.error));
  }
  const mod = data || (tree.modules.length ? await api(`apidocs/${encodeURIComponent(tree.package)}`, {}, { signal }) : null);
  setTitle(mod ? mod.name : "API", "API");
  const nav = moduleTree(tree, mod && mod.name);
  const browse = (main, toc) => browsePage({
    nav, main, toc, storageKey: NAV_KEY, hideLabel: "Hide modules", showLabel: "Show modules",
  });
  if (!mod) return browse(empty("No modules found"), null);
  const crumbs = h("nav", { class: "crumbs" }, [...mod.parents, mod.name].map((part, index, all) => [index ? h("span", { class: "sep" }, ".") : null,
    index === all.length - 1 ? h("span", { class: "current" }, part.split(".").pop()) : h("a", { href: moduleRoute(part) }, part.split(".").pop())]));
  const onPage = [...mod.classes.map((cls) => ({ id: cls.anchor, text: cls.name, kind: "class" })),
    ...mod.functions.map((fn) => ({ id: fn.anchor, text: `${fn.name}()`, kind: "function" }))];
  const main = h("article", { class: "api-main" },
    crumbs,
    h("h1", { class: "mono-title" }, mod.name),
    h("div", { class: "meta-row" }, badge(mod.is_package ? "package" : "module", "type"),
      mod.source ? h("a", { class: "small", href: `/files/${mod.source.split("/").map(encodeURIComponent).join("/")}?view=source` }, mod.source) : null),
    withSearch ? h("div", { class: "api-overview muted small" }, `${tree.totals.modules} modules, ${tree.totals.classes} classes and ${tree.totals.functions} functions, parsed from ${tree.source || tree.location}.`) : null,
    withSearch ? searchBox() : null,
    mod.error ? h("div", { class: "notice notice-warn" }, `This module could not be parsed: ${mod.error}`) : null,
    mod.doc ? renderMarkdown(mod.doc, {}, { className: "markdown doc module-doc" }) : h("p", { class: "muted" }, "No module docstring."),
    mod.exports.length ? h("section", { class: "api-section" }, h("h2", null, "Exports"),
      h("ul", { class: "export-list" }, mod.exports.map((item) => h("li", null,
        item.route ? h("a", { href: item.route }, h("code", null, item.name)) : h("code", null, item.name),
        item.target !== `${mod.name}.${item.name}` ? h("span", { class: "muted small" }, ` from ${item.target.slice(0, item.target.lastIndexOf("."))}`) : null)))) : null,
    mod.submodules.length ? h("section", { class: "api-section" }, h("h2", null, "Submodules"),
      h("ul", { class: "rows" }, mod.submodules.map((item) => h("li", { class: "row" }, h("div", { class: "row-main" },
        h("a", { class: "row-title mono", href: moduleRoute(item.name) }, item.name.split(".").pop()),
        item.summary ? h("div", { class: "row-sub" }, item.summary) : null))))) : null,
    mod.classes.length ? h("section", { class: "api-section" }, h("h2", null, "Classes"), mod.classes.map(classItem)) : null,
    mod.functions.length ? h("section", { class: "api-section" }, h("h2", null, "Functions"), mod.functions.map((item) => functionItem(item, 3))) : null,
    mod.constants.length ? h("section", { class: "api-section" }, h("h2", null, "Constants"), attributeList(mod.constants)) : null);
  const side = onPage.length > 1 ? h("nav", { class: "toc" }, h("div", { class: "toc-title" }, "On this page"),
    h("ul", null, onPage.map((item) => h("li", null, h("a", { href: `#${item.id}` }, h("code", null, item.text)))))) : null;
  return browse(main, side);
}

export async function overview({ signal }) {
  return modulePage(null, signal, true);
}

export async function module({ params, signal }) {
  return modulePage(params[0], signal, false);
}
