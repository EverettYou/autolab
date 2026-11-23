// The browser page: a collapsible side index, one content card, and an on-this-page list.
// Wiki and the API manual share it. Each section remembers its own open or closed side index.

import { icon } from "../icons.js";
import { h } from "../ui.js";

export function sideSearch(input) {
  return h("label", { class: "side-search" }, icon("search", "search-glyph"), input);
}

export function browsePage({ nav, main, toc, storageKey, hideLabel, showLabel }) {
  main.classList.add("browse-main");
  const rail = h("button", {
    class: "browse-rail", type: "button", "data-nav-toggle": "1",
    "aria-expanded": "true", "aria-label": hideLabel,
  }, h("span", { class: "browse-rail-chevron", "aria-hidden": "true" }));
  main.prepend(h("div", { class: "browse-rail-slot" }, rail));
  const layout = h("div", { class: "browse-layout" },
    h("div", { class: "browse-side" }, nav),
    main,
    h("aside", { class: "browse-toc" }, toc || null));
  bindBrowseNav(layout, storageKey, hideLabel, showLabel);
  return h("div", { class: "page wide" }, layout);
}

export function bindBrowseNav(layout, storageKey, hideLabel, showLabel) {
  let open = true;
  try { open = window.localStorage.getItem(storageKey) !== "0"; } catch { /* storage may be unavailable */ }
  const apply = (next) => {
    layout.classList.toggle("nav-collapsed", !next);
    try { window.localStorage.setItem(storageKey, next ? "1" : "0"); } catch { /* storage may be unavailable */ }
    for (const button of layout.querySelectorAll("[data-nav-toggle]")) {
      button.setAttribute("aria-expanded", next ? "true" : "false");
      button.setAttribute("aria-label", next ? hideLabel : showLabel);
    }
  };
  apply(open);
  for (const button of layout.querySelectorAll("[data-nav-toggle]")) {
    button.addEventListener("click", () => apply(layout.classList.contains("nav-collapsed")));
  }
}
