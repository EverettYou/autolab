// One reader for every PDF the dashboard serves. Callers link here instead of embedding the file.
// Uses the shared Notes-quality PDF.js viewer (pdf-browser), not a separate slim stack.

import { empty, h, setTitle } from "../ui.js";
import { mountPDF } from "../pdf-browser.js";

const BYTE_PREFIXES = ["/references/", "/raw/"];

export function pdfBytePath(src) {
  if (!src || !src.startsWith("/") || src.startsWith("//")) return null;
  let url;
  try {
    url = new URL(src, "http://dashboard.local");
  } catch {
    return null;
  }
  if (url.origin !== "http://dashboard.local") return null;
  const path = url.pathname;
  if (!path.toLowerCase().endsWith(".pdf") || path.split("/").includes("..")) return null;
  if (!BYTE_PREFIXES.some((prefix) => path.startsWith(prefix))) return null;
  return path;
}

export function pdfReaderHref(src, back) {
  const params = new URLSearchParams();
  params.set("src", src);
  if (back) params.set("back", back);
  return `/pdf?${params.toString()}`;
}

function safeBack(value) {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.includes("\\")) return "";
  if (value.split(/[?#]/, 1)[0].split("/").includes("..")) return "";
  return value;
}

function fallbackBack(src) {
  const paper = src.match(/^\/references\/([^/]+)\/paper\.pdf$/);
  if (paper) return `/references/${paper[1]}`;
  const raw = src.match(/^\/raw\/(.+)$/);
  if (!raw) return "/references";
  let rel = raw[1];
  try { rel = decodeURIComponent(rel); } catch { /* keep the encoded path */ }
  const refPaper = rel.match(/^references\/([^/]+)\/paper\.pdf$/);
  if (refPaper) return `/references/${refPaper[1]}`;
  const slash = rel.lastIndexOf("/");
  return slash > 0 ? `/files/${rel.slice(0, slash)}` : "/files";
}

function fileTitle(src) {
  const name = src.split("/").pop() || "paper.pdf";
  try { return decodeURIComponent(name); } catch { return name; }
}

export async function render({ query }) {
  const src = pdfBytePath(query.get("src") || "");
  const title = src ? fileTitle(src) : "PDF";
  setTitle(title, "PDF");
  const back = safeBack(query.get("back") || "") || (src ? fallbackBack(src) : "/references");
  const shell = h("div", { class: "pdf-shell", role: "region", "aria-label": `${title} PDF` });
  // shell is still detached here; content-core.lifecycle only tears down after a
  // host has been connected, so PDF.js can finish pagesinit once app.js appends.
  if (src) mountPDF(shell, { url: src, title });
  return h("div", { class: "pdf-page" },
    h("div", { class: "pdf-reader-bar" },
      h("a", { href: back }, "← Back"),
      h("span", { class: "pdf-reader-title" }, title)),
    src ? shell : empty("This PDF address is not valid", "The reader only opens PDF files served by this dashboard."));
}
