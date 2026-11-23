// Canvas PDF reader. The dashboard browser has no built-in PDF plugin, so pages are painted
// with PDF.js instead of an iframe. `url` is a same-origin byte URL such as
// `/references/<id>/paper.pdf` or `/raw/<path>.pdf`.

import { bindGestureZoom, zoomAround } from "./gesture-zoom.js";
import { h } from "./ui.js";

const LIB = "/static/vendor/pdfjs/pdf.min.mjs";
const WORKER = "/static/vendor/pdfjs/pdf.worker.min.mjs";
const ZOOM_STEPS = [0.5, 0.75, 1, 1.25, 1.5, 2, 3, 4];

let library;

// Font Awesome Free 6.7.2 (CC BY 4.0, Fonticons, Inc.). The download mark matches
// arrow-down-to-line, which is not in the free set, so that one path is drawn here.
function faIcon(body, viewBox = "0 0 512 512") {
  const host = document.createElement("span");
  host.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${viewBox}" width="15" height="15" aria-hidden="true" fill="currentColor">${body}</svg>`;
  return host.firstChild;
}

const ICONS = {
  prev: faIcon('<path d="M233.4 105.4c12.5-12.5 32.8-12.5 45.3 0l192 192c12.5 12.5 12.5 32.8 0 45.3s-32.8 12.5-45.3 0L256 173.3 86.6 342.6c-12.5 12.5-32.8 12.5-45.3 0s-12.5-32.8 0-45.3l192-192z"/>'),
  next: faIcon('<path d="M233.4 406.6c12.5 12.5 32.8 12.5 45.3 0l192-192c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0L256 338.7 86.6 169.4c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3l192 192z"/>'),
  minus: faIcon('<path d="M432 256c0 17.7-14.3 32-32 32L48 288c-17.7 0-32-14.3-32-32s14.3-32 32-32l352 0c17.7 0 32 14.3 32 32z"/>', "0 0 448 512"),
  plus: faIcon('<path d="M256 80c0-17.7-14.3-32-32-32s-32 14.3-32 32l0 144L48 224c-17.7 0-32 14.3-32 32s14.3 32 32 32l144 0 0 144c0 17.7 14.3 32 32 32s32-14.3 32-32l0-144 144 0c17.7 0 32-14.3 32-32s-14.3-32-32-32l-144 0 0-144z"/>', "0 0 448 512"),
  width: faIcon('<path d="M406.6 374.6l96-96c12.5-12.5 12.5-32.8 0-45.3l-96-96c-12.5-12.5-32.8-12.5-45.3 0s-12.5 32.8 0 45.3L402.7 224l-293.5 0 41.4-41.4c12.5-12.5 12.5-32.8 0-45.3s-32.8-12.5-45.3 0l-96 96c-12.5 12.5-12.5 32.8 0 45.3l96 96c12.5 12.5 32.8 12.5 45.3 0s12.5-32.8 0-45.3L109.3 288l293.5 0-41.4 41.4c-12.5 12.5-12.5 32.8 0 45.3s32.8 12.5 45.3 0z"/>'),
  page: faIcon('<path d="M384 80c8.8 0 16 7.2 16 16l0 320c0 8.8-7.2 16-16 16L64 432c-8.8 0-16-7.2-16-16L48 96c0-8.8 7.2-16 16-16l320 0zM64 32C28.7 32 0 60.7 0 96L0 416c0 35.3 28.7 64 64 64l320 0c35.3 0 64-28.7 64-64l0-320c0-35.3-28.7-64-64-64L64 32z"/>', "0 0 448 512"),
  rotate: faIcon('<path d="M142.9 142.9c-17.5 17.5-30.1 38-37.8 59.8c-5.9 16.7-24.2 25.4-40.8 19.5s-25.4-24.2-19.5-40.8C55.6 150.7 73.2 122 97.6 97.6c87.2-87.2 228.3-87.5 315.8-1L455 55c6.9-6.9 17.2-8.9 26.2-5.2s14.8 12.5 14.8 22.2l0 128c0 13.3-10.7 24-24 24l-8.4 0c0 0 0 0 0 0L344 224c-9.7 0-18.5-5.8-22.2-14.8s-1.7-19.3 5.2-26.2l41.1-41.1c-62.6-61.5-163.1-61.2-225.3 1zM16 312c0-13.3 10.7-24 24-24l7.6 0 .7 0L168 288c9.7 0 18.5 5.8 22.2 14.8s1.7 19.3-5.2 26.2l-41.1 41.1c62.6 61.5 163.1 61.2 225.3-1c17.5-17.5 30.1-38 37.8-59.8c5.9-16.7 24.2-25.4 40.8-19.5s25.4 24.2 19.5 40.8c-10.8 30.6-28.4 59.3-52.9 83.8c-87.2 87.2-228.3 87.5-315.8 1L57 457c-6.9 6.9-17.2 8.9-26.2 5.2S16 449.7 16 440l0-119.6 0-.7 0-7.6z"/>'),
  download: faIcon('<path d="M64 400h384a32 32 0 0 1 0 64H64a32 32 0 0 1 0-64z"/><path d="M216 48h80v176h72L256 364 144 224h72z"/>'),
};

