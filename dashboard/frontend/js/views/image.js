// Full-page image reader. The file view only shows a fitted preview; this page is the
// place to zoom. It uses the PDF reader's shell. PDF.js itself only paints PDF pages.

import { bindGestureZoom, zoomAround } from "../gesture-zoom.js";
import { empty, h, setTitle } from "../ui.js";

const BYTE_PREFIXES = ["/references/", "/raw/"];
const IMAGE_EXT = /\.(png|jpe?g|gif|webp|svg|bmp|avif|ico)$/i;
const ZOOM_STEPS = [0.25, 0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

function faIcon(body, viewBox = "0 0 512 512") {
  const host = document.createElement("span");
  host.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="15" height="15" aria-hidden="true" fill="currentColor">${body}</svg>`;
  return host.firstChild;
}

const ICONS = {
  minus: faIcon('<path d="M432 256c0 17.7-14.3 32-32 32L48 288c-17.7 0-32-14.3-32-32s14.3-32 32-32l352 0c17.7 0 32 14.3 32 32z"/>', "0 0 448 512"),
  plus: faIcon('<path d="M256 80c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 144L48 224c-17.7 0-32 14.3-32 32s14.3 32 32 32l144 0 0 144c0 17.7 14.3 32 32 32s32-14.3 32-32l0-144 144 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l-144 0 0-144z"/>', "0 0 448 512"),
  width: faIcon('<path d="M406.6 374.6l96-96c12.5-12.5 12.5-32.8 0-45.3l-96-96c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L402.7 224l-293.5 0 41.4-41.4c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-96 96c-12.5 12.5-12.5 32.8 0 45.3l96 96c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L109.3 288l293.5 0-41.4 41.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0z"/>'),
  page: faIcon('<path d="M384 80c8.8 0 16 7.2 16 16l0 320c0 8.8-7.2 16-16 16L64 432c-8.8 0-16-7.2-16-16L48 96c0-8.8 7.2-16 16-16l320 0zM64 32C28.7 32 0 60.7 0 96L0 416c0 35.3 28.7 64 64 64l320 0c35.3 0 64-28.7 64-64l0-320c0-35.3-28.7-64-64-64L64 32z"/>', "0 0 448 512"),
  download: faIcon('<path d="M64 400h384a32 32 0 0 1 0 64H64a32 32 0 0 1 0-64z"/><path d="M216 48h80v176h72L256 364 144 224h72z"/>'),
};

export function imageBytePath(src) {
  if (!src || !src.startsWith("/") || src.startsWith("//")) return null;
  let url;
  try {
    url = new URL(src, "http://dashboard.local");
  } catch {
    return null;
  }
  if (url.origin !== "http://dashboard.local") return null;
  const path = url.pathname;
  if (!IMAGE_EXT.test(path) || path.split("/").includes("..")) return null;
  if (!BYTE_PREFIXES.some((prefix) => path.startsWith(prefix))) return null;
  return path;
}

export function imageReaderHref(src, back) {
  const params = new URLSearchParams();
  params.set("src", src);
  if (back) params.set("back", back);
  return `/image?${params.toString()}`;
}

function safeBack(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "";
  if (value.split(/[?#]/, 1)[0].split("/").includes("..")) return "";
  return value;
}

function fallbackBack(src) {
  const raw = src.match(/^\/raw\/(.+)$/);
  if (!raw) return "/files";
  let rel = raw[1];
  try { rel = decodeURIComponent(rel); } catch { /* keep the encoded path */ }
  const slash = rel.lastIndexOf("/");
  return slash > 0 ? `/files/${rel.slice(0, slash)}` : "/files";
}

function fileTitle(src) {
  const name = src.split("/").pop() || "image";
  try { return decodeURIComponent(name); } catch { return name; }
}

function toolButton(act, label, glyph) {
  return h("button", { type: "button", "data-image-act": act, "aria-label": label, title: label }, glyph);
}

function fitScale(state) {
  const pad = 32;
  const width = Math.max(80, state.stage.clientWidth - pad);
  const height = Math.max(80, state.stage.clientHeight - pad);
  const naturalWidth = state.img.naturalWidth || 1;
  const naturalHeight = state.img.naturalHeight || 1;
  if (state.mode === "width") return width / naturalWidth;
  return Math.min(width / naturalWidth, height / naturalHeight);
}

function apply(state) {
  const scale = state.mode === "custom" ? state.scale : fitScale(state);
  state.scale = scale;
  state.img.style.width = `${Math.max(1, Math.round(state.img.naturalWidth * scale))}px`;
  state.img.style.height = `${Math.max(1, Math.round(state.img.naturalHeight * scale))}px`;
  state.label.textContent = `${Math.round(scale * 100)}%`;
  state.root.querySelector('[data-image-act="fit-width"]').classList.toggle("active", state.mode === "width");
  state.root.querySelector('[data-image-act="fit-page"]').classList.toggle("active", state.mode === "page");
}

function gestureZoom(state, factor, clientX, clientY) {
  if (!state.img.naturalWidth) return;
  const before = state.scale;
  const next = Math.min(4, Math.max(0.1, before * factor));
  if (Math.abs(next - before) < 0.0005) return;
  zoomAround(state.stage, state.img, clientX, clientY, () => {
    state.mode = "custom";
    state.scale = next;
    apply(state);
  });
}

function stepZoom(state, direction) {
  const current = state.scale;
  const next = direction < 0
    ? [...ZOOM_STEPS].reverse().find((step) => step < current - 0.01)
    : ZOOM_STEPS.find((step) => step > current + 0.01);
  state.mode = "custom";
  state.scale = next || (direction < 0 ? Math.max(0.1, current / 1.25) : Math.min(4, current * 1.25));
  apply(state);
}

function mount(container, url) {
  const label = h("span", { class: "pdf-zoom-label" }, "100%");
  const img = h("img", { alt: "", draggable: "false" });
  const stage = h("div", { class: "pdf-stage" },
    h("p", { class: "pdf-status" }, "Loading image…"),
    h("div", { class: "image-frame", hidden: true }, img));
  const toolbar = h("div", { class: "pdf-toolbar", role: "toolbar", "aria-label": "Image controls" },
    h("div", { class: "pdf-toolbar-group" }),
    h("div", { class: "pdf-toolbar-group pdf-toolbar-zoom" },
      toolButton("zoom-out", "Zoom out", ICONS.minus),
      label,
      toolButton("zoom-in", "Zoom in", ICONS.plus),
      toolButton("fit-width", "Fit to width", ICONS.width),
      toolButton("fit-page", "Fit to page", ICONS.page)),
    h("div", { class: "pdf-toolbar-group" },
      h("a", { class: "pdf-download", href: url, download: "", "aria-label": "Download image", title: "Download" }, ICONS.download)));
  container.replaceChildren(toolbar, stage);
  const state = { root: container, stage, img, label, mode: "page", scale: 1 };
  bindGestureZoom(stage, (factor, clientX, clientY) => gestureZoom(state, factor, clientX, clientY));
  container.addEventListener("click", (event) => {
    const button = event.target.closest("[data-image-act]");
    if (!button || !container.contains(button)) return;
    const act = button.dataset.imageAct;
    if (act === "zoom-out") stepZoom(state, -1);
    if (act === "zoom-in") stepZoom(state, 1);
    if (act === "fit-width") { state.mode = "width"; apply(state); }
    if (act === "fit-page") { state.mode = "page"; apply(state); }
  });
  const frame = stage.querySelector(".image-frame");
  img.addEventListener("load", () => {
    stage.querySelector(".pdf-status")?.remove();
    frame.hidden = false;
    apply(state);
  });
  img.addEventListener("error", () => {
    stage.replaceChildren(h("p", { class: "pdf-status" }, "This image could not be opened."));
  });
  img.src = url;
  const observer = new ResizeObserver(() => {
    if (state.mode !== "custom" && state.img.complete && state.img.naturalWidth) apply(state);
  });
  observer.observe(stage);
}

export async function render({ query }) {
  const src = imageBytePath(query.get("src") || "");
  const title = src ? fileTitle(src) : "Image";
  setTitle(title, "Image");
  const back = safeBack(query.get("back") || "") || (src ? fallbackBack(src) : "/files");
  const shell = h("div", { class: "pdf-shell", role: "region", "aria-label": `${title} image` });
  if (src) mount(shell, src);
  return h("div", { class: "pdf-reader" },
    h("div", { class: "pdf-reader-bar" },
      h("a", { href: back }, "← Back"),
      h("span", { class: "pdf-reader-title" }, title)),
    src ? shell : empty("This image address is not valid", "The reader only opens images served by this dashboard."));
}
