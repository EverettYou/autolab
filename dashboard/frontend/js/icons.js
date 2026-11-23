// Dashboard + Notes workbench icons from the local Font Awesome solid subset.

import { faSvg, faHtml } from "../vendor/fontawesome/icons.mjs";

/** Semantic names → FA glyph ids. Shared by ESM icon() and WorkbenchIcons.html. */
const ICONS = {
  // Dashboard chrome
  search: "magnifying-glass",
  menu: "bars",
  close: "xmark",
  sun: "sun",
  moon: "moon",
  system: "circle-half-stroke",
  gear: "gear",
  // Notes / workbench
  previous: "chevron-left",
  next: "chevron-right",
  up: "chevron-up",
  down: "chevron-down",
  folder: "folder",
  "folder-open": "folder-open",
  "folder-tree": "folder-tree",
  "folder-plus": "folder-plus",
  document: "file",
  "file-code": "file-code",
  "file-tex": "file-lines",
  "file-pdf": "file-pdf",
  "file-plus": "file-circle-plus",
  source: "file-lines",
  pdf: "file-pdf",
  play: "play",
  "hourglass-half": "hourglass-half",
  save: "floppy-disk",
  "arrows-rotate": "arrows-rotate",
  refresh: "arrows-rotate",
  "lock-keyhole": "lock",
  "circle-small": "circle",
  plus: "plus",
  minus: "minus",
  check: "check",
  download: "download",
  more: "ellipsis",
  sortUp: "sort-up",
  sortDown: "sort-down",
  "cloud-check": "cloud",
  code: "code",
  preview: "eye",
  markdown: "file-lines",
  json: "code",
  text: "align-left",
  // Mapped for menus; glyphs may be absent from the subset (falls back below).
  pen: "pen",
  trash: "trash",
};

function glyphFor(name, fallback) {
  if (Object.hasOwn(ICONS, name)) return ICONS[name];
  return fallback;
}

/** DOM node icon for dashboard ESM views. */
export function icon(name, className) {
  const glyph = glyphFor(name, "circle");
  return faSvg(glyph, className) || faSvg("circle", className);
}

/** HTML string icon for Notes templates / classic WorkbenchIcons consumers. */
export function iconHtml(name, className = "app-icon") {
  const glyph = glyphFor(name, "file");
  return faHtml(glyph, className) || faHtml("file", className) || "";
}

export function installWorkbenchIcons() {
  window.WorkbenchIcons = { html: iconHtml };
}

installWorkbenchIcons();