async function pdfjs() {
  if (library) return library;
  library = await import(LIB);
  library.GlobalWorkerOptions.workerSrc = WORKER;
  return library;
}

function fileName(url) {
  try {
    const parts = new URL(url, window.location.origin).pathname.split("/").filter(Boolean);
    return decodeURIComponent(parts.at(-1) || "paper.pdf");
  } catch {
    return "paper.pdf";
  }
}

function toolButton(act, label, glyph) {
  return h("button", { type: "button", "data-pdf-act": act, "aria-label": label, title: label }, glyph);
}

function toolbar() {
  return h("div", { class: "pdf-toolbar", role: "toolbar", "aria-label": "PDF controls" },
    h("div", { class: "pdf-toolbar-group" },
      toolButton("prev", "Previous page", ICONS.prev),
      h("label", { class: "pdf-page-control" },
        h("input", { "data-pdf-page": "true", inputmode: "numeric", "aria-label": "Page number" }),
        h("span", null, "/ ", h("em", { "data-pdf-total": "true" }, "1"))),
      toolButton("next", "Next page", ICONS.next)),
    h("div", { class: "pdf-toolbar-group pdf-toolbar-zoom" },
      toolButton("zoom-out", "Zoom out", ICONS.minus),
      h("span", { class: "pdf-zoom-label", "data-pdf-zoom": "true" }, "100%"),
      toolButton("zoom-in", "Zoom in", ICONS.plus),
      toolButton("fit-width", "Fit to width", ICONS.width),
      toolButton("fit-page", "Fit to page", ICONS.page)),
    h("div", { class: "pdf-toolbar-group" },
      toolButton("rotate", "Rotate clockwise", ICONS.rotate),
      h("button", { type: "button", class: "pdf-download", "data-pdf-download": "true", "aria-label": "Download PDF", title: "Download" }, ICONS.download)));
}

function pageViewport(page, scale, rotation) {
  return page.getViewport({ scale, rotation: (page.rotate + rotation) % 360 });
}

function computeScale(state) {
  const base = state.base;
  const pad = 32;
  const availW = Math.max(240, state.stage.clientWidth - pad);
  const availH = Math.max(240, state.stage.clientHeight - pad);
  if (state.mode === "width") return availW / base.width;
  if (state.mode === "page") return Math.min(availW / base.width, availH / base.height);
  return state.scale;
}

function syncChrome(state) {
  state.root.querySelector("[data-pdf-zoom]").textContent = `${Math.round(state.currentScale * 100)}%`;
  state.root.querySelector("[data-pdf-total]").textContent = String(state.pdf.numPages);
  const pageInput = state.root.querySelector("[data-pdf-page]");
  if (document.activeElement !== pageInput) pageInput.value = String(state.currentPage);
  state.root.querySelector('[data-pdf-act="prev"]').disabled = state.currentPage <= 1;
  state.root.querySelector('[data-pdf-act="next"]').disabled = state.currentPage >= state.pdf.numPages;
  state.root.querySelector('[data-pdf-act="fit-width"]').classList.toggle("active", state.mode === "width");
  state.root.querySelector('[data-pdf-act="fit-page"]').classList.toggle("active", state.mode === "page");
}

async function paintPage(state, number) {
  const item = state.pages[number - 1];
  if (!item || item.drawn === state.paintKey) return;
  const page = await state.pdf.getPage(number);
  if (item.drawn === state.paintKey) return;
  const viewport = pageViewport(page, state.currentScale, state.rotation);
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const canvas = item.canvas;
  canvas.width = Math.floor(viewport.width * ratio);
  canvas.height = Math.floor(viewport.height * ratio);
  canvas.style.width = `${Math.floor(viewport.width)}px`;
  canvas.style.height = `${Math.floor(viewport.height)}px`;
  const context = canvas.getContext("2d", { alpha: false });
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  if (item.task) {
    try { item.task.cancel(); } catch { /* already finished */ }
  }
  const task = page.render({ canvasContext: context, viewport });
  item.task = task;
  try {
    await task.promise;
    item.drawn = state.paintKey;
  } catch (error) {
    if (error?.name !== "RenderingCancelledException") throw error;
  }
}

async function paintVisible(state) {
  const stage = state.stage.getBoundingClientRect();
  const visible = [];
  state.pages.forEach((item, index) => {
    const box = item.wrap.getBoundingClientRect();
    if (box.bottom >= stage.top - 400 && box.top <= stage.bottom + 400) visible.push(index + 1);
  });
  const order = visible.length ? visible : [state.currentPage];
  for (const number of order) await paintPage(state, number);
}

function updateCurrentPage(state) {
  const mid = state.stage.getBoundingClientRect().top + state.stage.clientHeight / 3;
  let current = 1;
  state.pages.forEach((item, index) => {
    if (item.wrap.getBoundingClientRect().top <= mid) current = index + 1;
  });
  if (current !== state.currentPage) {
    state.currentPage = current;
    syncChrome(state);
  }
}

async function relayout(state) {
  const page = await state.pdf.getPage(1);
  state.base = pageViewport(page, 1, state.rotation);
  state.currentScale = computeScale(state);
  state.paintKey = `${state.currentScale}:${state.rotation}:${state.root.clientWidth}`;
  syncChrome(state);
  await paintVisible(state);
}

function goToPage(state, number) {
  const target = Math.min(Math.max(1, number), state.pdf.numPages);
  state.currentPage = target;
  state.pages[target - 1].wrap.scrollIntoView({ block: "start" });
  syncChrome(state);
  paintVisible(state);
}

function changeZoom(state, nextScale) {
  state.mode = "custom";
  state.scale = Math.min(4, Math.max(0.4, nextScale));
  relayout(state);
}

function pageAt(state, clientX, clientY) {
  const hit = document.elementFromPoint(clientX, clientY);
  const page = hit && hit.closest ? hit.closest(".pdf-page") : null;
  if (page && state.root.contains(page)) return page;
  let best = state.pages[0] ? state.pages[0].wrap : null;
  let bestDist = Infinity;
  for (const item of state.pages) {
    const box = item.wrap.getBoundingClientRect();
    const dist = Math.abs(clientY - (box.top + box.height / 2));
    if (dist < bestDist) {
      best = item.wrap;
      bestDist = dist;
    }
  }
  return best;
}

function stretchPages(state, ratio) {
  for (const item of state.pages) {
    const width = item.canvas.clientWidth;
    const height = item.canvas.clientHeight;
    if (!width || !height) continue;
    item.canvas.style.width = `${Math.max(1, Math.round(width * ratio))}px`;
    item.canvas.style.height = `${Math.max(1, Math.round(height * ratio))}px`;
  }
}

function gestureZoom(state, factor, clientX, clientY) {
  const before = state.currentScale;
  const next = Math.min(4, Math.max(0.4, before * factor));
  if (!state.pages.length || Math.abs(next - before) < 0.0005) return;
  const page = pageAt(state, clientX, clientY);
  if (!page) return;
  const ratio = next / before;
  zoomAround(state.stage, page, clientX, clientY, () => stretchPages(state, ratio));
  state.mode = "custom";
  state.scale = next;
  state.currentScale = next;
  syncChrome(state);
  window.clearTimeout(state.gestureTimer);
  state.gestureTimer = window.setTimeout(() => relayout(state), 90);
}

function stepZoom(state, direction) {
  const current = state.currentScale;
  const next = direction < 0
    ? [...ZOOM_STEPS].reverse().find((step) => step < current - 0.01)
    : ZOOM_STEPS.find((step) => step > current + 0.01);
  changeZoom(state, next || (direction < 0 ? Math.max(0.4, current / 1.25) : Math.min(4, current * 1.25)));
}

function bind(state) {
  state.root.addEventListener("click", (event) => {
    const button = event.target.closest("[data-pdf-act]");
    if (!button || !state.root.contains(button)) return;
    const act = button.dataset.pdfAct;
    if (act === "prev") goToPage(state, state.currentPage - 1);
    if (act === "next") goToPage(state, state.currentPage + 1);
    if (act === "zoom-out") stepZoom(state, -1);
    if (act === "zoom-in") stepZoom(state, 1);
    if (act === "fit-width") { state.mode = "width"; relayout(state); }
    if (act === "fit-page") { state.mode = "page"; relayout(state); }
    if (act === "rotate") { state.rotation = (state.rotation + 90) % 360; relayout(state); }
  });
  state.root.querySelector("[data-pdf-download]").addEventListener("click", () => downloadPdf(state.source));
  state.root.querySelector("[data-pdf-page]").addEventListener("change", (event) => {
    goToPage(state, Number.parseInt(event.target.value, 10) || 1);
  });
  state.stage.addEventListener("scroll", () => {
    updateCurrentPage(state);
    window.clearTimeout(state.scrollTimer);
    state.scrollTimer = window.setTimeout(() => paintVisible(state), 80);
  }, { passive: true });
  bindGestureZoom(state.stage, (factor, clientX, clientY) => gestureZoom(state, factor, clientX, clientY));
  state.root.tabIndex = 0;
  state.root.addEventListener("keydown", (event) => {
    if (event.target.matches("input")) return;
    if (event.key === "ArrowUp" || event.key === "PageUp") { event.preventDefault(); goToPage(state, state.currentPage - 1); }
    if (event.key === "ArrowDown" || event.key === "PageDown") { event.preventDefault(); goToPage(state, state.currentPage + 1); }
    if (event.key === "+" || event.key === "=") { event.preventDefault(); stepZoom(state, 1); }
    if (event.key === "-" || event.key === "_") { event.preventDefault(); stepZoom(state, -1); }
    if (event.key === "0") { event.preventDefault(); state.mode = "width"; relayout(state); }
  });
}

async function downloadPdf(source) {
  const response = await fetch(source);
  if (!response.ok) throw new Error(`download failed (${response.status})`);
  const blob = await response.blob();
  const objectUrl = URL.createObjectURL(blob);
  const link = h("a", { href: objectUrl, download: fileName(source) });
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(objectUrl);
}

function fail(status, source, error) {
  const button = h("button", { type: "button", class: "link-button" }, "Download PDF");
  button.addEventListener("click", () => downloadPdf(source).catch(() => {}));
  status.replaceChildren(
    document.createTextNode(`PDF reader could not render this file. ${error?.message || error} `),
    button);
}

export async function mount(container, url) {
  if (!container || !url) return;
  const generation = Number(container.dataset.pdfGeneration || 0) + 1;
  container.dataset.pdfGeneration = String(generation);
  container.classList.add("pdf-shell");
  const status = h("p", { class: "pdf-status" }, "Loading PDF…");
  const pagesNode = h("div", { class: "pdf-pages", hidden: true });
  container.replaceChildren(toolbar(), h("div", { class: "pdf-stage" }, status, pagesNode));
  try {
    const pdfjsLib = await pdfjs();
    if (container.dataset.pdfGeneration !== String(generation)) return;
    const pdf = await pdfjsLib.getDocument({ url, verbosity: 0 }).promise;
    if (container.dataset.pdfGeneration !== String(generation)) return;
    const state = {
      root: container, stage: container.querySelector(".pdf-stage"), source: url, pdf, pages: [],
      mode: "width", scale: 1, currentScale: 1, rotation: 0, currentPage: 1, paintKey: "",
      base: { width: 1, height: 1 },
    };
    for (let number = 1; number <= pdf.numPages; number += 1) {
      const canvas = h("canvas", { "aria-label": `Page ${number}` });
      const wrap = h("div", { class: "pdf-page", "data-page": String(number) }, canvas);
      pagesNode.appendChild(wrap);
      state.pages.push({ wrap, canvas, drawn: "", task: null });
    }
    pagesNode.hidden = false;
    status.remove();
    bind(state);
    if (container._pdfResize) container._pdfResize.disconnect();
    let timer = 0;
    const observer = new ResizeObserver(() => {
      window.clearTimeout(timer);
      timer = window.setTimeout(() => relayout(state), 120);
    });
    observer.observe(container);
    container._pdfResize = observer;
    await relayout(state);
  } catch (error) {
    if (container.dataset.pdfGeneration !== String(generation)) return;
    fail(container.querySelector(".pdf-status") || container, url, error);
  }
}
